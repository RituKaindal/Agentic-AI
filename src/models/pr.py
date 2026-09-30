"""Pull Request data models."""

from enum import Enum

from pydantic import BaseModel, Field


class PRProvider(str, Enum):
    """Supported PR providers."""

    GITHUB = "github"
    BITBUCKET = "bitbucket"


class PRType(str, Enum):
    """Classification of PR types."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    INFRASTRUCTURE = "infrastructure"
    DOCUMENTATION = "documentation"
    TESTS = "tests"
    DEPENDENCIES = "dependencies"
    CONFIGURATION = "configuration"
    HOTFIX = "hotfix"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Risk level assessment for PRs."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PRFile(BaseModel):
    """Represents a file changed in a PR."""

    path: str = Field(description="File path relative to repository root")
    diff: str = Field(description="Unified diff content for this file")
    status: str = Field(description="File status: added, modified, deleted, renamed")
    additions: int = Field(default=0, description="Number of lines added")
    deletions: int = Field(default=0, description="Number of lines deleted")
    language: str | None = Field(default=None, description="Detected programming language")
    old_path: str | None = Field(default=None, description="Original path for renamed files")

    @property
    def extension(self) -> str:
        """Get file extension."""
        if "." in self.path:
            return "." + self.path.rsplit(".", 1)[-1].lower()
        return ""

    @property
    def filename(self) -> str:
        """Get filename without path."""
        return self.path.rsplit("/", 1)[-1]


class PRMetadata(BaseModel):
    """Metadata about a pull request."""

    id: str = Field(description="PR ID or number")
    title: str = Field(description="PR title")
    description: str = Field(default="", description="PR description/body")
    author: str = Field(description="PR author username")
    source_branch: str = Field(description="Source/head branch name")
    target_branch: str = Field(description="Target/base branch name")
    url: str = Field(description="URL to the PR")
    provider: PRProvider = Field(description="PR provider (github/bitbucket)")
    repository: str = Field(description="Repository full name (owner/repo)")
    created_at: str | None = Field(default=None, description="PR creation timestamp")
    labels: list[str] = Field(default_factory=list, description="PR labels")


class PullRequest(BaseModel):
    """Complete pull request representation."""

    metadata: PRMetadata = Field(description="PR metadata")
    files: list[PRFile] = Field(default_factory=list, description="Changed files")
    context: str | None = Field(
        default=None, description="Repository context from .ai-review-context.md"
    )

    @property
    def file_count(self) -> int:
        """Get number of changed files."""
        return len(self.files)

    @property
    def total_additions(self) -> int:
        """Get total lines added."""
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        """Get total lines deleted."""
        return sum(f.deletions for f in self.files)

    def get_files_by_extension(self, extension: str) -> list[PRFile]:
        """Get files matching a specific extension."""
        return [f for f in self.files if f.extension == extension]

    def get_files_by_language(self, language: str) -> list[PRFile]:
        """Get files matching a specific language."""
        return [f for f in self.files if f.language == language]

    def should_skip_review(self) -> bool:
        """Check if PR should skip AI review."""
        skip_markers = ["[skip-ai-review]", "[no-ai-review]", "[skip ai review]"]
        title_lower = self.metadata.title.lower()
        return any(marker.lower() in title_lower for marker in skip_markers)


class PRClassification(BaseModel):
    """Classification result from orchestrator."""

    pr_type: PRType = Field(description="Type of PR")
    risk_level: RiskLevel = Field(description="Risk assessment")
    summary: str = Field(description="Brief summary of changes")
    key_changes: list[str] = Field(default_factory=list, description="Key changes identified")
    specialists_needed: list[str] = Field(
        default_factory=list, description="List of specialist agents to invoke"
    )
    reasoning: str = Field(description="Reasoning for classification and specialist selection")
