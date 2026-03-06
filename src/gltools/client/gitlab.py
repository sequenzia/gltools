"""Top-level GitLab API client composing all resource managers."""

from __future__ import annotations

from typing import Any

from gltools.client.http import GitLabHTTPClient
from gltools.client.managers import IssueManager, JobManager, MergeRequestManager, PipelineManager


class GitLabClient:
    """Typed GitLab REST API client with resource managers.

    Composes all resource managers into a single interface, providing
    typed attribute access to each GitLab API resource.

    Usage::

        async with GitLabClient(host="https://gitlab.com", token="glpat-xxx") as client:
            mrs = await client.merge_requests.list("mygroup/myproject")
    """

    def __init__(
        self,
        host: str,
        token: str,
        *,
        http_client: GitLabHTTPClient | None = None,
        **http_kwargs: Any,
    ) -> None:
        """Initialize the GitLab client.

        Args:
            host: GitLab instance URL (e.g., "https://gitlab.com").
            token: GitLab Personal Access Token.
            http_client: Optional pre-configured HTTP client. If provided,
                         host, token, and http_kwargs are ignored.
            **http_kwargs: Additional keyword arguments passed to GitLabHTTPClient
                          (e.g., retry_config, timeout).
        """
        if http_client is not None:
            self._http = http_client
        else:
            self._http = GitLabHTTPClient(host, token, **http_kwargs)

        self.merge_requests = MergeRequestManager(self._http)
        self.issues = IssueManager(self._http)
        self.pipelines = PipelineManager(self._http)
        self.jobs = JobManager(self._http)

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._http.close()

    async def __aenter__(self) -> GitLabClient:
        await self._http._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
