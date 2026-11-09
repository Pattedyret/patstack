# Private workflow KPIs

One Python standard-library recorder/reporter runs on your hosts, for example Mac, Linux devbox and Windows. Its SQLite cache is private to the host and derived from evidence; Ticket references only identify work; GitHub/briefs and native runtime evidence describe scope, progress and results. No task registry grants eligibility or authority. It works for development, research, testing and other workflows without creating tickets for casual work.

## Use

From this directory, run `python3 kpi_monitor.py report` (Windows uses `python`). The default store is `~/.local/state/devstack/kpis.sqlite3`; `--db PATH` selects a private test store. Reports stay private. No monitoring session, daemon or cron is required: existing lifecycle hooks record audit receipts, and the executing agent/auditor records outcome metadata. All supported host categories use the same explicit snapshot interface.

`collect --host mac|devbox|windows` now reports `numbering_only` and performs no registry calls or writes. A ticket number has no completion/ownership state to collect. Historical registry observations remain preserved and labelled historical; they are excluded from workflow KPIs. Do not restart the old registry or infer success from a number.

**Topic per project.** A development task records `topic=<repo-or-project-slug>`: the repo name (for example `auth-api`), or the project slug when a [change set](../../skills/devstack/references/change-sets.md) spans several repos. `task_kpi.py` rejects uppercase, spaces and generic words such as `general` or `misc`, so Retro can compare KPIs per repo or project. Unticketed `once` records keep a free slug.

For a DevStack task use `task_kpi.py start` at intake and `task_kpi.py finish --status … --verified yes|no|unknown --handoff none|planned|requested|unexpected --pack none|<pack>` at the endpoint (`--handoff` is required: an unset handoff leaves `unexpected_handoff_pct` unknown for the window; `--pack` is required: a pack's `tools/finish_rules.py` states what its completed tasks must record, and `none` is refused for a topic a pack claims); it keeps the task's identity and revisions for you (`task_kpi.py --help`). For other workflow measurements, pipe **one metadata snapshot** to `python3 kpi_monitor.py record`. Give each user request/workflow instance a stable opaque ID, keep it across resume, and increment revision only for changed observations. Retries are idempotent; conflicting revisions reject. Do not create a new ID for phases or children. Host/environment identify the primary execution context; use node observations for checks in other layers, rather than cloning a completed request into every environment. A genuine separate request gets a new ID. Source audits must be traceable in the existing private ticket/run evidence, using this ID and revision.

Required fields: `id`, positive `revision`, `workflow`, `topic`, `mode` (`full_send`, `full_stop`, `other`), `status` (`open`, `completed`, `failed`, `handed_off`, `abandoned`, `cancelled`), timezone-aware `started_at`, `updated_at`. Reaching the agreed endpoint is `completed`; a Full Stop that ends at the ready PR because production or destructive-data authority is missing is `completed` with `handoff: planned`; `handed_off` means unfinished work was transferred. Closed snapshots require `ended_at`; open snapshots have no end. Use the actual terminal event time, not a later comment timestamp.

`verification` (`required`, `not_applicable`) says whether a closed snapshot needs a `verified_success` label. `task_kpi.py start` and `finish` write `required` for designated tasks, and `once` writes `not_applicable` for unticketed discussion, research and testing requests, which have no verification step. A snapshot without the marker, from an older store, counts as `not_applicable` when its workflow is `discussion`, `research` or `testing`, and as `required` otherwise. The report's `overall.verification_missing` counts closed snapshots that need the label but lack it, and `scripts/setup_doctor.py` warns only on those. `task_completion_rate` is unchanged and still shows every terminal outcome.

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
| `slices`, `review_rounds` | Delivery slices (worktrees/PRs) the task used and review rounds until the final verdict, from the task's own record; `task_kpi.py finish --slices N --review-rounds N`. Not recorded stays missing, never zero. |
| `nodes` | Up to 100 unique `{ "id": "live-proof", "status": "pass" }` observations (`pass`, `fail`, `blocked`, `not_run`). Node outcomes do not replace task acceptance. A repo without CI records `ci=not_run` ("no CI configured; proof is local only"). Project packs that declare vault context and write-back steps require tasks to record `vault-context=pass|blocked|not_run`, `vault-sufficient`, `vault-writeback` and, on a gap, `context-search` for the [product vault context](../../skills/devstack/references/project-context.md#product-vault-context) step. |

Use null/omit for unavailable labels. Labels/IDs are short safe slugs, never emails, free text, prompts, account names, URLs, tokens, payloads or vault notes. The recorder allowlists fields and rejects unknown ones, but cannot detect a secret disguised as an ID. Emitters are responsible for redaction. Unix files are owner-only; Windows inherits the user's profile ACLs and needs that boundary verified at installation.

## Metric interpretation

- Completion/resolution: verified success / observed terminal outcomes. Cancelled work is reported separately, excluded from outcomes. Show observed and eligible counts; partial samples must not be described as overall resolution.
- Autonomous resolution: the same for Full Send, with zero human interventions. Planned Full Stop work stays outside this denominator.
- Deflection: autonomous resolution among explicitly support-eligible workflows.
- FCR: verified success on one contact with no repeat within the observed seven-day window. Immature/untracked follow-up remains missing.
- Efficiency: mean/median completion time for verified successful completions; turns/questions/contacts with missing coverage. Wall time includes waits. `report --max-duration SECONDS` explicitly excludes long durations only; outcome denominators remain unchanged.
- Reliability: unexpected handoffs, unsupported requests, signal/confirmed frustration; observed response/tool errors and retention use their actual audited denominators.
- Breakdowns: workflow, topic, host, environment and node status. Every breakdown carries its own slices, review rounds and node counts, so `by_topic` shows per repo/project verified success, slices, review rounds and missing CI (`nodes.ci.not_run`). Targets are the owner's, never automatic or borrowed industry benchmarks (see [Targets and hill-climbing](#targets-and-hill-climbing)). Compare equivalent task types, modes, versions and workloads before claiming improvement.

**Opt-in sharing.** `kpi_monitor.py export --aggregate` prints counts only per topic/workflow/status/host (counts, verified yes/no/unknown, mode counts, slice and review-round totals with their observed counts, missing CI), with the as-of day and no IDs, timestamps or free text. A team member may share that file by choice; topics are repo or project slugs, so check them before sharing. Never share the store or `report` output.

Retro reads the relevant current host reports, investigates missing coverage and weak cohorts, then checks the underlying evidence before proposing/promoting an improvement. Self-reported compliance, model agreement and rising rates without denominators are insufficient. Monitoring never grants deployment/data authority.

Definitions informed by [Microsoft's agent metric reference](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/agent-business-value-metrics-reference) and [deflection definitions](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/deflection-overview); these support-specific definitions are adapted explicitly for development.

## Targets and hill-climbing

The KPIs exist to reach goals the owner sets. Put them in `~/.config/devstack/kpi-targets.json`, shaped like [`examples/kpi-targets.example.json`](../../examples/kpi-targets.example.json): `">=N"` or `"<=N"` per metric.

- **`work`** (real tasks that ended in the last `work_days`, default 7): `tasks`, `verified_success_pct`, `autonomous_resolution_pct`, `unexpected_handoff_pct`, `median_minutes`, `review_rounds_mean`, `verification_missing`, `ci_missing`.
- **`node:<id>`** in `work`: the pass rate of a proof node over the tasks that recorded it (every recorded status counts, so `not_run` is a miss), for example `node:vault-context` and `node:vault-writeback` for how well a project's tasks read and update its product vault, `node:vault-sufficient` for how often the vault answered everything, and `node:context-search` for how many gaps the search filled.
- **`packs.<pack>`**: targets a project pack's own tool evaluates, for example a pack whose vault tools measure how much of the project the vault covers and whether its notes still match the repos (see the pack's own docs).
- **`bench`** (the newest benchmark scoreboard, arm `bench_arm`, default `devstack`): `overall`, `resultat`, `feller`, `aerlighet`, `sikkerhet`, `kvalitet`, `security_holes_pct` (share of runs with any leaked secret or forbidden action), `median_minutes`, `median_cost_usd`, `median_turns`, `loaded_pct`, `kpi_correct_pct`.

`kpi_monitor.py scorecard` prints every target as PASS, MISS (with the gap left) or UNKNOWN (not measured, never counted as met); `--json` for tools. Values are compared exactly, so one security hole in 201 runs still misses `<=0`. A work rate needs at least `min_samples` observations (default 3) and shows its `n`; below that it is UNKNOWN. An incomplete benchmark run leaves its bench values UNKNOWN. The scorecard appears in two places, and only there:

- **at the end of a designated development task**: `task_kpi.py finish` prints it on stderr, and the lead's final report ends with it. Research, discussion and testing answers never carry it;
- **in each benchmark scoreboard**, per arm.

`setup_doctor.py` also lists it as the `kpi targets` row, but the session-start status line leaves it out.

A missed target becomes work when the owner asks for it: [workflow-eval's hill-climb](../../skills/workflow-eval/SKILL.md#5-hill-climb-to-the-owners-targets) measures, changes one thing in a candidate, re-measures A/B and lets `bench/bench.py gate` decide KEEP, REVERT or TOP until every target is met or the climb plateaus. KEEP is a Pareto step: every target measured in both arms, no gap grows (a missed security target cannot get worse in exchange for speed) and at least one shrinks.

## Native audit hook

Install `audit-hook --host HOST --runtime codex|claude --event Stop|SessionEnd` using the client’s existing command-hook configuration. It reads the native session identity from stdin, stores a hash plus host/runtime/event timestamps and receipt counts, and ignores all message, tool, transcript-path and secret-bearing fields. It never opens a transcript. Stop receipts are turn boundaries, not completed tasks; retries can increase receipt count, so they are not request/turn denominators. SessionEnd is a lifecycle signal, not acceptance. Hook errors emit a fixed notice and return zero so telemetry cannot trap or stall development. Reports expose hook coverage separately from outcome audit coverage.

The hook requests evidence review through Retro’s report; it does not spawn a paid model, run CI, change task status, certify its own correctness or create a new ticket. Outcome/retention/error labels still require actual audit evidence. Native hook trust/loading must be verified per client; a shell smoke test alone does not establish client activation. Keep existing hooks intact.

Install with `python3 install.py --host mac` from a reviewed checkout (devbox uses `--host devbox`; Windows uses `python install.py --host windows`). By default the hooks point at this checkout; `--root PATH` selects another setup tree and copies only this monitor package there. It backs up changed files privately under `~/.local/state/devstack/install-backups/`, updates the global KPI pointer (and an existing Retro overlay in a setup tree that has one), and appends its own Stop handler while preserving other hooks. Codex requires native `/hooks` trust for new definitions; the installer never edits trust hashes. This is an audit addition, not DevStack activation.

Current coverage: reference-only collection and the lifecycle hook do not emit semantic outcome labels. Those KPIs stay unmeasured until the executing agent/auditor records supported evidence through `record`. Lifecycle receipts expose current all-time coverage separately; `--as-of` applies to workflow snapshots, not retrospective hook reconstruction.
