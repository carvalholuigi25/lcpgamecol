---
name: optimize-code
description: "Use when improving runtime speed, latency, throughput, memory use, or database efficiency without changing intended behavior."
---

# Optimize Code

## Workflow

1. Clarify the performance goal and identify representative inputs and operating conditions.
2. Establish a baseline with a repeatable benchmark, profiler, query plan, or resource measurement before changing code. Do not optimize based only on intuition.
3. Locate the measured bottleneck and inspect its callers, data volume, and existing tests.
4. Make the smallest change that addresses that bottleneck while preserving API behavior, correctness, security checks, and error handling.
5. Run correctness tests first, then repeat the same measurement under comparable conditions. Report the measured difference and any tradeoffs.
6. Inspect the diff for added complexity or unrelated changes. If an improvement cannot be measured, describe it as a hypothesis rather than a result.

## Project Guidance

- Use the repository's existing Python, FastAPI, and SQLite patterns. For database work, check indexes and query plans before adding caching or denormalized state.
- Prefer profiling representative requests or data sets over synthetic micro-optimizations that do not reflect application use.
- Preserve concurrency safety, authorization, validation, and transaction boundaries. A faster path that changes these guarantees is not an optimization.
- Keep benchmark setup and results reproducible; do not commit generated profiles or benchmark output unless requested.