# Recipe: sign in and land on the dashboard

| Field | Value |
|---|---|
| Entry point | `<origin>/login` |
| Persona | `reviewer-basic` (least-privilege test role, approved for stage) |
| Fixtures | None created; read-only journey |
| Last verified | Not verified (fictional example) |

## Steps and assertions

1. Open `<origin>/login`. Assert the origin matches the target after redirects.
2. Fill credentials through native vault autofill for the matching origin. No secret enters chat or command arguments.
3. Submit. Assert the URL becomes `<origin>/dashboard` within 5 s and the heading reads "Dashboard".
4. Assert the account menu shows the role `Reviewer`, not `Admin`.

## Negative cases

- Wrong password shows an inline error and stays on `/login`; no session cookie is set.
- `reviewer-basic` opening `<origin>/admin` gets the 403 page, not an empty admin shell.

## Quality targets

- Keyboard-only sign-in completes; focus is visible on every control.
- No horizontal overflow at 360 px and 1280 px widths.

## Side effects

None expected. Any write request during this journey is a failure.
