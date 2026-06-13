"""Analysis API router — create, list, get, delete analysis jobs."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.schemas import (
    AnalysisResponse,
    ChunkBboxResponse,
    ChunkResponse,
    CreateAnalysisRequest,
    RechunkRequest,
    UpdateChunkTextRequest,
)
from services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyses", tags=["analyses"])


# Per-deployment threshold for marking a RUNNING job "stale" in the API
# response. Mirrors the threshold used by the startup `fail_stale_running`
# sweep in `main.py`: a job is stale if its `created_at` is older than
# `2 * conversion_timeout + 5min` (i.e. the user can never be waiting on
# it; it would have finished or timed out long ago). Computed at import
# time so the router doesn't reach into `infra.settings` on every call.
def _stale_threshold_seconds() -> int:
    from infra.settings import settings
    return 2 * settings.conversion_timeout + 300


def _get_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


ServiceDep = Annotated[AnalysisService, Depends(_get_service)]


def _to_response(job, *, stale_after_seconds: int | None = None) -> AnalysisResponse:
    """Convert an AnalysisJob to its API response shape.

    `stale_after_seconds` lets the router pass a per-deployment
    threshold (computed from settings.conversion_timeout). A job is
    "stale" if it's still RUNNING and its `created_at` is older than
    the threshold — that means the in-memory asyncio.Task that would
    normally transition it to COMPLETED/FAILED is gone (server
    restarted) and the deployment's `fail_stale_running` sweep has
    not yet been able to mark it FAILED.
    """
    from datetime import UTC, datetime

    is_stale = False
    if stale_after_seconds and job.status.value == "RUNNING" and job.created_at:
        age = (datetime.now(UTC) - job.created_at).total_seconds()
        if age > stale_after_seconds:
            is_stale = True
    return AnalysisResponse(
        id=job.id,
        document_id=job.document_id,
        document_filename=job.document_filename,
        status=job.status.value,
        content_markdown=job.content_markdown,
        content_html=job.content_html,
        content_json=job.content_json,
        pages_json=job.pages_json,
        chunks_json=job.chunks_json,
        has_document_json=job.document_json is not None,
        error_message=job.error_message,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        started_at=str(job.started_at) if job.started_at else None,
        completed_at=str(job.completed_at) if job.completed_at else None,
        created_at=str(job.created_at),
        is_stale=is_stale,
    )


@router.post("", response_model=AnalysisResponse)
async def create_analysis(body: CreateAnalysisRequest, service: ServiceDep) -> AnalysisResponse:
    """Create a new analysis job for a document."""
    if not body.documentId or not body.documentId.strip():
        raise HTTPException(status_code=400, detail="documentId is required")

    pipeline_opts = None
    if body.pipelineOptions:
        pipeline_opts = body.pipelineOptions.model_dump()

    chunking_opts = None
    if body.chunkingOptions:
        chunking_opts = body.chunkingOptions.model_dump()

    try:
        job = await service.create(
            body.documentId,
            pipeline_options=pipeline_opts,
            chunking_options=chunking_opts,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return _to_response(job, stale_after_seconds=_stale_threshold_seconds())


@router.get("", response_model=list[AnalysisResponse])
async def list_analyses(
    service: ServiceDep,
    document_id: str | None = Query(default=None, alias="documentId"),
) -> list[AnalysisResponse]:
    """List analysis jobs, optionally filtered by documentId."""
    if document_id:
        jobs = await service.find_by_document(document_id)
    else:
        jobs = await service.find_all()
    threshold = _stale_threshold_seconds()
    return [_to_response(j, stale_after_seconds=threshold) for j in jobs]


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str, service: ServiceDep) -> AnalysisResponse:
    """Get a single analysis job."""
    job = await service.find_by_id(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _to_response(job, stale_after_seconds=_stale_threshold_seconds())


@router.post("/{analysis_id}/rechunk", response_model=list[ChunkResponse])
async def rechunk_analysis(
    analysis_id: str, body: RechunkRequest, service: ServiceDep
) -> list[ChunkResponse]:
    """Re-chunk a completed analysis with new chunking options."""
    try:
        chunks = await service.rechunk(analysis_id, body.chunkingOptions.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [
        ChunkResponse(
            text=c.text,
            headings=c.headings,
            source_page=c.source_page,
            token_count=c.token_count,
            bboxes=[ChunkBboxResponse(page=b.page, bbox=b.bbox) for b in c.bboxes],
        )
        for c in chunks
    ]


@router.patch("/{analysis_id}/chunks/{chunk_index}", response_model=list[ChunkResponse])
async def update_chunk_text(
    analysis_id: str, chunk_index: int, body: UpdateChunkTextRequest, service: ServiceDep
) -> list[ChunkResponse]:
    """Update the text of a single chunk by index."""
    try:
        chunks = await service.update_chunk_text(analysis_id, chunk_index, body.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [
        ChunkResponse(
            text=c["text"],
            headings=c.get("headings", []),
            source_page=c.get("sourcePage"),
            token_count=c.get("tokenCount", 0),
            bboxes=[ChunkBboxResponse(page=b["page"], bbox=b["bbox"]) for b in c.get("bboxes", [])],
            modified=c.get("modified", False),
            deleted=c.get("deleted", False),
        )
        for c in chunks
    ]


@router.delete("/{analysis_id}/chunks/{chunk_index}", response_model=list[ChunkResponse])
async def delete_chunk(
    analysis_id: str, chunk_index: int, service: ServiceDep
) -> list[ChunkResponse]:
    """Soft-delete a chunk by index (marks it as deleted)."""
    try:
        chunks = await service.delete_chunk(analysis_id, chunk_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [
        ChunkResponse(
            text=c["text"],
            headings=c.get("headings", []),
            source_page=c.get("sourcePage"),
            token_count=c.get("tokenCount", 0),
            bboxes=[ChunkBboxResponse(page=b["page"], bbox=b["bbox"]) for b in c.get("bboxes", [])],
            modified=c.get("modified", False),
            deleted=c.get("deleted", False),
        )
        for c in chunks
    ]


@router.delete("/{analysis_id}", status_code=204, response_model=None)
async def delete_analysis(analysis_id: str, service: ServiceDep) -> None:
    """Delete an analysis job."""
    deleted = await service.delete(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found")
