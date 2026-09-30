"""Abstract base class for PR providers."""

from abc import ABC, abstractmethod

from src.models.pr import PRFile, PRMetadata, PullRequest
from src.models.review import ReviewFinding, ReviewResult


class PRProvider(ABC):
    """Abstract base class for PR providers (GitHub, Bitbucket, etc.)."""

    @abstractmethod
    async def get_pr(self, pr_url: str) -> PullRequest:
        """Fetch a pull request by URL.

        Args:
            pr_url: Full URL to the pull request.

        Returns:
            PullRequest object with metadata and files.
        """
        pass

    @abstractmethod
    async def get_pr_by_id(
        self, owner: str, repo: str, pr_number: int | str
    ) -> PullRequest:
        """Fetch a pull request by repository and PR number.

        Args:
            owner: Repository owner/organization.
            repo: Repository name.
            pr_number: PR number or ID.

        Returns:
            PullRequest object with metadata and files.
        """
        pass

    @abstractmethod
    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str | None:
        """Get content of a file at a specific ref.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path in repository.
            ref: Git ref (branch, commit, tag).

        Returns:
            File content as string, or None if not found.
        """
        pass

    @abstractmethod
    async def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int | str,
        body: str,
    ) -> dict:
        """Post a general comment on the PR.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: PR number.
            body: Comment body (markdown).

        Returns:
            API response with comment details.
        """
        pass

    @abstractmethod
    async def post_inline_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int | str,
        finding: ReviewFinding,
        commit_sha: str,
    ) -> dict:
        """Post an inline comment on a specific line.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: PR number.
            finding: ReviewFinding with file, line, and message.
            commit_sha: Commit SHA to comment on.

        Returns:
            API response with comment details.
        """
        pass

    @abstractmethod
    async def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int | str,
        result: ReviewResult,
        commit_sha: str,
    ) -> dict:
        """Post a complete review with summary and inline comments.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: PR number.
            result: Complete ReviewResult.
            commit_sha: Commit SHA for inline comments.

        Returns:
            API response with review details.
        """
        pass

    @abstractmethod
    async def get_repo_context(self, owner: str, repo: str, ref: str) -> str | None:
        """Get repository context from .ai-review-context.md file.

        Args:
            owner: Repository owner.
            repo: Repository name.
            ref: Git ref to read from.

        Returns:
            Context file content, or None if not found.
        """
        pass

    def _detect_language(self, path: str) -> str | None:
        """Detect programming language from file extension."""
        extension_map = {
            ".py": "python",
            ".java": "java",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".scala": "scala",
            ".groovy": "groovy",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".sh": "shell",
            ".bash": "shell",
            ".zsh": "shell",
            ".sql": "sql",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".tf": "terraform",
            ".hcl": "hcl",
            ".dockerfile": "dockerfile",
        }
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if path.lower().endswith("dockerfile"):
            return "dockerfile"
        if path.lower().endswith("jenkinsfile"):
            return "groovy"
        return extension_map.get(ext)
