"""CLI entry point for the email agent pipeline."""

import argparse
import logging
import sys

from dotenv import load_dotenv

from src.orchestrator import EmailAgentOrchestrator


def main() -> int:
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run the email agent pipeline")
    parser.add_argument(
        "--max-emails",
        type=int,
        default=50,
        help="Maximum number of emails to process (default: 50)",
    )
    args = parser.parse_args()

    orchestrator = EmailAgentOrchestrator(max_emails=args.max_emails)
    result = orchestrator.run()

    # Print summary
    print("\n--- Pipeline Summary ---")
    for step in result.steps:
        status = "OK" if step.success else "FAILED"
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
