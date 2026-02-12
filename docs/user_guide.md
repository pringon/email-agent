# User Guide

The Agentic Email Organizer is an email-to-task assistant. It reads your Gmail, extracts action items, and creates tasks in Google Tasks.

## Features

### Task Extraction

The agent reads your unread emails and uses AI to pull out actionable items. Each task includes:

- **Title** — a short, actionable description
- **Description** — context from the email
- **Due date** — if a deadline was mentioned
- **Priority** — urgent, high, medium, or low, based on the language in the email

Tasks are created in a Google Tasks list called **"Email Tasks"**.

### Auto-Completion

When you reply to an email that generated tasks, the agent picks up the reply and marks those tasks as complete automatically.

### Daily Digest

A daily email summarizing your pending tasks, grouped into sections:

- **Overdue**
- **Due Today**
- **Due This Week**
- **Due Later**
- **No Due Date**

### Deduplication

Processing the same email twice won't create duplicate tasks.

### Schedule

The agent runs automatically in the background:

- **Every 2 hours** — processes new emails and creates tasks
- **Every 2 hours** — checks Sent Mail and completes replied-to tasks
- **Daily at 7:00 AM UTC** — sends the digest email

## Task Commands

You can control tasks by adding commands directly in the task notes inside Google Tasks. Write one command per line using the `@command` syntax. Commands are case-insensitive and are removed from the notes after they run.

### @priority

Change a task's priority level.

```
@priority high
```

Valid levels: `low`, `medium`, `high`, `urgent`.

### @due

Set an absolute due date.

```
@due 2026-03-15
```

Date must be in `YYYY-MM-DD` format.

### @snooze

Push the due date forward by a relative amount.

```
@snooze 3 days
@snooze 2 weeks
```

Valid units: `day`/`days`, `week`/`weeks`. If the task has no due date, it snoozes from today.

### @ignore

Dismiss a task by marking it as complete without deleting it.

```
@ignore
```

### @delete

Permanently remove a task from Google Tasks.

```
@delete
```

### @note

Append text to the task notes.

```
@note Check with Sarah before submitting
```

## Task Notes

Each task has a metadata block at the bottom of its notes that links it back to the original email thread:

```
---email-agent-metadata---
email_id: 18e1a2b3c4d5e6f7
thread_id: 18e1a2b3c4d5e6f7
```

This is used for auto-completion and deduplication. Don't remove it.

## FAQ

**Not every email creates a task.** The agent only extracts clear action items. Newsletters, notifications, and informational emails typically produce no tasks.

**Deleting a task manually is fine.** The agent won't recreate it.

**The agent only reads unread inbox emails.** It does not access drafts, spam, trash, or other labels. It also reads recent Sent Mail to detect replies.

**Email content is not stored.** The only persistent data is the tasks in Google Tasks and a record of which emails have been processed.
