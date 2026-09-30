"""Coordinator agent for consolidating and deduplicating findings."""

import logging
from collections import defaultdict

from pydantic import BaseModel, Field

from src.config import get_comment_limit
from src.llm.client import LLMClient, get_llm_client
from src.models.pr import PRClassification, PullRequest
from src.models.review import (
    ReviewFinding,
    ReviewResult,
    ReviewVerdict,
    Severity,
    SpecialistReviewResult,
)

logger = logging.getLogger(__name__)


class ConsolidationResponse(BaseModel):
    """Structured response for finding consolidation."""

    summary: str = Field(description="Executive summary of the review")
    verdict: str = Field(description="Overall verdict: approve, request_changes, or comment")
    questions: list[str] = Field(default_factory=list, description="Questions for the PR author")
    checklist: list[str] = Field(default_factory=list, description="Items to verify manually")
    duplicate_groups: list[list[int]] = Field(
        default_factory=list,
        description="Groups of finding indices that are duplicates (keep first of each group)",
    )


class CoordinatorAgent:
    """Coordinator agent that consolidates findings from specialists."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize the coordinator.

        Args:
            llm_client: LLM client instance.
        """
        self.llm = llm_client or get_llm_client()

    async def consolidate(
        self,
        pr: PullRequest,
        classification: PRClassification,
        specialist_results: list[SpecialistReviewResult],
    ) -> ReviewResult:
        """Consolidate findings from all specialists into a final review.

        Args:
            pr: The pull request.
            classification: PR classification from orchestrator.
            specialist_results: Results from specialist agents.

        Returns:
            Consolidated ReviewResult.
        """
        all_findings = []
        for result in specialist_results:
            all_findings.extend(result.findings)

        if not all_findings:
            return self._create_clean_result(pr, classification)

        all_findings.sort(key=lambda f: f.severity.priority)

        deduped_findings = await self._deduplicate_findings(all_findings, pr)

        comment_limit = get_comment_limit(pr.file_count)
        inline_comments = self._select_inline_comments(deduped_findings, comment_limit)

        summary_response = await self._generate_summary(
            pr, classification, deduped_findings, specialist_results
        )

        try:
            verdict = ReviewVerdict(summary_response.verdict.lower())
        except ValueError:
            verdict = self._determine_verdict(deduped_findings)

        stats = {
            "file_count": pr.file_count,
            "total_findings": len(deduped_findings),
            "blocker_count": sum(1 for f in deduped_findings if f.severity == Severity.BLOCKER),
            "major_count": sum(1 for f in deduped_findings if f.severity == Severity.MAJOR),
            "minor_count": sum(1 for f in deduped_findings if f.severity == Severity.MINOR),
            "suggestion_count": sum(1 for f in deduped_findings if f.severity == Severity.SUGGESTION),
            "inline_comment_count": len(inline_comments),
            "specialists_invoked": [r.agent for r in specialist_results],
        }

        return ReviewResult(
            pr_id=pr.metadata.id,
            verdict=verdict,
            summary=summary_response.summary,
            risk_level=classification.risk_level.value,
            findings=deduped_findings,
            inline_comments=inline_comments,
            questions=summary_response.questions,
            checklist=summary_response.checklist,
            stats=stats,
        )

    async def _deduplicate_findings(
        self, findings: list[ReviewFinding], pr: PullRequest
    ) -> list[ReviewFinding]:
        """Deduplicate similar findings using LLM assistance."""
        if len(findings) <= 1:
            return findings

        findings_summary = []
        for i, f in enumerate(findings):
            findings_summary.append(
                f"{i}: [{f.severity.value}] {f.file}:{f.line or 'N/A'} - {f.title}"
            )

        system_prompt = """You are a deduplication system. Identify groups of findings that are essentially the same issue reported by different specialists.
Two findings are duplicates if they:
1. Point to the same or very similar code location
2. Describe the same fundamental issue
3. Would result in redundant comments if both posted

Return groups of duplicate finding indices. Keep the most informative finding from each group (usually first one since they're sorted by severity)."""

        user_prompt = f"""Identify duplicate findings from this list:

{chr(10).join(findings_summary)}

Respond with a JSON object containing:
- duplicate_groups: array of arrays, where each inner array contains indices of duplicate findings
  Example: [[0, 3], [1, 5, 7]] means findings 0&3 are duplicates, and 1&5&7 are duplicates
- summary: brief explanation of what was deduplicated

Only group findings that are truly duplicates of each other."""

        try:
            response = await self.llm.complete_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=ConsolidationResponse,
                temperature=0.0,
            )

            indices_to_remove = set()
            for group in response.duplicate_groups:
                for idx in group[1:]:
                    if 0 <= idx < len(findings):
                        indices_to_remove.add(idx)

            return [f for i, f in enumerate(findings) if i not in indices_to_remove]

        except Exception as e:
            logger.warning(f"Deduplication failed, using all findings: {e}")
            return findings

    def _select_inline_comments(
        self, findings: list[ReviewFinding], limit: int
    ) -> list[ReviewFinding]:
        """Select findings to post as inline comments."""
        inline_eligible = [f for f in findings if f.is_inline]
        inline_eligible.sort(key=lambda f: f.severity.priority)

        selected = []
        files_with_comments: dict[str, int] = defaultdict(int)
        max_per_file = max(2, limit // 3)

        for finding in inline_eligible:
            if len(selected) >= limit:
                break
            if files_with_comments[finding.file] >= max_per_file:
                continue

            selected.append(finding)
            files_with_comments[finding.file] += 1

        return selected

    async def _generate_summary(
        self,
        pr: PullRequest,
        classification: PRClassification,
        findings: list[ReviewFinding],
        specialist_results: list[SpecialistReviewResult],
    ) -> ConsolidationResponse:
        """Generate executive summary and questions."""
        finding_summary = []
        for f in findings[:20]:
            finding_summary.append(f"- [{f.severity.value.upper()}] {f.file}: {f.title}")

        specialist_summaries = []
        for r in specialist_results:
            specialist_summaries.append(f"**{r.agent}**: {r.summary}")

        system_prompt = """You are a code review summarizer. Create a concise, actionable summary of the review findings.

Your summary should:
1. Be 2-3 sentences highlighting the most important issues
2. Mention the verdict recommendation
3. Call out any blockers specifically

Also identify:
- Questions for the PR author (things that need clarification)
- Checklist items (things that need manual verification)"""

        user_prompt = f"""Summarize this code review:

## PR Information
- Title: {pr.metadata.title}
- Type: {classification.pr_type.value}
- Risk Level: {classification.risk_level.value}
- Files Changed: {pr.file_count}

## Specialist Summaries
{chr(10).join(specialist_summaries)}

## Key Findings
{chr(10).join(finding_summary) if finding_summary else "No significant issues found"}

## Statistics
- Blockers: {sum(1 for f in findings if f.severity == Severity.BLOCKER)}
- Major: {sum(1 for f in findings if f.severity == Severity.MAJOR)}
- Minor: {sum(1 for f in findings if f.severity == Severity.MINOR)}
- Suggestions: {sum(1 for f in findings if f.severity == Severity.SUGGESTION)}

Respond with a JSON object containing:
- summary: 2-3 sentence executive summary
- verdict: approve, request_changes, or comment
- questions: list of questions for the author (max 3)
- checklist: list of items to verify manually (max 5)
- duplicate_groups: [] (not needed here)"""

        return await self.llm.complete_structured(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_model=ConsolidationResponse,
            temperature=0.0,
        )

    def _determine_verdict(self, findings: list[ReviewFinding]) -> ReviewVerdict:
        """Determine verdict based on findings."""
        blocker_count = sum(1 for f in findings if f.severity == Severity.BLOCKER)
        major_count = sum(1 for f in findings if f.severity == Severity.MAJOR)

        if blocker_count > 0:
            return ReviewVerdict.REQUEST_CHANGES
        elif major_count > 0:
            return ReviewVerdict.REQUEST_CHANGES
        elif findings:
            return ReviewVerdict.COMMENT
        return ReviewVerdict.APPROVE

    def _create_clean_result(
        self, pr: PullRequest, classification: PRClassification
    ) -> ReviewResult:
        """Create a clean review result when no issues are found."""
        return ReviewResult(
            pr_id=pr.metadata.id,
            verdict=ReviewVerdict.APPROVE,
            summary=f"No significant issues found. This {classification.pr_type.value} PR looks good to merge.",
            risk_level=classification.risk_level.value,
            findings=[],
            inline_comments=[],
            questions=[],
            checklist=[],
            stats={
                "file_count": pr.file_count,
                "total_findings": 0,
                "blocker_count": 0,
                "major_count": 0,
                "minor_count": 0,
                "suggestion_count": 0,
                "inline_comment_count": 0,
            },
        )
