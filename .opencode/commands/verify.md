---
description: Run the Meridian verification loop (pytest + yarn)
agent: build
---

# Verify Command

Run the Meridian verification loop for: $ARGUMENTS

## Backend

Use the project virtualenv, never the system Python:

```bash
cd backend && .venv/bin/python -m pytest jumeau/tests -q
```

Focused suites when relevant:

```bash
cd backend && .venv/bin/python -m pytest tests/test_conversation_routes.py -q
```

- Do **not** modify `backend/pytest.ini` (`-n 2 --dist loadscope`).
- For serial debugging use `-n 0`, not `-p no:xdist`.
- `backend/tests` has pre-existing environment failures (`REACT_APP_BACKEND_URL`, missing fixtures). Report them separately from regressions.
- Optional style gate on changed files only: `.venv/bin/flake8 <files> --select=E9,F63,F7,F82`.

## Frontend

Use `yarn`, not `npm`:

```bash
cd frontend && yarn test --watchAll=false
cd frontend && yarn build
```

- `CI=true yarn build` may fail on pre-existing ESLint warnings; distinguish that from a real build failure.
- There is no `lint` script and no TypeScript in this project; skip `tsc`/`npm run lint`.

## Checklist

### Correctness
- [ ] Backend tests pass (`jumeau/tests`)
- [ ] Focused tests for the changed area pass
- [ ] Frontend tests pass
- [ ] Frontend build succeeds

### Quality
- [ ] No new `console.log`
- [ ] No hardcoded secrets
- [ ] Input validation on API boundaries
- [ ] Existing conventions preserved

## Report

| Check | Status | Notes |
|-------|--------|-------|
| Backend `jumeau/tests` | PASS/FAIL | counts |
| Focused backend tests | PASS/FAIL | files |
| Frontend tests | PASS/FAIL | suites |
| Frontend build | PASS/FAIL | warnings |
| Pre-existing failures | n/a | list |

End with a clear PASS or FAIL. List only actionable fixes.
