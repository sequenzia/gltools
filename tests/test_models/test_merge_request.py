"""Tests for MergeRequest, DiffFile, and Note models."""

from datetime import datetime

from gltools.models import DiffFile, MergeRequest, Note

AUTHOR_DATA = {"id": 1, "username": "jdoe", "name": "Jane Doe"}
PIPELINE_DATA = {"id": 100, "status": "success", "web_url": "https://gitlab.com/p/100"}

MINIMAL_MR_DATA = {
    "id": 1,
    "iid": 42,
    "title": "Add feature",
    "state": "opened",
    "source_branch": "feature-branch",
    "target_branch": "main",
    "author": AUTHOR_DATA,
    "labels": [],
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T12:00:00Z",
}


class TestMergeRequest:
    """Tests for MergeRequest model."""

    def test_parse_minimal(self) -> None:
        """MergeRequest parses with only required fields."""
        mr = MergeRequest.model_validate(MINIMAL_MR_DATA)
        assert mr.id == 1
        assert mr.iid == 42
        assert mr.title == "Add feature"
        assert mr.state == "opened"
        assert mr.source_branch == "feature-branch"
        assert mr.target_branch == "main"
        assert mr.author.username == "jdoe"
        assert mr.description is None
        assert mr.assignee is None
        assert mr.pipeline is None
        assert mr.merged_at is None
        assert mr.labels == []

    def test_parse_full(self) -> None:
        """MergeRequest parses with all fields populated."""
        data = {
            **MINIMAL_MR_DATA,
            "description": "Adds the new feature",
            "assignee": {"id": 2, "username": "assignee", "name": "Assignee User"},
            "pipeline": PIPELINE_DATA,
            "labels": ["bug", "urgent"],
            "merged_at": "2025-01-16T09:00:00Z",
        }
        mr = MergeRequest.model_validate(data)
        assert mr.description == "Adds the new feature"
        assert mr.assignee is not None
        assert mr.assignee.username == "assignee"
        assert mr.pipeline is not None
        assert mr.pipeline.status == "success"
        assert mr.labels == ["bug", "urgent"]
        assert mr.merged_at is not None

    def test_datetime_parses_iso8601(self) -> None:
        """Datetime fields parse ISO 8601 strings from GitLab API."""
        mr = MergeRequest.model_validate(MINIMAL_MR_DATA)
        assert isinstance(mr.created_at, datetime)
        assert isinstance(mr.updated_at, datetime)
        assert mr.created_at.year == 2025
        assert mr.created_at.month == 1
        assert mr.created_at.day == 15

    def test_datetime_parses_with_timezone_offset(self) -> None:
        """Datetime fields parse ISO 8601 with timezone offset."""
        data = {**MINIMAL_MR_DATA, "created_at": "2025-06-01T14:30:00+02:00"}
        mr = MergeRequest.model_validate(data)
        assert isinstance(mr.created_at, datetime)

    def test_optional_fields_handle_none(self) -> None:
        """Optional fields accept explicit None values."""
        data = {
            **MINIMAL_MR_DATA,
            "description": None,
            "assignee": None,
            "pipeline": None,
            "merged_at": None,
        }
        mr = MergeRequest.model_validate(data)
        assert mr.description is None
        assert mr.assignee is None
        assert mr.pipeline is None
        assert mr.merged_at is None

    def test_ignores_extra_fields(self) -> None:
        """MergeRequest ignores extra fields from the API response."""
        data = {**MINIMAL_MR_DATA, "web_url": "https://gitlab.com/mr/1", "sha": "abc123"}
        mr = MergeRequest.model_validate(data)
        assert not hasattr(mr, "web_url")
        assert not hasattr(mr, "sha")

    def test_all_valid_states(self) -> None:
        """State field accepts all valid MR states."""
        for state in ("opened", "closed", "merged", "locked"):
            data = {**MINIMAL_MR_DATA, "state": state}
            mr = MergeRequest.model_validate(data)
            assert mr.state == state

    def test_labels_default_empty(self) -> None:
        """Labels defaults to empty list when not provided."""
        data = {k: v for k, v in MINIMAL_MR_DATA.items() if k != "labels"}
        mr = MergeRequest.model_validate(data)
        assert mr.labels == []


class TestDiffFile:
    """Tests for DiffFile model."""

    def test_parse_valid(self) -> None:
        """DiffFile parses all required fields."""
        data = {
            "old_path": "src/old.py",
            "new_path": "src/new.py",
            "diff": "@@ -1,3 +1,4 @@\n+new line",
            "new_file": False,
            "renamed_file": True,
            "deleted_file": False,
        }
        df = DiffFile.model_validate(data)
        assert df.old_path == "src/old.py"
        assert df.new_path == "src/new.py"
        assert df.diff.startswith("@@")
        assert df.new_file is False
        assert df.renamed_file is True
        assert df.deleted_file is False

    def test_ignores_extra_fields(self) -> None:
        """DiffFile ignores extra API fields."""
        data = {
            "old_path": "a.py",
            "new_path": "a.py",
            "diff": "",
            "new_file": False,
            "renamed_file": False,
            "deleted_file": False,
            "a_mode": "100644",
            "b_mode": "100644",
        }
        df = DiffFile.model_validate(data)
        assert not hasattr(df, "a_mode")


class TestNote:
    """Tests for Note model."""

    def test_parse_valid(self) -> None:
        """Note parses all required fields."""
        data = {
            "id": 10,
            "body": "Looks good!",
            "author": AUTHOR_DATA,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "system": False,
        }
        note = Note.model_validate(data)
        assert note.id == 10
        assert note.body == "Looks good!"
        assert note.author.username == "jdoe"
        assert isinstance(note.created_at, datetime)
        assert note.system is False

    def test_system_note(self) -> None:
        """Note handles system-generated notes."""
        data = {
            "id": 11,
            "body": "merged",
            "author": AUTHOR_DATA,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "system": True,
        }
        note = Note.model_validate(data)
        assert note.system is True

    def test_ignores_extra_fields(self) -> None:
        """Note ignores extra API fields."""
        data = {
            "id": 12,
            "body": "Comment",
            "author": AUTHOR_DATA,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "system": False,
            "noteable_type": "MergeRequest",
            "attachment": None,
        }
        note = Note.model_validate(data)
        assert not hasattr(note, "noteable_type")
