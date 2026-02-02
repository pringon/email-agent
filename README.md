# Agentic Email Organizer

An intelligent assistant that processes your Gmail inbox, summarizes messages, extracts tasks, and tracks their completion using Google Tasks. The agent uses OpenAI to understand emails and generate actionable insights, running automatically via a cronjob.

## Features

- Periodically reads Gmail inbox via Gmail API
- Uses OpenAI to summarize and extract tasks from emails
- Creates tasks in Google Tasks with relevant context and deadlines
- Monitors Sent Mail to auto-close tasks when you reply
- Supports user comments to influence task handling
- Sends daily digest of email summaries and pending actions

## Tech Stack

- **Language:** Python 3.10+
- **Email Access:** Gmail API (`google-api-python-client`)
- **AI Integration:** OpenAI GPT-4 via API
- **Task Management:** Google Tasks API
- **Scheduler:** `cron` or `APScheduler`
- **Storage:** Local cache / SQLite (optional)

## Prerequisites

- Python 3.10 or higher
- Google Cloud Project with Gmail and Tasks APIs enabled
- OpenAI API key

## Setup

1. Clone the repository
2. Create a virtual environment and install dependencies
3. Set up Google Cloud credentials (OAuth2)
4. Configure your OpenAI API key in `.env`
5. Run the agent or set up the cronjob

## Documentation

See [docs/agentic_email_organizer_spec.md](docs/agentic_email_organizer_spec.md) for the full specification including architecture details and project plan.

## Security

- OAuth2 for Gmail and Google Tasks access with minimal scopes
- API credentials stored securely via `.env` and encrypted config
- Email content passed to OpenAI is handled with care to avoid sensitive data exposure
- Logging is minimal and local-only by default

## License

MIT
