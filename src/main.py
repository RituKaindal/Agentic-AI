"""FastAPI server for PR review webhook handling."""

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from src.agents.graph import run_review
from src.config import get_settings
from src.models.pr import PRProvider
from src.models.review import ReviewResult
from src.providers.bitbucket import BitbucketProvider
from src.providers.github import GitHubProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("PR Review Agent starting up...")
    yield
    logger.info("PR Review Agent shutting down...")


app = FastAPI(
    title="PR Review Agent",
    description="Multi-agent AI-powered PR review system",
    version="0.1.0",
    lifespan=lifespan,
)


class ManualReviewRequest(BaseModel):
    """Request model for manual review endpoint."""

    pr_url: str = Field(description="Full URL to the pull request")
    post_comments: bool = Field(default=False, description="Whether to post comments to the PR")


class ReviewResponse(BaseModel):
    """Response model for review endpoints."""

    pr_id: str
    verdict: str
    summary: str
    risk_level: str
    finding_count: int
    inline_comment_count: int
    stats: dict


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature[7:], expected)


def verify_bitbucket_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Bitbucket webhook signature."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


async def process_github_review(
    owner: str, repo: str, pr_number: int, post_comments: bool = True
) -> ReviewResult:
    """Process a GitHub PR review."""
    settings = get_settings()
    provider = GitHubProvider(token=settings.github_token)

    pr = await provider.get_pr_by_id(owner, repo, pr_number)
    logger.info(f"Reviewing GitHub PR: {pr.metadata.url}")

    result = await run_review(pr)

    if post_comments and result.findings:
        try:
            commit_sha = pr.metadata.head_sha
            await provider.post_review(owner, repo, pr_number, result, commit_sha, pr.files)
            logger.info(f"Posted review to GitHub PR {pr_number}")
        except Exception as e:
            logger.error(f"Failed to post GitHub review: {e}")

    return result


async def process_bitbucket_review(
    project: str, repo: str, pr_id: int, post_comments: bool = True
) -> ReviewResult:
    """Process a Bitbucket PR review."""
    settings = get_settings()
    provider = BitbucketProvider(
        base_url=settings.bitbucket_url,
        username=settings.bitbucket_username,
        token=settings.bitbucket_token,
    )

    pr = await provider.get_pr_by_id(project, repo, pr_id)
    logger.info(f"Reviewing Bitbucket PR: {pr.metadata.url}")

    result = await run_review(pr)

    if post_comments and result.findings:
        try:
            commit_sha = pr.metadata.head_sha
            await provider.post_review(project, repo, pr_id, result, commit_sha)
            logger.info(f"Posted review to Bitbucket PR {pr_id}")
        except Exception as e:
            logger.error(f"Failed to post Bitbucket review: {e}")

    return result


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "PR Review Agent",
        "version": "0.1.0",
        "description": "Multi-agent AI-powered PR review system",
        "endpoints": {
            "health": "GET /health",
            "review": "POST /review",
            "github_webhook": "POST /webhook/github",
            "bitbucket_webhook": "POST /webhook/bitbucket",
        },
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pr-review-agent"}


@app.post("/review", response_model=ReviewResponse)
async def manual_review(request: ManualReviewRequest):
    """Manually trigger a review for a PR URL."""
    pr_url = request.pr_url.lower()

    try:
        if "github.com" in pr_url:
            provider = GitHubProvider()
            pr = await provider.get_pr(request.pr_url)
        elif any(x in pr_url for x in ["bitbucket", "/projects/", "/repos/"]):
            provider = BitbucketProvider()
            pr = await provider.get_pr(request.pr_url)
        else:
            raise HTTPException(400, "Unsupported PR URL format")

        result = await run_review(pr)

        if request.post_comments and result.findings:
            parts = pr.metadata.repository.split("/")
            commit_sha = pr.metadata.head_sha
            await provider.post_review(
                parts[0], parts[1], pr.metadata.id, result, commit_sha, pr.files
            )

        return ReviewResponse(
            pr_id=result.pr_id,
            verdict=result.verdict.value,
            summary=result.summary,
            risk_level=result.risk_level,
            finding_count=len(result.findings),
            inline_comment_count=len(result.inline_comments),
            stats=result.stats,
        )

    except Exception as e:
        logger.error(f"Review failed: {e}")
        raise HTTPException(500, f"Review failed: {str(e)}")


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
):
    """Handle GitHub webhook events."""
    settings = get_settings()
    body = await request.body()

    if settings.github_webhook_secret and x_hub_signature_256:
        if not verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(401, "Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Event type: {x_github_event}"}

    payload = await request.json()
    action = payload.get("action")

    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"Action: {action}"}

    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})

    owner = repo_data.get("owner", {}).get("login")
    repo = repo_data.get("name")
    pr_number = pr_data.get("number")

    if not all([owner, repo, pr_number]):
        raise HTTPException(400, "Missing required fields in payload")

    background_tasks.add_task(process_github_review, owner, repo, pr_number, True)

    return {
        "status": "accepted",
        "pr": f"{owner}/{repo}#{pr_number}",
        "message": "Review queued",
    }


@app.post("/webhook/bitbucket")
async def bitbucket_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_event_key: str = Header(None),
    x_hub_signature: str = Header(None),
):
    """Handle Bitbucket webhook events."""
    settings = get_settings()
    body = await request.body()

    if settings.bitbucket_webhook_secret and x_hub_signature:
        if not verify_bitbucket_signature(body, x_hub_signature, settings.bitbucket_webhook_secret):
            raise HTTPException(401, "Invalid signature")

    if x_event_key not in ("pr:opened", "pullrequest:created"):
        return {"status": "ignored", "reason": f"Event type: {x_event_key}"}

    payload = await request.json()

    pr_data = payload.get("pullRequest") or payload.get("pullrequest", {})
    if not pr_data:
        raise HTTPException(400, "Missing pull request data")

    project = None
    repo = None

    if "toRef" in pr_data:
        to_ref = pr_data.get("toRef", {})
        repo_data = to_ref.get("repository", {})
        project_data = repo_data.get("project", {})
        project = project_data.get("key")
        repo = repo_data.get("slug")
    else:
        repo_data = payload.get("repository", {})
        project = repo_data.get("project", {}).get("key")
        repo = repo_data.get("name") or repo_data.get("slug")

    pr_id = pr_data.get("id")

    if not all([project, repo, pr_id]):
        raise HTTPException(400, "Missing required fields in payload")

    background_tasks.add_task(process_bitbucket_review, project, repo, pr_id, True)

    return {
        "status": "accepted",
        "pr": f"{project}/{repo}#{pr_id}",
        "message": "Review queued",
    }


@app.get("/result/{pr_id}")
async def get_result(pr_id: str):
    """Get stored review result (placeholder for future implementation)."""
    return {"status": "not_implemented", "message": "Result storage not yet implemented"}


def run():
    """Run the server."""
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
