# Status and limits

What is true for this publication, as of 2026-10-26. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means the real behavior was seen; **REPORTED** means stated by the source owner and not reproducible from this package; **NOT DONE** means it has not happened.

## Activation

| Claim | Status |
|---|---|
| Patstack is the live workflow on the owner's hosts | **NOT DONE.** This package mirrors the agreed cutover candidate. Activation is a separate step. |
| Unattended overnight runs are ready on every host | **NOT CLAIMED.** Hook trust, registry coverage and secret-safe login must be verified per host first. |
| A T3 progress bar or taskbar phase display | **NOT IMPLEMENTED.** Phases are visible through native plans and checkpoints only. No progress-bar setter exists today; this is a possible future UI integration. |

## What this package verifies

| Check | Status |
|---|---|
| KPI recorder unit tests (`monitoring/patstack/test_kpi_monitor.py`) | **EXECUTED** by `scripts/check.py` |
| Example KPI snapshot records and reports through the real recorder | **EXECUTED** by `scripts/check.py` |
| Relative links and anchors, privacy scan, JSON/SVG parsing, skill frontmatter | **EXECUTED** by `scripts/check.py` |
| Published files match the recorded source hashes | **EXECUTED** by `scripts/check.py`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). |
| Workflow SVG renders as intended | **OBSERVED** in a headless browser, light and dark themes, at 1200 px |
| Walkthrough HTML: autoplay advances, Pause stops, reduced motion starts paused, no horizontal overflow at 390 px in dark mode | **OBSERVED** in a headless browser |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** No Mermaid renderer was available offline. |
| The source candidate's full test suite (registry, migration, hosts) | **REPORTED** passing by the source owner; those tests and the registry are not part of this package |

## Monitoring reality

- **Hooks:** lifecycle hooks record audit receipts (hashed session identity, host, runtime, event counts). They do not record outcomes, prompts or transcripts. Earlier installs on three hosts are **REPORTED**. Hook loading must be verified in each client: native Codex hook trust is not verified on every host.
- **Discovery:** registry discovery (`collect`) is supported on macOS and Linux hosts only. Retro refreshes it when reading the report.
- **Outcomes:** semantic KPIs (verified success, interventions, response or tool errors) stay **unmeasured** until an agent or auditor records labelled snapshots with evidence.
- **Windows:** there is **no native Windows registry adapter**, and no Unix registry has been ported. Windows uses explicit snapshots only. The source owner **REPORTS** four native Windows OS tests passing (Python UTF-8 mode off) and junction-safe metadata copying. Native Windows Computer Use facts are kept in the private host profile.

## Authority

- A Full Send grant covers the task's established test target and repair revisions. It is **not** production permission. Production needs explicit task-specific authority.
- Model review verdicts are not GitHub human approvals.
- Monitoring, retro and recipe generation grant no deployment, data or service authority.

## Known gaps

- The task registry is described by contract only; you need your own implementation for durable ownership.
- `monitoring/patstack/install.py` targets the source setup's directory layout. Plain checkouts should wire the hook manually ([setup](setup.md#6-kpi-recorder-and-audit-hook-optional)).
- The skills address their owner by name in a few rules (for example retained human gates). Replace the name when adopting them.
