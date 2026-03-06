"""Tests for Pipeline and Job models."""

import json
from datetime import UTC, datetime

from gltools.models.job import Job
from gltools.models.pipeline import Pipeline


class TestJob:
    """Tests for Job model."""

    def test_parse_valid_response(self) -> None:
        """Job parses a valid GitLab API job object."""
        data = {
            "id": 1001,
            "name": "rspec",
            "stage": "test",
            "status": "success",
            "duration": 120.5,
            "failure_reason": None,
            "web_url": "https://gitlab.com/project/-/jobs/1001",
        }
        job = Job.model_validate(data)
        assert job.id == 1001
        assert job.name == "rspec"
        assert job.stage == "test"
        assert job.status == "success"
        assert job.duration == 120.5
        assert job.failure_reason is None
        assert job.web_url == "https://gitlab.com/project/-/jobs/1001"

    def test_nullable_fields_default_none(self) -> None:
        """Job nullable fields default to None when not provided."""
        data = {"id": 1, "name": "lint", "stage": "lint", "status": "running"}
        job = Job.model_validate(data)
        assert job.duration is None
        assert job.failure_reason is None
        assert job.web_url is None

    def test_failed_job_with_failure_reason(self) -> None:
        """Job with failure_reason parses correctly."""
        data = {
            "id": 2,
            "name": "deploy",
            "stage": "deploy",
            "status": "failed",
            "duration": 5.0,
            "failure_reason": "script_failure",
        }
        job = Job.model_validate(data)
        assert job.status == "failed"
        assert job.failure_reason == "script_failure"

    def test_all_valid_statuses(self) -> None:
        """Job accepts all valid GitLab job statuses."""
        statuses = [
            "created",
            "waiting_for_resource",
            "preparing",
            "pending",
            "running",
            "success",
            "failed",
            "canceled",
            "skipped",
            "manual",
            "scheduled",
        ]
        for status in statuses:
            job = Job(id=1, name="test", stage="test", status=status)
            assert job.status == status

    def test_ignores_extra_fields(self) -> None:
        """Job ignores extra fields from the API response."""
        data = {
            "id": 3,
            "name": "build",
            "stage": "build",
            "status": "success",
            "coverage": 95.5,
            "artifacts": [],
        }
        job = Job.model_validate(data)
        assert job.id == 3
        assert not hasattr(job, "coverage")

    def test_serialize_to_dict(self) -> None:
        """Job serializes to dict correctly."""
        job = Job(id=1, name="test", stage="test", status="success", duration=10.0)
        d = job.model_dump()
        assert d == {
            "id": 1,
            "name": "test",
            "stage": "test",
            "status": "success",
            "duration": 10.0,
            "failure_reason": None,
            "web_url": None,
        }

    def test_serialize_to_json(self) -> None:
        """Job serializes to JSON correctly."""
        job = Job(id=1, name="test", stage="test", status="success")
        j = job.model_dump_json()
        parsed = json.loads(j)
        assert parsed["id"] == 1
        assert parsed["status"] == "success"

    def test_duration_is_float(self) -> None:
        """Job duration is a float (seconds)."""
        job = Job(id=1, name="test", stage="test", status="success", duration=45.123)
        assert isinstance(job.duration, float)
        assert job.duration == 45.123


class TestPipeline:
    """Tests for Pipeline model."""

    def test_parse_valid_response(self) -> None:
        """Pipeline parses a valid GitLab API pipeline object."""
        data = {
            "id": 500,
            "status": "success",
            "ref": "main",
            "sha": "abc123def456",
            "source": "push",
            "created_at": "2025-01-15T10:30:00Z",
            "finished_at": "2025-01-15T10:35:00Z",
            "duration": 300.0,
        }
        pipeline = Pipeline.model_validate(data)
        assert pipeline.id == 500
        assert pipeline.status == "success"
        assert pipeline.ref == "main"
        assert pipeline.sha == "abc123def456"
        assert pipeline.source == "push"
        assert pipeline.created_at == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert pipeline.finished_at == datetime(2025, 1, 15, 10, 35, 0, tzinfo=UTC)
        assert pipeline.duration == 300.0

    def test_jobs_defaults_to_empty_list(self) -> None:
        """Pipeline.jobs defaults to empty list."""
        data = {
            "id": 1,
            "status": "running",
            "ref": "main",
            "sha": "abc123",
            "source": "push",
            "created_at": "2025-01-15T10:30:00Z",
        }
        pipeline = Pipeline.model_validate(data)
        assert pipeline.jobs == []
        assert isinstance(pipeline.jobs, list)

    def test_pipeline_still_running(self) -> None:
        """Pipeline with no finished_at or duration (still running)."""
        data = {
            "id": 2,
            "status": "running",
            "ref": "feature-branch",
            "sha": "def456",
            "source": "merge_request_event",
            "created_at": "2025-01-15T10:30:00Z",
            "finished_at": None,
            "duration": None,
        }
        pipeline = Pipeline.model_validate(data)
        assert pipeline.status == "running"
        assert pipeline.finished_at is None
        assert pipeline.duration is None

    def test_pipeline_with_jobs(self) -> None:
        """Pipeline with nested Job objects."""
        data = {
            "id": 3,
            "status": "success",
            "ref": "main",
            "sha": "abc123",
            "source": "push",
            "created_at": "2025-01-15T10:30:00Z",
            "finished_at": "2025-01-15T10:35:00Z",
            "duration": 300.0,
            "jobs": [
                {"id": 10, "name": "lint", "stage": "lint", "status": "success", "duration": 30.0},
                {"id": 11, "name": "test", "stage": "test", "status": "success", "duration": 120.0},
            ],
        }
        pipeline = Pipeline.model_validate(data)
        assert len(pipeline.jobs) == 2
        assert isinstance(pipeline.jobs[0], Job)
        assert pipeline.jobs[0].name == "lint"
        assert pipeline.jobs[1].name == "test"

    def test_all_valid_pipeline_statuses(self) -> None:
        """Pipeline accepts all valid GitLab pipeline statuses."""
        statuses = [
            "created",
            "waiting_for_resource",
            "preparing",
            "pending",
            "running",
            "success",
            "failed",
            "canceled",
            "skipped",
            "manual",
            "scheduled",
        ]
        for status in statuses:
            pipeline = Pipeline(
                id=1,
                status=status,
                ref="main",
                sha="abc",
                source="push",
                created_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
            assert pipeline.status == status

    def test_ignores_extra_fields(self) -> None:
        """Pipeline ignores extra fields from the API response."""
        data = {
            "id": 4,
            "status": "success",
            "ref": "main",
            "sha": "abc123",
            "source": "push",
            "created_at": "2025-01-15T10:30:00Z",
            "web_url": "https://gitlab.com/project/-/pipelines/4",
            "coverage": "95.5",
        }
        pipeline = Pipeline.model_validate(data)
        assert pipeline.id == 4
        assert not hasattr(pipeline, "web_url")
        assert not hasattr(pipeline, "coverage")

    def test_serialize_to_dict(self) -> None:
        """Pipeline serializes to dict correctly."""
        pipeline = Pipeline(
            id=1,
            status="success",
            ref="main",
            sha="abc",
            source="push",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            duration=60.0,
        )
        d = pipeline.model_dump()
        assert d["id"] == 1
        assert d["status"] == "success"
        assert d["jobs"] == []
        assert d["duration"] == 60.0

    def test_serialize_to_json(self) -> None:
        """Pipeline serializes to JSON correctly."""
        pipeline = Pipeline(
            id=1,
            status="success",
            ref="main",
            sha="abc",
            source="push",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        j = pipeline.model_dump_json()
        parsed = json.loads(j)
        assert parsed["id"] == 1
        assert parsed["jobs"] == []

    def test_duration_is_float(self) -> None:
        """Pipeline duration is a float (seconds) and nullable."""
        pipeline = Pipeline(
            id=1,
            status="success",
            ref="main",
            sha="abc",
            source="push",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            duration=123.456,
        )
        assert isinstance(pipeline.duration, float)
        assert pipeline.duration == 123.456

    def test_nullable_fields_default_none(self) -> None:
        """Pipeline nullable fields default to None when not provided."""
        pipeline = Pipeline(
            id=1,
            status="running",
            ref="main",
            sha="abc",
            source="push",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert pipeline.finished_at is None
        assert pipeline.duration is None
