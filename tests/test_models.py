"""Tests for data models."""

import pytest

from src.models.pr import PRFile, PRMetadata, PRProvider, PRType, PullRequest, RiskLevel
from src.models.review import (
    ReviewCategory,
    ReviewFinding,
    ReviewResult,
    ReviewVerdict,
    Severity,
)


class TestPRFile:
    """Tests for PRFile model."""

    def test_extension(self):
        """Test file extension detection."""
        f = PRFile(path="src/main.py", diff="", status="modified")
        assert f.extension == ".py"

    def test_extension_no_extension(self):
        """Test file without extension."""
        f = PRFile(path="Dockerfile", diff="", status="modified")
        assert f.extension == ""

    def test_filename(self):
        """Test filename extraction."""
        f = PRFile(path="src/utils/helpers.ts", diff="", status="modified")
        assert f.filename == "helpers.ts"


class TestPullRequest:
    """Tests for PullRequest model."""

    def test_file_count(self, sample_pull_request):
        """Test file count property."""
        assert sample_pull_request.file_count == 1

    def test_should_skip_review(self, sample_pr_metadata):
        """Test skip review detection."""
        metadata = sample_pr_metadata.model_copy(update={"title": "[skip-ai-review] Quick fix"})
        pr = PullRequest(metadata=metadata, files=[])
        assert pr.should_skip_review() is True

    def test_should_not_skip_review(self, sample_pull_request):
        """Test normal PR does not skip."""
        assert sample_pull_request.should_skip_review() is False


class TestReviewFinding:
    """Tests for ReviewFinding model."""

    def test_is_inline_with_line(self):
        """Test inline detection with line number."""
        finding = ReviewFinding(
            file="test.py",
            line=10,
            severity=Severity.MAJOR,
            category=ReviewCategory.SECURITY,
            title="Test",
            message="Test message",
            agent="security",
        )
        assert finding.is_inline is True

    def test_is_inline_without_line(self):
        """Test inline detection without line number."""
        finding = ReviewFinding(
            file="test.py",
            line=None,
            severity=Severity.MINOR,
            category=ReviewCategory.STANDARDS,
            title="Test",
            message="Test message",
            agent="standards",
        )
        assert finding.is_inline is False


class TestReviewResult:
    """Tests for ReviewResult model."""

    def test_severity_counts(self):
        """Test severity count properties."""
        findings = [
            ReviewFinding(
                file="a.py", severity=Severity.BLOCKER, category=ReviewCategory.SECURITY,
                title="Blocker", message="", agent="security"
            ),
            ReviewFinding(
                file="b.py", severity=Severity.MAJOR, category=ReviewCategory.PERFORMANCE,
                title="Major", message="", agent="performance"
            ),
            ReviewFinding(
                file="c.py", severity=Severity.MAJOR, category=ReviewCategory.SECURITY,
                title="Major 2", message="", agent="security"
            ),
            ReviewFinding(
                file="d.py", severity=Severity.MINOR, category=ReviewCategory.STANDARDS,
                title="Minor", message="", agent="standards"
            ),
        ]

        result = ReviewResult(
            pr_id="123",
            verdict=ReviewVerdict.REQUEST_CHANGES,
            summary="Test",
            risk_level="high",
            findings=findings,
        )

        assert result.blocker_count == 1
        assert result.major_count == 2
        assert result.minor_count == 1
        assert result.suggestion_count == 0

    def test_format_summary_table(self):
        """Test markdown summary table generation."""
        result = ReviewResult(
            pr_id="123",
            verdict=ReviewVerdict.COMMENT,
            summary="Test summary",
            risk_level="medium",
            findings=[],
        )

        table = result.format_summary_table()
        assert "medium" in table.lower() or "MEDIUM" in table
        assert "Comment" in table or "comment" in table.lower()
