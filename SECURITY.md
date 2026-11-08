# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Only the maintainer can see the report. Include what you found, where (file and line, or the skill name), and how to reproduce it.

You can expect an acknowledgement within a week. Fixes land through a normal pull request once the report is resolved.

## What counts

- A file in this repository that exposes a private value: a credential, token, host address, device inventory, customer or project name, or session or ticket identifier.
- A gap in [`scripts/check.py`](scripts/check.py) that lets such a value through the publication check.
- A skill instruction that would lead an agent to bypass a stated permission gate, such as production deploys, destructive data or Git actions, or credential handling.
- Code in `monitoring/`, `scripts/` or `tools/` that writes private data where this repository says it never goes.

## What does not

Patstack is a set of agent instructions and small standard-library Python tools. It runs no service and holds no user data. Problems in Claude Code, Codex, T3 Code, REA or any other tool Patstack calls belong with that project.

## Supported versions

Only the latest commit on `main` is supported.
