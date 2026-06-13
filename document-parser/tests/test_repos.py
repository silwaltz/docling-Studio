"""Tests for persistence repositories using a temporary SQLite database."""

from datetime import UTC, datetime

import pytest

from domain.models import AnalysisJob, AnalysisStatus, Document
from domain.value_objects import DocumentLifecycleState
from persistence.analysis_repo import SqliteAnalysisRepository
from persistence.database import init_db
from persistence.document_repo import SqliteDocumentRepository


@pytest.fixture(autouse=True)
async def setup_db(monkeypatch, tmp_path):
    """Use a temp file SQLite database for all repo tests."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("persistence.database.DB_PATH", db_path)
    await init_db()
    yield


@pytest.fixture
def document_repo():
    return SqliteDocumentRepository()


@pytest.fixture
def analysis_repo():
    return SqliteAnalysisRepository()


class TestDocumentRepo:
    async def test_insert_and_find_by_id(self, document_repo):
        doc = Document(
            id="doc-1",
            filename="test.pdf",
            content_type="application/pdf",
            file_size=1024,
            storage_path="/tmp/test.pdf",
        )
        await document_repo.insert(doc)

        found = await document_repo.find_by_id("doc-1")
        assert found is not None
        assert found.id == "doc-1"
        assert found.filename == "test.pdf"
        assert found.file_size == 1024

    async def test_find_by_id_not_found(self, document_repo):
        found = await document_repo.find_by_id("nonexistent")
        assert found is None

    async def test_find_all(self, document_repo):
        for i in range(3):
            doc = Document(id=f"doc-{i}", filename=f"file{i}.pdf", storage_path=f"/tmp/{i}")
            await document_repo.insert(doc)

        all_docs = await document_repo.find_all()
        assert len(all_docs) == 3

    async def test_update_page_count(self, document_repo):
        doc = Document(id="doc-1", filename="test.pdf", storage_path="/tmp/test.pdf")
        await document_repo.insert(doc)

        await document_repo.update_page_count("doc-1", 10)

        updated = await document_repo.find_by_id("doc-1")
        assert updated.page_count == 10

    async def test_delete(self, document_repo):
        doc = Document(id="doc-1", filename="test.pdf", storage_path="/tmp/test.pdf")
        await document_repo.insert(doc)

        deleted = await document_repo.delete("doc-1")
        assert deleted is True

        found = await document_repo.find_by_id("doc-1")
        assert found is None

    async def test_delete_nonexistent(self, document_repo):
        deleted = await document_repo.delete("nonexistent")
        assert deleted is False

    async def test_default_lifecycle_state_is_uploaded(self, document_repo):
        """Fresh document round-trip preserves the default Uploaded state."""
        doc = Document(id="doc-1", filename="t.pdf", storage_path="/tmp/t.pdf")
        await document_repo.insert(doc)

        found = await document_repo.find_by_id("doc-1")
        assert found is not None
        assert found.lifecycle_state == DocumentLifecycleState.UPLOADED
        assert found.lifecycle_state_at is None

    async def test_update_lifecycle_persists_state_and_timestamp(self, document_repo):
        doc = Document(id="doc-1", filename="t.pdf", storage_path="/tmp/t.pdf")
        await document_repo.insert(doc)

        when = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
        await document_repo.update_lifecycle("doc-1", DocumentLifecycleState.PARSED, when)

        found = await document_repo.find_by_id("doc-1")
        assert found is not None
        assert found.lifecycle_state == DocumentLifecycleState.PARSED
        assert found.lifecycle_state_at is not None
        assert found.lifecycle_state_at == when

    async def test_lifecycle_state_round_trips_for_each_value(self, document_repo):
        """Every enum value must serialize cleanly into and out of SQLite."""
        when = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
        for value in DocumentLifecycleState:
            doc = Document(
                id=f"doc-{value.value}",
                filename="t.pdf",
                storage_path="/tmp/t.pdf",
                lifecycle_state=value,
                lifecycle_state_at=when,
            )
            await document_repo.insert(doc)

            found = await document_repo.find_by_id(f"doc-{value.value}")
            assert found is not None
            assert found.lifecycle_state == value


class TestAnalysisRepo:
    async def _insert_doc(self, document_repo):
        doc = Document(id="doc-1", filename="test.pdf", storage_path="/tmp/test.pdf")
        await document_repo.insert(doc)
        return doc

    async def test_insert_and_find_by_id(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        job = AnalysisJob(id="job-1", document_id="doc-1")
        await analysis_repo.insert(job)

        found = await analysis_repo.find_by_id("job-1")
        assert found is not None
        assert found.id == "job-1"
        assert found.document_id == "doc-1"
        assert found.status == AnalysisStatus.PENDING
        assert found.document_filename == "test.pdf"

    async def test_find_by_id_not_found(self, analysis_repo):
        found = await analysis_repo.find_by_id("nonexistent")
        assert found is None

    async def test_find_all(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        for i in range(3):
            job = AnalysisJob(id=f"job-{i}", document_id="doc-1")
            await analysis_repo.insert(job)

        all_jobs = await analysis_repo.find_all()
        assert len(all_jobs) == 3

    async def test_update_status(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        job = AnalysisJob(id="job-1", document_id="doc-1")
        await analysis_repo.insert(job)

        job.mark_running()
        await analysis_repo.update_status(job)

        found = await analysis_repo.find_by_id("job-1")
        assert found.status == AnalysisStatus.RUNNING
        assert isinstance(found.started_at, datetime)

    async def test_update_status_completed(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        job = AnalysisJob(id="job-1", document_id="doc-1")
        await analysis_repo.insert(job)

        job.mark_running()
        job.mark_completed(markdown="# Test", html="<h1>Test</h1>", pages_json="[]")
        await analysis_repo.update_status(job)

        found = await analysis_repo.find_by_id("job-1")
        assert found.status == AnalysisStatus.COMPLETED
        assert found.content_markdown == "# Test"
        assert found.content_html == "<h1>Test</h1>"
        assert found.pages_json == "[]"

    async def test_delete(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        job = AnalysisJob(id="job-1", document_id="doc-1")
        await analysis_repo.insert(job)

        deleted = await analysis_repo.delete("job-1")
        assert deleted is True

        found = await analysis_repo.find_by_id("job-1")
        assert found is None

    async def test_delete_nonexistent(self, analysis_repo):
        deleted = await analysis_repo.delete("nonexistent")
        assert deleted is False

    async def test_find_latest_completed_by_document(self, document_repo, analysis_repo):
        """Reasoning tunnel helper: latest COMPLETED analysis with document_json."""
        await self._insert_doc(document_repo)

        # Each job must be insert()'d before update_status can touch it.
        # Scenarios: pending (excluded — not COMPLETED), old completed without
        # document_json (excluded — NULL json), recent completed with
        # document_json (the one we want), running (excluded).
        pending = AnalysisJob(id="job-pending", document_id="doc-1")
        await analysis_repo.insert(pending)

        old_completed = AnalysisJob(id="job-old", document_id="doc-1")
        await analysis_repo.insert(old_completed)
        old_completed.mark_running()
        old_completed.mark_completed(markdown="", html="", pages_json="[]")
        await analysis_repo.update_status(old_completed)

        latest = AnalysisJob(id="job-latest", document_id="doc-1")
        await analysis_repo.insert(latest)
        latest.mark_running()
        latest.mark_completed(
            markdown="md",
            html="<p/>",
            pages_json="[]",
            document_json='{"body":{"children":[]},"texts":[]}',
        )
        await analysis_repo.update_status(latest)

        running = AnalysisJob(id="job-running", document_id="doc-1")
        await analysis_repo.insert(running)
        running.mark_running()
        await analysis_repo.update_status(running)

        found = await analysis_repo.find_latest_completed_by_document("doc-1")
        assert found is not None
        assert found.id == "job-latest"
        assert found.document_json == '{"body":{"children":[]},"texts":[]}'

    async def test_find_latest_completed_by_document_none(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        found = await analysis_repo.find_latest_completed_by_document("doc-1")
        assert found is None

    async def test_delete_by_document(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        for i in range(3):
            job = AnalysisJob(id=f"job-{i}", document_id="doc-1")
            await analysis_repo.insert(job)

        count = await analysis_repo.delete_by_document("doc-1")
        assert count == 3

        all_jobs = await analysis_repo.find_all()
        assert len(all_jobs) == 0


class TestFailStaleRunning:
    """Sweep RUNNING jobs whose `created_at` is older than the threshold
    and flip them to FAILED.

    Background: a container restart clears the in-memory `asyncio.Task`
    dict but leaves the DB row at RUNNING. The original task is never
    going to run again, so on the next startup we sweep those rows.
    """

    async def _insert_doc(self, document_repo):
        doc = Document(
            id="doc-1",
            filename="test.pdf",
            content_type="application/pdf",
            file_size=1024,
            storage_path="/tmp/test.pdf",
            lifecycle_state=DocumentLifecycleState.UPLOADED,
        )
        await document_repo.insert(doc)

    async def _make_running_job(self, analysis_repo, *, age_seconds: int) -> AnalysisJob:
        from datetime import timedelta

        job = AnalysisJob(id="job-stale", document_id="doc-1")
        job.status = AnalysisStatus.RUNNING
        # Backdate `created_at` so the job is "older than" the threshold.
        job.created_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
        await analysis_repo.insert(job)
        return job

    async def test_marks_old_running_as_failed(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        await self._make_running_job(analysis_repo, age_seconds=3600)  # 1h old

        recovered = await analysis_repo.fail_stale_running(older_than_seconds=300)
        assert recovered == 1

        # The job now reports FAILED with the explanatory error message.
        stale = await analysis_repo.find_by_id("job-stale")
        assert stale is not None
        assert stale.status == AnalysisStatus.FAILED
        assert stale.error_message is not None
        assert "Stale" in stale.error_message
        # `completed_at` is set so the UI knows the job reached a terminal
        # state and the row stops looking "in progress" at a glance.
        assert stale.completed_at is not None

    async def test_keeps_fresh_running_untouched(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        await self._make_running_job(analysis_repo, age_seconds=10)  # 10s old

        recovered = await analysis_repo.fail_stale_running(older_than_seconds=300)
        assert recovered == 0

        running = await analysis_repo.find_by_id("job-stale")
        assert running is not None
        assert running.status == AnalysisStatus.RUNNING
        assert running.error_message is None

    async def test_does_not_touch_completed_jobs(self, document_repo, analysis_repo):
        await self._insert_doc(document_repo)
        # 1h-old COMPLETED job — must not be touched.
        from datetime import timedelta

        job = AnalysisJob(id="job-done", document_id="doc-1")
        job.status = AnalysisStatus.COMPLETED
        job.created_at = datetime.now(UTC) - timedelta(seconds=3600)
        job.completed_at = datetime.now(UTC) - timedelta(seconds=3500)
        await analysis_repo.insert(job)

        recovered = await analysis_repo.fail_stale_running(older_than_seconds=300)
        assert recovered == 0

        done = await analysis_repo.find_by_id("job-done")
        assert done is not None
        assert done.status == AnalysisStatus.COMPLETED
        assert done.error_message is None

    async def test_threshold_boundary_uses_age(self, document_repo, analysis_repo):
        """Threshold is interpreted as 'older than N seconds' — boundary
        jobs (exactly N seconds old) should NOT be swept, and a job
        that's N+1 seconds old SHOULD be swept.
        """
        await self._insert_doc(document_repo)

        # Insert three RUNNING jobs with distinct ids at different ages.
        from datetime import timedelta

        def _job(job_id: str, age_seconds: int) -> AnalysisJob:
            j = AnalysisJob(id=job_id, document_id="doc-1")
            j.status = AnalysisStatus.RUNNING
            j.created_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
            return j

        for jid, age in (("job-boundary", 300), ("job-just-over", 301), ("job-old", 600)):
            await analysis_repo.insert(_job(jid, age))

        recovered = await analysis_repo.fail_stale_running(older_than_seconds=300)
        assert recovered == 2  # the 301s-old one and the 600s-old one

        # The boundary job (exactly 300s old) is still RUNNING.
        boundary = await analysis_repo.find_by_id("job-boundary")
        assert boundary is not None
        assert boundary.status == AnalysisStatus.RUNNING
        # Both older jobs are FAILED.
        for job_id in ("job-just-over", "job-old"):
            swept = await analysis_repo.find_by_id(job_id)
            assert swept is not None
            assert swept.status == AnalysisStatus.FAILED, f"{job_id} should be FAILED"
