"""GitLab API resource managers."""

from gltools.client.managers.issues import IssueManager
from gltools.client.managers.jobs import JobManager
from gltools.client.managers.merge_requests import MergeRequestManager
from gltools.client.managers.pipelines import PipelineManager

__all__ = [
    "IssueManager",
    "JobManager",
    "MergeRequestManager",
    "PipelineManager",
]
