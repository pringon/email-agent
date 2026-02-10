#!/usr/bin/env python3
"""Local smoke test for run_agent.py.

Validates that all required environment variables and credential files
are present before running the agent pipeline with --max-emails 1.

Run from project root:
    python scripts/local_test_run_agent.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
]

REQUIRED_FILES = [
    CONFIG_DIR / "credentials.json",
    CONFIG_DIR / "token.json",
    CONFIG_DIR / "tasks_token.json",
]


def check_prerequisites() -> list[str]:
    errors = []

    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            errors.append(f"Missing env var: {var}")

    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"Missing file: {path.relative_to(PROJECT_ROOT)}")

    return errors


def main() -> int:
    print("Checking prerequisites ...\n")
    errors = check_prerequisites()

    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        print(
            "\nSetup instructions:"
            "\n  1. Set OPENAI_API_KEY in .env or export it"
            "\n  2. Place OAuth credentials in config/credentials.json"
            "\n  3. Run 'python run_agent.py' once interactively to generate token files"
        )
        return 1

    for var in REQUIRED_ENV_VARS:
        print(f"  ✓ {var}")
    for path in REQUIRED_FILES:
        print(f"  ✓ {path.relative_to(PROJECT_ROOT)}")

    print("\nAll prerequisites met. Running agent with --max-emails 1 ...\n")

    from src.orchestrator import EmailAgentOrchestrator

    orchestrator = EmailAgentOrchestrator(max_emails=1)
    result = orchestrator.run()

    print("\n--- Pipeline Summary ---")
    for step in result.steps:
        status = "OK" if step.success else "FAILED"
        print(f"  {step.name}: {status} ({step.duration_seconds}s)")
        for key, value in step.details.items():
            print(f"    {key}: {value}")
        if step.error:
            print(f"    error: {step.error}")

    overall = "PASS" if result.success else "FAIL"
    print(f"\nResult: {overall}")
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
