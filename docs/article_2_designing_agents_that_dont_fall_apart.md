# Designing AI Agents That Don't Fall Apart: Architecture Lessons from an Email Organizer

I built an agent that reads my Gmail inbox, uses GPT-4 to extract tasks, manages them via Google Tasks, and auto-closes them when I reply. It runs every two hours via GitHub Actions.

It sounds straightforward. It wasn't.

The hard part of building LLM-powered systems isn't getting the LLM to do something useful — it's building everything around it so the system keeps working when the LLM does something unexpected. Here's what I learned.

## Inference Over Configuration

The first real architectural decision came when I needed to filter out newsletters and marketing emails. The obvious approach: maintain a blocklist of senders and domains. Bloomberg, Substack, promotional@whatever.com.

I went the other direction. I had the LLM classify each email into a type — personal, newsletter, marketing, automated, notification — and determine actionability from there.

Why? Because blocklists rot. Every new newsletter subscription means updating the list. Every marketing sender that changes their from-address slips through. And edge cases are brutal: is an email from "Bloomberg" a financial newsletter or a personal message from someone who works at Bloomberg?

The LLM handles all of this. It reads the email content — the unsubscribe links, the bulk formatting, the editorial tone — and classifies accordingly. No maintenance, no edge-case rules, works in any language.

But this introduced its own problem. I initially tied actionability to email type: personal = actionable, everything else = not. This seemed clean until a CI/CD failure notification came through. It's clearly `automated`, not `personal`. But it absolutely requires action — there's a broken build to fix.

The fix was decoupling email type from actionability entirely. The LLM now determines both independently:
- **Email type:** What kind of email is this? (automated)
- **Is actionable:** Does the recipient need to do something? (yes — fix the build)

This produces accurate classifications without prompt workarounds. An automated CI failure is `automated` AND `actionable`. A marketing presale offer is `marketing` AND `not actionable`. The two dimensions are orthogonal, and trying to collapse them into one was the mistake.

**Takeaway:** If you're building classification into an LLM system, resist the urge to derive downstream decisions from the classification label. Let the LLM determine each decision dimension independently. You'll avoid the contortion of making the label do double duty.

## Error Isolation Is Non-Negotiable

The agent pipeline looks like this:

```
Fetch emails → Analyze with LLM → Create tasks → Check completions → Send digest
```

When I first wired this up, a failure in any step killed the whole run. An OpenAI rate limit during analysis meant no tasks got created, no completions got checked, and no digest was sent.

The fix was wrapping every step in its own try/except:

```python
def _run_step(self, name, fn):
    try:
        details = fn()
        return StepResult(name=name, success=True, details=details)
    except Exception as e:
        logger.exception("Step '%s' failed", name)
        return StepResult(name=name, success=False, error=str(e))
```

But error isolation goes deeper than the pipeline level. Inside the analysis step, each email is analyzed independently. If parsing one email's LLM response fails, the others still get processed. Inside the completion checker, each thread is checked independently. One failed thread match doesn't stop the scan.

The pattern repeats at every level: **catch the error, record it, continue.** Each module returns a result object (`CompletionResult`, `ProcessingResult`, `DeliveryResult`) that carries both successes and errors. The caller decides what to do with them.

This isn't glamorous engineering. But for a system that runs unattended every two hours, it's the difference between "works reliably" and "silently stopped working three days ago because one email had malformed headers."

**Takeaway:** In any pipeline that calls external APIs (LLMs, email providers, task managers), design for partial failure from the start. The question isn't "will a step fail?" but "when a step fails, what keeps running?"

## Test LLM Behavior With Specimens, Not Mocks

This is probably the most transferable pattern from this project.

Unit tests mock the LLM. They verify that the code around the LLM works correctly — retry logic, response parsing, error handling. These are fast (400 tests in under a second) and reliable.

But mocked tests can't tell you whether your prompt actually works. For that, I built a specimen test suite.

Each `EmailSpecimen` is a real email (or realistic synthetic one) with expected classification outcomes:

```python
@dataclass
class EmailSpecimen:
    name: str           # "spotify_presale_promo"
    sender: str         # "Spotify"
    sender_email: str   # "no-reply@spotify.com"
    subject: str        # "Presale Access: Taylor Swift | The Eras Tour"
    body: str           # Full email body
    labels: list[str]   # ["CATEGORY_PROMOTIONS"]
    expect_tasks: bool  # False
    expected_email_type: EmailType  # MARKETING
```

The test sends this email through the real LLM and asserts on the result:

```bash
python -m pytest tests/test_analyzer_classification.py -v -s -k "spotify_presale_promo"
```

When I modified the prompt to better handle receipt emails, I added a new specimen for an iCloud billing receipt and ran it against the real API. When marketing CTAs from platforms like Spotify were getting through, I added specimens and iterated on the prompt until they were classified correctly.

The specimen suite now has 10+ entries covering marketing, newsletters, automated notifications, receipts, and genuinely actionable emails. Each prompt change gets a new specimen. Each specimen is a permanent regression test.

**Why this matters:** LLM behavior drifts. Model updates change outputs. Prompt modifications have unintended side effects. Mocks can't catch any of this. Specimens can.

**Takeaway:** Build a specimen suite early. Each real-world failure or edge case becomes a test entry. Run it against the real API (not in CI — it's slow and costs money — but before every prompt merge). This is the only reliable way to test LLM-based classification.

## Pluggable Adapters From Day One

Even though I only use OpenAI, the LLM integration goes through an abstract `LLMAdapter` interface:

```python
class LLMAdapter(ABC):
    @abstractmethod
    def complete(self, messages, json_mode=False) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...
```

`OpenAIAdapter` implements this. If I wanted to switch to Anthropic or a local model, I'd implement a new adapter and swap it in.

This might sound like over-engineering for a personal project. It's not. The real value is **testability**. Every module that uses the LLM accepts an optional adapter parameter. In tests, I pass in a `MagicMock(spec=LLMAdapter)` and control exactly what the "LLM" returns. No API calls, no flaky tests, no costs.

The same pattern applies to the state repository (how we track processed emails) and the authenticators (Gmail, Tasks). Injecting dependencies through constructor parameters with lazy defaults:

```python
def __init__(self, adapter: Optional[LLMAdapter] = None):
    self._adapter = adapter

def _get_adapter(self) -> LLMAdapter:
    if self._adapter is None:
        self._adapter = OpenAIAdapter()
    return self._adapter
```

Production code passes nothing and gets real implementations. Test code injects mocks. The module doesn't know or care.

**Takeaway:** Abstract your LLM calls behind an interface, even if you only have one provider. The testing benefit alone justifies it. The flexibility to swap providers is a bonus.

## Metadata Embedding Over Databases

The agent needs to know which tasks came from which emails. The obvious solution: a SQLite database mapping email IDs to task IDs.

Instead, I embedded the metadata directly in Google Tasks notes:

```
Fix the deployment script before Friday

---email-agent-metadata---
email_id: 18d5f2a3b4c6e7f8
thread_id: 18d5f2a3b4c6e7f0
```

Task lookup by thread or email ID scans the task list and parses the metadata section. It's not as fast as a database query, but for the scale of a personal email inbox, it's more than fast enough.

The wins:
- **No additional infrastructure.** No SQLite file to manage, no database migrations, no corruption recovery.
- **Single source of truth.** The task *is* the record. If a task exists, its metadata exists. No orphaned database rows.
- **Portable.** The agent can run from any machine with OAuth credentials. No state to sync.
- **Inspectable.** Open Google Tasks, look at the note, see the metadata. No need for a separate admin tool.

The tradeoff is that listing tasks by thread requires iterating through all tasks instead of a direct index lookup. For hundreds of tasks, this is negligible. For thousands, you might want a real database. Know your scale.

**Takeaway:** Before reaching for a database, ask if the metadata can live alongside the data it describes. For small-scale agents, embedding metadata in the platform you're already using (task notes, issue labels, file headers) eliminates an entire category of infrastructure.

## Safe Defaults for LLM Fallibility

LLMs are unreliable. Not in a "sometimes they're wrong" way — in a "they might return malformed JSON, hallucinate task IDs that don't exist, or classify a personal email as marketing" way.

Every LLM interaction in this project has a defensive default:

- **Unknown email type?** Default to `personal`. Rationale: it's worse to accidentally filter a real email than to let a newsletter through.
- **LLM can't determine if reply resolves a task?** Complete nothing. Rationale: it's worse to close a task the user hasn't addressed than to leave it open.
- **LLM returns task IDs not in the input list?** Discard them. Rationale: hallucinated IDs shouldn't trigger real actions.
- **Malformed task in LLM response?** Skip it and log a warning. Rationale: one bad task shouldn't prevent the other valid tasks from being created.
- **Retry only on JSON parse failures.** Don't retry authentication errors or rate limits — those won't fix themselves on the next attempt.

The common thread: **when in doubt, do the less destructive thing.** Don't complete tasks you're unsure about. Don't filter emails you're unsure about. Don't trust IDs you didn't generate.

This sounds obvious. But in practice, it's tempting to use the LLM output optimistically — it was right the last 50 times, so it's probably right now. The problem is that the 51st time, you've auto-closed a task the user hasn't actually addressed, and they miss a deadline.

**Takeaway:** For every LLM output, define what happens when it's wrong. The safe default is usually "do nothing" or "assume the most conservative interpretation." Build the happy path on top of the safe default, not the other way around.

## Prompt Engineering Is Iterative, Not Upfront

I didn't sit down and write the perfect classification prompt. I wrote a decent one, tested it with real emails, and refined it through failures.

The timeline:
1. **Initial prompt:** Classify emails, extract tasks. Worked for obvious cases.
2. **Newsletters slipping through:** Added email type classification with explicit rules.
3. **Receipts creating tasks:** Added rule: "Receipts and invoices are NOT actionable."
4. **CI failures being filtered:** Decoupled actionability from type (described above).
5. **Marketing CTAs from platforms:** Broadened marketing definition to include "platform engagement CTAs" like event suggestions and presale offers.

Each iteration followed the same pattern:
1. Discover a misclassification from real email data.
2. Add an `EmailSpecimen` test entry capturing the failing case.
3. Modify the prompt.
4. Run the specimen against the real LLM.
5. Verify it passes without breaking existing specimens.

This is basically test-driven development for prompts. The specimen suite is the test suite. The prompt is the implementation. You iterate until the tests pass.

One thing I've learned: **be specific in your prompt rules.** "Marketing emails are not actionable" is too vague — the LLM still thought a presale ticket offer was actionable because the user could "take action" (buy tickets). The fix was adding explicit examples: "Presale ticket offers, event suggestions from platforms, and limited-time deals are MARKETING, not personal."

**Takeaway:** Don't try to write the perfect prompt upfront. Write a good-enough prompt, build a specimen suite, and iterate. Each real-world failure makes the prompt better and the test suite more comprehensive. This is the LLM equivalent of test-driven development.

## The Pipeline Orchestration Pattern

The agent's orchestrator follows a pattern I'd recommend for any multi-step LLM system:

```python
@dataclass
class StepResult:
    name: str
    success: bool
    duration_seconds: float
    details: Optional[dict]
    error: Optional[str]

@dataclass
class PipelineResult:
    started_at: datetime
    finished_at: datetime
    steps: list[StepResult]
```

Each step is a named function. The orchestrator runs them in sequence, catches errors per-step, measures duration, and produces a structured result. The result tells you exactly what happened: which steps succeeded, which failed, how long each took, and what the details were.

This gives you observability for free. When the agent runs at 2 AM via GitHub Actions, you can look at the `PipelineResult` and see that Fetch took 2.3 seconds, Analyze processed 15 emails (2 errors), and CreateTasks added 8 new tasks. If something went wrong, the error is right there in the step result.

It also makes testing straightforward. Each step function is independently testable. The orchestrator itself is testable by injecting mock step functions. You can verify that a failed Fetch step causes subsequent steps to skip without hitting any real APIs.

**Takeaway:** Wrap your agent's workflow in a pipeline with named, measured, error-isolated steps. The structure costs almost nothing to implement and pays dividends in debugging, monitoring, and testing.

## What I'd Do Differently

Looking back, a few things I'd change:

**Start the specimen suite earlier.** I added it midway through the project when classification problems emerged. If I'd started it from the first prompt, I'd have caught issues sooner.

**Be more opinionated about test verbosity.** Claude Code generates thorough tests, which is good. But some test files grew to 1,000+ lines. I should have established a testing philosophy earlier — which patterns warrant exhaustive testing (serialization roundtrips? probably. every enum value? maybe not).

**Document the "why" in prompts.** My prompt file has rules like "receipts are NOT actionable," but doesn't explain why. When I come back to tweak the prompt in 6 months, I'll wish each rule had a one-line rationale.

## Closing Thoughts

Building LLM-powered agents is less about the LLM and more about everything around it. The LLM is the easy part — give it a prompt, get a response. The hard part is:

- What happens when the response is wrong?
- What happens when the API is down?
- How do you test that the prompt still works after a change?
- How do you keep the system reliable when it runs unattended?

The patterns in this article — error isolation, specimen testing, safe defaults, pluggable adapters, metadata embedding — aren't specific to email agents. They apply to any system where an LLM is making decisions that drive real actions.

The LLM is a powerful but unreliable component. Everything you build around it should assume that, plan for it, and degrade gracefully when it happens.

---

*This is part 2 of 2. Part 1 covers how I used Claude Code to ship this project 3x faster — the workflow patterns, CLAUDE.md feedback loops, and parallelization strategies that made it possible.*
