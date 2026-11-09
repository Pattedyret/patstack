# Status and limits — DevStack

This independently maintained copy retains workflow version **1.4.0**. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means real behavior was seen; **REPORTED** means historical upstream evidence, not reproduced for this copy; **NOT DONE** means it has not happened.

## Activation

**Installed** means files and links are in place and setup checks pass. **Discovered** means a fresh client session lists the skills. **Runtime-proven** means a real task ran through the workflow and its proof was observed. These are separate claims.

| Layer | Claim | Status |
|---|---|---|
| Team repository | 19 skills and 69 manifest-covered resources, any bundled private project pack, the benchmark and the global-instructions template; local manifest, privacy/provenance/links/formats, 58 KPI recorder and target tests, 17 task KPI tests, 10 numbering tests, 35 package controls, 99 setup-tool tests, 39 benchmark harness tests and the pack's own JS and Python tests | **EXECUTED** by the local checks described below. |
| Team installation and native discovery | This copy installed and discovered on your hosts | **NOT DONE** by this repository change. Verify each host and client separately. |
| Runtime | A full development task run end to end under this copy on each host | **NOT CLAIMED.** |
| Runtime | Codex hook trust on your hosts | **UNPROVEN.** The real trust gate is preserved. |
| Runtime | Unattended overnight runs | **NOT GUARANTEED.** A durable wake source and actual tool/login readiness must be verified per task. |
| UI | A T3 progress bar or taskbar phase display | **NOT IMPLEMENTED.** Phases use native plans and checkpoints; there is no progress-bar setter. |

Numbering works independently of a task registry. The retired registry and its historical records are private preserved data, not an installation prerequisite or a Windows blocker. Host-specific test results must still be observed on the actual OS.

## What this copy verifies

| Check | Status |
|---|---|
| KPI recorder and task KPI unit tests (`monitoring/devstack/test_kpi_monitor.py`, `test_task_kpi.py`) | **EXECUTED** by `scripts/check.py`: 47 + 15 tests. |
| Benchmark harness (`bench/test_bench.py`): every task workspace builds, good oracles pass their graders, arm installer, sandbox settings | **EXECUTED** by `scripts/check.py`: 35 tests, no model call, including the grader sandbox (bubblewrap), known grader bypasses and failed-trial accounting. Benchmark *results* are not claimed here. |
| Reference numbering tests (`tools/ticket-ref/test_ticket_ref.py`), including the team slot table | **EXECUTED** by `scripts/check.py`: 10 tests. |
| Setup tools (`scripts/test_setup_doctor.py`, `test_skill_mirrors.py`, `test_codex_hook_trust.py`, `test_detach.py`, `test_ticket_launcher.py`) | **EXECUTED** by `scripts/check.py`: 98 tests. |
| Example KPI snapshot records and reports through the real recorder | **EXECUTED** by `scripts/check.py`. |
| Relative links and anchors, privacy scan, JSON/SVG parsing, skill frontmatter | **EXECUTED** by `scripts/check.py`. |
| All 69 manifest-covered resources, including all 19 skills, match local source and published hashes with exact coverage | **EXECUTED** by `scripts/check.py` and `refresh_from_source.py --check`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). No installed private source is required. |
| Mutation and privacy negative controls | **EXECUTED** by `scripts/check.py`: 35 tests, including original coverage, privacy, link and sanitization controls plus personal-name rejection, the project-pack exception, upstream rename mapping, local manifest generation and refusal to overwrite team edits from upstream. |
| Installation, native discovery and real task behavior | **NOT DONE** for the team copy. Local checks establish no client activation or release proof. |
| Workflow SVG, HTML and animated README preview | Upstream visual/playback observations are historical only; no new visual rendering claim is made for this copy. The original GIF remains unchanged and checked by exact hash, signature, size and dimensions. |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** |

## Upstream rollout history

These are historical checks reported by the upstream rollout lead for the original setup, before this independent team copy. None establishes installation, activation, review approval or runtime behavior of this repository on your hosts. Catalog totals include unrelated native/project skills; DevStack contributes the same 19 on every host.

| Host | Installation targets | Fresh Codex catalog | Fresh Claude Code catalog | Native checks reported |
|---|---:|---:|---:|---|
| Mac | 93 | 68 total; all 19 present | 131 total; all 19 present | 19 cutover/transaction tests, 26 KPI tests; isolated launcher init/new passes |
| devbox | 98 | 58 total; all 19 present | 130 total; all 19 present | 5 numbering tests, 8 cutover tests; isolated launcher init/new passes |
| Windows | 95 | 46 total; all 19 present | 69 total; all 19 present | 5 numbering tests, 8 cutover tests; isolated launcher init/new passes |

The upstream lead reported all 52 canonical source hashes matching the then-reviewed upstream manifest across those three hosts, and all 19 native skill mirrors checked, including Windows' required external Markdown-link adaptation. That export transformed three documented private paragraphs. The [team manifest](../SOURCE-MANIFEST.json) now records this repository's own bytes and provides no parity claim about those upstream hosts.

Known legacy runtime bindings were retired with private rollback archives: three Mac launchd jobs were stopped and their plists archived; seven devbox unit/timer names were stopped and their unit/enabling links archived. The old board listener is closed on all three hosts. Known legacy hook bindings removed: 11 on Mac, 10 on devbox and none on Windows. Retained config/hook content matches the expected transformation, retained Codex hook positions were checked, and cached legacy hook paths were neutralized. The old CLI returns a retirement notice with exit code 64 on Mac and devbox; Windows had no old adapter.

Private counters use distinct issuer slots above the combined historical high-water mark. No real new-task reference was issued during rollout; launcher tests used isolated stores. Historical records remain private and preserved. Native configuration trust was not edited. Device data and credentials are not published, and production was untouched.

Independent Opus review produced conditional findings, which the rollout lead reports fixing and checking with native regressions. There is no unconditional Opus approval of the final bytes. An additional Sol review could not run because of capacity; no substitute model was presented as that review. Executed test evidence remains separate from model judgments.

## Monitoring reality

- **Hooks:** lifecycle and tool hooks record audit receipts (hashed session identity, host, runtime, event counts: turns, tool calls and, for Claude, tool failures), not outcomes, prompts, tool data or transcripts. A SessionStart hook shows a one-line setup status in every session. Native loading and trust require actual client evidence. Shell and config checks are separate.
- **Historical discovery:** old `agent-work` discovery remains historical/retired. It is not required for numbering, task entry or Retro.
- **Outcomes:** verified success, interventions and other semantic KPIs stay **unmeasured** until the lead records them with `task_kpi.py` (`start` at intake, `finish` at the endpoint, `once` for unticketed requests), backed by evidence. The setup check warns about completed tasks without a recorded outcome.
- **Private state:** Unix stores use owner-only access; Windows stores inherit the user profile ACLs and need that boundary verified at installation. Real host profiles and state are excluded from publication.

## Authority

- A Full Send grant covers the task's established test target and repair revisions. It is **not** production permission. Production needs explicit task-specific authority, except a FRIENDS or INTERNAL project's own production, which the owner's tier grant covers.
- Model review verdicts are not GitHub human approvals.
- Monitoring, retro and recipe generation grant no deployment, data or service authority.

## Known gaps

- `monitoring/devstack/install.py` points the hooks at the checkout that contains it (or `--root`). Moving the checkout breaks the hooks: the setup check reports the missing path as `FAIL`, and the installer names the old checkout and suggests `scripts/detach.py --from OLD_PATH`, which removes them.
- Codex older than about 0.160 skips async hooks, so that host records no Codex KPIs until Codex is updated. One-shot `claude -p` runs record no Stop receipt. Codex tool failures are unmeasured. See [known limits](setup.md#known-limits-observed-2026-10-28).
- Optional upstream comparison requires a separately available upstream source tree. It maps the pre-rename layout, brand and owner name and reports every remaining difference; importing changes stays manual ([sync procedure](setup.md#syncing-a-change-from-upstream)) and the team manifest does not track an installed private tree.
- The existing GIF is retained without regeneration. All nine decoded frames were inspected and OCR-scanned during this change, with no personal-name text found. The binary hash remains unchanged.
