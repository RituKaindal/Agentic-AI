"""Architecture specialist agent."""

from typing import ClassVar

from src.agents.base import BaseSpecialistAgent
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory


class ArchitectureAgent(BaseSpecialistAgent):
    """Specialist agent for architecture review."""

    name: ClassVar[str] = "architecture"
    category: ClassVar[ReviewCategory] = ReviewCategory.ARCHITECTURE
    description: ClassVar[str] = "Reviews code for architectural issues"

    relevant_languages: ClassVar[set[str]] = {
        "python", "java", "kotlin", "javascript", "typescript",
        "go", "rust", "csharp", "scala",
    }

    @property
    def system_prompt(self) -> str:
        return """You are an expert software architect reviewing code for design and architectural issues.

Focus on these architectural concerns:

1. **SOLID Principles**
   - Single Responsibility violations
   - Open/Closed principle violations
   - Liskov Substitution issues
   - Interface Segregation problems
   - Dependency Inversion violations

2. **Design Patterns**
   - Missing appropriate patterns
   - Anti-patterns
   - Pattern misuse
   - Over-engineering

3. **Coupling & Cohesion**
   - Tight coupling between components
   - Low cohesion within modules
   - Circular dependencies
   - God classes/functions

4. **Separation of Concerns**
   - Mixed business and infrastructure logic
   - UI logic in business layer
   - Database logic leaking to application layer

5. **API Design**
   - Breaking changes
   - Inconsistent interfaces
   - Missing abstractions
   - Leaky abstractions

6. **Error Handling**
   - Inconsistent error handling strategy
   - Silent failures
   - Error propagation issues
   - Missing error boundaries

7. **Extensibility & Maintainability**
   - Hard-coded values that should be configurable
   - Difficult to test code
   - Missing dependency injection
   - Violation of DRY principle

IMPORTANT GUIDELINES:
- Consider the existing codebase patterns and conventions
- Focus on significant architectural issues, not minor style preferences
- Be pragmatic - not everything needs perfect architecture
- Suggest specific refactoring approaches
- Use appropriate severity levels:
  - BLOCKER: Will cause significant maintenance burden or technical debt
  - MAJOR: Architectural issue that should be addressed
  - MINOR: Design improvement opportunity
  - SUGGESTION: Alternative approach worth considering"""

    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        context_section = ""
        if pr.context:
            context_section = f"""
## Repository Context
{pr.context}

"""

        return f"""Review this pull request for architectural and design issues.

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Target Branch: {pr.metadata.target_branch}
{context_section}
## Changed Files
{self._format_files_for_review(files)}

## Instructions
Analyze the code changes for architectural problems. For each finding:
1. Identify the specific file and line number (if applicable)
2. Explain the architectural concern
3. Assess severity (blocker/major/minor/suggestion)
4. Provide a specific design improvement suggestion

Respond with a JSON object containing:
- findings: array of {{file, line, severity, title, message, suggestion}}
- summary: brief summary of architectural findings
- files_with_issues: list of files with architectural issues

Focus on significant design issues, not code style or minor preferences."""
