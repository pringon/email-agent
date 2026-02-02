# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agentic Email Organizer - an intelligent assistant that processes Gmail inbox, summarizes messages using OpenAI GPT-4, extracts tasks, and manages them via Google Tasks. Runs automatically via cronjob.

## Tech Stack

- Python 3.10+
- Gmail API (`google-api-python-client`) for email access
- OpenAI GPT-4 API for email analysis and task extraction
- Google Tasks API for task management
- `cron` or `APScheduler` for scheduling
- SQLite or local cache for optional storage

## Architecture

Six main modules handle the email-to-task pipeline:

1. **EmailFetcher** - Fetches emails via Gmail API, tracks last processed message to avoid reprocessing
2. **EmailAnalyzer** - Sends email content to OpenAI GPT, returns structured task data (title, due date, priority)
3. **TaskManager** - Creates/updates tasks in Google Tasks, tracks metadata including email thread IDs
4. **CompletionChecker** - Scans Sent Mail for replies to task-related threads, auto-closes tasks on reply
5. **CommentInterpreter** - Parses user comments in task notes or CLI flags to modify task handling
6. **DigestReporter** - Generates daily summaries via email or plain text output

## Development Setup

1. Create Google Cloud Project with Gmail and Tasks APIs enabled
2. Set up OAuth2 credentials for Gmail and Tasks
3. Configure `.env` with OpenAI API key and Google credentials
4. Create virtual environment: `python3 -m venv venv && source venv/bin/activate`
5. Install dependencies: `pip install -r requirements.txt`

## Key Documentation

- `docs/agentic_email_organizer_spec.md` - Full specification with architecture diagrams and project plan
- `docs/development_log.md` - Development journal for blog post content

## Development Log

Maintain `docs/development_log.md` as a running journal of development sessions. At the end of each session or when significant progress is made, append a summary including:

- Date and session goals
- What was implemented or changed
- Key decisions and rationale
- Current status and next steps
- Any blockers or issues encountered

This log will be used for a blog post about the development journey.
