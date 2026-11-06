---
description: Analyze and improve test coverage
agent: tdd-guide
subtask: true
---

# Test Coverage Command

Analyze coverage and identify meaningful gaps: $ARGUMENTS

## Run coverage

Backend (only if `pytest-cov` is installed):

```bash
cd backend && .venv/bin/python -c "import pytest_cov" && \
  .venv/bin/python -m pytest jumeau/tests --cov=jumeau --cov-report=term-missing
```

If `pytest-cov` is not installed, say so and analyze the tests instead of installing it unprompted.

Frontend:

```bash
cd frontend && yarn test --watchAll=false --coverage
```

## Targets

| Code | Target |
|------|--------|
| Critical business logic (`backend/jumeau/flux.py`, routes) | 90% |
| Standard backend code | 80% |
| Frontend components | 70% |
| Utilities | 90% |

## Analysis

- Prioritize uncovered error paths, disconnections, timeouts, and permission boundaries.
- A line covered only by an assertion-free smoke test does not count as meaningful coverage.
- For each gap: file, function, why it matters, and the smallest test that would catch a regression.

## Output

1. Coverage summary (backend / frontend).
2. Top 5 gaps by risk, with file:line.
3. Proposed tests, using the project's existing pytest / React testing patterns.
4. Any pre-existing failures that make coverage unreliable.

**IMPORTANT**: Coverage is a signal, not a goal. Do not add low-value tests just to raise the number.
