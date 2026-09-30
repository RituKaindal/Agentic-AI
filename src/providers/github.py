"""GitHub API provider implementation."""

import base64
import logging
import re
from urllib.parse import urlparse

import httpx

from src.config import get_settings
from src.models.pr import PRFile, PRMetadata, PRProvider as PRProviderEnum, PullRequest
from src.models.review import ReviewFinding, ReviewResult, ReviewVerdict, Severity
from src.providers.base import PRProvider

logger = logging.getLogger(__name__)


class GitHubProvider(PRProvider):
    """GitHub API provider for fetching and commenting on PRs."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        """Initialize GitHub provider.

        Args:
            token: GitHub personal access token. If not provided, uses settings.
        """
        settings = get_settings()
        self.token = token or settings.github_token
        if not self.token:
            raise ValueError("GitHub token is required")

        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _parse_pr_url(self, pr_url: str) -> tuple[str, str, int]:
        """Parse GitHub PR URL into owner, repo, and PR number."""
        parsed = urlparse(pr_url)
        match = re.match(r"/([^/]+)/([^/]+)/pull/(\d+)", parsed.path)
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
        return match.group(1), match.group(2), int(match.group(3))

    async def get_pr(self, pr_url: str) -> PullRequest:
        """Fetch a pull request by URL."""
        owner, repo, pr_number = self._parse_pr_url(pr_url)
        return await self.get_pr_by_id(owner, repo, pr_number)

    async def get_pr_by_id(
        self, owner: str, repo: str, pr_number: int | str
    ) -> PullRequest:
        """Fetch a pull request by repository and PR number."""
        async with httpx.AsyncClient() as client:
            pr_response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=self.headers,
            )
            pr_response.raise_for_status()
            pr_data = pr_response.json()

            files_response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=self.headers,
                params={"per_page": 100},
            )
            files_response.raise_for_status()
            files_data = files_response.json()

        metadata = PRMetadata(
            id=str(pr_data["number"]),
            title=pr_data["title"],
            description=pr_data["body"] or "",
            author=pr_data["user"]["login"],
            source_branch=pr_data["head"]["ref"],
            target_branch=pr_data["base"]["ref"],
            url=pr_data["html_url"],
            provider=PRProviderEnum.GITHUB,
            repository=f"{owner}/{repo}",
            created_at=pr_data["created_at"],
            labels=[label["name"] for label in pr_data.get("labels", [])],
        )

        files = []
        for f in files_data:
            files.append(
                PRFile(
                    path=f["filename"],
                    diff=f.get("patch", ""),
                    status=f["status"],
                    additions=f["additions"],
                    deletions=f["deletions"],
                    language=self._detect_language(f["filename"]),
                    old_path=f.get("previous_filename"),
                )
            )

        context = await self.get_repo_context(owner, repo, pr_data["head"]["ref"])

        return PullRequest(metadata=metadata, files=files, context=context)

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str | None:
        """Get content of a file at a specific ref."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{path}",
                headers=self.headers,
                params={"ref": ref},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8")
            return data.get("content")

    async def get_repo_context(self, owner: str, repo: str, ref: str) -> str | None:
        """Get repository context from .ai-review-context.md file."""
        return await self.get_file_content(owner, repo, ".ai-review-context.md", ref)

    async def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int | str,
        body: str,
    ) -> dict:
        """Post a general comment on the PR."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{pr_number}/comments",
                headers=self.headers,
                json={"body": body},
            )
            response.raise_for_status()
            return response.json()

    async def post_inline_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int | str,
        finding: ReviewFinding,
        commit_sha: str,
    ) -> dict:
        """Post an inline comment on a specific line."""
        body = self._format_inline_comment(finding)

        comment_data = {
            "body": body,
            "commit_id": commit_sha,
            "path": finding.file,
            "side": "RIGHT",
        }

        if finding.line:
            comment_data["line"] = finding.line
        if finding.line_end and finding.line_end != finding.line:
            comment_data["start_line"] = finding.line
            comment_data["line"] = finding.line_end

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                headers=self.headers,
                json=comment_data,
            )
            response.raise_for_status()
            return response.json()

    async def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int | str,
        result: ReviewResult,
        commit_sha: str,
    ) -> dict:
        """Post a complete review with summary and inline comments."""
        event_map = {
            ReviewVerdict.APPROVE: "APPROVE",
            ReviewVerdict.REQUEST_CHANGES: "REQUEST_CHANGES",
            ReviewVerdict.COMMENT: "COMMENT",
        }

        comments = []
        for finding in result.inline_comments:
            comment = {
                "path": finding.file,
                "body": self._format_inline_comment(finding),
            }
            if finding.line:
                comment["line"] = finding.line
                comment["side"] = "RIGHT"
            if finding.line_end and finding.line_end != finding.line:
                comment["start_line"] = finding.line
                comment["line"] = finding.line_end
            comments.append(comment)

        review_data = {
            "commit_id": commit_sha,
            "body": result.format_markdown_report(),
            "event": event_map.get(result.verdict, "COMMENT"),
            "comments": comments,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                headers=self.headers,
                json=review_data,
            )
            response.raise_for_status()
            return response.json()

    def _format_inline_comment(self, finding: ReviewFinding) -> str:
        """Format a finding as an inline comment."""
        severity_emoji = {
            Severity.BLOCKER: "🔴",
            Severity.MAJOR: "🟠",
            Severity.MINOR: "🟡",
            Severity.SUGGESTION: "🔵",
        }[finding.severity]

        lines = [
            f"{severity_emoji} **[{finding.severity.value.upper()}]** {finding.title}",
            "",
            finding.message,
        ]

        if finding.suggestion:
            lines.extend(["", "**Suggestion:**", finding.suggestion])

        if finding.code_snippet:
            lines.extend(["", "```suggestion", finding.code_snippet, "```"])

        return "\n".join(lines)
