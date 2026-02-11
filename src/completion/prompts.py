"""Prompt templates for LLM-based reply resolution."""

REPLY_RESOLVER_SYSTEM_PROMPT = """You analyze sent email replies to determine which pending tasks they address.

You will receive:
1. The text of a sent reply
2. A list of pending tasks associated with the email thread

For each task, decide whether the reply resolves, addresses, or completes that task.
A task is "resolved" if the reply:
- Directly responds to the request that created the task
- Provides the deliverable the task asked for
- Confirms completion of the action item
- Explicitly declines or defers the task (it's still "handled")

A task is NOT resolved if the reply doesn't mention or address it at all.

Respond in JSON format only."""


REPLY_RESOLVER_USER_PROMPT_TEMPLATE = """SUBJECT: {subject}

SENT REPLY:
---
{reply_body}
---

PENDING TASKS:
{tasks_list}

For each task, indicate whether this reply resolves it.
Respond with a JSON object in this exact format:
{{
    "resolved_tasks": [
        {{
            "task_id": "the task ID",
            "resolved": true or false,
            "reason": "Why this task is/isn't resolved by the reply"
        }}
    ]
}}"""
