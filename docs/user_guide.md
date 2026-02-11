# User Guide

## Overview

The Agentic Email Organizer is an intelligent assistant that:

- Reads your Gmail inbox and analyzes messages with OpenAI GPT-4
- Extracts actionable tasks and creates them in Google Tasks
- Monitors your Sent Mail to auto-complete tasks when you reply
- Generates daily digests summarizing your pending tasks

It runs on demand via the CLI or automatically via GitHub Actions.

## Prerequisites

- Python 3.10 or later
- A Google Cloud project with the **Gmail API** and **Google Tasks API** enabled
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Installation

```bash
git clone https://github.com/pringon/email-agent.git
cd email-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Google Cloud Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or select an existing one).
2. Enable the **Gmail API** and **Google Tasks API** from the API Library.
3. Go to **APIs & Services > Credentials** and create an **OAuth 2.0 Client ID** (application type: Desktop app).
4. Download the credentials JSON file and save it as `config/credentials.json` in the project root.

> **Tip:** If your OAuth consent screen is in "Testing" mode, refresh tokens expire after 7 days. Publishing the app to "Production" (internal use is fine) gives you long-lived tokens.

## Configuration

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
```

That is the only required variable. The following optional variables override default paths and behavior:

| Variable | Default | Description |
|---|---|---|
| `GMAIL_CREDENTIALS_PATH` | `config/credentials.json` | Path to your OAuth client credentials |
| `GMAIL_TOKEN_PATH` | `config/token.json` | Path to the cached Gmail OAuth token |
| `TASKS_CREDENTIALS_PATH` | (same as Gmail credentials) | Separate credentials for Tasks API, if needed |
| `TASKS_TOKEN_PATH` | `config/tasks_token.json` | Path to the cached Tasks OAuth token |
| `GMAIL_NON_INTERACTIVE` | unset | Set to `1` to fail instead of opening a browser for re-auth (useful in CI) |
| `TASKS_NON_INTERACTIVE` | unset | Same as above, for the Tasks API |

## First Run and OAuth

On the first run, a browser window will open asking you to sign in with your Google account and grant permissions. After you authorize, token files are saved automatically (`config/token.json` and `config/tasks_token.json`) and reused on subsequent runs.

```bash
python run_agent.py --max-emails 5
```

Start with a small `--max-emails` value to verify everything works before processing your full inbox.

## CLI Usage

```
python run_agent.py [OPTIONS]
```

### Options

| Flag | Description |
|---|---|
| `--max-emails N` | Maximum number of unread emails to process (default: 50) |
| `--check-completions` | Scan Sent Mail for replies and auto-complete matching tasks |
| `--send-digest EMAIL` | Generate a daily task digest and send it to the given email address |

### Examples

```bash
# Process up to 50 unread emails (default)
python run_agent.py

# Process only the 10 most recent unread emails
python run_agent.py --max-emails 10

# Check Sent Mail and auto-complete tasks you've replied to
python run_agent.py --check-completions

# Send a daily digest to yourself
python run_agent.py --send-digest you@example.com
```

Each run prints a pipeline summary showing the status, duration, and key metrics for every step.

## How It Works

The pipeline runs in four stages:

1. **Fetch** — Retrieves unread emails from Gmail. Emails are deduplicated so the same message is never processed twice.
2. **Analyze** — Sends each email to GPT-4, which returns a structured JSON response containing a summary, extracted tasks (with title, description, due date, and priority), and whether a response is needed.
3. **Create Tasks** — Writes each extracted task to Google Tasks. Email metadata (message ID and thread ID) is embedded in the task notes so tasks stay linked to their source email.
4. **Check Completions** (when `--check-completions` is passed) — Scans your Sent Mail for recent replies. If you replied to a thread that has linked tasks, those tasks are automatically marked as completed.

The **digest** (`--send-digest`) is a separate mode that reads all pending tasks from Google Tasks, groups them by due date (Overdue, Due Today, Due This Week, Due Later, No Due Date), and sends the report as an email.

## Task Metadata

Every task created by the agent embeds metadata at the bottom of its notes:

```
---email-agent-metadata---
email_id: 18e1a2b3c4d5e6f7
thread_id: 18e1a2b3c4d5e6f7
```

This is how the agent links tasks back to email threads. Do not remove this section — the completion checker uses it to match replies to tasks.

## Scheduling with GitHub Actions

Three workflows automate the agent:

| Workflow | Schedule | What it does |
|---|---|---|
| `run_agent.yml` | Every 2 hours | Processes new emails and creates tasks |
| `check_completions.yml` | Every 2 hours | Auto-completes tasks for replied threads |
| `send_digest.yml` | Daily at 7:00 AM UTC | Sends a task digest email |

All workflows can also be triggered manually via `workflow_dispatch`.

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `GMAIL_PROD_CREDENTIALS` | Base64-encoded `credentials.json` |
| `GMAIL_PROD_TOKEN` | Base64-encoded `token.json` |
| `GOOGLE_TASKS_PROD_TOKEN` | Base64-encoded `tasks_token.json` |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `DIGEST_RECIPIENT_EMAIL` | Email address for the daily digest |

To base64-encode a file:

```bash
base64 -i config/credentials.json | tr -d '\n'
```

## Troubleshooting

**OAuth token expired / re-authentication required**
If running locally, delete `config/token.json` (or `config/tasks_token.json`) and run again — a browser window will open for re-authorization. In CI, you'll need to re-generate the token locally and update the corresponding GitHub secret.

**`GMAIL_NON_INTERACTIVE` failures in CI**
This means the cached token has expired and cannot be refreshed. Generate a fresh token locally, base64-encode it, and update the `GMAIL_PROD_TOKEN` secret.

**Rate limits (HTTP 429)**
The Gmail and Tasks APIs have quota limits. Reduce `--max-emails` or space out your cron schedule if you hit rate limits frequently.

**Duplicate tasks**
The agent deduplicates by email ID, so processing the same inbox twice will not create duplicate tasks. If you see duplicates, check that the task notes contain the `---email-agent-metadata---` section — tasks without metadata cannot be deduplicated.

**No tasks extracted from an email**
Not every email produces tasks. The LLM only extracts actionable items. Newsletters, notifications, and purely informational emails are summarized but may yield zero tasks.
