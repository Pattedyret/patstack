# Status and limits

What is true for this publication, as of 2026-10-27. Labels: **EXECUTED** means code or assertions ran and passed; **OBSERVED** means the real behavior was seen; **REPORTED** means stated by the source owner and not reproducible from this package; **NOT DONE** means it has not happened.

## Activation

**Installed** means files and links are in place and setup checks pass. **Discovered** means a fresh client session lists the skills. **Runtime-proven** means a real task ran through the workflow and its proof was observed. These are separate claims.

| Layer | Claim | Status |
|---|---|---|
| 1.2.0 publication | All 19 skills plus reference-only numbering; 52 approved source files | **EXECUTED:** exact source parity, privacy/provenance/links/formats, 26 KPI tests, 5 numbering tests and 19 package controls pass. |
| 1.2.0 installation | Updated source and numbering tool installed on Mac, devbox and Windows | **NOT YET CLAIMED.** Awaiting actual host evidence. |
| 1.2.0 native discovery | Fresh Claude Code and Codex sessions discover the updated catalog | **NOT YET CLAIMED.** File parity alone is insufficient. |
| Historical 1.1.0 | Earlier installation and fresh discovery of 19 skills on all three hosts, with 49 source files matching | **REPORTED** by the root lead in the preceding rollout. This is historical evidence, not 1.2.0 activation proof. |
| Historical monitoring | Earlier KPI config/command smoke checks, real Claude Stop receipts on Mac and devbox | **REPORTED** by the root lead. Does not prove native Windows or Codex hook loading. |
| Runtime | A full development task run end to end under the updated workflow on each host | **NOT CLAIMED.** |
| Runtime | Codex hook trust on every host | **UNPROVEN.** The real trust gate is preserved. |
| Runtime | Unattended overnight runs | **NOT GUARANTEED.** A durable wake source and actual tool/login readiness must be verified per task. |
| UI | A T3 progress bar or taskbar phase display | **NOT IMPLEMENTED.** Phases use native plans and checkpoints; there is no progress-bar setter. |

Numbering works independently of a task registry. The retired registry and its historical records are private preserved data, not an installation prerequisite or a Windows blocker. Host-specific test results must still be observed on the actual OS.

## What this package verifies

| Check | Status |
|---|---|
| KPI recorder unit tests (`monitoring/patstack/test_kpi_monitor.py`) | **EXECUTED** by `scripts/check.py` |
| Example KPI snapshot records and reports through the real recorder | **EXECUTED** by `scripts/check.py` |
| Relative links and anchors, privacy scan, JSON/SVG parsing, skill frontmatter | **EXECUTED** by `scripts/check.py` |
| All 52 source files, including all 19 skills/resources, match the recorded published hashes with exact coverage | **EXECUTED** by `scripts/check.py`. See [SOURCE-MANIFEST.json](../SOURCE-MANIFEST.json). |
| Full source/publication parity | `refresh_from_source.py --check` recomputes source and transformed hashes, exact coverage and actual published bytes. Consumers can repeat this check against the exact approved source tree; a passing package check does not establish host activation. |
| Mutation and privacy negative controls | **EXECUTED** by `scripts/check.py`: omitted/extra resources, changed source/output, stale manifests, privacy anchors/values and broken links fail as expected. |
| Workflow SVG renders as intended | **OBSERVED** in a headless browser, light and dark themes, at 1200 px |
| Walkthrough HTML: autoplay advances, Pause stops, reduced motion starts paused, no horizontal overflow at 390 px in dark mode | **OBSERVED** in a headless browser |
| Animated README preview | **EXECUTED:** 9 distinct feature-route frames, 960 × 550 px, 36-second loop, 143,274 bytes; local headless-browser screenshots differ after 4.5 seconds, proving playback advances. **OBSERVED:** representative exported frames are readable with no clipped content. Illustrative workflow only; GitHub playback awaits publication. |
| Mermaid diagram in the README renders on GitHub | **Not verified locally.** No Mermaid renderer was available offline. |
| Host installation, retirement and native client tests | Separate source-owner evidence; private rollout helpers and runtime state are not part of this package |

## Monitoring reality

- **Hooks:** lifecycle hooks record audit receipts (hashed session identity, host, runtime, event counts), not outcomes, prompts or transcripts. Native loading and trust require actual client evidence; shell/config checks are separate.
- **Historical discovery:** old `agent-work` discovery remains historical/retired. It is not required for numbering, task entry or Retro.
- **Outcomes:** verified success, interventions, response/tool errors and other semantic KPIs stay **unmeasured** until an executing agent or auditor records explicit labelled snapshots supported by evidence.
- **Private state:** Unix stores use owner-only access; Windows stores inherit the user profile ACLs and need that boundary verified at installation. Real host profiles and state are excluded from publication.

## Authority

- A Full Send grant covers the task's established test target and repair revisions. It is **not** production permission. Production needs explicit task-specific authority.
- Model review verdicts are not GitHub human approvals.
- Monitoring, retro and recipe generation grant no deployment, data or service authority.

## Known gaps

- `monitoring/patstack/install.py` targets the source setup's directory layout. Plain checkouts should wire the hook manually ([setup](setup.md#6-kpi-recorder-and-audit-hook-optional)).
- The skills address their owner by name in a few rules (for example retained human gates). Replace the name when adopting them.
