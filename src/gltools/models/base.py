"""Base model configuration for GitLab API models."""

from pydantic import BaseModel, ConfigDict


class BaseGitLabModel(BaseModel):
    """Base model with permissive parsing for GitLab API responses."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
