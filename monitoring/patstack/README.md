# Private workflow KPIs

One Python standard-library recorder/reporter runs on Mac, devbox and Windows. Its SQLite cache is private to the host and derived from evidence; Ticket references only identify work; GitHub/briefs and native runtime evidence describe scope, progress and results. No task registry grants eligibility or authority. It works for development, research, testing and other workflows without creating tickets for casual work.

## Use

From this directory, run `python3 kpi_monitor.py report` (Windows uses `python`). The default store is `~/.local/state/patstack/kpis.sqlite3`; `--db PATH` selects a private test store. Reports stay private. No monitoring session, daemon or cron is required: existing lifecycle hooks record audit receipts, and the executing agent/auditor records outcome metadata. All three OS hosts use the same explicit snapshot interface.

`collect --host mac|devbox|windows` now reports `numbering_only` and performs no registry calls or writes. A ticket number has no completion/ownership state to collect. Historical registry observations remain preserved and labelled historical; they are excluded from workflow KPIs. Do not restart the old registry or infer success from a number.

For a Patstack task use `task_kpi.py start` at intake and `task_kpi.py finish --status … --verified yes|no|unknown` at the endpoint; it keeps the task's identity and revisions for you (`task_kpi.py --help`). For other workflow measurements, pipe **one metadata snapshot** to `python3 kpi_monitor.py record`. Give each user request/workflow instance a stable opaque ID, keep it across resume, and increment revision only for changed observations. Retries are idempotent; conflicting revisions reject. Do not create a new ID for phases or children. Host/environment identify the primary execution context; use node observations for checks in other layers, rather than cloning a completed request into every environment. A genuine separate request gets a new ID. Source audits must be traceable in the existing private ticket/run evidence, using this ID and revision.

Required fields: `id`, positive `revision`, `workflow`, `topic`, `mode` (`full_send`, `full_stop`, `other`), `status` (`open`, `completed`, `failed`, `handed_off`, `abandoned`, `cancelled`), timezone-aware `started_at`, `updated_at`. Reaching the agreed endpoint, including Full Stop’s ready-PR handover, is `completed` with `handoff: planned`; `handed_off` means unfinished work was transferred. Closed snapshots require `ended_at`; open snapshots have no end. Use the actual terminal event time, not a later comment timestamp.

Optional dimensions: `host` (`mac`, `devbox`, `windows`), `environment` (`local`, `pr_preview`, `test`, `stage`, `production`), `source` (safe metadata slug). Omitted dimensions become `unknown`. Expected hosts/environments with no workflow snapshots show `unmeasured`. Host stores are independent; Retro fetches each host report through approved SSH, not by opening its raw databases. Never sum the same request reported by two hosts.

Optional observations:

| Fields | Evidence required |
|---|---|
| `verified_success`, `human_interventions` | Acceptance and required proof; count unplanned human assistance, not merely user turns. Missing proof stays null. |
| `contacts`, `repeat_contact`, `followup_checked_at` | Contact tracking and actual follow-up observation. Successful FCR needs seven observed days after ending; a known failure, repeat contact or multiple contacts counts as failure immediately. |
| `handoff` | `none`, `planned`, `requested`, `unexpected`; classify using actual cause. Full Stop review is planned. |
| `support_eligible` | Explicitly declare when support deflection applies. Development completion is not support deflection. |
| `turns`, `questions`, `unsupported` | Observable counts/labels for the workflow, including boundaries. |
| `frustration_signal`, `frustration_confirmed` | Signals and confirmed user frustration separately. Capitals alone do not confirm rage. |
| `responses_reviewed`, `response_errors`, `hallucinations` | Audited response sample and labels; include broken logic in response errors. No audit means unknown, never zero. |
| `tool_calls`, `invalid_tool_calls`, `tool_failures` | Actual tool events; invalid invocation and runtime failure are separate. |
| `outputs_reviewed`, `outputs_kept` | Observed downstream/user retention, not assumed from output generation. |
| `nodes` | Up to 100 unique `{ "id": "live-proof", "status": "pass" }` observations (`pass`, `fail`, `blocked`, `not_run`). Node outcomes do not replace task acceptance. |

Use null/omit for unavailable labels. Labels/IDs are short safe slugs, never emails, free text, prompts, account names, URLs, tokens, payloads or vault notes. The recorder allowlists fields and rejects unknown ones, but cannot detect a secret disguised as an ID. Emitters are responsible for redaction. Unix files are owner-only; Windows inherits the user's profile ACLs and needs that boundary verified at installation.

## Metric interpretation

- Completion/resolution: verified success / observed terminal outcomes. Cancelled work is reported separately, excluded from outcomes. Show observed and eligible counts; partial samples must not be described as overall resolution.
- Autonomous resolution: the same for Full Send, with zero human interventions. Planned Full Stop work stays outside this denominator.
- Deflection: autonomous resolution among explicitly support-eligible workflows.
- FCR: verified success on one contact with no repeat within the observed seven-day window. Immature/untracked follow-up remains missing.
- Efficiency: mean/median completion time for verified successful completions; turns/questions/contacts with missing coverage. Wall time includes waits. `report --max-duration SECONDS` explicitly excludes long durations only; outcome denominators remain unchanged.
- Reliability: unexpected handoffs, unsupported requests, signal/confirmed frustration; observed response/tool errors and retention use their actual audited denominators.
- Breakdowns: workflow, topic, host, environment and node status. No automatic universal targets or unsupported industry benchmarks. Compare equivalent task types, modes, versions and workloads before claiming improvement.

Retro reads the relevant current host reports, investigates missing coverage and weak cohorts, then checks the underlying evidence before proposing/promoting an improvement. Self-reported compliance, model agreement and rising rates without denominators are insufficient. Monitoring never grants deployment/data authority.

Definitions informed by [Microsoft's agent metric reference](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/agent-business-value-metrics-reference) and [deflection definitions](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/deflection-overview); these support-specific definitions are adapted explicitly for development.

## Native audit hook

Install `audit-hook --host HOST --runtime codex|claude --event Stop|SessionEnd` using the client’s existing command-hook configuration. It reads the native session identity from stdin, stores a hash plus host/runtime/event timestamps and receipt counts, and ignores all message, tool, transcript-path and secret-bearing fields. It never opens a transcript. Stop receipts are turn boundaries, not completed tasks; retries can increase receipt count, so they are not request/turn denominators. SessionEnd is a lifecycle signal, not acceptance. Hook errors emit a fixed notice and return zero so telemetry cannot trap or stall development. Reports expose hook coverage separately from outcome audit coverage.

The hook requests evidence review through Retro’s report; it does not spawn a paid model, run CI, change task status, certify its own correctness or create a new ticket. Outcome/retention/error labels still require actual audit evidence. Native hook trust/loading must be verified per client; a shell smoke test alone does not establish client activation. Keep existing hooks intact.

Install with `python3 install.py --host mac` from a reviewed copy (devbox uses `--host devbox`; Windows uses `python install.py --host windows`). It backs up changed files privately, copies only this monitor package, updates the global KPI pointer and the existing Retro overlay, and appends its own Stop handler while preserving other hooks. Codex requires native `/hooks` trust for new definitions; the installer never edits trust hashes. This is an audit addition, not Patstack activation.

Current coverage: reference-only collection and the lifecycle hook do not emit semantic outcome labels. Those KPIs stay unmeasured until the executing agent/auditor records supported evidence through `record`. Lifecycle receipts expose current all-time coverage separately; `--as-of` applies to workflow snapshots, not retrospective hook reconstruction.
