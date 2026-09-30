"""Base class for specialist review agents."""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from src.llm.client import LLMClient, get_llm_client
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory, ReviewFinding, Severity, SpecialistReviewResult


class FindingsResponse(BaseModel):
    """Structured response from specialist agents."""

    findings: list[dict] = Field(
        default_factory=list,
        description="List of findings with file, line, severity, title, message, and suggestion",
    )
    summary: str = Field(description="Brief summary of the review")
    files_with_issues: list[str] = Field(
        default_factory=list, description="Files that have issues"
    )


class BaseSpecialistAgent(ABC):
    """Base class for specialist review agents."""

    name: ClassVar[str] = "base"
    category: ClassVar[ReviewCategory] = ReviewCategory.GENERAL
    description: ClassVar[str] = "Base specialist agent"

    relevant_extensions: ClassVar[set[str]] = set()
    relevant_languages: ClassVar[set[str]] = set()

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize the specialist agent.

        Args:
            llm_client: LLM client instance. If not provided, uses default.
        """
        self.llm = llm_client or get_llm_client()

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this specialist."""
        pass

    @abstractmethod
    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        """Generate the review prompt for the given files.

        Args:
            pr: The pull request being reviewed.
            files: Files to review (filtered to relevant ones).

        Returns:
            The user prompt for the LLM.
        """
        pass

    def filter_relevant_files(self, pr: PullRequest) -> list[PRFile]:
        """Filter PR files to those relevant for this specialist.

        Args:
            pr: The pull request.

        Returns:
            List of relevant files.
        """
        relevant = []
        for f in pr.files:
            if f.status == "deleted":
                continue
            if not f.diff:
                continue

            if self.relevant_extensions and f.extension in self.relevant_extensions:
                relevant.append(f)
            elif self.relevant_languages and f.language in self.relevant_languages:
                relevant.append(f)
            elif not self.relevant_extensions and not self.relevant_languages:
                relevant.append(f)

        return relevant

    async def review(self, pr: PullRequest) -> SpecialistReviewResult:
        """Perform the review.

        Args:
            pr: The pull request to review.

        Returns:
            SpecialistReviewResult with findings.
        """
        files = self.filter_relevant_files(pr)
        if not files:
            return SpecialistReviewResult(
                agent=self.name,
                findings=[],
                summary=f"No relevant files for {self.name} review.",
                files_reviewed=[],
            )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.get_review_prompt(pr, files)},
        ]

        response = await self.llm.complete_structured(
            messages=messages,
            response_model=FindingsResponse,
            temperature=0.0,
            max_tokens=4096,
        )

        findings = []
        for f in response.findings:
            severity_str = f.get("severity", "minor").lower()
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.MINOR

            findings.append(
                ReviewFinding(
                    file=f.get("file", ""),
                    line=f.get("line"),
                    line_end=f.get("line_end"),
                    severity=severity,
                    category=self.category,
                    title=f.get("title", "Issue found"),
                    message=f.get("message", ""),
                    suggestion=f.get("suggestion"),
                    code_snippet=f.get("code_snippet"),
                    agent=self.name,
                )
            )

        return SpecialistReviewResult(
            agent=self.name,
            findings=findings,
            summary=response.summary,
            files_reviewed=[f.path for f in files],
        )

    def _format_files_for_review(self, files: list[PRFile]) -> str:
        """Format files for inclusion in prompts."""
        parts = []
        for f in files:
            parts.append(f"### File: {f.path}")
            if f.language:
                parts.append(f"Language: {f.language}")
            parts.append(f"Status: {f.status}")
            parts.append(f"Changes: +{f.additions} -{f.deletions}")
            parts.append("\n```diff")
            parts.append(f.diff[:8000])
            if len(f.diff) > 8000:
                parts.append("\n... (truncated)")
            parts.append("```\n")
        return "\n".join(parts)
