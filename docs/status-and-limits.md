# Status and limits — Patstack

This independently maintained copy retains workflow version **1.5.0**. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means real behavior was seen; **NOT DONE** means it has not happened.

## Activation

**Installed** means files and links are in place and setup checks pass. **Discovered** means a fresh client session lists the skills. **Runtime-proven** means a real task ran through the workflow and its proof was observed. These are separate claims.

| Layer | Claim | Status |
|---|---|---|
| Team repository | 20 skills and 68 manifest-covered resources, any bundled private project pack, the benchmark and the global-instructions template; local manifest, privacy/provenance/links/formats, 10 numbering tests, 244 tool tests (merge gate and guard, task status, Monday tickets, tiers and more), 36 package controls, 145 setup-tool tests, 46 benchmark harness tests and the pack's own JS and Python tests | **EXECUTED** by the local checks described below. |
| Team installation and native discovery | This copy installed and discovered on your hosts | **NOT DONE** by this repository change. Verify each host and client separately. |
| Runtime | A full development task run end to end under this copy on each host | **NOT CLAIMED.** |
| Runtime | Unattended overnight runs | **NOT GUARANTEED.** A durable wake source and actual tool/login readiness must be verified per task. |
| UI | A T3 progress bar or taskbar phase display | **NOT IMPLEMENTED.** Phases use native plans and checkpoints; there is no progress-bar setter. |

Host-specific test results must still be observed on the actual OS. Windows runs the portable suite; POSIX-only task fixtures, executable-mode tests and Linux sandbox checks are explicitly skipped there. Linux remains required for those checks; a passing Windows run does not establish sandbox coverage.

## What this copy verifies

| Check | Status |
|---|---|
| Benchmark harness (`bench/test_bench.py`): every task workspace builds, good oracles pass their graders, arm installer, sandbox settings | **EXECUTED** by `scripts/check.py`: 46 tests (with `bench/test_targets.py`), no model call, including the grader sandbox (bubblewrap), known grader bypasses and failed-trial accounting. Benchmark *results* are not claimed here. |
| Reference numbering tests (`tools/ticket-ref/test_ticket_ref.py`), including the team slot table | **EXECUTED** by `scripts/check.py`: 10 tests. |
| Setup tools (`scripts/test_setup_doctor.py`, `test_skill_mirrors.py`, `test_detach.py`, `test_ticket_launcher.py`, `test_start_here.py`, `test_preferences.py`) | **EXECUTED** by `scripts/check.py`: 145 tests. |
| Relative links and anchors, privacy scan, JSON/SVG parsing, skill frontmatter | **EXECUTED** by `scripts/check.py`. |
| All 68 manifest-covered resources, including all 20 skills, match local source and published hashes with exact coverage | **EXECUTED** by `scripts/check.py` and `refresh_from_source.py --check`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). No installed private source is required. |
| Mutation and privacy negative controls | **EXECUTED** by `scripts/check.py`: 36 tests, including original coverage, privacy, link and sanitization controls plus personal-name rejection, the project-pack exception, upstream owner-name mapping, local manifest generation and refusal to overwrite team edits from upstream. |
| Installation, native discovery and real task behavior | **NOT DONE** for the team copy. Local checks establish no client activation or release proof. |
| Workflow SVG and HTML | No visual rendering claim is made for this copy. |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** |

## Hooks and private state

- **Hooks:** Patstack installs no hooks on its own; `scripts/start_here.py --apply` adds the recommended merge guard, a `PreToolUse` hook that refuses direct merges, to Claude Code and Codex. Codex skips it until the person trusts it once; `setup_doctor.py` reports that. OBSERVED on Codex CLI 0.167 (isolated home): untrusted, the command ran; after **Trust all and continue**, Codex blocked it. Native loading in each person's own client still needs that client's evidence.
- **Private state:** Unix stores use owner-only access; Windows stores inherit the user profile ACLs and need that boundary verified at installation. Real host profiles and state are excluded from publication.

## Authority

- A Full Send grant covers the task's established test target and repair revisions. It is **not** production permission. Production needs explicit task-specific authority, except an INTERNAL project's own production, which the owner's tier grant covers.
- Model review verdicts are not GitHub human approvals.
- Retro and recipe generation grant no deployment, data or service authority.

## Known gaps

- The merge guard hook points at the checkout. Moving the checkout breaks it: the setup check reports the missing path as `FAIL` until you edit the path in `~/.claude/settings.json`.
- Optional upstream comparison requires a separately available upstream source tree. It maps the upstream owner name and reports every remaining difference; importing changes stays manual ([sync procedure](setup.md#syncing-a-change-from-upstream)) and the team manifest does not track an installed private tree.
