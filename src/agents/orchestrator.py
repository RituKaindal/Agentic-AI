"""Orchestrator agent for classifying PRs and selecting specialists."""

from pydantic import BaseModel, Field

from src.config import get_settings
from src.llm.client import LLMClient, get_llm_client
from src.models.pr import PRClassification, PRType, PullRequest, RiskLevel


class ClassificationResponse(BaseModel):
    """Structured response for PR classification."""

    pr_type: str = Field(description="Type of PR: feature, bugfix, refactor, infrastructure, documentation, tests, dependencies, configuration, hotfix, unknown")
    risk_level: str = Field(description="Risk level: low, medium, high, critical")
    summary: str = Field(description="Brief summary of what the PR does")
    key_changes: list[str] = Field(description="List of key changes in the PR")
    specialists_needed: list[str] = Field(description="List of specialist agents to invoke")
    reasoning: str = Field(description="Reasoning for the classification and specialist selection")


class OrchestratorAgent:
    """Orchestrator agent that classifies PRs and selects specialist reviewers."""

    SPECIALIST_MAP = {
        "security": "SecurityAgent",
        "performance": "PerformanceAgent",
        "architecture": "ArchitectureAgent",
        "testing": "TestingAgent",
        "standards": "StandardsAgent",
        "database": "DatabaseAgent",
    }

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize the orchestrator.

        Args:
            llm_client: LLM client instance.
        """
        self.llm = llm_client or get_llm_client()
        self.settings = get_settings()

    async def classify(self, pr: PullRequest) -> PRClassification:
        """Classify a PR and determine which specialists to invoke.

        Args:
            pr: The pull request to classify.

        Returns:
            PRClassification with type, risk, and specialist selections.
        """
        file_summary = self._summarize_files(pr)
        enabled_specialists = self._get_enabled_specialists()

        system_prompt = """You are a PR classification system. Your job is to analyze a pull request and:
1. Determine its type (feature, bugfix, refactor, etc.)
2. Assess its risk level based on the changes
3. Select which specialist reviewers should analyze it

Available specialists:
- security: For security-sensitive code (auth, crypto, input handling, secrets)
- performance: For performance-critical code (queries, algorithms, I/O)
- architecture: For significant design changes
- testing: For changes that need test review
- standards: For code quality and style review
- database: For database migrations, schemas, and queries

Select specialists based on:
- File types and extensions changed
- Keywords in code changes
- PR title and description
- Risk level of the changes

Be selective - don't select all specialists for every PR. Choose those most relevant."""

        user_prompt = f"""Classify this pull request:

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Author: {pr.metadata.author}
- Source Branch: {pr.metadata.source_branch}
- Target Branch: {pr.metadata.target_branch}
- File Count: {pr.file_count}
- Total Changes: +{pr.total_additions} -{pr.total_deletions}

## Files Changed
{file_summary}

## Enabled Specialists
{', '.join(enabled_specialists)}

Respond with a JSON object containing:
- pr_type: one of [feature, bugfix, refactor, infrastructure, documentation, tests, dependencies, configuration, hotfix, unknown]
- risk_level: one of [low, medium, high, critical]
- summary: brief description of the PR
- key_changes: list of key changes
- specialists_needed: list from enabled specialists that should review this PR
- reasoning: explanation of your classification"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.llm.complete_structured(
            messages=messages,
            response_model=ClassificationResponse,
            temperature=0.0,
        )

        try:
            pr_type = PRType(response.pr_type.lower())
        except ValueError:
            pr_type = PRType.UNKNOWN

        try:
            risk_level = RiskLevel(response.risk_level.lower())
        except ValueError:
            risk_level = RiskLevel.MEDIUM

        valid_specialists = [s for s in response.specialists_needed if s in enabled_specialists]

        return PRClassification(
            pr_type=pr_type,
            risk_level=risk_level,
            summary=response.summary,
            key_changes=response.key_changes,
            specialists_needed=valid_specialists,
            reasoning=response.reasoning,
        )

    def _summarize_files(self, pr: PullRequest) -> str:
        """Create a summary of changed files for the prompt."""
        lines = []
        for f in pr.files[:50]:
            lang = f" ({f.language})" if f.language else ""
            lines.append(f"- {f.path}{lang}: {f.status} (+{f.additions} -{f.deletions})")

        if len(pr.files) > 50:
            lines.append(f"... and {len(pr.files) - 50} more files")

        return "\n".join(lines)

    def _get_enabled_specialists(self) -> list[str]:
        """Get list of enabled specialist names."""
        enabled = []
        if self.settings.enable_security_agent:
            enabled.append("security")
        if self.settings.enable_performance_agent:
            enabled.append("performance")
        if self.settings.enable_architecture_agent:
            enabled.append("architecture")
        if self.settings.enable_testing_agent:
            enabled.append("testing")
        if self.settings.enable_standards_agent:
            enabled.append("standards")
        if self.settings.enable_database_agent:
            enabled.append("database")
        return enabled
