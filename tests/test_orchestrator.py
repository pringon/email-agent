"""Unit tests for the EmailAgentOrchestrator."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.analyzer import AnalysisResult, EmailType, ExtractedTask, Priority
from src.comments import ProcessingResult
from src.fetcher import Email
from src.orchestrator import EmailAgentOrchestrator, PipelineResult, StepResult
from src.completion import CompletionResult
from src.tasks import Task


def _make_email(id: str = "msg1", thread_id: str = "thread1") -> Email:
    return Email(
        id=id,
        thread_id=thread_id,
        subject="Test Subject",
        sender="Alice",
        sender_email="alice@example.com",
        recipient="bob@example.com",
        date=datetime(2025, 1, 1, 12, 0),
        body="Please review the attached document by Friday.",
    )


def _make_analysis(email: Email) -> AnalysisResult:
    return AnalysisResult(
        email_id=email.id,
        thread_id=email.thread_id,
        summary="Review request for document",
        tasks=[
            ExtractedTask(
                title="Review document",
                description="Review the attached document",
                priority=Priority.MEDIUM,
                source_email_id=email.id,
                source_thread_id=email.thread_id,
                due_date=date(2025, 1, 3),
            )
        ],
    )


class TestStepResult:
    def test_successful_step(self):
        step = StepResult(
            name="fetch",
            success=True,
            duration_seconds=1.5,
            details={"emails_fetched": 3},
        )
        assert step.success is True
        assert step.error is None

    def test_failed_step(self):
        step = StepResult(
            name="fetch",
            success=False,
            duration_seconds=0.1,
            details={},
            error="Connection refused",
        )
        assert step.success is False
        assert step.error == "Connection refused"


class TestPipelineResult:
    def test_success_when_all_steps_pass(self):
        result = PipelineResult(started_at=datetime.now())
        result.steps = [
            StepResult(name="fetch", success=True, duration_seconds=1.0, details={}),
            StepResult(name="analyze", success=True, duration_seconds=2.0, details={}),
        ]
        assert result.success is True

    def test_failure_when_any_step_fails(self):
        result = PipelineResult(started_at=datetime.now())
        result.steps = [
            StepResult(name="fetch", success=True, duration_seconds=1.0, details={}),
            StepResult(
                name="analyze",
                success=False,
                duration_seconds=0.1,
                details={},
                error="LLM error",
            ),
        ]
        assert result.success is False

    def test_success_with_no_steps(self):
        result = PipelineResult(started_at=datetime.now())
        assert result.success is True


class TestEmailAgentOrchestrator:
    def _make_orchestrator(self, fetcher=None, analyzer=None, task_manager=None):
        return EmailAgentOrchestrator(
            fetcher=fetcher or MagicMock(),
            analyzer=analyzer or MagicMock(),
            task_manager=task_manager or MagicMock(),
        )

    def test_full_pipeline_success(self):
        email = _make_email()
        analysis = _make_analysis(email)

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email]

        analyzer = MagicMock()
        analyzer.analyze.return_value = analysis

        task_manager = MagicMock()
        task_manager.find_tasks_by_email_id.return_value = []
        task_manager.create_from_extracted_task.return_value = Task(
            title="Review document", id="task1"
        )

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is True
        assert len(result.steps) == 3
        assert result.steps[0].name == "fetch"
        assert result.steps[0].details["emails_fetched"] == 1
        assert result.steps[1].name == "analyze"
        assert result.steps[1].details["emails_analyzed"] == 1
        assert result.steps[1].details["tasks_found"] == 1
        assert result.steps[2].name == "create_tasks"
        assert result.steps[2].details["tasks_created"] == 1
        assert result.steps[2].details["duplicates_skipped"] == 0
        assert result.steps[2].details["newsletters_filtered"] == 0
        assert result.finished_at is not None

    def test_no_emails_returns_success(self):
        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = []

        orchestrator = self._make_orchestrator(fetcher=fetcher)
        result = orchestrator.run()

        assert result.success is True
        assert result.steps[0].details["emails_fetched"] == 0
        assert result.steps[1].details["emails_analyzed"] == 0
        assert result.steps[2].details["tasks_created"] == 0
        assert result.steps[2].details["newsletters_filtered"] == 0

    def test_fetch_failure_skips_later_steps(self):
        fetcher = MagicMock()
        fetcher.fetch_unread.side_effect = RuntimeError("Gmail API down")

        orchestrator = self._make_orchestrator(fetcher=fetcher)
        result = orchestrator.run()

        assert result.success is False
        assert result.steps[0].success is False
        assert result.steps[0].error == "Gmail API down"
        # Dependent steps are skipped
        assert result.steps[1].skipped is True
        assert result.steps[2].skipped is True

    def test_analyze_failure_for_single_email_is_isolated(self):
        email1 = _make_email(id="msg1")
        email2 = _make_email(id="msg2")
        analysis2 = _make_analysis(email2)

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email1, email2]

        analyzer = MagicMock()
        analyzer.analyze.side_effect = [RuntimeError("LLM timeout"), analysis2]

        task_manager = MagicMock()
        task_manager.find_tasks_by_email_id.return_value = []
        task_manager.create_from_extracted_task.return_value = Task(
            title="Review document", id="task1"
        )

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is True
        assert result.steps[1].details["emails_analyzed"] == 1
        assert result.steps[1].details["errors"] == 1
        assert result.steps[2].details["tasks_created"] == 1

    def test_duplicate_tasks_are_skipped(self):
        email = _make_email()
        analysis = _make_analysis(email)

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email]

        analyzer = MagicMock()
        analyzer.analyze.return_value = analysis

        task_manager = MagicMock()
        task_manager.find_tasks_by_email_id.return_value = [
            Task(title="Existing task", id="existing1")
        ]

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is True
        assert result.steps[2].details["tasks_created"] == 0
        assert result.steps[2].details["duplicates_skipped"] == 1
        task_manager.create_from_extracted_task.assert_not_called()

    def test_max_emails_passed_to_fetcher(self):
        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = []

        orchestrator = EmailAgentOrchestrator(
            fetcher=fetcher,
            analyzer=MagicMock(),
            task_manager=MagicMock(),
            max_emails=10,
        )
        orchestrator.run()

        fetcher.fetch_unread.assert_called_once_with(max_results=10)

    def test_multiple_tasks_from_multiple_emails(self):
        email1 = _make_email(id="msg1", thread_id="t1")
        email2 = _make_email(id="msg2", thread_id="t2")

        analysis1 = AnalysisResult(
            email_id="msg1",
            thread_id="t1",
            summary="Two tasks",
            tasks=[
                ExtractedTask(
                    title="Task A",
                    description="",
                    priority=Priority.HIGH,
                    source_email_id="msg1",
                    source_thread_id="t1",
                ),
                ExtractedTask(
                    title="Task B",
                    description="",
                    priority=Priority.LOW,
                    source_email_id="msg1",
                    source_thread_id="t1",
                ),
            ],
        )
        analysis2 = AnalysisResult(
            email_id="msg2",
            thread_id="t2",
            summary="One task",
            tasks=[
                ExtractedTask(
                    title="Task C",
                    description="",
                    priority=Priority.MEDIUM,
                    source_email_id="msg2",
                    source_thread_id="t2",
                ),
            ],
        )

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email1, email2]

        analyzer = MagicMock()
        analyzer.analyze.side_effect = [analysis1, analysis2]

        task_manager = MagicMock()
        task_manager.find_tasks_by_email_id.return_value = []
        task_manager.create_from_extracted_task.return_value = Task(
            title="t", id="tid"
        )

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.steps[1].details["tasks_found"] == 3
        assert result.steps[2].details["tasks_created"] == 3

    def test_create_tasks_failure_is_isolated(self):
        email = _make_email()
        analysis = _make_analysis(email)

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email]

        analyzer = MagicMock()
        analyzer.analyze.return_value = analysis

        task_manager = MagicMock()
        task_manager.find_tasks_by_email_id.side_effect = RuntimeError("API error")

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is False
        assert result.steps[0].success is True
        assert result.steps[1].success is True
        assert result.steps[2].success is False
        assert "API error" in result.steps[2].error

    def test_newsletter_emails_are_filtered(self):
        """Test that newsletter emails don't produce tasks."""
        email = _make_email()
        newsletter_analysis = AnalysisResult(
            email_id=email.id,
            thread_id=email.thread_id,
            summary="Bloomberg daily market roundup",
            email_type=EmailType.NEWSLETTER,
            tasks=[],
            sender_name="Bloomberg",
        )

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email]

        analyzer = MagicMock()
        analyzer.analyze.return_value = newsletter_analysis

        task_manager = MagicMock()

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is True
        assert result.steps[2].details["newsletters_filtered"] == 1
        assert result.steps[2].details["tasks_created"] == 0
        task_manager.create_from_extracted_task.assert_not_called()

    def test_mixed_personal_and_newsletter_emails(self):
        """Test pipeline with both personal and newsletter emails."""
        email1 = _make_email(id="msg1", thread_id="t1")
        email2 = _make_email(id="msg2", thread_id="t2")

        personal_analysis = AnalysisResult(
            email_id="msg1",
            thread_id="t1",
            summary="Please review this document",
            email_type=EmailType.PERSONAL,
            tasks=[
                ExtractedTask(
                    title="Review document",
                    description="Review the attached document",
                    priority=Priority.MEDIUM,
                    source_email_id="msg1",
                    source_thread_id="t1",
                ),
            ],
        )
        newsletter_analysis = AnalysisResult(
            email_id="msg2",
            thread_id="t2",
            summary="Weekly tech newsletter",
            email_type=EmailType.NEWSLETTER,
            tasks=[],
            sender_name="TechDigest",
        )

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email1, email2]

        analyzer = MagicMock()
        analyzer.analyze.side_effect = [personal_analysis, newsletter_analysis]

        task_manager = MagicMock()
        task_manager.find_tasks_by_email_id.return_value = []
        task_manager.create_from_extracted_task.return_value = Task(
            title="Review document", id="task1"
        )

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is True
        assert result.steps[2].details["tasks_created"] == 1
        assert result.steps[2].details["newsletters_filtered"] == 1
        assert task_manager.create_from_extracted_task.call_count == 1

    def test_marketing_emails_are_filtered(self):
        """Test that marketing emails are also filtered."""
        email = _make_email()
        marketing_analysis = AnalysisResult(
            email_id=email.id,
            thread_id=email.thread_id,
            summary="50% off sale",
            email_type=EmailType.MARKETING,
            tasks=[],
            sender_name="Store",
        )

        fetcher = MagicMock()
        fetcher.fetch_unread.return_value = [email]

        analyzer = MagicMock()
        analyzer.analyze.return_value = marketing_analysis

        task_manager = MagicMock()

        orchestrator = self._make_orchestrator(fetcher, analyzer, task_manager)
        result = orchestrator.run()

        assert result.success is True
        assert result.steps[2].details["newsletters_filtered"] == 1
        assert result.steps[2].details["tasks_created"] == 0

    def test_lazy_init_creates_default_instances(self):
        """Test that None parameters trigger lazy initialization."""
        orchestrator = EmailAgentOrchestrator()

        with patch("src.orchestrator.pipeline.EmailFetcher") as mock_fetcher_cls:
            mock_fetcher_cls.return_value = MagicMock()
            fetcher = orchestrator._get_fetcher()
            mock_fetcher_cls.assert_called_once()

        with patch("src.orchestrator.pipeline.EmailAnalyzer") as mock_analyzer_cls:
            mock_analyzer_cls.return_value = MagicMock()
            analyzer = orchestrator._get_analyzer()
            mock_analyzer_cls.assert_called_once()

        with patch("src.orchestrator.pipeline.TaskManager") as mock_tm_cls:
            mock_tm_cls.return_value = MagicMock()
            tm = orchestrator._get_task_manager()
            mock_tm_cls.assert_called_once()

        with patch(
            "src.orchestrator.pipeline.CompletionChecker"
        ) as mock_checker_cls, patch(
            "src.orchestrator.pipeline.ReplyResolver"
        ) as mock_resolver_cls:
            mock_checker_cls.return_value = MagicMock()
            mock_resolver_cls.return_value = MagicMock()
            checker = orchestrator._get_completion_checker()
            mock_checker_cls.assert_called_once()
            # ReplyResolver should be created and passed to CompletionChecker
            mock_resolver_cls.assert_called_once()
            call_kwargs = mock_checker_cls.call_args.kwargs
            assert "reply_resolver" in call_kwargs


class TestReplyResolverWiring:
    """Tests for ReplyResolver integration in the orchestrator."""

    def test_completion_checker_gets_reply_resolver(self):
        """Test that _get_completion_checker passes a ReplyResolver."""
        orchestrator = EmailAgentOrchestrator()

        with patch(
            "src.orchestrator.pipeline.CompletionChecker"
        ) as mock_checker_cls, patch(
            "src.orchestrator.pipeline.ReplyResolver"
        ) as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver_cls.return_value = mock_resolver
            mock_checker_cls.return_value = MagicMock()

            orchestrator._get_completion_checker()

            mock_checker_cls.assert_called_once_with(
                reply_resolver=mock_resolver,
            )

    def test_injected_reply_resolver_is_used(self):
        """Test that an injected ReplyResolver is passed through."""
        mock_resolver = MagicMock()
        orchestrator = EmailAgentOrchestrator(reply_resolver=mock_resolver)

        with patch(
            "src.orchestrator.pipeline.CompletionChecker"
        ) as mock_checker_cls:
            mock_checker_cls.return_value = MagicMock()

            orchestrator._get_completion_checker()

            call_kwargs = mock_checker_cls.call_args.kwargs
            assert call_kwargs["reply_resolver"] is mock_resolver

    def test_injected_completion_checker_skips_resolver_creation(self):
        """Test that injecting a CompletionChecker skips ReplyResolver creation."""
        mock_checker = MagicMock()
        orchestrator = EmailAgentOrchestrator(completion_checker=mock_checker)

        result = orchestrator._get_completion_checker()

        assert result is mock_checker

        with patch(
            "src.orchestrator.pipeline.CommentInterpreter"
        ) as mock_interpreter_cls:
            mock_interpreter_cls.return_value = MagicMock()
            interpreter = orchestrator._get_comment_interpreter()
            mock_interpreter_cls.assert_called_once()


class TestCompletionCheck:
    def test_completion_check_success(self):
        completion_result = CompletionResult(
            sent_emails_scanned=5,
            threads_matched=2,
            tasks_completed=["task1", "task2"],
            thread_task_map={"t1": ["task1"], "t2": ["task2"]},
        )

        checker = MagicMock()
        checker.check_for_completions.return_value = completion_result

        orchestrator = EmailAgentOrchestrator(completion_checker=checker)
        result = orchestrator.run_completion_check()

        assert result.success is True
        assert len(result.steps) == 1
        assert result.steps[0].name == "check_completions"
        assert result.steps[0].details["sent_emails_scanned"] == 5
        assert result.steps[0].details["threads_matched"] == 2
        assert result.steps[0].details["tasks_completed"] == 2
        assert result.finished_at is not None

    def test_completion_check_no_matches(self):
        checker = MagicMock()
        checker.check_for_completions.return_value = CompletionResult()

        orchestrator = EmailAgentOrchestrator(completion_checker=checker)
        result = orchestrator.run_completion_check()

        assert result.success is True
        assert result.steps[0].details["sent_emails_scanned"] == 0
        assert result.steps[0].details["threads_matched"] == 0
        assert result.steps[0].details["tasks_completed"] == 0

    def test_completion_check_failure_captured(self):
        checker = MagicMock()
        checker.check_for_completions.side_effect = RuntimeError("Gmail unavailable")

        orchestrator = EmailAgentOrchestrator(completion_checker=checker)
        result = orchestrator.run_completion_check()

        assert result.success is False
        assert result.steps[0].success is False
        assert "Gmail unavailable" in result.steps[0].error

    def test_completion_check_with_errors_in_result(self):
        completion_result = CompletionResult(
            sent_emails_scanned=3,
            threads_matched=1,
            tasks_completed=["task1"],
            thread_task_map={"t1": ["task1"]},
            errors=["Failed to complete tasks for thread t2: API error"],
        )

        checker = MagicMock()
        checker.check_for_completions.return_value = completion_result

        orchestrator = EmailAgentOrchestrator(completion_checker=checker)
        result = orchestrator.run_completion_check()

        assert result.success is True
        assert result.steps[0].details["tasks_completed"] == 1
        assert "errors" in result.steps[0].details


class TestCommentProcessing:
    def test_comment_processing_success(self):
        processing_result = ProcessingResult(
            tasks_scanned=5,
            commands_found=3,
            commands_executed=3,
        )

        interpreter = MagicMock()
        interpreter.process_pending_tasks.return_value = processing_result

        orchestrator = EmailAgentOrchestrator(comment_interpreter=interpreter)
        result = orchestrator.run_comment_processing()

        assert result.success is True
        assert len(result.steps) == 1
        assert result.steps[0].name == "process_comments"
        assert result.steps[0].details["tasks_scanned"] == 5
        assert result.steps[0].details["commands_found"] == 3
        assert result.steps[0].details["commands_executed"] == 3
        assert result.finished_at is not None

    def test_comment_processing_no_commands(self):
        interpreter = MagicMock()
        interpreter.process_pending_tasks.return_value = ProcessingResult(
            tasks_scanned=3,
        )

        orchestrator = EmailAgentOrchestrator(comment_interpreter=interpreter)
        result = orchestrator.run_comment_processing()

        assert result.success is True
        assert result.steps[0].details["tasks_scanned"] == 3
        assert result.steps[0].details["commands_found"] == 0
        assert result.steps[0].details["commands_executed"] == 0

    def test_comment_processing_failure_captured(self):
        interpreter = MagicMock()
        interpreter.process_pending_tasks.side_effect = RuntimeError(
            "Tasks API unavailable"
        )

        orchestrator = EmailAgentOrchestrator(comment_interpreter=interpreter)
        result = orchestrator.run_comment_processing()

        assert result.success is False
        assert result.steps[0].success is False
        assert "Tasks API unavailable" in result.steps[0].error

    def test_comment_processing_with_errors_in_result(self):
        processing_result = ProcessingResult(
            tasks_scanned=4,
            commands_found=2,
            commands_executed=1,
            errors=["Error processing task 'Buy milk' (t1): API error"],
        )

        interpreter = MagicMock()
        interpreter.process_pending_tasks.return_value = processing_result

        orchestrator = EmailAgentOrchestrator(comment_interpreter=interpreter)
        result = orchestrator.run_comment_processing()

        assert result.success is True
        assert result.steps[0].details["commands_executed"] == 1
        assert "errors" in result.steps[0].details


class TestRunAgentCLI:
    def test_main_returns_zero_on_success(self):
        with patch("run_agent.EmailAgentOrchestrator") as mock_cls:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.steps = []
            mock_cls.return_value.run.return_value = mock_result

            from run_agent import main

            with patch("sys.argv", ["run_agent.py"]):
                assert main() == 0

    def test_main_returns_one_on_failure(self):
        with patch("run_agent.EmailAgentOrchestrator") as mock_cls:
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.steps = []
            mock_cls.return_value.run.return_value = mock_result

            from run_agent import main

            with patch("sys.argv", ["run_agent.py"]):
                assert main() == 1

    def test_max_emails_argument(self):
        with patch("run_agent.EmailAgentOrchestrator") as mock_cls:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.steps = []
            mock_cls.return_value.run.return_value = mock_result

            from run_agent import main

            with patch("sys.argv", ["run_agent.py", "--max-emails", "10"]):
                main()

            mock_cls.assert_called_once_with(max_emails=10)

    def test_check_completions_flag(self):
        with patch("run_agent.EmailAgentOrchestrator") as mock_cls:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.steps = []
            mock_cls.return_value.run_completion_check.return_value = mock_result

            from run_agent import main

            with patch(
                "sys.argv", ["run_agent.py", "--check-completions"]
            ):
                assert main() == 0

            mock_cls.return_value.run_completion_check.assert_called_once()
            mock_cls.return_value.run.assert_not_called()

    def test_process_comments_flag(self):
        with patch("run_agent.EmailAgentOrchestrator") as mock_cls:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.steps = []
            mock_cls.return_value.run_comment_processing.return_value = mock_result

            from run_agent import main

            with patch(
                "sys.argv", ["run_agent.py", "--process-comments"]
            ):
                assert main() == 0

            mock_cls.return_value.run_comment_processing.assert_called_once()
            mock_cls.return_value.run.assert_not_called()
