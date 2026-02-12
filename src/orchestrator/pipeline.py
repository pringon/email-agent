"""EmailAgentOrchestrator - connects modules into a single pipeline run."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from src.analyzer import AnalysisResult, EmailAnalyzer
from src.comments import CommentInterpreter
from src.completion import CompletionChecker
from src.fetcher import Email, EmailFetcher
from src.tasks import TaskManager

from .models import PipelineResult, StepResult

logger = logging.getLogger(__name__)


class EmailAgentOrchestrator:
    """Orchestrates the email-to-task pipeline.

    Connects EmailFetcher, EmailAnalyzer, and TaskManager into a single
    run with per-step error isolation and structured results.

    Example:
        result = EmailAgentOrchestrator().run()
        print(f"Success: {result.success}")
    """

    def __init__(
        self,
        fetcher: Optional[EmailFetcher] = None,
        analyzer: Optional[EmailAnalyzer] = None,
        task_manager: Optional[TaskManager] = None,
        completion_checker: Optional[CompletionChecker] = None,
        comment_interpreter: Optional[CommentInterpreter] = None,
        max_emails: int = 50,
    ):
        self._fetcher = fetcher
        self._analyzer = analyzer
        self._task_manager = task_manager
        self._completion_checker = completion_checker
        self._comment_interpreter = comment_interpreter
        self._max_emails = max_emails

    def _get_fetcher(self) -> EmailFetcher:
        if self._fetcher is None:
            self._fetcher = EmailFetcher()
        return self._fetcher

    def _get_analyzer(self) -> EmailAnalyzer:
        if self._analyzer is None:
            self._analyzer = EmailAnalyzer()
        return self._analyzer

    def _get_task_manager(self) -> TaskManager:
        if self._task_manager is None:
            self._task_manager = TaskManager()
        return self._task_manager

    def _get_completion_checker(self) -> CompletionChecker:
        if self._completion_checker is None:
            self._completion_checker = CompletionChecker()
        return self._completion_checker

    def _get_comment_interpreter(self) -> CommentInterpreter:
        if self._comment_interpreter is None:
            self._comment_interpreter = CommentInterpreter()
        return self._comment_interpreter

    @staticmethod
    def _skip_step(name: str) -> StepResult:
        """Record a step as skipped due to a prior failure."""
        return StepResult(
            name=name,
            success=False,
            duration_seconds=0.0,
            details={},
            skipped=True,
        )

    def _run_step(self, name: str, fn: callable) -> StepResult:
        """Run a pipeline step with timing and error isolation."""
        start = time.monotonic()
        try:
            details = fn()
            duration = time.monotonic() - start
            return StepResult(
                name=name,
                success=True,
                duration_seconds=round(duration, 2),
                details=details,
            )
        except Exception as e:
            duration = time.monotonic() - start
            logger.exception("Step '%s' failed", name)
            return StepResult(
                name=name,
                success=False,
                duration_seconds=round(duration, 2),
                details={},
                error=str(e),
            )

    def run(self) -> PipelineResult:
        """Execute the full pipeline.

        Steps:
            1. Fetch unread emails
            2. Analyze each email for tasks
            3. Create tasks (with dedup)

        Returns:
            PipelineResult with per-step metrics.
        """
        result = PipelineResult(started_at=datetime.now(timezone.utc))

        # Shared state between steps
        emails: list[Email] = []
        analyses: list[AnalysisResult] = []

        # Step 1: Fetch
        def fetch_step() -> dict:
            nonlocal emails
            fetcher = self._get_fetcher()
            emails = list(fetcher.fetch_unread(max_results=self._max_emails))
            logger.info("Fetched %d unread emails", len(emails))
            return {"emails_fetched": len(emails)}

        fetch_result = self._run_step("fetch", fetch_step)
        result.steps.append(fetch_result)

        # Step 2: Analyze (depends on fetch)
        if not fetch_result.success:
            result.steps.append(self._skip_step("analyze"))
            result.steps.append(self._skip_step("create_tasks"))
            result.finished_at = datetime.now(timezone.utc)
            return result

        def analyze_step() -> dict:
            nonlocal analyses
            if not emails:
                return {"emails_analyzed": 0, "tasks_found": 0, "errors": 0}

            analyzer = self._get_analyzer()
            errors = 0
            for email in emails:
                try:
                    analysis = analyzer.analyze(email)
                    analyses.append(analysis)
                except Exception:
                    errors += 1
                    logger.exception(
                        "Failed to analyze email %s (%s)",
                        email.id,
                        email.subject,
                    )

            total_tasks = sum(len(a.tasks) for a in analyses)
            logger.info(
                "Analyzed %d emails, found %d tasks (%d errors)",
                len(analyses),
                total_tasks,
                errors,
            )
            return {
                "emails_analyzed": len(analyses),
                "tasks_found": total_tasks,
                "errors": errors,
            }

        analyze_result = self._run_step("analyze", analyze_step)
        result.steps.append(analyze_result)

        # Step 3: Create tasks (depends on analyze)
        if not analyze_result.success:
            result.steps.append(self._skip_step("create_tasks"))
            result.finished_at = datetime.now(timezone.utc)
            return result

        def create_tasks_step() -> dict:
            if not analyses:
                return {"tasks_created": 0, "duplicates_skipped": 0}

            tm = self._get_task_manager()
            created = 0
            skipped = 0

            for analysis in analyses:
                for task in analysis.tasks:
                    existing = tm.find_tasks_by_email_id(task.source_email_id)
                    if existing:
                        skipped += 1
                        logger.debug(
                            "Skipping duplicate task for email %s",
                            task.source_email_id,
                        )
                        continue

                    tm.create_from_extracted_task(task)
                    created += 1

            logger.info(
                "Created %d tasks (%d duplicates skipped)", created, skipped
            )
            return {"tasks_created": created, "duplicates_skipped": skipped}

        result.steps.append(self._run_step("create_tasks", create_tasks_step))

        result.finished_at = datetime.now(timezone.utc)
        return result

    def run_completion_check(self) -> PipelineResult:
        """Check Sent Mail for replies and complete matching tasks.

        Returns:
            PipelineResult with a single check_completions step.
        """
        result = PipelineResult(started_at=datetime.now(timezone.utc))

        def check_completions_step() -> dict:
            checker = self._get_completion_checker()
            completion = checker.check_for_completions()
            logger.info(
                "Scanned %d sent emails, matched %d threads, completed %d tasks",
                completion.sent_emails_scanned,
                completion.threads_matched,
                completion.total_completed,
            )
            details = {
                "sent_emails_scanned": completion.sent_emails_scanned,
                "threads_matched": completion.threads_matched,
                "tasks_completed": completion.total_completed,
            }
            if completion.errors:
                details["errors"] = completion.errors
            return details

        result.steps.append(
            self._run_step("check_completions", check_completions_step)
        )

        result.finished_at = datetime.now(timezone.utc)
        return result

    def run_comment_processing(self) -> PipelineResult:
        """Scan tasks for @commands in notes and execute them.

        Returns:
            PipelineResult with a single process_comments step.
        """
        result = PipelineResult(started_at=datetime.now(timezone.utc))

        def process_comments_step() -> dict:
            interpreter = self._get_comment_interpreter()
            processing = interpreter.process_pending_tasks()
            logger.info(
                "Scanned %d tasks, found %d commands, executed %d",
                processing.tasks_scanned,
                processing.commands_found,
                processing.commands_executed,
            )
            details = {
                "tasks_scanned": processing.tasks_scanned,
                "commands_found": processing.commands_found,
                "commands_executed": processing.commands_executed,
            }
            if processing.errors:
                details["errors"] = processing.errors
            return details

        result.steps.append(
            self._run_step("process_comments", process_comments_step)
        )

        result.finished_at = datetime.now(timezone.utc)
        return result
