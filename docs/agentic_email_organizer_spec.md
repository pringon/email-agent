# 📬 Agentic Email Organizer – Specification

An intelligent assistant that processes your Gmail inbox, summarizes messages, extracts tasks, and tracks their completion using Google Tasks. The agent uses OpenAI to understand emails and generate actionable insights, running automatically via a cronjob.

---

## ✨ Core Features

- ✅ Periodically reads Gmail inbox via Gmail API.
- 🧠 Uses OpenAI to summarize and extract tasks from emails.
- 📋 Creates tasks in Google Tasks with relevant context and deadlines.
- 📤 Monitors Sent Mail to auto-close tasks when the user replies.
- 💬 Supports user comments (in Google Tasks notes or command-line flags) to influence task handling.
- 🗞️ Sends daily digest of email summaries and pending actions (via email or plain text report).

---

## 🏗️ High-Level Architecture

```plaintext
GitHub Actions (cron: every 2 hours)  or  run_agent.py (CLI)
                          │
                          ▼
              ┌───────────────────────┐
              │ EmailAgentOrchestrator │
              │   (Pipeline Runner)    │
              └───────────┬───────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌─────────────┐ ┌────────────┐ ┌─────────────┐
   │  Gmail API  │ │ OpenAI API │ │ Tasks API   │
   └──────┬──────┘ └─────┬──────┘ └──────┬──────┘
          │               │               │
          ▼               ▼               ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ EmailFetcher │ │EmailAnalyzer │ │ TaskManager  │
  │              │ │              │ │              │
  │ Fetch unread │ │ Extract tasks│ │ Create tasks │
  │ emails       │→│ via LLM      │→│ (deduplicate)│
  └──────────────┘ └──────────────┘ └──────┬───────┘
                                           │
                          ┌────────────────┤
                          ▼                ▼
              ┌──────────────────┐ ┌──────────────┐
              │CompletionChecker │ │DigestReporter │
              │                  │ │              │
              │ Scan Sent Mail,  │ │ Daily summary│
              │ auto-close tasks │ │ email/text   │
              └──────────────────┘ └──────────────┘
```

### Pipeline Flow

Each orchestrator run executes these steps with per-step error isolation:

1. **Fetch** — `EmailFetcher` retrieves unread emails via Gmail API
2. **Analyze** — `EmailAnalyzer` sends each email to OpenAI GPT-4, returns structured `AnalysisResult` with summary and `ExtractedTask` list
3. **Create Tasks** — `TaskManager` deduplicates by email ID, then creates tasks in Google Tasks with embedded email metadata
4. **Check Completions** — `CompletionChecker` scans Sent Mail for replies to task-related threads, auto-completes matching tasks
5. **Report** — `DigestReporter` generates a daily digest of pending and completed tasks

---

## 🧩 Modules & Components

### 0. `EmailAgentOrchestrator` (`src/orchestrator/`)
- Pipeline runner that coordinates all modules in sequence.
- Executes fetch → analyze → create tasks → check completions → digest.
- Each step runs with error isolation: a failed step records its error but doesn't block subsequent steps.
- Produces `PipelineResult` with per-step `StepResult` (success, duration, details, error).
- Lazy-initializes all dependencies with sensible defaults; accepts injected mocks for testing.
- CLI entry point: `run_agent.py` with `--max-emails` flag.

### 1. `EmailFetcher` (`src/fetcher/`)
- Uses Gmail API via `GmailAuthenticator` to fetch unread or recent messages.
- Returns `Email` dataclass with parsed body (MIME, base64, HTML-to-text), headers, labels, and thread info.
- Pluggable `StateRepository` interface tracks processed message IDs to avoid reprocessing across runs.
- Iterator-based pagination for memory efficiency with large inboxes.

### 2. `EmailAnalyzer` (`src/analyzer/`)
- Sends email content to an LLM via the `LLMAdapter` interface (current implementation: `OpenAIAdapter` using GPT-4).
- Returns `AnalysisResult` containing a summary, `requires_response` flag, and a list of `ExtractedTask` objects (title, description, due date, priority, confidence score).
- Uses JSON mode for structured output parsing.
- Built-in retry logic (max 2 retries) for transient LLM failures.

### 3. `TaskManager` (`src/tasks/`)
- Full CRUD interface with Google Tasks API via `TasksAuthenticator`.
- Creates tasks from `ExtractedTask`, embedding email metadata (message ID, thread ID) in task notes using a `---email-agent-metadata---` prefix.
- Supports lookup by email ID and thread ID for deduplication and reply detection.
- Auto-creates a default "Email Tasks" list if none exists.

### 4. `CompletionChecker` (`src/completion/`)
- Scans Sent Mail for replies linked to task-related threads.
- Matches sent messages to tasks via embedded thread IDs.
- Auto-completes tasks in Google Tasks when matching replies are detected.

### 5. `CommentInterpreter` (`src/comments/`)
- Parses user comments in task notes or terminal flags.
- Executes relevant action or updates task metadata.
- Status: planned, not yet implemented.

### 6. `DigestReporter` (`src/digest/`)
- Generates daily summaries with task categorization by due date and status.
- Supports plain text formatting and email delivery via Gmail API.

---

## 🔒 Privacy & Security Considerations

- OAuth2 used for Gmail and Google Tasks access; scopes restricted to read/send/manage only.
- All API credentials stored securely (use `.env` + token vault or encrypted config).
- Email content passed to OpenAI is sensitive:
  - Avoid sending full threads when not needed.
  - Optionally use summarization prompts that redact sensitive fields.
- No third-party databases required.
- Logging is minimal and local-only unless configured otherwise.

---

## 🚀 Tech Stack

| Layer                 | Technology                                    |
|----------------------|-----------------------------------------------|
| Scheduler            | GitHub Actions cron workflows (every 2 hours) |
| Language             | Python 3.10+                                  |
| Email Access         | Gmail API (`google-api-python-client`)        |
| AI Integration       | OpenAI GPT-4 via API (pluggable `LLMAdapter`) |
| Task Management      | Google Tasks API                              |
| Storage              | Metadata embedded in Google Tasks notes       |
| CI/CD                | GitHub Actions (`tests.yml`, `run_agent.yml`) |

---

## 📅 Project Plan

| Task ID | Description                                           | Priority | Depends On         | Milestone                | Status      |
|--------:|--------------------------------------------------------|----------|---------------------|--------------------------|-------------|
| T01     | Write initial documentation and setup instructions     | High     | -                   | Initialization           | ✅ Complete |
| T02     | Setup Google Cloud Project & enable Gmail + Tasks API | High     | T01                 | Initialization           | ✅ Complete |
| T03     | Implement Gmail auth (OAuth2) & email fetcher         | High     | T02                 | Core Agent               | ✅ Complete |
| T04     | Integrate OpenAI API & prompt for task extraction     | High     | T03                 | Core Agent               | ✅ Complete |
| T05     | Design JSON schema for extracted tasks                | Medium   | T04                 | Core Agent               | ✅ Complete |
| T06     | Implement Google Tasks API integration                | High     | T02, T05            | Task Management          | ✅ Complete |
| T07     | Link tasks to originating email threads               | High     | T05, T06            | Task Management          | ✅ Complete |
| T08     | Write logic to detect task completion via Sent Mail   | Medium   | T07                 | Task Management          | ✅ Complete |
| T09     | Build daily digest generator (email or text output)   | Medium   | T06, T07            | Reporting                | ✅ Complete |
| T10     | Implement comment parser for task instructions        | Medium   | T06                 | Agentic Features         | ⬚ Pending  |
| T11     | Add scheduler (cron job) to run agent periodically    | High     | T03, T06            | Deployment Ready         | ✅ Complete |
| T12     | Final testing and QA pass                             | High     | T01–T11             | Finalization             | ⬚ Pending  |
| T13     | Revise and finalize documentation                     | High     | T12                 | Finalization             | ⬚ Pending  |

### Progress Notes

- **T01** (2026-02-02): Documentation created including README, CLAUDE.md, and spec document.
- **T02** (2026-02-02): Google Cloud Project configured with Gmail API enabled. OAuth2 credentials working.
- **T03** (2026-02-02): Gmail auth implemented and tested via integration test.
- **T03** (2026-02-04): EmailFetcher module fully implemented with Email model, body parsing, Gmail authentication, and state repository pattern. 31 unit tests passing.
- **T04** (2026-02-04): EmailAnalyzer module implemented with pluggable LLMAdapter interface, OpenAI GPT-4 adapter, and task extraction prompts. 46 unit tests passing.
- **T05** (2026-02-04): JSON schema designed via ExtractedTask and AnalysisResult dataclasses with serialization support.
- **T06** (2026-02-08): TaskManager module implemented with Google Tasks API integration, CRUD operations, email metadata embedding, and thread-based task lookup. 48 unit tests passing.
- **T07** (2026-02-08): Completed as part of T06. Tasks embed thread_id and email_id in notes, with find_tasks_by_thread_id and find_tasks_by_email_id lookup methods.
- **T08** (2026-02-08): CompletionChecker module implemented. Scans Sent Mail for replies to task-related threads and auto-completes matching tasks. 35 unit tests and 3 e2e tests passing.
- **T09** (2026-02-10): DigestReporter module implemented with daily task digest generation, plain text formatting, email delivery via Gmail API, and task categorization by due date. 62 unit tests passing.
- **T11** (2026-02-10): Orchestrator pipeline and GitHub Actions cron workflow implemented. Runs agent periodically via run_agent.yml with scheduled dispatch.

---

## ✅ Milestones Summary

- **Initialization:** T01–T02
- **Core Agent:** T03–T05
- **Task Management:** T06–T08
- **Reporting:** T09
- **Agentic Features:** T10
- **Deployment Ready:** T11
- **Finalization:** T12–T13