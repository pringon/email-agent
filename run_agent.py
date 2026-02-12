"""CLI entry point for the email agent pipeline."""

import argparse
import sys

from dotenv import load_dotenv

from src.digest import DigestReporter
from src.logging_config import configure_logging
from src.orchestrator import EmailAgentOrchestrator


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the email agent pipeline")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Set logging level (overrides LOG_LEVEL env var)",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=50,
        help="Maximum number of emails to process (default: 50)",
    )
    parser.add_argument(
        "--check-completions",
        action="store_true",
        help="Check Sent Mail for replies and complete matching tasks",
    )
    parser.add_argument(
        "--process-comments",
        action="store_true",
        help="Scan task notes for @commands and execute them",
    )
    parser.add_argument(
        "--send-digest",
        metavar="EMAIL",
        help="Generate and send a daily digest to the given email address",
    )
    args = parser.parse_args()
    configure_logging(level_override=args.log_level)

    if args.send_digest:

        reporter = DigestReporter()
        delivery = reporter.generate_and_send(recipient=args.send_digest)
        print(delivery.plain_text_output or "(no output)")
        if delivery.errors:
            for err in delivery.errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
        return 0

    orchestrator = EmailAgentOrchestrator(max_emails=args.max_emails)
    if args.check_completions:
        result = orchestrator.run_completion_check()
    elif args.process_comments:
        result = orchestrator.run_comment_processing()
    else:
        result = orchestrator.run()

    # Print summary
    print("\n--- Pipeline Summary ---")
    for step in result.steps:
        status = "SKIPPED" if step.skipped else ("OK" if step.success else "FAILED")
        print(f"  {step.name}: {status} ({step.duration_seconds}s)")
        for key, value in step.details.items():
            print(f"    {key}: {value}")
        if step.error:
            print(f"    error: {step.error}")

    overall = "SUCCESS" if result.success else "FAILURE"
    print(f"\nResult: {overall}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
