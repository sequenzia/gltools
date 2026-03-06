"""MergeRequest and related models for GitLab API responses."""

from datetime import datetime
from typing import TYPE_CHECKING

from gltools.models.base import BaseGitLabModel
from gltools.models.user import UserRef

if TYPE_CHECKING:
    from gltools.models import PipelineRef


class DiffFile(BaseGitLabModel):
    """Represents a single file diff from a merge request."""

    old_path: str
    new_path: str
    diff: str
    new_file: bool
    renamed_file: bool
    deleted_file: bool


class Note(BaseGitLabModel):
    """Represents a comment/note on a merge request."""

    id: int
    body: str
    author: UserRef
    created_at: datetime
    updated_at: datetime
    system: bool


class MergeRequest(BaseGitLabModel):
    """GitLab merge request resource."""

    id: int
    iid: int
    title: str
    description: str | None = None
    state: str
    source_branch: str
    target_branch: str
    author: UserRef
    assignee: UserRef | None = None
    labels: list[str] = []
    pipeline: "PipelineRef | None" = None
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
