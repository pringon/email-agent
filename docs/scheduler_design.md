# Scheduler Design: GitHub Actions Cron

## Overview

The email agent runs on a schedule via GitHub Actions cron workflows. A pipeline orchestrator connects the four core modules (EmailFetcher, EmailAnalyzer, TaskManager, CompletionChecker) into a single run, triggered every 15 minutes during business hours.

GitHub Actions was chosen over Docker/self-hosted approaches because:
- Zero additional infrastructure (already on GitHub)
- Cron schedule lives in version control
- Built-in monitoring, logs, and failure notifications
- Credential management via GitHub Secrets (already configured for CI)

This replaces both T11 (scheduler) and T12 (Docker deployment) from the project plan.

## Architecture

```
GitHub Actions (cron: */15 8-20 * * 1-5)
    |
    v
run_agent.py (CLI entry point)
    |
    v
EmailAgentOrchestrator.run()
    |
    +-- Step 1: Fetch unread emails (EmailFetcher)
    +-- Step 2: Analyze each email (EmailAnalyzer)
    +-- Step 3: Create tasks from results (TaskManager)
    +-- Step 4: Check sent mail for completions (CompletionChecker)
    |
    v
PipelineResult (structured output with per-step metrics)
```

## File Structure

```
src/orchestrator/
    __init__.py         # Exports: EmailAgentOrchestrator, PipelineResult, StepResult
    pipeline.py         # EmailAgentOrchestrator class
    models.py           # PipelineResult, StepResult dataclasses

run_agent.py            # CLI entry point at project root

.github/workflows/
    run_agent.yml       # Cron workflow (separate from tests.yml)

tests/
    test_orchestrator.py
```

## Orchestrator Design

### `EmailAgentOrchestrator`

```python
class EmailAgentOrchestrator:
    def __init__(
        self,
        fetcher: EmailFetcher | None = None,
        analyzer: EmailAnalyzer | None = None,
        task_manager: TaskManager | None = None,
        completion_checker: CompletionChecker | None = None,
        max_emails: int = 50,
    ): ...

    def run(self) -> PipelineResult: ...
```

All module parameters default to `None` and are created lazily (matching the pattern used by CompletionChecker and EmailFetcher). This means production usage is just `EmailAgentOrchestrator().run()` with zero config, while tests inject mocks.

### Pipeline Steps

**Step 1 - Fetch:** Calls `fetcher.fetch_unread(max_results=max_emails)` and collects results into a list.

**Step 2 - Analyze:** Iterates emails and calls `analyzer.analyze(email)` for each. Uses per-email error handling so one failure doesn't block the rest. The analyzer has built-in retry logic (2 retries) for transient LLM errors.

**Step 3 - Create Tasks:** For each `AnalysisResult`, iterates `result.tasks`. Before creating, checks `task_manager.find_tasks_by_email_id(task.source_email_id)` to prevent duplicates (important for idempotency if the same unread email is processed across multiple cron runs). Calls `task_manager.create_from_extracted_task(task)` for new tasks.

**Step 4 - Check Completions:** Calls `completion_checker.check_for_completions()` which scans Sent Mail for replies to task-related threads and auto-completes matching tasks.

### Error Isolation

Each step is wrapped in its own try/except. A failed step records the error in its `StepResult` but does not prevent later steps from running. This is important because the steps are largely independent - a Gmail fetch failure shouldn't prevent completion checking from running on previously created tasks.

### Result Model

```python
@dataclass
class StepResult:
    name: str               # "fetch", "analyze", "create_tasks", "check_completions"
    success: bool
    duration_seconds: float
    details: dict            # Step-specific metrics
    error: str | None = None

@dataclass
class PipelineResult:
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[StepResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(step.success for step in self.steps)
```

## CLI Entry Point

`run_agent.py` at the project root:
- Loads `.env` via `python-dotenv`
- Configures logging (INFO level, timestamped)
- Accepts `--max-emails N` argument (default 50)
- Creates `EmailAgentOrchestrator()` and calls `run()`
- Prints step-by-step summary
- Exits 0 on full success, 1 on any step failure

```bash
# Local usage
python run_agent.py
python run_agent.py --max-emails 10
```

## GitHub Actions Workflow

### `.github/workflows/run_agent.yml`

```yaml
name: Run Email Agent

on:
  schedule:
    - cron: '*/15 8-20 * * 1-5'    # Every 15 min, Mon-Fri, 8am-8pm UTC
  workflow_dispatch:                  # Manual trigger from GitHub UI

jobs:
  run-agent:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: pip install -r requirements.txt
      - name: Setup credentials
        run: |
          mkdir -p config
          echo "${{ secrets.GMAIL_TEST_CREDENTIALS }}" | base64 -d > config/credentials.json
          echo "${{ secrets.GMAIL_TEST_TOKEN }}" | base64 -d > config/token.json
          echo "${{ secrets.GOOGLE_TASKS_TEST_TOKEN }}" | base64 -d > config/tasks_token.json
      - name: Run agent
        env:
          GMAIL_NON_INTERACTIVE: "1"
          TASKS_NON_INTERACTIVE: "1"
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python run_agent.py
```

### Schedule Options

| Schedule | Cron Expression | GitHub Minutes/Month |
|---|---|---|
| Every 15 min, business hours (default) | `*/15 8-20 * * 1-5` | ~720 |
| Every 30 min, business hours | `*/30 8-20 * * 1-5` | ~360 |
| Every hour, all day | `0 * * * *` | ~360 |
| Every 15 min, all day | `*/15 * * * *` | ~1440 |

Free GitHub accounts get 2,000 minutes/month. The default schedule uses ~36% of that.

### Credentials

Reuses the exact same GitHub Secrets already configured for e2e tests:
- `GMAIL_TEST_CREDENTIALS` - Google OAuth client credentials (base64)
- `GMAIL_TEST_TOKEN` - Gmail OAuth token (base64)
- `GOOGLE_TASKS_TEST_TOKEN` - Google Tasks OAuth token (base64)
- `OPENAI_API_KEY` - OpenAI API key

No new secrets need to be configured.

### Monitoring

- **Run history:** Visible in the GitHub Actions tab
- **Failure notifications:** GitHub sends email on workflow failure by default
- **Manual trigger:** `workflow_dispatch` allows on-demand runs from the UI
- **Logs:** Each step's metrics are printed to stdout and captured in Actions logs

## Considerations

**OAuth Token Refresh:** The authenticators handle token refresh automatically via `creds.refresh(Request())`. However, if the OAuth consent screen is in "testing" mode, tokens expire after 7 days. For production use, the consent screen should be set to "production" for long-lived refresh tokens.

**Idempotency:** The duplicate check via `find_tasks_by_email_id()` ensures repeated cron runs don't create duplicate tasks for the same email. This scans all tasks each time, which is acceptable for typical task list sizes but could be optimized with local caching if needed.

**GitHub Actions Timing:** Cron triggers are not guaranteed to fire at the exact scheduled time - delays of several minutes are common. This is acceptable for a 15-minute interval email processing use case.
