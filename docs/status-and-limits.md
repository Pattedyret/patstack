# Status and limits

What is true for this publication, as of 2026-10-26. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means the real behavior was seen; **REPORTED** means stated by the source owner and not reproducible from this package; **NOT DONE** means it has not happened.

## Activation

Three layers are kept apart. **Installed** means files and links are in place and the setup checker passes. **Discovered** means a fresh client session lists the skills. **Runtime-proven** means a real task ran through the workflow and its proof was observed. Rows marked REPORTED come from the owner's real hosts; this package cannot reproduce them.

| Layer | Claim | Status |
|---|---|---|
| Installed | r5 snapshots applied: Mac 118 targets, devbox 139, Windows 48 | **REPORTED** |
| Installed | Setup checker passes on Mac and devbox (5 global skills, 25 roles); task-registry integrity check OK on both | **REPORTED** |
| Installed | Devbox checker found a duplicate same-path pack label and an alias-name mismatch. Both were corrected in a separate reversible transaction; 25 migration tests pass and the checker is green. | **REPORTED** |
| Installed | Private host profile: on Windows the ACL is limited to the owner account, SYSTEM and Administrators; POSIX hosts use mode 0600 | **REPORTED** |
| Discovered | Fresh Codex and Claude Code initialize catalogs received on all three hosts without model turns (catalog sizes as reported: Mac 52/116, devbox 42/115, Windows 30/94) | **REPORTED** |
| Discovered | Mac and devbox catalogs list all 5 global skills and no retired or project-scoped skills | **REPORTED** |
| Discovered | Windows native catalogs list the 3 core global skills and no retired or project-scoped globals; app-managed Chirp/Xirp is unavailable on this host | **REPORTED** |
| Runtime | Devbox isolated headless Chromium DOM smoke test passes | **REPORTED.** Proves browser infrastructure readiness only, not any feature or auth behavior. |
| Runtime | A full development task run end to end under Patstack on each host | **NOT CLAIMED** |
| Runtime | Native task registry on Windows | **NOT SUPPORTED.** No adapter and no Unix registry port. |
| Runtime | Codex hook trust on every host | **UNPROVEN.** The real trust gate is preserved, not bypassed. |
| Runtime | Unattended overnight runs | **NOT GUARANTEED.** Hook trust, registry coverage and secret-safe login must be verified per host first. |
| UI | A T3 progress bar or taskbar phase display | **NOT IMPLEMENTED.** Phases are visible through native plans and checkpoints only. No progress-bar setter exists today; this is a possible future UI integration. |

## What this package verifies

| Check | Status |
|---|---|
| KPI recorder unit tests (`monitoring/patstack/test_kpi_monitor.py`) | **EXECUTED** by `scripts/check.py` |
| Example KPI snapshot records and reports through the real recorder | **EXECUTED** by `scripts/check.py` |
| Relative links and anchors, privacy scan, JSON/SVG parsing, skill frontmatter | **EXECUTED** by `scripts/check.py` |
| Published files match the recorded source hashes | **EXECUTED** by `scripts/check.py`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). |
| Published skill and KPI bytes are unchanged by the r5 apply | **EXECUTED**: `refresh_from_source.py --check` reports no drift against both the cutover candidate and the installed Mac setup |
| Workflow SVG renders as intended | **OBSERVED** in a headless browser, light and dark themes, at 1200 px |
| Walkthrough HTML: autoplay advances, Pause stops, reduced motion starts paused, no horizontal overflow at 390 px in dark mode | **OBSERVED** in a headless browser |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** No Mermaid renderer was available offline. |
| The source candidate's full test suite (registry, migration, hosts) | **REPORTED** passing by the source owner; those tests and the registry are not part of this package |

## Monitoring reality

- **Configured-hook smoke:** all six client/host configurations contain the KPI handler; isolated-database receipt assertions pass for each. This is source-owner **REPORTED** command/config evidence, separate from native client loading.
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
