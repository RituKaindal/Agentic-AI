"""Code standards specialist agent."""

from typing import ClassVar

from src.agents.base import BaseSpecialistAgent
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory


class StandardsAgent(BaseSpecialistAgent):
    """Specialist agent for code standards review."""

    name: ClassVar[str] = "standards"
    category: ClassVar[ReviewCategory] = ReviewCategory.STANDARDS
    description: ClassVar[str] = "Reviews code style and standards compliance"

    relevant_extensions: ClassVar[set[str]] = set()
    relevant_languages: ClassVar[set[str]] = set()

    @property
    def system_prompt(self) -> str:
        return """You are an expert code reviewer focusing on code quality, readability, and standards compliance.

Focus on these code quality concerns:

1. **Naming Conventions**
   - Unclear or misleading names
   - Inconsistent naming style
   - Single-letter variables (except for standard loops)
   - Abbreviations that reduce clarity

2. **Code Clarity**
   - Overly complex expressions
   - Magic numbers without explanation
   - Deeply nested code
   - Long functions/methods

3. **Documentation**
   - Missing documentation for public APIs
   - Outdated comments
   - Misleading comments
   - Missing important context

4. **Error Messages**
   - Unhelpful error messages
   - Missing error context
   - Inconsistent error formatting

5. **Code Organization**
   - Inconsistent file organization
   - Related code scattered across files
   - Import organization issues

6. **Best Practices**
   - Language-specific idioms not followed
   - Deprecated patterns
   - Inconsistency with existing codebase style

7. **Maintainability**
   - Code that's hard to understand
   - Missing type hints (where applicable)
   - Complex conditionals

IMPORTANT GUIDELINES:
- Be pragmatic - not every style preference is worth mentioning
- Consider the existing codebase conventions
- Focus on readability and maintainability, not personal preferences
- Don't flag issues that linters/formatters should catch
- Use appropriate severity levels:
  - BLOCKER: Severely impacts code understanding or maintainability
  - MAJOR: Significant readability or maintainability issue
  - MINOR: Improvement would help
  - SUGGESTION: Consider this alternative"""

    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        context_section = ""
        if pr.context:
            context_section = f"""
## Repository Context
{pr.context}

"""

        return f"""Review this pull request for code quality and standards issues.

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Target Branch: {pr.metadata.target_branch}
{context_section}
## Changed Files
{self._format_files_for_review(files)}

## Instructions
Analyze the code changes for standards and quality issues. For each finding:
1. Identify the specific file and line number
2. Explain why this is a standards/quality concern
3. Assess severity (blocker/major/minor/suggestion)
4. Provide a specific improvement suggestion

Respond with a JSON object containing:
- findings: array of {{file, line, severity, title, message, suggestion}}
- summary: brief summary of standards findings
- files_with_issues: list of files with standards issues

Focus on significant readability and maintainability issues, not minor style preferences.
Keep findings limited to the most impactful issues."""
