"""Inject a fake stale RUNNING job into the analysis_jobs table."""
import asyncio
from datetime import datetime, timedelta, UTC

from domain.models import AnalysisJob, AnalysisStatus
from persistence.analysis_repo import SqliteAnalysisRepository
from persistence.document_repo import SqliteDocumentRepository


async def main():
    doc = SqliteDocumentRepository()
    ar = SqliteAnalysisRepository()
    d = await doc.find_all()
    if not d:
        print("no docs in db; cannot insert")
        return
    j = AnalysisJob(id="fake-stale-job-001", document_id=d[0].id)
    j.status = AnalysisStatus.RUNNING
    j.created_at = datetime.now(UTC) - timedelta(hours=2)
    await ar.insert(j)
    print("injected fake-stale-job-001 (2h old)")


asyncio.run(main())
