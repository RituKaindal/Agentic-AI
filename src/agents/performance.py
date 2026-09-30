"""Performance specialist agent."""

from typing import ClassVar

from src.agents.base import BaseSpecialistAgent
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory


class PerformanceAgent(BaseSpecialistAgent):
    """Specialist agent for performance review."""

    name: ClassVar[str] = "performance"
    category: ClassVar[ReviewCategory] = ReviewCategory.PERFORMANCE
    description: ClassVar[str] = "Reviews code for performance issues"

    relevant_languages: ClassVar[set[str]] = {
        "python", "java", "kotlin", "javascript", "typescript",
        "go", "rust", "c", "cpp", "csharp", "ruby", "php", "scala",
    }
    relevant_extensions: ClassVar[set[str]] = {".sql"}

    @property
    def system_prompt(self) -> str:
        return """You are an expert performance code reviewer. Your job is to identify performance issues and optimization opportunities in code changes.

Focus on these performance issues:

1. **Database Performance**
   - N+1 query problems
   - Missing indexes
   - Inefficient queries
   - Unnecessary eager loading
   - Large result sets without pagination

2. **Memory Issues**
   - Memory leaks
   - Large object allocations in loops
   - Unbounded collections
   - Not closing resources
   - Holding references unnecessarily

3. **Algorithmic Complexity**
   - O(n²) or worse algorithms where O(n) is possible
   - Inefficient data structures
   - Redundant iterations
   - Missing caching opportunities

4. **I/O Performance**
   - Blocking I/O in async contexts
   - Sequential operations that could be parallel
   - Missing connection pooling
   - Inefficient file operations

5. **Concurrency Issues**
   - Lock contention
   - Thread starvation
   - Unnecessary synchronization
   - Missing async/await

6. **Resource Management**
   - Unclosed connections/streams
   - Missing connection limits
   - No timeout configurations
   - Unbounded queues/buffers

7. **Caching**
   - Missing cache for expensive operations
   - Cache invalidation issues
   - Inappropriate cache expiration

IMPORTANT GUIDELINES:
- Focus on measurable performance impacts, not micro-optimizations
- Consider the scale and context of the application
- Provide specific metrics or reasoning for why something is a problem
- Suggest concrete improvements with expected impact
- Use appropriate severity levels:
  - BLOCKER: Will cause outages or severe degradation at scale
  - MAJOR: Significant performance impact in production
  - MINOR: Noticeable but tolerable impact
  - SUGGESTION: Optimization opportunity"""

    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        context_section = ""
        if pr.context:
            context_section = f"""
## Repository Context
{pr.context}

"""

        return f"""Review this pull request for performance issues.

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Target Branch: {pr.metadata.target_branch}
{context_section}
## Changed Files
{self._format_files_for_review(files)}

## Instructions
Analyze the code changes for performance problems. For each finding:
1. Identify the specific file and line number
2. Explain the performance issue and its impact
3. Assess severity (blocker/major/minor/suggestion)
4. Provide a specific optimization suggestion

Respond with a JSON object containing:
- findings: array of {{file, line, severity, title, message, suggestion}}
- summary: brief summary of performance findings
- files_with_issues: list of files with performance issues

Only report genuine performance concerns that would have measurable impact."""
