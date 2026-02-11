# Agentic Email Organizer

An intelligent assistant that processes your Gmail inbox, summarizes messages, extracts tasks, and tracks their completion using Google Tasks. The agent uses OpenAI to understand emails and generate actionable insights, running automatically via a cronjob.

## Features

- Periodically reads Gmail inbox via Gmail API
- Uses OpenAI GPT-4 to summarize emails and extract actionable tasks
- Creates tasks in Google Tasks with context, deadlines, and email metadata
- Monitors Sent Mail to auto-close tasks when you reply to the originating thread
- Generates daily digest of email summaries and pending actions
- Runs automatically every 2 hours via GitHub Actions cron workflow

## Architecture

```
run_agent.py (CLI)
    │
    ▼
EmailAgentOrchestrator
    │
    ├── Step 1: EmailFetcher
    │   └── Gmail API ──► Iterator[Email]
    │
    ├── Step 2: EmailAnalyzer
    │   └── Email ──► OpenAI GPT-4 ──► AnalysisResult (summary + ExtractedTasks)
    │
    ├── Step 3: TaskManager
    │   └── ExtractedTask ──► deduplicate ──► Google Tasks API
    │
    ├── Step 4: CompletionChecker
    │   └── Sent Mail ──► match threads ──► auto-complete tasks
    │
    └── Step 5: DigestReporter
        └── Pending tasks ──► daily summary email
```

The orchestrator runs each step with error isolation — a failed step records its error but doesn't block subsequent steps. Each run produces a `PipelineResult` with per-step timing and metrics.

### Key Design Decisions

- **No database:** Email metadata (message ID, thread ID) is embedded directly in Google Tasks notes, enabling task lookup without external storage
- **Pluggable LLM:** `LLMAdapter` interface allows swapping OpenAI for other providers
- **Idempotent processing:** Tasks are deduplicated by email ID before creation, preventing duplicates across cron runs
- **Lazy initialization:** All modules auto-configure with sensible defaults; constructor injection available for testing

## Tech Stack

- **Language:** Python 3.10+
- **Email Access:** Gmail API (`google-api-python-client`)
- **AI Integration:** OpenAI GPT-4 via API
- **Task Management:** Google Tasks API
- **Scheduler:** GitHub Actions cron workflows
- **Storage:** Metadata embedded in Google Tasks notes (no external DB required)

## Prerequisites

- Python 3.10 or higher
- Google Cloud Project with Gmail and Tasks APIs enabled
- OpenAI API key

## Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd email-agent
   ```

2. **Create virtual environment and install dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Set up Google Cloud credentials**
   - Create a Google Cloud Project
   - Enable Gmail API and Google Tasks API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download the credentials JSON and save as `config/credentials.json`

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

5. **Run the agent**
   ```bash
   python run_agent.py
   python run_agent.py --max-emails 10  # limit emails processed
   ```

## Deployment

The agent runs automatically via GitHub Actions cron workflows - no Docker or separate infrastructure needed.

- **Schedule:** Every 2 hours
- **Manual trigger:** Available via the Actions tab in GitHub (`workflow_dispatch`)
- **Monitoring:** Run history and logs in the GitHub Actions tab; email notifications on failure

Credentials are stored as GitHub Secrets (base64-encoded OAuth tokens and API keys). The same secrets used for CI e2e tests power the scheduled runs. See [docs/scheduler_design.md](docs/scheduler_design.md) for the full design.

## Project Structure

```
src/
├── fetcher/        # EmailFetcher – Gmail API access, email parsing, state tracking
├── analyzer/       # EmailAnalyzer – LLM-based task extraction with pluggable adapters
├── tasks/          # TaskManager – Google Tasks CRUD with email metadata embedding
├── completion/     # CompletionChecker – Sent Mail scanning, auto-task completion
├── digest/         # DigestReporter – Daily summary generation and delivery
├── comments/       # CommentInterpreter – User comment parsing (planned)
└── orchestrator/   # EmailAgentOrchestrator – Pipeline runner with error isolation
```

## Testing

```bash
source venv/bin/activate

# Unit tests (mocked dependencies)
pytest tests/ -v -m "not integration and not e2e"

# Integration tests (requires Gmail credentials)
pytest tests/ -v -m integration

# E2E tests (requires Gmail + OpenAI credentials)
pytest tests/ -v -m e2e
```

On first run, a browser window will open for OAuth authorization. After authorizing, token files are saved under `config/` for future use.

For local smoke testing of the full pipeline:

```bash
python scripts/local_test_run_agent.py --max-emails 5
```

See [docs/testing.md](docs/testing.md) for full setup and troubleshooting.

## Documentation

- [docs/agentic_email_organizer_spec.md](docs/agentic_email_organizer_spec.md) - Full specification with architecture and project plan
- [docs/scheduler_design.md](docs/scheduler_design.md) - Scheduler and orchestrator design
- [docs/testing.md](docs/testing.md) - Testing setup, credential configuration, and CI/CD
- [docs/development_log.md](docs/development_log.md) - Development journal

## Security

- OAuth2 for Gmail and Google Tasks access with minimal scopes
- API credentials stored securely via `.env` and encrypted config
- Email content passed to OpenAI is handled with care to avoid sensitive data exposure
- Logging is minimal and local-only by default

## License

MIT
