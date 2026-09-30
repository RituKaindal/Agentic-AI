"""Pytest fixtures for PR Review Agent tests."""

import pytest

from src.models.pr import PRFile, PRMetadata, PRProvider, PullRequest


@pytest.fixture
def sample_pr_file():
    """Create a sample PR file."""
    return PRFile(
        path="src/utils/auth.py",
        diff="""@@ -10,6 +10,12 @@ def authenticate(username, password):
+    # TODO: Add rate limiting
+    query = f"SELECT * FROM users WHERE username='{username}'"
+    cursor.execute(query)
+    user = cursor.fetchone()
+    if user and user.password == password:
+        return create_session(user)
     return None""",
        status="modified",
        additions=6,
        deletions=0,
        language="python",
    )


@pytest.fixture
def sample_pr_metadata():
    """Create sample PR metadata."""
    return PRMetadata(
        id="123",
        title="Add user authentication",
        description="This PR adds basic user authentication to the application.",
        author="developer",
        source_branch="feature/auth",
        target_branch="main",
        url="https://github.com/test/repo/pull/123",
        provider=PRProvider.GITHUB,
        repository="test/repo",
    )


@pytest.fixture
def sample_pull_request(sample_pr_metadata, sample_pr_file):
    """Create a sample pull request."""
    return PullRequest(
        metadata=sample_pr_metadata,
        files=[sample_pr_file],
        context=None,
    )


@pytest.fixture
def sample_pr_with_context(sample_pr_metadata, sample_pr_file):
    """Create a sample pull request with context."""
    return PullRequest(
        metadata=sample_pr_metadata,
        files=[sample_pr_file],
        context="""## Team Conventions
- We use SQLAlchemy ORM for database queries
- All authentication must go through the auth service
""",
    )
