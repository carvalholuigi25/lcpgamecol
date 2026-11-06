---
name: fix-code
description: "Use when diagnosing and fixing a bug, regression, failing behavior, or code defect in this project."
---

# Fix Code

## Workflow

1. Identify the observable failure and trace it to the code that owns the behavior. Read the nearest implementation, caller, and relevant tests.
2. State a falsifiable cause and the cheapest check that could disprove it. Reproduce the issue or run that check before editing when practical.
3. Fix the root cause with the smallest change that preserves existing APIs and conventions. Avoid unrelated cleanup.
4. Add or update a focused regression test that fails without the fix.
5. Immediately run the narrowest relevant test or check after editing. If it fails, repair the same behavior and rerun it before broadening validation.
6. Run the relevant surrounding tests, inspect the final diff, and report behavior changed, checks run, and anything still unverified.

## Project Guidance

- This repository is primarily Python with FastAPI, SQLite, pytest, and browser-side JavaScript.
- Follow nearby patterns and fixtures, especially in `tests/conftest.py` and the test module for the affected route or feature.
- Do not weaken assertions, remove coverage, or hide an error just to make a test pass. Change an expectation only when the intended behavior has changed and that change is justified.
- If a failure cannot be reproduced, share the evidence and uncertainty instead of making a speculative broad rewrite.