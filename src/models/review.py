"""Review finding and result models."""

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity levels for review findings."""

    BLOCKER = "blocker"  # Must fix before merge
    MAJOR = "major"  # Should fix before merge
    MINOR = "minor"  # Worth addressing
    SUGGESTION = "suggestion"  # Optional improvement

    @property
    def priority(self) -> int:
        """Get numeric priority (lower = more severe)."""
        return {"blocker": 0, "major": 1, "minor": 2, "suggestion": 3}[self.value]


class ReviewCategory(str, Enum):
    """Categories of review findings."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    STANDARDS = "standards"
    DATABASE = "database"
    GENERAL = "general"


class ReviewVerdict(str, Enum):
    """Overall review verdict."""

    APPROVE = "approve"  # No blockers, ready to merge
    REQUEST_CHANGES = "request_changes"  # Has blockers or major issues
    COMMENT = "comment"  # Minor suggestions only


class ReviewFinding(BaseModel):
    """A single review finding/comment."""

    file: str = Field(description="File path where the issue was found")
    line: int | None = Field(default=None, description="Line number (for inline comments)")
    line_end: int | None = Field(default=None, description="End line for multi-line comments")
    severity: Severity = Field(description="Severity level")
    category: ReviewCategory = Field(description="Finding category")
    title: str = Field(description="Short title for the finding")
    message: str = Field(description="Detailed explanation of the issue")
    suggestion: str | None = Field(default=None, description="Suggested fix or improvement")
    code_snippet: str | None = Field(default=None, description="Relevant code snippet")
    agent: str = Field(description="Agent that produced this finding")

    @property
    def is_inline(self) -> bool:
        """Check if this is an inline comment."""
        return self.line is not None


class SpecialistReviewResult(BaseModel):
    """Result from a single specialist agent."""

    agent: str = Field(description="Name of the specialist agent")
    findings: list[ReviewFinding] = Field(default_factory=list, description="Findings from agent")
    summary: str = Field(description="Brief summary from the specialist")
    files_reviewed: list[str] = Field(
        default_factory=list, description="Files reviewed by this agent"
    )


class ReviewResult(BaseModel):
    """Final consolidated review result."""

    pr_id: str = Field(description="PR identifier")
    verdict: ReviewVerdict = Field(description="Overall verdict")
    summary: str = Field(description="Executive summary of the review")
    risk_level: str = Field(description="Risk assessment")
    findings: list[ReviewFinding] = Field(
        default_factory=list, description="All findings (deduplicated and prioritized)"
    )
    inline_comments: list[ReviewFinding] = Field(
        default_factory=list, description="Findings to post as inline comments"
    )
    questions: list[str] = Field(
        default_factory=list, description="Questions for the PR author"
    )
    checklist: list[str] = Field(
        default_factory=list, description="Verification checklist items"
    )
    stats: dict = Field(
        default_factory=dict, description="Statistics (file count, finding counts by severity)"
    )

    @property
    def blocker_count(self) -> int:
        """Count of blocker-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.BLOCKER)

    @property
    def major_count(self) -> int:
        """Count of major-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.MAJOR)

    @property
    def minor_count(self) -> int:
        """Count of minor-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.MINOR)

    @property
    def suggestion_count(self) -> int:
        """Count of suggestion-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.SUGGESTION)

    def format_summary_table(self) -> str:
        """Format a markdown summary table."""
        return f"""| Metric | Value |
|--------|-------|
| **Risk Level** | {self.risk_level.upper()} |
| **Verdict** | {self.verdict.value.replace('_', ' ').title()} |
| **Blockers** | {self.blocker_count} |
| **Major Issues** | {self.major_count} |
| **Minor Issues** | {self.minor_count} |
| **Suggestions** | {self.suggestion_count} |
"""

    def format_markdown_report(self) -> str:
        """Format complete review as markdown."""
        lines = [
            "## AI Code Review Summary",
            "",
            self.format_summary_table(),
            "",
            "### Summary",
            self.summary,
            "",
        ]

        if self.findings:
            lines.extend(["### Findings", ""])
            for finding in sorted(self.findings, key=lambda f: f.severity.priority):
                severity_emoji = {
                    Severity.BLOCKER: "🔴",
                    Severity.MAJOR: "🟠",
                    Severity.MINOR: "🟡",
                    Severity.SUGGESTION: "🔵",
                }[finding.severity]
                lines.append(
                    f"- {severity_emoji} **[{finding.severity.value.upper()}]** "
                    f"`{finding.file}`: {finding.title}"
                )
            lines.append("")

        if self.questions:
            lines.extend(["### Questions for Author", ""])
            for q in self.questions:
                lines.append(f"- {q}")
            lines.append("")

        if self.checklist:
            lines.extend(["### Verification Checklist", ""])
            for item in self.checklist:
                lines.append(f"- [ ] {item}")
            lines.append("")

        return "\n".join(lines)
