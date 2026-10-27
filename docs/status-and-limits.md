# Status and limits

What is true for this publication, as of 2026-10-27. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means the real behavior was seen; **REPORTED** means stated by the source owner and not reproducible from this package; **NOT DONE** means it has not happened.

## Activation

Three layers are kept apart. **Installed** means files and links are in place and the setup checker passes. **Discovered** means a fresh client session lists the skills. **Runtime-proven** means a real task ran through the workflow and its proof was observed. Rows marked REPORTED come from the owner's real hosts; this package cannot reproduce them.

| Layer | Claim | Status |
|---|---|---|
| Baseline 1.0 | Installed on Mac, devbox and Windows; fresh Claude Code and Codex catalogs received on all three | **REPORTED** historical baseline evidence. Does not prove the modular candidate is active. |
| Modular 1.1.0 | Exactly 19 required callable skills; Chirp/Xirp remain optional external app aliases | **EXECUTED** package validation; **REPORTED** installed on all three hosts by the root lead. |
| Modular 1.1.0 | Fresh Claude Code and Codex initialization catalogs on Mac, devbox and Windows each contain all 19 | **REPORTED** actual native discovery; no model turn or application task was sent. Codex entries are enabled, without discovery errors. |
| Modular 1.1.0 | All 49 source files match across the three hosts; all migration targets match their installed journals | **REPORTED** exact byte-hash and journal checks. Only the three documented private paragraphs are sanitized for publication. |
| Modular 1.1.0 | Mac and devbox setup checks, catalog/context/KPI/PR-to-Retro tests | **REPORTED**: 21 globals including two optional aliases, 25 roles; 19/11/25/21 focused tests pass on each. |
| Native T3 tools | Existing Patstack, File PR, Babysit PR and Verify instructions route to available native tools | **REPORTED** instruction-only update on all three hosts (five files, plus Windows mirrors). Opposite-model review matched live tool contracts; this is not proof of every tool or an end-to-end delivery. |
| Modular migration | Reversible additive installation and rollback, preservation of native/project/client state, concurrent edits and name collisions | **REPORTED**: six local tests pass with host subcases; five selected tests pass on native Windows, including its dangling-link case. |
| Private host profile | Windows ACL restricted to owner, SYSTEM and Administrators; POSIX hosts use mode 0600 | **REPORTED** baseline host evidence; actual profiles are excluded. |
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
| All 19 skills/resources match the recorded published hashes with exact coverage | **EXECUTED** by `scripts/check.py`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). |
| Full source/publication parity | `refresh_from_source.py --check` recomputes source and transformed hashes, exact coverage and actual published bytes. The root lead verified installed-source parity after activation; consumers can repeat the same check against their accessible source. |
| Mutation and privacy negative controls | **EXECUTED** by `scripts/check.py`: omitted/extra resources, changed source/output, stale manifests, privacy anchors/values and broken links fail as expected. |
| Workflow SVG renders as intended | **OBSERVED** in a headless browser, light and dark themes, at 1200 px |
| Walkthrough HTML: autoplay advances, Pause stops, reduced motion starts paused, no horizontal overflow at 390 px in dark mode | **OBSERVED** in a headless browser |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** No Mermaid renderer was available offline. |
| The source setup's broader test suite (registry, migration, hosts) | **REPORTED** passing by the source owner; those tests and the registry are not part of this package |

## Monitoring reality

- **Configured-hook smoke:** all six client/host configurations contain the KPI handler; isolated-database receipt assertions pass for each. This is source-owner **REPORTED** command/config evidence, separate from native client loading.
- **Native Claude Stop:** real native Stop receipts on Mac and devbox are **REPORTED** by the root lead. This does not establish native Windows or Codex hook loading.
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
