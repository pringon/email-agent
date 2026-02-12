"""Unit tests for the CommentInterpreter module."""

import base64
from datetime import date, datetime, timedelta
from email import message_from_bytes
from unittest.mock import MagicMock, call

import pytest
from googleapiclient.errors import HttpError

from src.comments import (
    CommandResult,
    CommandType,
    CommentError,
    CommentExecutionError,
    CommentInterpreter,
    CommentParseError,
    ParsedCommand,
    ProcessingResult,
)
from src.tasks.models import Task, TaskStatus


# ==================== Model Tests ====================


class TestCommandType:
    """Tests for CommandType enum."""

    def test_command_type_values(self):
        """Verify all enum values."""
        assert CommandType.PRIORITY.value == "priority"
        assert CommandType.DUE.value == "due"
        assert CommandType.SNOOZE.value == "snooze"
        assert CommandType.IGNORE.value == "ignore"
        assert CommandType.DELETE.value == "delete"
        assert CommandType.NOTE.value == "note"
        assert CommandType.RESPOND.value == "respond"

    def test_command_type_count(self):
        """Verify expected number of command types."""
        assert len(CommandType) == 7


class TestParsedCommand:
    """Tests for ParsedCommand dataclass."""

    def test_create(self):
        """Test basic construction."""
        cmd = ParsedCommand(
            command_type=CommandType.PRIORITY,
            raw_text="@priority high",
            arguments="high",
        )
        assert cmd.command_type == CommandType.PRIORITY
        assert cmd.raw_text == "@priority high"
        assert cmd.arguments == "high"

    def test_default_arguments(self):
        """Test default empty arguments."""
        cmd = ParsedCommand(
            command_type=CommandType.IGNORE,
            raw_text="@ignore",
        )
        assert cmd.arguments == ""

    def test_to_dict(self):
        """Test serialization."""
        cmd = ParsedCommand(
            command_type=CommandType.DUE,
            raw_text="@due 2026-03-01",
            arguments="2026-03-01",
        )
        data = cmd.to_dict()
        assert data["command_type"] == "due"
        assert data["raw_text"] == "@due 2026-03-01"
        assert data["arguments"] == "2026-03-01"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "command_type": "snooze",
            "raw_text": "@snooze 3 days",
            "arguments": "3 days",
        }
        cmd = ParsedCommand.from_dict(data)
        assert cmd.command_type == CommandType.SNOOZE
        assert cmd.raw_text == "@snooze 3 days"
        assert cmd.arguments == "3 days"

    def test_roundtrip(self):
        """Test serialize/deserialize roundtrip."""
        original = ParsedCommand(
            command_type=CommandType.NOTE,
            raw_text="@note Check with Sarah",
            arguments="Check with Sarah",
        )
        restored = ParsedCommand.from_dict(original.to_dict())
        assert restored.command_type == original.command_type
        assert restored.raw_text == original.raw_text
        assert restored.arguments == original.arguments


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_create_success(self):
        """Test successful result construction."""
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority high", "high")
        result = CommandResult(
            task_id="task1",
            task_title="Review email",
            command=cmd,
            success=True,
            action_taken="Priority changed to high",
        )
        assert result.success is True
        assert result.action_taken == "Priority changed to high"
        assert result.error == ""

    def test_create_failure(self):
        """Test failure result construction."""
        cmd = ParsedCommand(CommandType.DUE, "@due invalid", "invalid")
        result = CommandResult(
            task_id="task1",
            task_title="Review email",
            command=cmd,
            success=False,
            error="Invalid date format",
        )
        assert result.success is False
        assert result.error == "Invalid date format"

    def test_to_dict(self):
        """Test serialization."""
        cmd = ParsedCommand(CommandType.IGNORE, "@ignore")
        result = CommandResult(
            task_id="t1",
            task_title="Test",
            command=cmd,
            success=True,
            action_taken="Ignored",
        )
        data = result.to_dict()
        assert data["task_id"] == "t1"
        assert data["command"]["command_type"] == "ignore"
        assert data["success"] is True

    def test_roundtrip(self):
        """Test serialize/deserialize roundtrip."""
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 2 weeks", "2 weeks")
        original = CommandResult(
            task_id="t1",
            task_title="Test",
            command=cmd,
            success=True,
            action_taken="Snoozed",
        )
        restored = CommandResult.from_dict(original.to_dict())
        assert restored.task_id == original.task_id
        assert restored.command.command_type == original.command.command_type
        assert restored.success == original.success


class TestProcessingResult:
    """Tests for ProcessingResult dataclass."""

    def test_create_default(self):
        """Test defaults."""
        result = ProcessingResult()
        assert result.tasks_scanned == 0
        assert result.commands_found == 0
        assert result.commands_executed == 0
        assert result.results == []
        assert result.errors == []

    def test_has_errors_false(self):
        """Test has_errors when no errors."""
        assert ProcessingResult().has_errors is False

    def test_has_errors_true(self):
        """Test has_errors with errors."""
        result = ProcessingResult()
        result.add_error("Something failed")
        assert result.has_errors is True

    def test_add_error(self):
        """Test adding errors."""
        result = ProcessingResult()
        result.add_error("Error 1")
        result.add_error("Error 2")
        assert len(result.errors) == 2
        assert result.errors[0] == "Error 1"

    def test_to_dict(self):
        """Test serialization."""
        result = ProcessingResult(
            tasks_scanned=5,
            commands_found=3,
            commands_executed=2,
        )
        data = result.to_dict()
        assert data["tasks_scanned"] == 5
        assert data["commands_found"] == 3
        assert data["commands_executed"] == 2

    def test_roundtrip(self):
        """Test serialize/deserialize roundtrip."""
        original = ProcessingResult(
            tasks_scanned=10,
            commands_found=4,
            commands_executed=3,
            errors=["One error"],
        )
        restored = ProcessingResult.from_dict(original.to_dict())
        assert restored.tasks_scanned == original.tasks_scanned
        assert restored.commands_found == original.commands_found
        assert restored.errors == original.errors


# ==================== Exception Tests ====================


class TestExceptions:
    """Tests for comment interpreter exceptions."""

    def test_comment_error_is_exception(self):
        """CommentError inherits from Exception."""
        assert issubclass(CommentError, Exception)

    def test_parse_error_inherits(self):
        """CommentParseError inherits from CommentError."""
        assert issubclass(CommentParseError, CommentError)

    def test_parse_error_attributes(self):
        """CommentParseError stores line and reason."""
        err = CommentParseError("@foobar", "Unknown command")
        assert err.line == "@foobar"
        assert err.reason == "Unknown command"

    def test_parse_error_message(self):
        """CommentParseError has human-readable message."""
        err = CommentParseError("@bad", "Invalid")
        assert "Failed to parse comment '@bad': Invalid" in str(err)

    def test_execution_error_inherits(self):
        """CommentExecutionError inherits from CommentError."""
        assert issubclass(CommentExecutionError, CommentError)

    def test_execution_error_attributes(self):
        """CommentExecutionError stores command_type, task_id, reason."""
        err = CommentExecutionError("priority", "task1", "Invalid value")
        assert err.command_type == "priority"
        assert err.task_id == "task1"
        assert err.reason == "Invalid value"

    def test_execution_error_message(self):
        """CommentExecutionError has human-readable message."""
        err = CommentExecutionError("due", "t1", "Bad date")
        assert "Failed to execute 'due' on task 't1': Bad date" in str(err)


# ==================== Parse Tests ====================


class TestParseCommands:
    """Tests for CommentInterpreter.parse_commands()."""

    @pytest.fixture
    def interpreter(self):
        """Create a CommentInterpreter (no TaskManager needed for parsing)."""
        return CommentInterpreter()

    def test_parse_single_command(self, interpreter):
        """Parse a single @priority command."""
        commands = interpreter.parse_commands("@priority high")
        assert len(commands) == 1
        assert commands[0].command_type == CommandType.PRIORITY
        assert commands[0].arguments == "high"

    def test_parse_multiple_commands(self, interpreter):
        """Parse multiple commands from notes."""
        notes = "@priority urgent\n@due 2026-03-01"
        commands = interpreter.parse_commands(notes)
        assert len(commands) == 2
        assert commands[0].command_type == CommandType.PRIORITY
        assert commands[1].command_type == CommandType.DUE

    def test_parse_no_commands(self, interpreter):
        """Regular notes without @ commands return empty list."""
        commands = interpreter.parse_commands("Just some regular notes here")
        assert commands == []

    def test_parse_empty_notes(self, interpreter):
        """Empty string returns empty list."""
        assert interpreter.parse_commands("") == []

    def test_parse_none_notes(self, interpreter):
        """None returns empty list."""
        assert interpreter.parse_commands(None) == []

    def test_parse_ignores_unrecognized(self, interpreter):
        """Unrecognized @commands are skipped."""
        notes = "@foobar something\n@priority low"
        commands = interpreter.parse_commands(notes)
        assert len(commands) == 1
        assert commands[0].command_type == CommandType.PRIORITY

    def test_parse_case_insensitive(self, interpreter):
        """Commands are case-insensitive."""
        commands = interpreter.parse_commands("@PRIORITY HIGH")
        assert len(commands) == 1
        assert commands[0].command_type == CommandType.PRIORITY
        assert commands[0].arguments == "HIGH"

    def test_parse_preserves_arguments(self, interpreter):
        """Arguments are preserved as-is."""
        commands = interpreter.parse_commands("@note Check with Sarah first")
        assert len(commands) == 1
        assert commands[0].arguments == "Check with Sarah first"

    def test_parse_command_no_arguments(self, interpreter):
        """Commands without arguments have empty string."""
        commands = interpreter.parse_commands("@ignore")
        assert len(commands) == 1
        assert commands[0].arguments == ""

    def test_parse_mixed_content(self, interpreter):
        """Notes with both commands and regular text."""
        notes = "Priority: medium\n\nSome context here\n@snooze 3 days\nMore notes\n@delete"
        commands = interpreter.parse_commands(notes)
        assert len(commands) == 2
        assert commands[0].command_type == CommandType.SNOOZE
        assert commands[1].command_type == CommandType.DELETE

    def test_parse_at_sign_mid_line_ignored(self, interpreter):
        """@ in the middle of a line is not treated as a command."""
        notes = "email me @priority high"
        commands = interpreter.parse_commands(notes)
        assert commands == []

    def test_parse_stores_raw_text(self, interpreter):
        """Raw text is the full original line."""
        commands = interpreter.parse_commands("@due 2026-05-01")
        assert commands[0].raw_text == "@due 2026-05-01"

    def test_parse_all_command_types(self, interpreter):
        """All seven command types are recognized."""
        notes = "\n".join([
            "@priority high",
            "@due 2026-03-01",
            "@snooze 3 days",
            "@ignore",
            "@delete",
            "@note hello",
            "@respond Got it, thanks!",
        ])
        commands = interpreter.parse_commands(notes)
        types = {c.command_type for c in commands}
        assert types == set(CommandType)

    def test_parse_respond_command(self, interpreter):
        """Parse a @respond command with full message."""
        commands = interpreter.parse_commands("@respond Thanks, I'll handle this")
        assert len(commands) == 1
        assert commands[0].command_type == CommandType.RESPOND
        assert commands[0].arguments == "Thanks, I'll handle this"

    def test_parse_respond_preserves_special_characters(self, interpreter):
        """Arguments with special characters are preserved."""
        commands = interpreter.parse_commands("@respond I'll be there @ 3pm, OK?")
        assert len(commands) == 1
        assert commands[0].arguments == "I'll be there @ 3pm, OK?"


class TestStripCommands:
    """Tests for CommentInterpreter.strip_commands()."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_removes_processed_commands(self, interpreter):
        """Command lines are removed from notes."""
        notes = "Some notes\n@priority high\nMore notes"
        commands = [
            ParsedCommand(CommandType.PRIORITY, "@priority high", "high")
        ]
        result = interpreter.strip_commands(notes, commands)
        assert "@priority" not in result
        assert "Some notes" in result
        assert "More notes" in result

    def test_preserves_non_command_lines(self, interpreter):
        """Non-command lines are preserved."""
        notes = "Line 1\n@ignore\nLine 2"
        commands = [ParsedCommand(CommandType.IGNORE, "@ignore")]
        result = interpreter.strip_commands(notes, commands)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_empty_after_removal(self, interpreter):
        """Empty result when all lines are commands."""
        notes = "@ignore"
        commands = [ParsedCommand(CommandType.IGNORE, "@ignore")]
        result = interpreter.strip_commands(notes, commands)
        assert result == ""

    def test_collapses_blank_lines(self, interpreter):
        """Multiple consecutive blank lines collapse to one."""
        notes = "Line 1\n\n@delete\n\nLine 2"
        commands = [ParsedCommand(CommandType.DELETE, "@delete")]
        result = interpreter.strip_commands(notes, commands)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_none_notes(self, interpreter):
        """None notes returns empty string."""
        result = interpreter.strip_commands(None, [])
        assert result == ""

    def test_no_commands_to_strip(self, interpreter):
        """No commands means notes returned as-is."""
        result = interpreter.strip_commands("Hello world", [])
        assert result == "Hello world"


# ==================== Command Execution Tests ====================


class TestExecutePriority:
    """Tests for @priority command execution."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_priority_high(self, interpreter):
        """Valid priority change to high."""
        task = Task(title="Test", id="t1", notes="Priority: low\n\nDo something")
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority high", "high")
        action = interpreter._execute_priority(task, cmd)
        assert "high" in action
        assert "Priority: high" in task.notes

    def test_priority_updates_existing_line(self, interpreter):
        """Updates the Priority: line in notes."""
        task = Task(title="Test", id="t1", notes="Priority: medium\n\nDetails")
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority urgent", "urgent")
        interpreter._execute_priority(task, cmd)
        assert "Priority: urgent" in task.notes
        assert "Priority: medium" not in task.notes
        assert "Details" in task.notes

    def test_priority_adds_when_missing(self, interpreter):
        """Adds Priority line when notes don't have one."""
        task = Task(title="Test", id="t1", notes="Just some notes")
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority high", "high")
        interpreter._execute_priority(task, cmd)
        assert task.notes.startswith("Priority: high")
        assert "Just some notes" in task.notes

    def test_priority_invalid_value(self, interpreter):
        """Invalid priority raises CommentExecutionError."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority extreme", "extreme")
        with pytest.raises(CommentExecutionError) as exc_info:
            interpreter._execute_priority(task, cmd)
        assert "Invalid priority" in str(exc_info.value)

    def test_priority_case_insensitive(self, interpreter):
        """Priority argument is case-insensitive."""
        task = Task(title="Test", id="t1", notes="Priority: low")
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority HIGH", "HIGH")
        interpreter._execute_priority(task, cmd)
        assert "Priority: high" in task.notes

    def test_priority_on_none_notes(self, interpreter):
        """Priority on task with no notes."""
        task = Task(title="Test", id="t1", notes=None)
        cmd = ParsedCommand(CommandType.PRIORITY, "@priority medium", "medium")
        interpreter._execute_priority(task, cmd)
        assert task.notes == "Priority: medium"


class TestExecuteDue:
    """Tests for @due command execution."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_due_valid_date(self, interpreter):
        """Sets due date from valid ISO date."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.DUE, "@due 2026-03-15", "2026-03-15")
        action = interpreter._execute_due(task, cmd)
        assert task.due == date(2026, 3, 15)
        assert "2026-03-15" in action

    def test_due_replaces_existing(self, interpreter):
        """Replaces an existing due date."""
        task = Task(title="Test", id="t1", due=date(2026, 2, 1))
        cmd = ParsedCommand(CommandType.DUE, "@due 2026-04-01", "2026-04-01")
        interpreter._execute_due(task, cmd)
        assert task.due == date(2026, 4, 1)

    def test_due_invalid_format(self, interpreter):
        """Invalid date format raises CommentExecutionError."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.DUE, "@due tomorrow", "tomorrow")
        with pytest.raises(CommentExecutionError) as exc_info:
            interpreter._execute_due(task, cmd)
        assert "Invalid date format" in str(exc_info.value)


class TestExecuteSnooze:
    """Tests for @snooze command execution."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_snooze_days_from_existing_due(self, interpreter):
        """Snooze adds days to existing due date."""
        task = Task(title="Test", id="t1", due=date(2026, 2, 10))
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 3 days", "3 days")
        interpreter._execute_snooze(task, cmd)
        assert task.due == date(2026, 2, 13)

    def test_snooze_days_no_due_date(self, interpreter):
        """Snooze from today when no existing due date."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 5 days", "5 days")
        interpreter._execute_snooze(task, cmd)
        expected = date.today() + timedelta(days=5)
        assert task.due == expected

    def test_snooze_weeks(self, interpreter):
        """Snooze by weeks."""
        task = Task(title="Test", id="t1", due=date(2026, 2, 10))
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 2 weeks", "2 weeks")
        interpreter._execute_snooze(task, cmd)
        assert task.due == date(2026, 2, 24)

    def test_snooze_singular_day(self, interpreter):
        """'day' (singular) works."""
        task = Task(title="Test", id="t1", due=date(2026, 2, 10))
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 1 day", "1 day")
        interpreter._execute_snooze(task, cmd)
        assert task.due == date(2026, 2, 11)

    def test_snooze_singular_week(self, interpreter):
        """'week' (singular) works."""
        task = Task(title="Test", id="t1", due=date(2026, 2, 10))
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 1 week", "1 week")
        interpreter._execute_snooze(task, cmd)
        assert task.due == date(2026, 2, 17)

    def test_snooze_invalid_format(self, interpreter):
        """Missing unit raises error."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 3", "3")
        with pytest.raises(CommentExecutionError) as exc_info:
            interpreter._execute_snooze(task, cmd)
        assert "Invalid snooze format" in str(exc_info.value)

    def test_snooze_invalid_unit(self, interpreter):
        """Invalid unit raises error."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze 3 months", "3 months")
        with pytest.raises(CommentExecutionError) as exc_info:
            interpreter._execute_snooze(task, cmd)
        assert "Invalid time unit" in str(exc_info.value)

    def test_snooze_non_numeric(self, interpreter):
        """Non-numeric amount raises error."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.SNOOZE, "@snooze three days", "three days")
        with pytest.raises(CommentExecutionError) as exc_info:
            interpreter._execute_snooze(task, cmd)
        assert "Invalid number" in str(exc_info.value)


class TestExecuteIgnore:
    """Tests for @ignore command execution."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_ignore_marks_completed(self, interpreter):
        """Task is marked as completed."""
        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.IGNORE, "@ignore")
        action = interpreter._execute_ignore(task, cmd)
        assert task.status == TaskStatus.COMPLETED
        assert task.completed is not None
        assert "completed" in action.lower()


class TestExecuteDelete:
    """Tests for @delete command execution."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_delete_returns_sentinel(self, interpreter):
        """Returns the delete sentinel string."""
        from src.comments.comment_interpreter import _DELETE_ACTION

        task = Task(title="Test", id="t1")
        cmd = ParsedCommand(CommandType.DELETE, "@delete")
        action = interpreter._execute_delete(task, cmd)
        assert action == _DELETE_ACTION


class TestExecuteNote:
    """Tests for @note command execution."""

    @pytest.fixture
    def interpreter(self):
        return CommentInterpreter()

    def test_note_appends_text(self, interpreter):
        """Text is appended to existing notes."""
        task = Task(title="Test", id="t1", notes="Existing notes")
        cmd = ParsedCommand(CommandType.NOTE, "@note Check with Sarah", "Check with Sarah")
        interpreter._execute_note(task, cmd)
        assert "Existing notes" in task.notes
        assert "Check with Sarah" in task.notes

    def test_note_on_empty_notes(self, interpreter):
        """Creates notes when none exist."""
        task = Task(title="Test", id="t1", notes=None)
        cmd = ParsedCommand(CommandType.NOTE, "@note First note", "First note")
        interpreter._execute_note(task, cmd)
        assert task.notes == "First note"

    def test_note_on_empty_string(self, interpreter):
        """Creates notes when empty string."""
        task = Task(title="Test", id="t1", notes="")
        cmd = ParsedCommand(CommandType.NOTE, "@note Added", "Added")
        interpreter._execute_note(task, cmd)
        assert task.notes == "Added"


# ==================== Process Task Tests ====================


class TestProcessTask:
    """Tests for CommentInterpreter._process_task()."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        tm = MagicMock()
        tm.update_task.return_value = Task(title="Updated", id="t1")
        return tm

    @pytest.fixture
    def interpreter(self, mock_task_manager):
        """Create interpreter with mock TaskManager."""
        return CommentInterpreter(task_manager=mock_task_manager)

    def test_process_task_with_commands(self, interpreter, mock_task_manager):
        """Full flow: parse, execute, clean, update."""
        task = Task(
            title="Review doc",
            id="t1",
            notes="Priority: low\n\nContext\n@priority high",
        )
        results = interpreter._process_task(task, "list1")
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].command.command_type == CommandType.PRIORITY
        mock_task_manager.update_task.assert_called_once()

    def test_process_task_no_commands(self, interpreter, mock_task_manager):
        """Task without commands returns empty list."""
        task = Task(title="No commands", id="t1", notes="Just notes")
        results = interpreter._process_task(task)
        assert results == []
        mock_task_manager.update_task.assert_not_called()

    def test_process_task_none_notes(self, interpreter, mock_task_manager):
        """Task with None notes returns empty list."""
        task = Task(title="No notes", id="t1", notes=None)
        results = interpreter._process_task(task)
        assert results == []

    def test_process_task_delete_calls_delete(self, interpreter, mock_task_manager):
        """@delete triggers delete_task instead of update_task."""
        task = Task(title="Delete me", id="t1", notes="@delete")
        results = interpreter._process_task(task, "list1")
        assert len(results) == 1
        assert results[0].success is True
        mock_task_manager.delete_task.assert_called_once_with("t1", "list1")
        mock_task_manager.update_task.assert_not_called()

    def test_process_task_update_called_once(self, interpreter, mock_task_manager):
        """Multiple commands result in a single update_task call."""
        task = Task(
            title="Multi",
            id="t1",
            notes="Priority: low\n@priority high\n@due 2026-05-01",
        )
        results = interpreter._process_task(task, "list1")
        assert len(results) == 2
        mock_task_manager.update_task.assert_called_once()

    def test_process_task_removes_commands(self, interpreter, mock_task_manager):
        """Commands are removed from notes after processing."""
        task = Task(
            title="Clean",
            id="t1",
            notes="Keep this\n@ignore\nAnd this",
        )
        interpreter._process_task(task, "list1")
        # The task passed to update_task should have cleaned notes
        updated_task = mock_task_manager.update_task.call_args[0][0]
        assert "@ignore" not in (updated_task.notes or "")
        assert "Keep this" in (updated_task.notes or "")

    def test_process_task_failed_command_continues(self, interpreter, mock_task_manager):
        """One command failure does not block subsequent commands."""
        task = Task(
            title="Mixed",
            id="t1",
            notes="@priority extreme\n@due 2026-03-01",
        )
        results = interpreter._process_task(task, "list1")
        assert len(results) == 2
        assert results[0].success is False  # invalid priority
        assert results[1].success is True  # valid due date

    def test_process_task_delete_overrides_ignore(self, interpreter, mock_task_manager):
        """@delete takes precedence when both @ignore and @delete are present."""
        task = Task(title="Both", id="t1", notes="@ignore\n@delete")
        results = interpreter._process_task(task, "list1")
        mock_task_manager.delete_task.assert_called_once()
        mock_task_manager.update_task.assert_not_called()


# ==================== Process Pending Tasks Tests ====================


class TestProcessPendingTasks:
    """Tests for CommentInterpreter.process_pending_tasks()."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        tm = MagicMock()
        tm.update_task.return_value = Task(title="Updated", id="t1")
        return tm

    @pytest.fixture
    def interpreter(self, mock_task_manager):
        return CommentInterpreter(task_manager=mock_task_manager)

    def test_process_empty_list(self, interpreter, mock_task_manager):
        """No tasks returns empty result."""
        mock_task_manager.list_tasks.return_value = iter([])
        result = interpreter.process_pending_tasks("list1")
        assert result.tasks_scanned == 0
        assert result.commands_found == 0
        assert result.has_errors is False

    def test_process_tasks_with_commands(self, interpreter, mock_task_manager):
        """End-to-end flow with tasks containing commands."""
        tasks = [
            Task(title="Task 1", id="t1", notes="@priority high"),
            Task(title="Task 2", id="t2", notes="@due 2026-04-01"),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)
        result = interpreter.process_pending_tasks("list1")
        assert result.tasks_scanned == 2
        assert result.commands_found == 2
        assert result.commands_executed == 2
        assert len(result.results) == 2

    def test_process_skips_tasks_without_commands(self, interpreter, mock_task_manager):
        """Tasks without commands are scanned but not modified."""
        tasks = [
            Task(title="No cmd", id="t1", notes="Just notes"),
            Task(title="Has cmd", id="t2", notes="@ignore"),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)
        result = interpreter.process_pending_tasks("list1")
        assert result.tasks_scanned == 2
        assert result.commands_found == 1
        assert result.commands_executed == 1

    def test_process_handles_list_error(self, interpreter, mock_task_manager):
        """API error when listing tasks is recorded."""
        mock_task_manager.list_tasks.side_effect = Exception("API failure")
        result = interpreter.process_pending_tasks("list1")
        assert result.has_errors is True
        assert "Failed to list tasks" in result.errors[0]
        assert result.tasks_scanned == 0

    def test_process_aggregates_stats(self, interpreter, mock_task_manager):
        """Stats are correctly aggregated across tasks."""
        tasks = [
            Task(title="T1", id="t1", notes="@priority high\n@due 2026-03-01"),
            Task(title="T2", id="t2", notes="@snooze 3 days"),
            Task(title="T3", id="t3", notes="Regular notes"),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)
        result = interpreter.process_pending_tasks("list1")
        assert result.tasks_scanned == 3
        assert result.commands_found == 3
        assert result.commands_executed == 3
        assert len(result.results) == 3

    def test_process_default_list(self, interpreter, mock_task_manager):
        """None list_id is passed through to list_tasks."""
        mock_task_manager.list_tasks.return_value = iter([])
        interpreter.process_pending_tasks()
        mock_task_manager.list_tasks.assert_called_once_with(
            list_id=None, show_completed=False
        )

    def test_process_handles_task_error(self, interpreter, mock_task_manager):
        """Error processing one task doesn't prevent processing others."""
        tasks = [
            Task(title="Error task", id="t1", notes="@priority high"),
            Task(title="Good task", id="t2", notes="@ignore"),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)
        # First update_task call raises, second succeeds
        mock_task_manager.update_task.side_effect = [
            Exception("API error"),
            Task(title="Good task", id="t2"),
        ]
        result = interpreter.process_pending_tasks("list1")
        assert result.tasks_scanned == 2
        assert result.has_errors is True
        # The first task's commands were found before the error
        assert result.commands_found >= 1


# ==================== Gmail Helpers ====================


def _make_gmail_headers_response(
    from_addr="sender@example.com",
    subject="Original Subject",
    message_id="<orig@msg.id>",
):
    """Build a mock Gmail API metadata response."""
    headers = []
    if from_addr:
        headers.append({"name": "From", "value": from_addr})
    if subject:
        headers.append({"name": "Subject", "value": subject})
    if message_id:
        headers.append({"name": "Message-ID", "value": message_id})
    return {"payload": {"headers": headers}}


def _make_task(
    task_id="task1",
    title="Reply to email",
    notes=None,
    source_thread_id="thread123",
    source_email_id="msg456",
):
    """Build a Task with email metadata for testing."""
    return Task(
        id=task_id,
        title=title,
        notes=notes,
        source_thread_id=source_thread_id,
        source_email_id=source_email_id,
    )


def _decode_sent_message(mock_gmail_service):
    """Extract and decode the MIME message from the send() call."""
    send_call = mock_gmail_service.users().messages().send
    body = send_call.call_args[1]["body"]
    raw_bytes = base64.urlsafe_b64decode(body["raw"])
    return message_from_bytes(raw_bytes)


# ==================== @respond Execution Tests ====================


class TestExecuteRespond:
    """Tests for the @respond command."""

    @pytest.fixture
    def mock_gmail_service(self):
        """Create a mock Gmail API service with default successful responses."""
        service = MagicMock()
        service.users().messages().get().execute.return_value = (
            _make_gmail_headers_response()
        )
        service.users().messages().send().execute.return_value = {
            "id": "sent_msg_id"
        }
        return service

    @pytest.fixture
    def mock_task_manager(self):
        return MagicMock()

    @pytest.fixture
    def interpreter(self, mock_gmail_service, mock_task_manager):
        return CommentInterpreter(
            task_manager=mock_task_manager,
            gmail_service=mock_gmail_service,
        )

    @pytest.fixture
    def task(self):
        return _make_task()

    @pytest.fixture
    def respond_command(self):
        return ParsedCommand(
            command_type=CommandType.RESPOND,
            raw_text="@respond Thanks, I'll handle this",
            arguments="Thanks, I'll handle this",
        )

    # --- Happy path ---

    def test_respond_success(self, interpreter, task, respond_command):
        """Successful respond returns action description with recipient."""
        action = interpreter._execute_respond(task, respond_command)
        assert "sender@example.com" in action
        assert "completed" in action

    def test_respond_marks_task_completed(self, interpreter, task, respond_command):
        """Task is marked as completed after sending reply."""
        interpreter._execute_respond(task, respond_command)
        assert task.is_completed
        assert task.completed is not None

    # --- Reply headers ---

    def test_respond_sends_to_original_sender(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Reply is addressed to the original email's From header."""
        interpreter._execute_respond(task, respond_command)
        msg = _decode_sent_message(mock_gmail_service)
        assert msg["to"] == "sender@example.com"

    def test_respond_subject_re_prefix(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Reply subject gets Re: prefix."""
        interpreter._execute_respond(task, respond_command)
        msg = _decode_sent_message(mock_gmail_service)
        assert msg["subject"] == "Re: Original Subject"

    def test_respond_subject_already_re(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Re: prefix is not doubled when already present."""
        mock_gmail_service.users().messages().get().execute.return_value = (
            _make_gmail_headers_response(subject="Re: Already prefixed")
        )
        interpreter._execute_respond(task, respond_command)
        msg = _decode_sent_message(mock_gmail_service)
        assert msg["subject"] == "Re: Already prefixed"

    def test_respond_sets_in_reply_to(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """In-Reply-To and References headers are set from original Message-ID."""
        interpreter._execute_respond(task, respond_command)
        msg = _decode_sent_message(mock_gmail_service)
        assert msg["In-Reply-To"] == "<orig@msg.id>"
        assert msg["References"] == "<orig@msg.id>"

    def test_respond_sends_with_thread_id(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Send call includes threadId to keep reply in same Gmail thread."""
        interpreter._execute_respond(task, respond_command)
        send_call = mock_gmail_service.users().messages().send
        body = send_call.call_args[1]["body"]
        assert body["threadId"] == "thread123"

    def test_respond_message_body(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Reply body matches the command argument."""
        interpreter._execute_respond(task, respond_command)
        msg = _decode_sent_message(mock_gmail_service)
        assert msg.get_payload() == "Thanks, I'll handle this"

    # --- Graceful degradation ---

    def test_respond_no_message_id_header(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Missing Message-ID sends reply without In-Reply-To/References."""
        mock_gmail_service.users().messages().get().execute.return_value = (
            _make_gmail_headers_response(message_id="")
        )
        interpreter._execute_respond(task, respond_command)
        msg = _decode_sent_message(mock_gmail_service)
        assert msg["In-Reply-To"] is None
        assert msg["References"] is None

    # --- Error cases ---

    def test_respond_no_thread_id(self, interpreter, respond_command):
        """Task without source_thread_id raises CommentExecutionError."""
        task = _make_task(source_thread_id=None)
        with pytest.raises(CommentExecutionError, match="no source email thread"):
            interpreter._execute_respond(task, respond_command)

    def test_respond_no_email_id(self, interpreter, respond_command):
        """Task without source_email_id raises CommentExecutionError."""
        task = _make_task(source_email_id=None)
        with pytest.raises(CommentExecutionError, match="no source email ID"):
            interpreter._execute_respond(task, respond_command)

    def test_respond_empty_message(self, interpreter, task):
        """Empty message raises CommentExecutionError."""
        cmd = ParsedCommand(
            command_type=CommandType.RESPOND,
            raw_text="@respond",
            arguments="",
        )
        with pytest.raises(CommentExecutionError, match="Reply message is empty"):
            interpreter._execute_respond(task, cmd)

    def test_respond_whitespace_only_message(self, interpreter, task):
        """Whitespace-only message raises CommentExecutionError."""
        cmd = ParsedCommand(
            command_type=CommandType.RESPOND,
            raw_text="@respond   ",
            arguments="   ",
        )
        with pytest.raises(CommentExecutionError, match="Reply message is empty"):
            interpreter._execute_respond(task, cmd)

    def test_respond_no_from_header(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Missing From header raises CommentExecutionError."""
        mock_gmail_service.users().messages().get().execute.return_value = (
            _make_gmail_headers_response(from_addr="")
        )
        with pytest.raises(CommentExecutionError, match="Could not determine recipient"):
            interpreter._execute_respond(task, respond_command)

    def test_respond_fetch_fails(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Gmail get() failure raises CommentExecutionError."""
        mock_gmail_service.users().messages().get().execute.side_effect = HttpError(
            resp=MagicMock(status=404), content=b"Not found"
        )
        with pytest.raises(CommentExecutionError, match="Failed to fetch original email"):
            interpreter._execute_respond(task, respond_command)

    def test_respond_send_fails_task_not_completed(
        self, interpreter, task, respond_command, mock_gmail_service
    ):
        """Send failure raises error and task stays open."""
        mock_gmail_service.users().messages().send().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )
        with pytest.raises(CommentExecutionError, match="Failed to send reply"):
            interpreter._execute_respond(task, respond_command)
        assert task.status == TaskStatus.NEEDS_ACTION


# ==================== @respond Integration via _process_task ====================


class TestProcessTaskRespond:
    """Tests for @respond flowing through _process_task."""

    @pytest.fixture
    def mock_gmail_service(self):
        service = MagicMock()
        service.users().messages().get().execute.return_value = (
            _make_gmail_headers_response()
        )
        service.users().messages().send().execute.return_value = {"id": "sent_id"}
        return service

    @pytest.fixture
    def mock_task_manager(self):
        return MagicMock()

    @pytest.fixture
    def interpreter(self, mock_gmail_service, mock_task_manager):
        return CommentInterpreter(
            task_manager=mock_task_manager,
            gmail_service=mock_gmail_service,
        )

    def test_process_task_respond_calls_update(
        self, interpreter, mock_task_manager
    ):
        """@respond processes and calls update_task."""
        task = _make_task(notes="@respond Got it, thanks!")
        results = interpreter._process_task(task)
        assert len(results) == 1
        assert results[0].success
        assert results[0].command.command_type == CommandType.RESPOND
        mock_task_manager.update_task.assert_called_once()

    def test_process_task_respond_strips_command_from_notes(
        self, interpreter, mock_task_manager
    ):
        """@respond line is removed from notes after processing."""
        task = _make_task(notes="Some context\n@respond Got it")
        interpreter._process_task(task)
        updated_task = mock_task_manager.update_task.call_args[0][0]
        assert "@respond" not in (updated_task.notes or "")
        assert "Some context" in (updated_task.notes or "")

    def test_process_task_respond_failure_recorded(
        self, interpreter, mock_gmail_service, mock_task_manager
    ):
        """Send failure is recorded as a failed CommandResult."""
        mock_gmail_service.users().messages().send().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )
        task = _make_task(notes="@respond Will do")
        results = interpreter._process_task(task)
        assert len(results) == 1
        assert not results[0].success
        assert "Failed to send reply" in results[0].error
