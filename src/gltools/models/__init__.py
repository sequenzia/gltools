"""Pydantic models for GitLab resources."""

from gltools.models.base import BaseGitLabModel
from gltools.models.issue import Issue
from gltools.models.job import Job
from gltools.models.milestone import MilestoneRef
from gltools.models.output import CommandResult, DryRunResult, ErrorResult, PaginatedResponse
from gltools.models.pipeline import Pipeline
from gltools.models.user import UserRef


class PipelineRef(BaseGitLabModel):
    """Lightweight pipeline reference as returned in nested GitLab API objects."""

    id: int
    status: str
    web_url: str


from gltools.models.merge_request import DiffFile, MergeRequest, Note

# Rebuild MergeRequest to resolve PipelineRef forward reference
MergeRequest.model_rebuild()

__all__ = [
    "BaseGitLabModel",
    "CommandResult",
    "DiffFile",
    "DryRunResult",
    "ErrorResult",
    "Issue",
    "Job",
    "MilestoneRef",
    "MergeRequest",
    "Note",
    "PaginatedResponse",
    "Pipeline",
    "PipelineRef",
    "UserRef",
]
