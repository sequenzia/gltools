"""Tests for base GitLab model and shared reference models."""

import json

from gltools.models import PipelineRef
from gltools.models.base import BaseGitLabModel
from gltools.models.user import UserRef


class TestBaseGitLabModel:
    """Tests for BaseGitLabModel configuration."""

    def test_ignores_extra_fields(self) -> None:
        """BaseGitLabModel silently ignores unknown API fields."""

        class SampleModel(BaseGitLabModel):
            name: str

        instance = SampleModel(name="test", unknown_field="ignored", another=123)
        assert instance.name == "test"
        assert not hasattr(instance, "unknown_field")
        assert not hasattr(instance, "another")

    def test_populate_by_name_enabled(self) -> None:
        """BaseGitLabModel supports field population by name when aliases are used."""
        assert BaseGitLabModel.model_config.get("populate_by_name") is True

    def test_extra_ignore_configured(self) -> None:
        """BaseGitLabModel uses extra='ignore' in config."""
        assert BaseGitLabModel.model_config.get("extra") == "ignore"


class TestUserRef:
    """Tests for UserRef model."""

    def test_parse_valid_response(self) -> None:
        """UserRef parses a valid GitLab API user object."""
        data = {"id": 42, "username": "jdoe", "name": "Jane Doe"}
        user = UserRef.model_validate(data)
        assert user.id == 42
        assert user.username == "jdoe"
        assert user.name == "Jane Doe"

    def test_ignores_extra_fields(self) -> None:
        """UserRef ignores extra fields from the API response."""
        data = {
            "id": 1,
            "username": "admin",
            "name": "Admin",
            "avatar_url": "https://example.com/avatar.png",
            "web_url": "https://gitlab.com/admin",
        }
        user = UserRef.model_validate(data)
        assert user.id == 1
        assert not hasattr(user, "avatar_url")

    def test_serialize_to_dict(self) -> None:
        """UserRef serializes to dict correctly."""
        user = UserRef(id=5, username="tester", name="Test User")
        d = user.model_dump()
        assert d == {"id": 5, "username": "tester", "name": "Test User"}

    def test_serialize_to_json(self) -> None:
        """UserRef serializes to JSON correctly."""
        user = UserRef(id=5, username="tester", name="Test User")
        j = user.model_dump_json()
        parsed = json.loads(j)
        assert parsed == {"id": 5, "username": "tester", "name": "Test User"}


class TestPipelineRef:
    """Tests for PipelineRef model."""

    def test_parse_valid_response(self) -> None:
        """PipelineRef parses a valid GitLab API pipeline object."""
        data = {"id": 100, "status": "success", "web_url": "https://gitlab.com/p/100"}
        pipeline = PipelineRef.model_validate(data)
        assert pipeline.id == 100
        assert pipeline.status == "success"
        assert pipeline.web_url == "https://gitlab.com/p/100"

    def test_ignores_extra_fields(self) -> None:
        """PipelineRef ignores extra fields from the API response."""
        data = {
            "id": 200,
            "status": "failed",
            "web_url": "https://gitlab.com/p/200",
            "ref": "main",
            "sha": "abc123",
        }
        pipeline = PipelineRef.model_validate(data)
        assert pipeline.id == 200
        assert not hasattr(pipeline, "ref")

    def test_serialize_to_dict(self) -> None:
        """PipelineRef serializes to dict correctly."""
        pipeline = PipelineRef(id=10, status="running", web_url="https://gitlab.com/p/10")
        d = pipeline.model_dump()
        assert d == {"id": 10, "status": "running", "web_url": "https://gitlab.com/p/10"}

    def test_serialize_to_json(self) -> None:
        """PipelineRef serializes to JSON correctly."""
        pipeline = PipelineRef(id=10, status="running", web_url="https://gitlab.com/p/10")
        j = pipeline.model_dump_json()
        parsed = json.loads(j)
        assert parsed == {"id": 10, "status": "running", "web_url": "https://gitlab.com/p/10"}
