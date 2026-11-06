---
name: run-unit-tests
description: "Use when selecting, running, or diagnosing unit tests for this project, including pytest test selection and full-suite runs."
---

# Run Unit Tests

## Workflow

1. Check the project test configuration and nearby fixtures to identify the test runner, required environment, and correct scope.
2. For a known change, run the smallest relevant test module or selection first. For an unspecified request, run the full unit test suite.
3. Use the active project environment. On Windows, prefer `.venv\Scripts\python.exe -m pytest`; on other platforms, use `python -m pytest` from the activated project environment.
4. When a test fails, preserve the complete failure signal, inspect the assertion and traceback, and distinguish product defects from setup or environment failures. Do not change production code or tests merely to silence a failure.
5. After a focused run passes, broaden to related tests or the full suite when practical. Keep unit-test results separate from integration, browser, or external-service checks.
6. Report the exact command, pass/fail/skip counts, and any tests that could not run or require external services.

## Project Guidance

- Tests live under `tests/` and use pytest fixtures in `tests/conftest.py`.
- `npm test` invokes `python -m pytest`; use the project virtual environment directly when the shell's `python` may refer to another interpreter.
- Prefer focused invocations such as `python -m pytest tests/test_api.py -q` before running the complete suite.
- Do not install dependencies, change test configuration, or contact external services solely to make a test command run unless the task authorizes that setup.