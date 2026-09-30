"""Bitbucket Server API provider implementation."""

import logging
import re
from urllib.parse import urlparse

import httpx

from src.config import get_settings
from src.models.pr import PRFile, PRMetadata, PRProvider as PRProviderEnum, PullRequest
from src.models.review import ReviewFinding, ReviewResult, ReviewVerdict, Severity
from src.providers.base import PRProvider

logger = logging.getLogger(__name__)


class BitbucketProvider(PRProvider):
    """Bitbucket Server API provider for fetching and commenting on PRs."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        token: str | None = None,
    ):
        """Initialize Bitbucket provider.

        Args:
            base_url: Bitbucket Server base URL.
            username: Bitbucket username.
            token: Bitbucket personal access token.
        """
        settings = get_settings()
        self.base_url = (base_url or settings.bitbucket_url or "").rstrip("/")
        self.username = username or settings.bitbucket_username
        self.token = token or settings.bitbucket_token

        if not self.base_url:
            raise ValueError("Bitbucket URL is required")
        if not self.token:
            raise ValueError("Bitbucket token is required")

        self.auth = (self.username, self.token) if self.username else None
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _parse_pr_url(self, pr_url: str) -> tuple[str, str, int]:
        """Parse Bitbucket PR URL into project, repo, and PR ID."""
        parsed = urlparse(pr_url)
        match = re.match(
            r"/projects/([^/]+)/repos/([^/]+)/pull-requests/(\d+)",
            parsed.path,
        )
        if not match:
            match = re.match(r"/([^/]+)/([^/]+)/pull-requests/(\d+)", parsed.path)
        if not match:
            raise ValueError(f"Invalid Bitbucket PR URL: {pr_url}")
        return match.group(1), match.group(2), int(match.group(3))

    async def get_pr(self, pr_url: str) -> PullRequest:
        """Fetch a pull request by URL."""
        project, repo, pr_id = self._parse_pr_url(pr_url)
        return await self.get_pr_by_id(project, repo, pr_id)

    async def get_pr_by_id(
        self, owner: str, repo: str, pr_number: int | str
    ) -> PullRequest:
        """Fetch a pull request by repository and PR number."""
        api_base = f"{self.base_url}/rest/api/1.0/projects/{owner}/repos/{repo}"

        async with httpx.AsyncClient() as client:
            pr_response = await client.get(
                f"{api_base}/pull-requests/{pr_number}",
                headers=self.headers,
                auth=self.auth,
            )
            pr_response.raise_for_status()
            pr_data = pr_response.json()

            diff_response = await client.get(
                f"{api_base}/pull-requests/{pr_number}/diff",
                headers={**self.headers, "Accept": "application/json"},
                auth=self.auth,
                params={"contextLines": 3, "withComments": False},
            )
            diff_response.raise_for_status()
            diff_data = diff_response.json()

            changes_response = await client.get(
                f"{api_base}/pull-requests/{pr_number}/changes",
                headers=self.headers,
                auth=self.auth,
                params={"limit": 1000},
            )
            changes_response.raise_for_status()
            changes_data = changes_response.json()

        from_ref = pr_data["fromRef"]
        to_ref = pr_data["toRef"]

        metadata = PRMetadata(
            id=str(pr_data["id"]),
            title=pr_data["title"],
            description=pr_data.get("description", ""),
            author=pr_data["author"]["user"]["name"],
            source_branch=from_ref["displayId"],
            target_branch=to_ref["displayId"],
            url=pr_data["links"]["self"][0]["href"],
            provider=PRProviderEnum.BITBUCKET,
            repository=f"{owner}/{repo}",
            created_at=str(pr_data.get("createdDate", "")),
        )

        files = self._parse_changes(changes_data, diff_data)
        context = await self.get_repo_context(owner, repo, from_ref["id"])

        return PullRequest(metadata=metadata, files=files, context=context)

    def _parse_changes(self, changes_data: dict, diff_data: dict) -> list[PRFile]:
        """Parse changes and diff data into PRFile objects."""
        diff_by_path = {}
        for diff in diff_data.get("diffs", []):
            dest = diff.get("destination", {})
            src = diff.get("source", {})
            path = dest.get("toString") or src.get("toString", "")
            if path:
                hunks_text = self._format_hunks(diff.get("hunks", []))
                diff_by_path[path] = hunks_text

        files = []
        for change in changes_data.get("values", []):
            path_info = change.get("path", {})
            path = path_info.get("toString", "")
            if not path:
                continue

            src_path = change.get("srcPath", {}).get("toString")
            change_type = change.get("type", "MODIFY")

            status_map = {
                "ADD": "added",
                "MODIFY": "modified",
                "DELETE": "deleted",
                "MOVE": "renamed",
                "COPY": "copied",
            }

            files.append(
                PRFile(
                    path=path,
                    diff=diff_by_path.get(path, ""),
                    status=status_map.get(change_type, "modified"),
                    additions=0,
                    deletions=0,
                    language=self._detect_language(path),
                    old_path=src_path if change_type in ("MOVE", "COPY") else None,
                )
            )

        return files

    def _format_hunks(self, hunks: list) -> str:
        """Format diff hunks into unified diff format."""
        lines = []
        for hunk in hunks:
            src_line = hunk.get("sourceLine", 1)
            src_span = hunk.get("sourceSpan", 0)
            dest_line = hunk.get("destinationLine", 1)
            dest_span = hunk.get("destinationSpan", 0)
            lines.append(f"@@ -{src_line},{src_span} +{dest_line},{dest_span} @@")

            for segment in hunk.get("segments", []):
                seg_type = segment.get("type", "CONTEXT")
                prefix = {
                    "CONTEXT": " ",
                    "ADDED": "+",
                    "REMOVED": "-",
                }.get(seg_type, " ")

                for line in segment.get("lines", []):
                    lines.append(f"{prefix}{line.get('line', '')}")

        return "\n".join(lines)

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str | None:
        """Get content of a file at a specific ref."""
        api_url = (
            f"{self.base_url}/rest/api/1.0/projects/{owner}/repos/{repo}"
            f"/raw/{path}?at={ref}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url,
                headers={"Accept": "text/plain"},
                auth=self.auth,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.text

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
        api_url = (
            f"{self.base_url}/rest/api/1.0/projects/{owner}/repos/{repo}"
            f"/pull-requests/{pr_number}/comments"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers=self.headers,
                auth=self.auth,
                json={"text": body},
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
        api_url = (
            f"{self.base_url}/rest/api/1.0/projects/{owner}/repos/{repo}"
            f"/pull-requests/{pr_number}/comments"
        )

        body = self._format_inline_comment(finding)

        comment_data = {
            "text": body,
            "anchor": {
                "path": finding.file,
                "srcPath": finding.file,
                "fileType": "TO",
            },
        }

        if finding.line:
            comment_data["anchor"]["line"] = finding.line
            comment_data["anchor"]["lineType"] = "ADDED"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers=self.headers,
                auth=self.auth,
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
        await self.post_review_comment(
            owner, repo, pr_number, result.format_markdown_report()
        )

        for finding in result.inline_comments:
            try:
                await self.post_inline_comment(
                    owner, repo, pr_number, finding, commit_sha
                )
            except Exception as e:
                logger.warning(f"Failed to post inline comment: {e}")

        return {"status": "posted", "comments": len(result.inline_comments) + 1}

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
            lines.extend(["", "```", finding.code_snippet, "```"])

        return "\n".join(lines)
