"""Pipeline model for GitLab CI/CD API responses."""

from datetime import datetime

from gltools.models.base import BaseGitLabModel
from gltools.models.job import Job


class Pipeline(BaseGitLabModel):
    """A GitLab CI/CD pipeline."""

    id: int
    status: str
    ref: str
    sha: str
    source: str
    jobs: list[Job] = []
    created_at: datetime
    finished_at: datetime | None = None
    duration: float | None = None
