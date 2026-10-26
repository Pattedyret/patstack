---
name: verify-example-app
description: Use when verifying example-app web behavior locally, on a PR preview or on stage, or when a task changes sign-in, the dashboard or the settings form.
---

# Verify example-app

Fictional example of a generated verification skill. Commands are illustrative.

## Launch

- Local: `npm ci && npm run dev`. Ready when `curl -fsS http://127.0.0.1:3000/health` returns `{"ok":true}`.
- PR preview or stage: no local startup. Use the Doctor check against the target origin instead.
- Owned resources: the dev server started by this run and the `./.verify-artifacts/<run-id>/` directory.

## Doctor (read-only)

1. `GET <origin>/version` returns the expected commit SHA for the candidate or release under test.
2. `GET <origin>/health` is `ok`.
3. Test persona alias `reviewer-basic` resolves through the access policy. Never print credentials.

## Run

| Journey | Recipe | Existing tests |
|---|---|---|
| Sign in and land on dashboard | [recipes/sign-in.md](recipes/sign-in.md) | `tests/e2e/sign-in.spec.ts` |
| Settings form validation | N/A in this example | `tests/e2e/settings.spec.ts` |

Entry command: `npx playwright test tests/e2e/sign-in.spec.ts --reporter=line`.

## Evidence

Write to `./.verify-artifacts/<run-id>/`: executed steps, expected vs actual, origin, `/version` SHA before and after the run, screenshots after secret-bearing UI is gone, and limitations. Do not keep cookies, storage state, tokens or signed URLs.

## Cleanup

Stop only the dev server this run started. Remove only fixtures this run created. Keep the evidence directory, including after a failed run.

## Status reporting

Report **recipe validity** (VALID / BROKEN / UNTESTED) separately from **application outcome** (PASS / FAIL / BLOCKED / NOT RUN). Local and live results are reported separately.
