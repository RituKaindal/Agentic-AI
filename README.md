# PR Review Agent

A multi-agent AI-powered code review system for GitHub and Bitbucket pull requests. Uses specialist agents to provide comprehensive, automated code reviews.

## Features

- **Multi-Agent Architecture**: Specialized agents for security, performance, architecture, testing, standards, and database reviews
- **LangGraph Orchestration**: State machine-based workflow for reliable agent coordination
- **Multi-Provider LLM Support**: Uses LiteLLM to support Claude, GPT-4, and other LLMs
- **GitHub & Bitbucket Support**: Works with both platforms via webhooks or manual invocation
- **Smart Routing**: Orchestrator classifies PRs and selects relevant specialists
- **Deduplication**: Coordinator consolidates findings and removes duplicates
- **Comment Limits**: Respects PR size-based limits to avoid noise
- **Repository Context**: Optional `.ai-review-context.md` for team conventions
- **Skip Mechanism**: Add `[skip-ai-review]` to PR title to skip

## Architecture

```
PR Event (Webhook/Manual)
         ↓
   Orchestrator Agent
   - Classifies PR type
   - Assesses risk level
   - Selects specialists
         ↓
   Specialist Agents (parallel)
   - Security
   - Performance
   - Architecture
   - Testing
   - Standards
   - Database
         ↓
   Coordinator Agent
   - Deduplicates findings
   - Prioritizes by severity
   - Enforces comment limits
         ↓
   Post Review to PR
   - Summary comment
   - Inline comments
```

## Quick Start

### 1. Install Dependencies

```bash
cd pr-review-agent
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

Required environment variables:
- `LLM_MODEL`: LiteLLM model identifier (e.g., `anthropic/claude-sonnet-4-20250514`)
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`: API key for your LLM provider
- `GITHUB_TOKEN` and/or `BITBUCKET_TOKEN`: For PR access

### 3. Run the Server

```bash
# Using the CLI
pr-review

# Or directly with uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 4. Test with a Manual Review

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123", "post_comments": false}'
```

## Webhook Setup

### GitHub

1. Go to repository **Settings → Webhooks → Add webhook**
2. Payload URL: `https://your-server/webhook/github`
3. Content type: `application/json`
4. Secret: Set `GITHUB_WEBHOOK_SECRET` in your `.env`
5. Events: Select **Pull requests**

### Bitbucket Server

1. Go to repository **Settings → Webhooks → Create webhook**
2. URL: `https://your-server/webhook/bitbucket`
3. Secret: Set `BITBUCKET_WEBHOOK_SECRET` in your `.env`
4. Events: Select **Pull request opened**

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/review` | POST | Manual review trigger |
| `/webhook/github` | POST | GitHub webhook handler |
| `/webhook/bitbucket` | POST | Bitbucket webhook handler |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_MODEL` | LiteLLM model identifier | `anthropic/claude-sonnet-4-20250514` |
| `MAX_PARALLEL_SPECIALISTS` | Max concurrent specialist agents | `4` |
| `ENABLE_*_AGENT` | Enable/disable specific specialists | `true` |

### Comment Limits

Based on PR size (file count):
- Small (1-5 files): 3 inline comments
- Medium (6-15 files): 5 inline comments
- Large (16-25 files): 7 inline comments
- Extra Large (25+ files): 12 inline comments

### Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| BLOCKER | Runtime failure, data loss, security vulnerability | Must fix before merge |
| MAJOR | Significant bug or design flaw | Should fix before merge |
| MINOR | Low-risk quality issue | Worth addressing |
| SUGGESTION | Optional improvement | Take it or leave it |

## Repository Context File

Add `.ai-review-context.md` to your repository root to provide team conventions:

```markdown
## Team Conventions
- We use SQLAlchemy for all database operations
- Authentication goes through the auth service
- All API endpoints require rate limiting

## Known Patterns
- `imagePullPolicy: Always` is intentional for dev tags
- Helm templates use {{ .Values.X }} syntax

## Shared Infrastructure
- Base templates in dmp-library provide common labels
```

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Supported Languages

The agent reviews these file types:
- **Languages**: Python, Java, Kotlin, JavaScript, TypeScript, Go, Rust, C/C++, C#, Ruby, PHP, Scala, Groovy
- **Config**: YAML, JSON, XML, TOML, Properties
- **Infrastructure**: Terraform, Helm templates, Kubernetes YAML, Dockerfiles
- **Database**: SQL, migration files
- **Web**: HTML, CSS, SCSS

Automatically skipped:
- Binary files (.jar, .class, images)
- Lock files (package-lock.json, yarn.lock)
- Generated files (.min.js, .map)
- System files (.DS_Store, __pycache__)

## Specialist Agents

### Security Agent
- SQL/Command injection
- XSS vulnerabilities
- Hardcoded credentials
- Authentication issues
- Cryptographic weaknesses

### Performance Agent
- N+1 query patterns
- Memory leaks
- Algorithmic complexity
- Missing caching
- Resource management

### Architecture Agent
- SOLID principle violations
- Design pattern issues
- Coupling and cohesion
- API design problems

### Testing Agent
- Missing test coverage
- Test quality issues
- Edge cases not tested
- Mocking problems

### Standards Agent
- Naming conventions
- Code clarity
- Documentation
- Maintainability

### Database Agent
- Migration safety
- Query performance
- Data integrity
- Schema design

## License

MIT
