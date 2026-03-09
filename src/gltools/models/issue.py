"""Issue model for GitLab Issue API responses."""

from datetime import datetime

from gltools.models.base import BaseGitLabModel
from gltools.models.milestone import MilestoneRef
from gltools.models.user import UserRef


class Issue(BaseGitLabModel):
    """GitLab Issue resource."""

    id: int
    iid: int
    title: str
    description: str | None
    state: str
    author: UserRef
    assignee: UserRef | None
    labels: list[str]
    milestone: MilestoneRef | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
