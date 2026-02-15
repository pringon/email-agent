# How I Ship and Learn Faster with Claude Code: Lessons from Building an AI Agent

I built a fully functional email-to-task agent in 11 days. 113 commits, 24 merged pull requests, 6 modules, ~400 tests. It comes with a full CI/CD harness. Major architectural and tech stack decisions have been made by Claude under my supervision.

I didn't write most of the code by hand. Claude Code did. Even this article was co-authored together with Claude and Gemini. In this article, I want to emphasize my learnings about working effectively with an AI coding agent.

Here's what actually matters when you're trying to ship good quality code fast with Claude Code.

## Start With a Spec, Not Code

The single most impactful thing I did was spend the first session writing a specification document with Claude before touching any code. Not a vague outline — a real spec with architecture diagrams, module descriptions, a 15-task project plan with dependencies, and milestone definitions.

This models the process of writing a technical spec or RFC before taking on a software development project and allows the agent to be more independent while executing on the work. The spec becomes **shared context**. When I later told Claude to "pick up T06," it knew exactly what TaskManager was supposed to do, what modules it depended on, and what interfaces it needed to satisfy.

The spec wasn't a static document either. It was updated 11 times over the project's lifetime — when new requirements emerged (ReplyResolver wasn't in the original plan), when tasks were completed, and when we made architectural pivots. It became a living record of both what we planned and what actually happened.

If you're going to use Claude Code for anything beyond one-off scripts, write the spec first. Let Claude help you draft it. The ROI is enormous.

## CLAUDE.md and the Development Log: Your Agent's Growing Context

Every project has a `CLAUDE.md` file that Claude Code reads at the start of each session. I started mine with the basics: project overview, tech stack, architecture summary, how to run tests. Then I kept adding to it whenever Claude struggled or did something suboptimal.

In parallel, I maintained a `development_log.md` — a running journal of each session including goals, what was implemented, key decisions, and test results. This became a data source for me to compile these articles and report progress, and it allowed Claude to understand not just the current codebase but *why* things were built the way they were.

**Key examples of what went into CLAUDE.md:**
- **After reviewing a 1,200-line PR:** Added guidance to keep PRs between 500-800 lines
- **After Claude started implementing without checking the spec:** Added "Before implementing any feature, consult the spec to ensure alignment"
- **After realizing worktrees needed credentials copied:** Added step-by-step worktree setup instructions including copying `.env` and `config/`
- **After a prompt change broke classification:** Added a rule to always add an `EmailSpecimen` test entry when modifying classification prompts

The key insight: **CLAUDE.md is a feedback loop, not a configuration file.** Each correction happens once, then persists across every future session. It's like updating your onboarding wiki or oncall runbook with new learnings.

**Important disclaimer:** As models and agents get smarter, some of these patterns may become unnecessary. Additionally, the more you add to context, the less performant agents become. Some people recommend compacting or deleting your project CLAUDE.md every few months and rebuilding it based on the current agent's capabilities.

## Plan the Work, Then Trust the Execution

My workflow for each feature followed a consistent pattern:

1. Tell Claude to plan the task and outline the work.
2. Review the plan — does the approach make sense? Are the right files being touched?
3. If the plan is sensible, let Claude execute.
4. Review the PR, not every keystroke.

The planning step is critical. Without it, Claude might implement something that technically works but architecturally doesn't fit. With it, you catch misalignments before any code is written.

Once I approved a plan, I mostly stepped back. Claude would create the branch, implement the module, write tests, and open a PR. My review focused on:
- Do the tests encode the behavior I expect?
- Are there any architectural red flags?
- Does the approach match what we discussed?

I found that reviewing the PR output was more productive than watching Claude code in real-time. The PR is the artifact that matters.

## Parallelize Ruthlessly

Git worktrees changed the game. I could have Claude working on TaskManager in one worktree while I reviewed the EmailAnalyzer PR in another, and had a third branch open for a bug fix.

On peak days, I was running 3 development tasks simultaneously:

1. Claude implementing a feature in worktree A
2. Me reviewing a PR from worktree B
3. Claude fixing a bug or running tests in worktree C

The limiting factor wasn't Claude — it was my ability to context-switch between tasks. But even with moderate context-switching overhead, the throughput was dramatically higher than sequential development.

The practical setup:
```bash
# Create a worktree for a feature branch
git worktree add ../email-agent-completion -b feature/completion-checker origin/main

# Copy gitignored files the worktree needs
cp .env ../email-agent-completion/
cp -r config ../email-agent-completion/
```

Each worktree gets its own Claude Code session, its own branch, its own PR. The main repo stays clean.

Note: I never had to run any of these commands myself — I just asked Claude to do it and asked it to update CLAUDE.md if it struggled with anything.

## Review Tests More Than Code

This was a mindset shift for me, though not entirely new. I once watched a talk by [Walter Schulze](https://www.linkedin.com/in/awalterschulze/) where he explained how he dealt with his open-source project becoming widely popular with him being the only maintainer. People would submit pull requests to add features that he didn't have time to fully comprehend, so his response was to ask them for thorough tests. As long as the tests looked sensible and passed, he felt more confident merging the PRs.

I use the same approach with reviewing AI code. When Claude writes code, my instinct was to read every function and understand every implementation detail. But that doesn't scale when you're moving at 10+ commits per day.

What I learned: **if the tests correctly encode the expected behavior, the implementation matters less** — as long as the architecture is sensible or at least well encapsulated so I can refactor it later.

When Claude opened a PR for the DigestReporter (62 tests), I spent most of my review time on the tests:
- Does `test_categorize_tasks_overdue` actually create a task with a past due date and verify it lands in the "Overdue" section?
- Does `test_generate_and_send_email_failure_still_returns_text` verify that a Gmail API error doesn't prevent plain-text output?
- Are edge cases covered — empty task lists, singular vs. plural formatting, missing due dates?

If the tests match my expectations, the code behind them is probably fine. I wasn't nitpicking variable names or debating whether a helper function should be extracted, or ensuring the Python language works as expected. I was asking: "does this system behave the way I want it to?"

This isn't the same as *ignoring* the code. Architectural decisions, error handling patterns, and security concerns still need human review. But for the bulk of implementation logic, tests are the better review surface.

## The Verbose Test Problem

I want to flag something I haven't solved: Claude writes very verbose tests.

Each test module in this project has dozens to hundreds of tests. The CommentInterpreter alone has 80 unit tests. Many of them are valuable. Some feel like they're testing the same thing with minor variations.

For example, does the EmailAnalyzer really need separate tests for `test_extracted_task_to_dict`, `test_extracted_task_from_dict`, `test_extracted_task_roundtrip`, AND `test_extracted_task_defaults`? Maybe. They each verify something slightly different. But the test file is 1,182 lines long.

I've been allowing this because:
1. The tests do catch real bugs (the roundtrip test caught a serialization issue early).
2. Deleting tests feels risky — you might remove the one that catches a regression.
3. The time cost of writing verbose tests is near-zero when Claude is doing it.

But I wonder about the maintenance and review cost. When you refactor a model, you're now updating 15 tests instead of 5. When you add a field, every serialization test needs updating.

I don't have a clean answer here. My current heuristic: if a test is testing behavior (what the system does), keep it. If it's testing structure (what the code looks like), question it. If you have any thoughts, please contact me or comment down below. 😄

## What This All Amounts To

Here's the honest math. This project has 6 modules, each with its own models, exceptions, implementation, tests, and integration. Pre-Claude-Code, I'd estimate this would take most of a work-week to implement.

With Claude Code, it took 11 days. The first module (EmailFetcher) took 2 days. By the sixth module (CommentInterpreter), the patterns were so established that Claude could implement the full module — 80 tests and all — in a single session.

The acceleration isn't uniform. It's fastest when:
- The spec and architecture are clear (Claude can execute autonomously)
- The patterns are established (subsequent modules follow the template of earlier ones)
- The task is well-decomposed (small PRs with clear boundaries)

It's slowest when:
- You're making architectural decisions (those still need human judgment)
- You need alignment with stakeholders or need to pull information from data sources Claude does not have access to
- The LLM prompt needs tuning (iteration requires real-world testing, not just code)
- You're debugging flaky tests (Claude sometimes struggles with timing-sensitive issues)

The real multiplier isn't raw coding speed. It's the ability to work on multiple streams simultaneously, to have the tedious parts (test scaffolding, boilerplate, serialization) handled automatically, and to focus your own attention on the decisions that actually matter: architecture, behavior, and user experience.

---

*Part 2 will cover what I learned about building reliable LLM-powered systems — the architecture patterns, testing strategies, and design decisions that make AI agents work in practice.*
