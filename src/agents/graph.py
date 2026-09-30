"""LangGraph workflow for PR review orchestration."""

import asyncio
import logging
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.agents.architecture import ArchitectureAgent
from src.agents.coordinator import CoordinatorAgent
from src.agents.database import DatabaseAgent
from src.agents.orchestrator import OrchestratorAgent
from src.agents.performance import PerformanceAgent
from src.agents.security import SecurityAgent
from src.agents.standards import StandardsAgent
from src.agents.testing import TestingAgent
from src.config import get_settings
from src.models.pr import PRClassification, PullRequest
from src.models.review import ReviewResult, SpecialistReviewResult

logger = logging.getLogger(__name__)


class ReviewState(TypedDict):
    """State for the review workflow."""

    pr: PullRequest
    classification: PRClassification | None
    specialist_results: list[SpecialistReviewResult]
    final_result: ReviewResult | None
    error: str | None


SPECIALIST_AGENTS = {
    "security": SecurityAgent,
    "performance": PerformanceAgent,
    "architecture": ArchitectureAgent,
    "testing": TestingAgent,
    "standards": StandardsAgent,
    "database": DatabaseAgent,
}


async def classify_pr(state: ReviewState) -> ReviewState:
    """Classify the PR and determine which specialists to invoke."""
    try:
        orchestrator = OrchestratorAgent()
        classification = await orchestrator.classify(state["pr"])
        logger.info(
            f"PR classified as {classification.pr_type.value} "
            f"(risk: {classification.risk_level.value}). "
            f"Specialists: {classification.specialists_needed}"
        )
        return {**state, "classification": classification}
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        return {**state, "error": f"Classification failed: {e}"}


async def run_specialists(state: ReviewState) -> ReviewState:
    """Run specialist agents in parallel."""
    if state.get("error"):
        return state

    classification = state["classification"]
    if not classification or not classification.specialists_needed:
        return {**state, "specialist_results": []}

    pr = state["pr"]
    settings = get_settings()

    async def run_specialist(name: str) -> SpecialistReviewResult | None:
        agent_class = SPECIALIST_AGENTS.get(name)
        if not agent_class:
            logger.warning(f"Unknown specialist: {name}")
            return None

        try:
            agent = agent_class()
            result = await agent.review(pr)
            logger.info(f"{name} found {len(result.findings)} issues")
            return result
        except Exception as e:
            logger.error(f"Specialist {name} failed: {e}")
            return SpecialistReviewResult(
                agent=name,
                findings=[],
                summary=f"Review failed: {e}",
                files_reviewed=[],
            )

    semaphore = asyncio.Semaphore(settings.max_parallel_specialists)

    async def run_with_semaphore(name: str) -> SpecialistReviewResult | None:
        async with semaphore:
            return await run_specialist(name)

    tasks = [run_with_semaphore(name) for name in classification.specialists_needed]
    results = await asyncio.gather(*tasks)

    specialist_results = [r for r in results if r is not None]
    return {**state, "specialist_results": specialist_results}


async def consolidate_results(state: ReviewState) -> ReviewState:
    """Consolidate specialist results into final review."""
    if state.get("error"):
        return state

    try:
        coordinator = CoordinatorAgent()
        result = await coordinator.consolidate(
            pr=state["pr"],
            classification=state["classification"],
            specialist_results=state["specialist_results"],
        )
        logger.info(
            f"Review complete: {result.verdict.value}, "
            f"{len(result.findings)} findings, "
            f"{len(result.inline_comments)} inline comments"
        )
        return {**state, "final_result": result}
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        return {**state, "error": f"Consolidation failed: {e}"}


def should_continue(state: ReviewState) -> str:
    """Determine if workflow should continue or end."""
    if state.get("error"):
        return "end"
    return "continue"


def build_review_graph() -> StateGraph:
    """Build the LangGraph workflow for PR review."""
    workflow = StateGraph(ReviewState)

    workflow.add_node("classify", classify_pr)
    workflow.add_node("specialists", run_specialists)
    workflow.add_node("consolidate", consolidate_results)

    workflow.set_entry_point("classify")

    workflow.add_conditional_edges(
        "classify",
        should_continue,
        {
            "continue": "specialists",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "specialists",
        should_continue,
        {
            "continue": "consolidate",
            "end": END,
        },
    )

    workflow.add_edge("consolidate", END)

    return workflow


async def run_review(pr: PullRequest) -> ReviewResult:
    """Run the complete review workflow.

    Args:
        pr: The pull request to review.

    Returns:
        ReviewResult with findings and verdict.

    Raises:
        RuntimeError: If the review workflow fails.
    """
    if pr.should_skip_review():
        logger.info(f"Skipping review for PR {pr.metadata.id} (skip marker in title)")
        from src.models.review import ReviewVerdict
        return ReviewResult(
            pr_id=pr.metadata.id,
            verdict=ReviewVerdict.COMMENT,
            summary="Review skipped per PR title marker.",
            risk_level="low",
            findings=[],
            inline_comments=[],
            questions=[],
            checklist=[],
            stats={"skipped": True},
        )

    workflow = build_review_graph()
    graph = workflow.compile()

    initial_state: ReviewState = {
        "pr": pr,
        "classification": None,
        "specialist_results": [],
        "final_result": None,
        "error": None,
    }

    final_state = await graph.ainvoke(initial_state)

    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    if not final_state.get("final_result"):
        raise RuntimeError("Review workflow completed without result")

    return final_state["final_result"]
