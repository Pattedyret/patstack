# Status and limits

What is true for this publication, as of 2026-10-27. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means the real behavior was seen; **REPORTED** means stated by the source owner and not reproducible from this package; **NOT DONE** means it has not happened.

## Activation

**Installed** means files and links are in place and setup checks pass. **Discovered** means a fresh client session lists the skills. **Runtime-proven** means a real task ran through the workflow and its proof was observed. These are separate claims.

| Layer | Claim | Status |
|---|---|---|
| 1.2.0 publication | All 19 skills plus reference-only numbering; 52 approved source files | **EXECUTED:** exact source parity, privacy/provenance/links/formats, 26 KPI tests, 5 numbering tests and 19 package controls pass. |
| 1.2.0 installation | Updated source and numbering tool installed on Mac, devbox and Windows | **REPORTED** by the rollout lead: 93 / 98 / 95 installation targets respectively; exact 52-file canonical source parity and all 19 native skill mirrors checked. |
| 1.2.0 native discovery | Fresh actual Claude Code and Codex initialization catalogs contain all 19 skills on every host | **REPORTED** by the rollout lead. Initialization only; no model turns were sent. Existing GUI sessions are not assumed reloaded. |
| Historical 1.1.0 | Earlier installation and fresh discovery of 19 skills on all three hosts, with 49 source files matching | **REPORTED** by the root lead in the preceding rollout. This is historical evidence, not 1.2.0 activation proof. |
| Historical monitoring | Earlier KPI config/command smoke checks, real Claude Stop receipts on Mac and devbox | **REPORTED** by the root lead. Does not prove native Windows or Codex hook loading. |
| Runtime | A full development task run end to end under the updated workflow on each host | **NOT CLAIMED.** |
| Runtime | Codex hook trust on every host | **UNPROVEN.** The real trust gate is preserved. |
| Runtime | Unattended overnight runs | **NOT GUARANTEED.** A durable wake source and actual tool/login readiness must be verified per task. |
| UI | A T3 progress bar or taskbar phase display | **NOT IMPLEMENTED.** Phases use native plans and checkpoints; there is no progress-bar setter. |

Numbering works independently of a task registry. The retired registry and its historical records are private preserved data, not an installation prerequisite or a Windows blocker. Host-specific test results must still be observed on the actual OS.

## Reported host rollout evidence

These are actual host checks reported by the rollout lead, separate from the checks this publication runs locally. Catalog totals include unrelated native/project skills; Patstack contributes the same 19 on every host.

| Host | Installation targets | Fresh Codex catalog | Fresh Claude Code catalog | Native checks reported |
|---|---:|---:|---:|---|
| Mac | 93 | 68 total; all 19 present | 131 total; all 19 present | 19 cutover/transaction tests, 26 KPI tests; isolated launcher init/new passes |
| devbox | 98 | 58 total; all 19 present | 130 total; all 19 present | 5 numbering tests, 8 cutover tests; isolated launcher init/new passes |
| Windows | 95 | 46 total; all 19 present | 69 total; all 19 present | 5 numbering tests, 8 cutover tests; isolated launcher init/new passes |

All 52 canonical source hashes match the reviewed source hashes in [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json) across the three hosts. All 19 native skill mirrors were checked, including Windows' required external Markdown-link adaptation. Publication still transforms exactly the three documented private paragraphs; source parity does not mean those private paragraphs are published.

Known legacy runtime bindings were retired with private rollback archives: three Mac launchd jobs were stopped and their plists archived; seven devbox unit/timer names were stopped and their unit/enabling links archived. The old board listener is closed on all three hosts. Known legacy hook bindings removed: 11 on Mac, 10 on devbox and none on Windows. Retained config/hook content matches the expected transformation, retained Codex hook positions were checked, and cached legacy hook paths were neutralized. The old CLI returns a retirement notice with exit code 64 on Mac and devbox; Windows had no old adapter.

Private counters use distinct issuer slots above the combined historical high-water mark. No real new-task reference was issued during rollout; launcher tests used isolated stores. Historical records remain private and preserved. Native configuration trust was not edited. Device data and credentials are not published, and production was untouched.

Independent Opus review produced conditional findings, which the rollout lead reports fixing and checking with native regressions. There is no unconditional Opus approval of the final bytes. An additional Sol review could not run because of capacity; no substitute model was presented as that review. Executed test evidence remains separate from model judgments.

## What this package verifies

| Check | Status |
|---|---|
| KPI recorder unit tests (`monitoring/patstack/test_kpi_monitor.py`) | **EXECUTED** by `scripts/check.py` |
| Example KPI snapshot records and reports through the real recorder | **EXECUTED** by `scripts/check.py` |
| Relative links and anchors, privacy scan, JSON/SVG parsing, skill frontmatter | **EXECUTED** by `scripts/check.py` |
| All 52 source files, including all 19 skills/resources, match the recorded published hashes with exact coverage | **EXECUTED** by `scripts/check.py`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). |
| Full source/publication parity | `refresh_from_source.py --check` recomputes source and transformed hashes, exact coverage and actual published bytes. **EXECUTED** against the installed Mac source with zero drift across all 52 files. Other-host parity is reported above. A passing package check alone does not establish host activation. |
| Mutation and privacy negative controls | **EXECUTED** by `scripts/check.py`: omitted/extra resources, changed source/output, stale manifests, privacy anchors/values and broken links fail as expected. |
| Workflow SVG renders as intended | **OBSERVED** in a headless browser, light and dark themes, at 1200 px |
| Walkthrough HTML: autoplay advances, Pause stops, reduced motion starts paused, no horizontal overflow at 390 px in dark mode | **OBSERVED** in a headless browser |
| Animated README preview | **EXECUTED:** 9 distinct feature-route frames, 960 × 550 px, 36-second loop, 143,274 bytes; local headless-browser screenshots differ after 4.5 seconds, proving playback advances. **OBSERVED:** representative exported frames are readable with no clipped content. Illustrative workflow only; playback inside GitHub itself is not browser-verified. |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** No Mermaid renderer was available offline. |
| Host installation, retirement and native client tests | Separate source-owner evidence; private rollout helpers and runtime state are not part of this package |

## Monitoring reality

- **Hooks:** lifecycle and tool hooks record audit receipts (hashed session identity, host, runtime, event counts: turns, tool calls and, for Claude, tool failures), not outcomes, prompts, tool data or transcripts. A SessionStart hook shows a one-line setup status in every session. Native loading and trust require actual client evidence. Shell and config checks are separate.
- **Historical discovery:** old `agent-work` discovery remains historical/retired. It is not required for numbering, task entry or Retro.
- **Outcomes:** verified success, interventions and other semantic KPIs stay **unmeasured** until the lead records them with `task_kpi.py` (`start` at intake, `finish` at the endpoint, `once` for unticketed requests), backed by evidence. The setup check warns about completed tasks without a recorded outcome.
- **Private state:** Unix stores use owner-only access; Windows stores inherit the user profile ACLs and need that boundary verified at installation. Real host profiles and state are excluded from publication.

## Authority

- A Full Send grant covers the task's established test target and repair revisions. It is **not** production permission. Production needs explicit task-specific authority.
- Model review verdicts are not GitHub human approvals.
- Monitoring, retro and recipe generation grant no deployment, data or service authority.

## Known gaps

- `monitoring/patstack/install.py` targets the source setup's directory layout. Plain checkouts wire the hooks in the exact form shown in [setup step 6](setup.md#6-session-status-kpi-hooks-and-outcomes).
- Codex older than about 0.160 skips async hooks, so that host records no Codex KPIs until Codex is updated. One-shot `claude -p` runs record no Stop receipt. Codex tool failures are unmeasured. See [known limits](setup.md#known-limits-observed-2026-10-28).
- The skills address their owner by name in a few rules (for example retained human gates). Replace the name when adopting them.
