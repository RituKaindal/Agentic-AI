"""Testing specialist agent."""

from typing import ClassVar

from src.agents.base import BaseSpecialistAgent
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory


class TestingAgent(BaseSpecialistAgent):
    """Specialist agent for testing review."""

    name: ClassVar[str] = "testing"
    category: ClassVar[ReviewCategory] = ReviewCategory.TESTING
    description: ClassVar[str] = "Reviews test coverage and quality"

    relevant_languages: ClassVar[set[str]] = {
        "python", "java", "kotlin", "javascript", "typescript",
        "go", "rust", "csharp", "ruby", "php", "scala",
    }

    @property
    def system_prompt(self) -> str:
        return """You are an expert in software testing reviewing code for test quality and coverage issues.

Focus on these testing concerns:

1. **Test Coverage**
   - Missing tests for new functionality
   - Untested edge cases
   - Untested error paths
   - Boundary conditions not tested

2. **Test Quality**
   - Tests that don't actually test anything meaningful
   - Brittle tests (too coupled to implementation)
   - Flaky test patterns
   - Missing assertions

3. **Test Organization**
   - Missing test descriptions/names
   - Tests doing too much
   - Poor test isolation
   - Missing arrange/act/assert structure

4. **Mocking & Stubbing**
   - Over-mocking (mocking everything)
   - Under-mocking (hitting real services in unit tests)
   - Incorrect mock setup
   - Mock verification issues

5. **Test Data**
   - Hardcoded magic values
   - Missing test fixtures
   - Shared mutable state between tests
   - Non-deterministic test data

6. **Integration Tests**
   - Missing integration tests for critical paths
   - Integration tests that should be unit tests
   - Missing cleanup/teardown

7. **Edge Cases**
   - Null/empty inputs
   - Boundary values
   - Error conditions
   - Concurrent scenarios

IMPORTANT GUIDELINES:
- Consider what types of tests are appropriate for the changes
- Don't require 100% coverage - focus on critical paths
- Balance test thoroughness with maintenance burden
- Suggest specific test cases that are missing
- Use appropriate severity levels:
  - BLOCKER: Critical functionality without tests
  - MAJOR: Important test coverage gap
  - MINOR: Additional test would be beneficial
  - SUGGESTION: Test improvement opportunity"""

    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        test_files = [f for f in files if self._is_test_file(f.path)]
        non_test_files = [f for f in files if not self._is_test_file(f.path)]

        context_section = ""
        if pr.context:
            context_section = f"""
## Repository Context
{pr.context}

"""

        return f"""Review this pull request for testing issues.

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Target Branch: {pr.metadata.target_branch}
{context_section}
## Non-Test Files (check if tests are needed)
{self._format_files_for_review(non_test_files) if non_test_files else "No non-test files changed"}

## Test Files (check quality)
{self._format_files_for_review(test_files) if test_files else "No test files changed"}

## Instructions
Analyze the code changes for testing issues. Consider:
1. Are there tests for the new/changed functionality?
2. Are the tests comprehensive and meaningful?
3. Are there edge cases that should be tested?
4. Is the test quality appropriate?

Respond with a JSON object containing:
- findings: array of {{file, line, severity, title, message, suggestion}}
- summary: brief summary of testing findings
- files_with_issues: list of files with testing issues

Focus on meaningful test coverage gaps, not achieving arbitrary coverage numbers."""

    def _is_test_file(self, path: str) -> bool:
        """Check if a file is a test file."""
        path_lower = path.lower()
        test_indicators = [
            "/test/", "/tests/", "/spec/", "/specs/",
            "_test.", ".test.", "_spec.", ".spec.",
            "test_", "spec_",
        ]
        return any(indicator in path_lower for indicator in test_indicators)
