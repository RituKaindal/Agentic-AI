"""Security specialist agent."""

from typing import ClassVar

from src.agents.base import BaseSpecialistAgent
from src.models.pr import PRFile, PullRequest
from src.models.review import ReviewCategory


class SecurityAgent(BaseSpecialistAgent):
    """Specialist agent for security review."""

    name: ClassVar[str] = "security"
    category: ClassVar[ReviewCategory] = ReviewCategory.SECURITY
    description: ClassVar[str] = "Reviews code for security vulnerabilities"

    relevant_languages: ClassVar[set[str]] = {
        "python", "java", "kotlin", "javascript", "typescript",
        "go", "rust", "c", "cpp", "csharp", "ruby", "php", "shell",
    }
    relevant_extensions: ClassVar[set[str]] = {
        ".yaml", ".yml", ".json", ".xml", ".env", ".properties",
        ".tf", ".hcl", ".dockerfile",
    }

    @property
    def system_prompt(self) -> str:
        return """You are an expert security code reviewer. Your job is to identify security vulnerabilities in code changes.

Focus on these security issues:

1. **Injection Attacks**
   - SQL injection
   - Command injection
   - LDAP injection
   - XPath injection
   - NoSQL injection

2. **Cross-Site Scripting (XSS)**
   - Reflected XSS
   - Stored XSS
   - DOM-based XSS

3. **Authentication & Authorization**
   - Missing authentication
   - Broken access control
   - Insecure session management
   - Hardcoded credentials

4. **Sensitive Data Exposure**
   - Hardcoded secrets, API keys, tokens
   - Unencrypted sensitive data
   - Logging sensitive information
   - Exposing internal errors

5. **Security Misconfigurations**
   - Insecure defaults
   - Open cloud storage
   - Permissive CORS
   - Debug mode in production

6. **Cryptographic Issues**
   - Weak algorithms (MD5, SHA1 for passwords)
   - Hardcoded encryption keys
   - Insecure random number generation

7. **Input Validation**
   - Missing input sanitization
   - Path traversal
   - Open redirects
   - SSRF vulnerabilities

IMPORTANT GUIDELINES:
- Only report REAL security issues, not theoretical ones
- Consider the context - what might look insecure could be intentional
- Be specific about the vulnerability and attack vector
- Provide actionable remediation suggestions
- Use appropriate severity levels:
  - BLOCKER: Exploitable vulnerability (SQLi, RCE, exposed secrets)
  - MAJOR: Significant security weakness
  - MINOR: Defense-in-depth improvement
  - SUGGESTION: Best practice recommendation"""

    def get_review_prompt(self, pr: PullRequest, files: list[PRFile]) -> str:
        context_section = ""
        if pr.context:
            context_section = f"""
## Repository Context
{pr.context}

"""

        return f"""Review this pull request for security vulnerabilities.

## PR Information
- Title: {pr.metadata.title}
- Description: {pr.metadata.description}
- Target Branch: {pr.metadata.target_branch}
{context_section}
## Changed Files
{self._format_files_for_review(files)}

## Instructions
Analyze the code changes for security vulnerabilities. For each finding:
1. Identify the specific file and line number
2. Explain the vulnerability and potential attack vector
3. Assess severity (blocker/major/minor/suggestion)
4. Provide a specific remediation suggestion

Respond with a JSON object containing:
- findings: array of {{file, line, severity, title, message, suggestion}}
- summary: brief summary of security findings
- files_with_issues: list of files with security issues

Only report genuine security concerns, not style issues or general code quality."""
