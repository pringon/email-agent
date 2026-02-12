# User Guide

## What Is the Agentic Email Organizer?

The Agentic Email Organizer is your personal email assistant. It reads your Gmail inbox, identifies action items buried in your messages, and turns them into tasks in Google Tasks — automatically, on a recurring schedule.

Instead of scanning through dozens of emails to figure out what needs doing, you get a clean task list and a daily summary delivered to your inbox.

## Features

### Automatic Task Extraction

Every time the agent runs, it reads your unread emails and uses AI to identify actionable items. For each task it finds, it captures:

- A clear, actionable **title** (e.g., "Review budget proposal", "Schedule team meeting")
- A **description** with context from the email
- A **due date**, if one was mentioned in the message
- A **priority level** — urgent, high, medium, or low — based on the language and deadlines in the email

Tasks appear directly in your Google Tasks, ready to work through.

### Smart Prioritization

The agent assesses priority based on cues in the email:

- **Urgent** — words like "ASAP", "immediately", or same-day deadlines
- **High** — near-term deadlines, important stakeholders, or blocking issues
- **Medium** — standard requests with reasonable timelines
- **Low** — FYI items, optional follow-ups, or messages with no deadline

### Auto-Completion on Reply

When you reply to an email that generated tasks, the agent detects your reply and automatically marks those tasks as complete. No need to manually close them — just respond to the email as you normally would, and the agent takes care of the rest.

### Daily Digest

Once a day, you receive a digest email summarizing all your pending tasks, organized by urgency:

- **Overdue** — tasks past their due date
- **Due Today** — tasks that need attention now
- **Due This Week** — tasks coming up in the next seven days
- **Due Later** — tasks with distant deadlines
- **No Due Date** — tasks without a specific deadline

The digest gives you a quick snapshot of where things stand without needing to open Google Tasks.

### No Duplicates

If the same email is processed more than once, the agent recognizes it and skips creating duplicate tasks. Your task list stays clean.

### Runs in the Background

Once set up, the agent runs automatically on a schedule:

- **Every 2 hours** — scans for new emails and creates tasks
- **Every 2 hours** — checks your Sent Mail and completes tasks you've replied to
- **Once daily (7:00 AM UTC)** — sends the task digest to your inbox

You don't need to do anything — it works quietly in the background.

## What to Expect

### Which Emails Create Tasks?

Not every email results in a task. The agent focuses on messages that contain clear action items — requests, deadlines, follow-ups, or anything requiring your attention. Newsletters, automated notifications, and purely informational emails are analyzed but typically produce no tasks.

### Where Do Tasks Appear?

All tasks are created in a Google Tasks list called **"Email Tasks"**. If this list doesn't exist yet, the agent creates it automatically on the first run.

### Task Notes

Each task includes notes with context from the original email. At the bottom of the notes, you'll see a metadata section that links the task back to its source email thread. This is what allows the auto-completion feature to work — avoid removing it.

## FAQ

**Can I control how many emails are processed at once?**
Yes. The agent processes up to 50 unread emails per run by default, but this limit is configurable.

**What happens if I delete a task manually?**
Nothing — the agent won't recreate it. Once a task has been created for an email, that email is marked as processed.

**What if the agent misses a task in an email?**
AI-based extraction is very good but not perfect. If an action item is vague or implicit, it may not be picked up. Important tasks that aren't captured can be created manually in Google Tasks as you normally would.

**Does the agent read all my emails?**
The agent only reads unread emails in your inbox. It does not access drafts, spam, trash, or emails in other labels. It also scans your Sent Mail folder (only recent messages) to detect replies for auto-completion.

**Is my email data stored anywhere?**
No. Emails are analyzed in real time and not stored. The only persistent data is the tasks created in your Google Tasks account and a small record of which emails have already been processed.
