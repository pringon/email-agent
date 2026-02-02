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
+-------------------+       +-------------------+       +-----------------------+
|   Gmail Inbox     | <---> |   Gmail API       |       |                       |
|                   |       |                   |       |                       |
+-------------------+       +-------------------+       |                       |
                                  |                     |                       |
                                  v                     |                       |
                        +--------------------+          |                       |
                        |   Email Parser     |          |      Google Cloud     |
                        | (via OpenAI GPT)   |--------> |  (Gmail + Tasks APIs) |
                        +--------------------+          |                       |
                                  |                     |                       |
                                  v                     |                       |
                        +--------------------+          |                       |
                        |  Task Generator    | -------->+-----------------------+
                        +--------------------+                   ^
                                  |                               |
                                  v                               |
                     +-----------------------------+              |
                     | Task Completion Detector     | ------------+
                     | (Monitors Sent Mail Threads) |
                     +-----------------------------+
                                  |
                                  v
                   +-----------------------------+
                   | Daily Digest Generator      |
                   | (Email/Text Output)         |
                   +-----------------------------+
```

---

## 🧩 Modules & Components

### 1. `EmailFetcher`
- Uses Gmail API to fetch unread or recent messages.
- Maintains state (last message ID or timestamp) to avoid reprocessing.

### 2. `EmailAnalyzer`
- Sends email content to OpenAI GPT.
- Parses summary and action items in structured format (e.g., title, due date, priority).

### 3. `TaskManager`
- Interfaces with Google Tasks API.
- Creates tasks, updates statuses, and tracks metadata (e.g., email thread ID).

### 4. `CompletionChecker`
- Periodically scans Sent Mail for replies linked to task-related threads.
- Marks tasks complete when matching replies are detected.

### 5. `CommentInterpreter`
- Parses user comments (in task notes or terminal flags).
- Executes relevant action or updates task metadata.

### 6. `DigestReporter`
- Compiles daily summaries into:
  - 📧 Email
  - 📄 Plain text output (optional log file or CLI print)

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

| Layer                 | Technology                     |
|----------------------|---------------------------------|
| Scheduler            | `cron` or `APScheduler`         |
| Language             | Python 3.10+                    |
| Email Access         | Gmail API (`google-api-python-client`) |
| AI Integration       | OpenAI GPT-4 via API            |
| Task Management      | Google Tasks API                |
| Optional Storage     | Local cache / SQLite            |

---

## 📅 Project Plan

| Task ID | Description                                           | Priority | Depends On         | Milestone                |
|--------:|--------------------------------------------------------|----------|---------------------|--------------------------|
| T01     | Write initial documentation and setup instructions     | High     | -                   | Initialization           |
| T02     | Setup Google Cloud Project & enable Gmail + Tasks API | High     | T01                 | Initialization           |
| T03     | Implement Gmail auth (OAuth2) & email fetcher         | High     | T02                 | Core Agent               |
| T04     | Integrate OpenAI API & prompt for task extraction     | High     | T03                 | Core Agent               |
| T05     | Design JSON schema for extracted tasks                | Medium   | T04                 | Core Agent               |
| T06     | Implement Google Tasks API integration                | High     | T02, T05            | Task Management          |
| T07     | Link tasks to originating email threads               | High     | T05, T06            | Task Management          |
| T08     | Write logic to detect task completion via Sent Mail   | Medium   | T07                 | Task Management          |
| T09     | Build daily digest generator (email or text output)   | Medium   | T06, T07            | Reporting                |
| T10     | Implement comment parser for task instructions        | Medium   | T06                 | Agentic Features         |
| T11     | Add scheduler (cron job) to run agent periodically    | High     | T03, T06            | Deployment Ready         |
| T12     | Dockerize for GitHub deployment                       | Medium   | T11                 | Deployment Ready         |
| T13     | Final testing and QA pass                             | High     | T01–T12             | Finalization             |
| T14     | Revise and finalize documentation                     | High     | T13                 | Finalization             |

---

## ✅ Milestones Summary

- **Initialization:** T01–T02
- **Core Agent:** T03–T05
- **Task Management:** T06–T08
- **Reporting:** T09
- **Agentic Features:** T10
- **Deployment Ready:** T11–T12
- **Finalization:** T13–T14