"""Database specialist agent."""

from typing import ClassVar

from src.agents.base import BaseSpecialistAgent
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory


class DatabaseAgent(BaseSpecialistAgent):
    """Specialist agent for database review."""

    name: ClassVar[str] = "database"
    category: ClassVar[ReviewCategory] = ReviewCategory.DATABASE
    description: ClassVar[str] = "Reviews database migrations and queries"

    relevant_extensions: ClassVar[set[str]] = {
        ".sql", ".yaml", ".yml", ".xml",
    }
    relevant_languages: ClassVar[set[str]] = {
        "python", "java", "kotlin", "javascript", "typescript",
        "go", "csharp", "ruby", "php",
    }

    @property
    def system_prompt(self) -> str:
        return """You are an expert database engineer reviewing code for database-related issues.

Focus on these database concerns:

1. **Migration Safety**
   - Destructive migrations without backup plan
   - Missing rollback scripts
   - Data loss risk
   - Large table alterations without online DDL
   - Missing data migration for schema changes

2. **Query Performance**
   - Missing indexes for WHERE/JOIN columns
   - SELECT * queries
   - Unnecessary JOINs
   - Cartesian products
   - Missing LIMIT on large tables

3. **Data Integrity**
   - Missing foreign key constraints
   - Missing NOT NULL where required
   - Missing unique constraints
   - Inconsistent data types

4. **Schema Design**
   - Denormalization issues
   - Poor naming conventions
   - Missing audit columns (created_at, updated_at)
   - Inappropriate column types

5. **ORM Usage**
   - N+1 query patterns
   - Missing eager loading
   - Raw queries bypassing ORM protections
   - Inefficient ORM patterns

6. **Transaction Safety**
   - Missing transactions for related operations
   - Long-running transactions
   - Deadlock potential
   - Missing retry logic for deadlocks

7. **Security**
   - SQL injection vulnerabilities
   - Exposed connection strings
   - Excessive database permissions

IMPORTANT GUIDELINES:
- Consider the database system being used (PostgreSQL, MySQL, etc.)
- Think about the impact on production data
- Consider migration execution time on large tables
- Be specific about query optimization suggestions
- Use appropriate severity levels:
  - BLOCKER: Data loss risk, security vulnerability, or breaking migration
  - MAJOR: Significant performance or integrity issue
  - MINOR: Improvement opportunity
  - SUGGESTION: Best practice consideration"""

    def filter_relevant_files(self, pr: PullRequest) -> list[PRFile]:
        """Override to include files that might contain database code."""
        relevant = []
        db_indicators = [
            "migration", "schema", "model", "entity", "repository",
            "dao", "database", "db", "query", "sql",
        ]

        for f in pr.files:
            if f.status == "deleted" or not f.diff:
                continue

            path_lower = f.path.lower()
            if f.extension in self.relevant_extensions:
                relevant.append(f)
            elif any(ind in path_lower for ind in db_indicators):
                relevant.append(f)
            elif f.language in self.relevant_languages:
                diff_lower = f.diff.lower()
                sql_keywords = ["select ", "insert ", "update ", "delete ", "create table", "alter table"]
                orm_keywords = ["query(", ".execute(", "cursor.", "session.", "@entity", "@table"]
                if any(kw in diff_lower for kw in sql_keywords + orm_keywords):
                    relevant.append(f)

        return relevant

    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        migration_files = [f for f in files if self._is_migration_file(f.path)]
        other_files = [f for f in files if not self._is_migration_file(f.path)]

        context_section = ""
        if pr.context:
            context_section = f"""
## Repository Context
{pr.context}

"""

        return f"""Review this pull request for database-related issues.

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Target Branch: {pr.metadata.target_branch}
{context_section}
## Migration Files
{self._format_files_for_review(migration_files) if migration_files else "No migration files"}

## Other Database-Related Files
{self._format_files_for_review(other_files) if other_files else "No other database files"}

## Instructions
Analyze the code changes for database issues. Consider:
1. Migration safety and rollback capability
2. Query performance and index usage
3. Data integrity and constraints
4. ORM usage patterns
5. Transaction safety

Respond with a JSON object containing:
- findings: array of {{file, line, severity, title, message, suggestion}}
- summary: brief summary of database findings
- files_with_issues: list of files with database issues

Pay special attention to migrations as they directly affect production data."""

    def _is_migration_file(self, path: str) -> bool:
        """Check if a file is a database migration."""
        path_lower = path.lower()
        migration_indicators = [
            "/migrations/", "/migrate/", "/db/migrate/",
            "/flyway/", "/liquibase/",
            "_migration", "migration_",
        ]
        return any(ind in path_lower for ind in migration_indicators) or path_lower.endswith(".sql")
