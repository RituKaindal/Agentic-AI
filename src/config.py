"""Configuration management for PR Review Agent."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Configuration (FICO AI Gateway / OpenAI-compatible)
    llm_model: str = Field(default="claude-sonnet-4-6", alias="LLM_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://llm.ai.fico.com", alias="OPENAI_BASE_URL")

    # GitHub Configuration
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_webhook_secret: str | None = Field(default=None, alias="GITHUB_WEBHOOK_SECRET")

    # Bitbucket Configuration
    bitbucket_url: str | None = Field(default=None, alias="BITBUCKET_URL")
    bitbucket_username: str | None = Field(default=None, alias="BITBUCKET_USERNAME")
    bitbucket_token: str | None = Field(default=None, alias="BITBUCKET_TOKEN")
    bitbucket_webhook_secret: str | None = Field(default=None, alias="BITBUCKET_WEBHOOK_SECRET")

    # Server Configuration
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Review Configuration
    max_parallel_specialists: int = Field(default=4, alias="MAX_PARALLEL_SPECIALISTS")
    enable_security_agent: bool = Field(default=True, alias="ENABLE_SECURITY_AGENT")
    enable_performance_agent: bool = Field(default=True, alias="ENABLE_PERFORMANCE_AGENT")
    enable_architecture_agent: bool = Field(default=True, alias="ENABLE_ARCHITECTURE_AGENT")
    enable_testing_agent: bool = Field(default=True, alias="ENABLE_TESTING_AGENT")
    enable_standards_agent: bool = Field(default=True, alias="ENABLE_STANDARDS_AGENT")
    enable_database_agent: bool = Field(default=True, alias="ENABLE_DATABASE_AGENT")


# Comment limits based on PR size
COMMENT_LIMITS = {
    "small": 3,  # 1-5 files
    "medium": 5,  # 6-15 files
    "large": 7,  # 16-25 files
    "xlarge": 12,  # 25+ files
}


def get_pr_size_category(file_count: int) -> str:
    """Determine PR size category based on file count."""
    if file_count <= 5:
        return "small"
    elif file_count <= 15:
        return "medium"
    elif file_count <= 25:
        return "large"
    return "xlarge"


def get_comment_limit(file_count: int) -> int:
    """Get maximum inline comments for a PR based on file count."""
    category = get_pr_size_category(file_count)
    return COMMENT_LIMITS[category]


# File extensions that should be reviewed
REVIEWABLE_EXTENSIONS = {
    # Programming languages
    ".py", ".java", ".kt", ".scala", ".groovy",
    ".js", ".ts", ".jsx", ".tsx",
    ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".rb", ".php",
    # Shell scripts
    ".sh", ".bash", ".zsh",
    # Configuration
    ".yaml", ".yml", ".json", ".xml", ".toml", ".ini", ".properties",
    # Infrastructure
    ".tf", ".hcl", ".tpl",
    # Database
    ".sql",
    # Web
    ".html", ".css", ".scss", ".sass", ".less",
    # Docker
    ".dockerfile",
}

# Files/patterns to skip
SKIP_PATTERNS = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.jar",
    "*.war",
    "*.ear",
    "*.min.js",
    "*.min.css",
    "*.map",
    "__pycache__/",
    "node_modules/",
    ".git/",
    "vendor/",
    "dist/",
    "build/",
}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
