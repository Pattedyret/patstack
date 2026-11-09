---
name: devstack
description: Use for any request to change code, configuration, data or another development deliverable (fix, add, deploy, migrate, release, sync), when Full Send or Full Stop is invoked, or to continue an existing implementation, PR or delivery task. Not for questions, discussion, research or non-development writing such as emails. Coordinates the lead, mode and which DevStack modules run; not needed for unticketed discussion, research or a standalone module request.
---

# DevStack

Workflow version: **1.4.0**. BIG TASK is the lead agent, not a separate role or skill. One lead owns the requested outcome through verified handoff, using the smallest complete path. DevStack chooses mode, route and modules; each module owns its procedure. Modules return results to the lead and never invoke DevStack again.

A concrete request to change code, configuration or an agreed deliverable designates a task; the literal word TASK is not required. Discussion, research and casual testing stay outside development intake until such a request.

## Enter or resume

Bind the actual workspace, project procedures and existing task. For a designated task, load [coordination](references/coordination.md) to reuse or allocate its reference number and share its brief. Title the native chat `[TKT-…] Short title` as soon as the reference is known, and retitle a generic or continued thread when it turns out to belong to a reference (in T3: `t3_thread_update`). Session starts create no development ticket; numbering imposes no eligibility, ownership or execution gate. Preserve its accepted spec and scope. The owner's latest explicit steering supersedes earlier constraints within retained authority gates. For project procedures, spec distribution or host choices, read [project context](references/project-context.md). When a project pack declares an intake context step, intake runs the pack's [product vault context](references/project-context.md#product-vault-context) step before planning; its light context pack (printed to stdout and saved in the task directory, never in the vault) goes into the task brief and every child brief. At intake record the private KPI start with `python3 monitoring/devstack/task_kpi.py start --id TKT-… --workflow <slug> --topic <repo-or-project-slug> --mode full_send|full_stop --host mac|devbox|windows` (Windows: `python`); resuming reuses it and it creates no ticket ([workflow KPI metadata](../../monitoring/devstack/README.md)). On long work or resume, read [task state](references/task-state.md); reconcile actual PR/build/release state before continuing. Work owned by someone else or stale work enters through [takeover](../takeover/SKILL.md) or [modernize](../modernize/SKILL.md).

## Choose the mode

Mode controls the owner's involvement and the endpoint. Size, urgency and review depth (R1/R2/R3) are separate choices; R3 does not by itself mean Full Stop.

The project's tier comes first. At intake run `python3 tools/project_tier.py --path <project>` from this workflow's checkout; the owner's private map decides ([shape](../../examples/project-tiers.example.json)).

| Tier | Who a failure reaches | Mode |
|---|---|---|
| CRITICAL | Customers: products for consulting work or other customers | Evaluate Full Send or Full Stop, as below |
| FRIENDS | Real people, but internal use for the owner and friends | Full Send always |
| INTERNAL | Only the owner | Full Send always |
| UNCLASSIFIED | Not in the map | Evaluate as CRITICAL, and report the project so the owner can classify it |

Full Send always means the Full Stop triggers below do not apply: FRIENDS and INTERNAL projects have no critical production, so nothing there stops for review, and Full Stop runs only when the owner asks for it on that task. The project's own production deployment is part of the task, under the owner's standing grant; name the tier in the PR's mode line. The grant covers only that project: a change that also deploys a CRITICAL or UNCLASSIFIED project follows that project's rules. Risk still raises review depth and proof (trust boundaries stay at least R2), and a tier never replaces the explicit authority for a destructive action (reset, reseed, force-push, deleting real data) or a stricter rule in the project itself.

- **[Full Send](../full-send/SKILL.md)** is the default: the lead owns routine decisions and continues through PR review, required CI/tests, the established authorized test deployment and real release proof.
- **[Full Stop](../full-stop/SKILL.md)**: the owner decides meaningful product/approach choices; the change gets an in-depth review (R2 or R3) before the lead merges it.
- The mode sets the minimum review before the lead merges, always through the merge gate ([merge rule](references/coordination.md#merge)): Full Send at least R1 (R2 at trust boundaries, R3 rare), Full Stop R2 or R3. Risk raises review depth and proof instead of stopping. On CRITICAL and UNCLASSIFIED projects, Full Stop is for what a revert cannot undo (production, destructive or irreversible data operations, a very large high-impact intake) or when the owner asks.
- At intake on those projects, Full Stop is chosen only for work a revert cannot undo or a very large high-impact intake (for example a broad rewrite of shared auth across products); explain the actual impact. Sensitive but revertible work stays Full Send with deeper review and proof. A cosmetic edit in such a repo does not qualify by filename alone.
- The owner's explicit Full Send for the task stays in effect within its scope and retained gates; its PRs merge through the merge gate under the merge rule; on a CRITICAL or UNCLASSIFIED project a change a revert cannot undo becomes Full Stop. Once selected, ordinary uncertainty or two viable technical options never switch the mode. A verified new high-impact dependency during execution raises review depth and, on a CRITICAL or UNCLASSIFIED project, gets one human checkpoint for that decision; unaffected work continues.

Research, check prior tasks and test assumptions where useful, then make and record the best supported in-scope choice. Significant new visual direction is presented as browser-viewable options for the owner's approval; an explicit requested colour/layout change is already directed.

## Route the work

| Task shape | Modules, in order | Notes |
|---|---|---|
| Tiny edit (copy, colour, small layout) | [ponytail](../ponytail/SKILL.md) → [implement](../implement/SKILL.md) direct → [review](../review/SKILL.md) R1 → [verify](../verify/SKILL.md) focused → file-pr/babysit-pr where the repo delivers through PRs → endpoint | No spec, subtickets, Council or benchmark matrix. Required repo checks still run. |
| Bounded bug fix | implement (reproduce first) → review R1/R2 by risk → verify → [file-pr](../file-pr/SKILL.md) → [babysit-pr](../babysit-pr/SKILL.md) → endpoint | Trust-boundary or data changes take at least R2. |
| Critical incident | implement critical path → review R2 (R3 if broad) in parallel → verify → file-pr → babysit-pr → endpoint → retro | Triage/route within ~5 min; no long spec first. |
| New feature / substantial change | [to-spec](../to-spec/SKILL.md) → [to-tickets](../to-tickets/SKILL.md) only for real parallel slices → implement → review (R3 via [council](../council/SKILL.md)) → verify incl. quality → file-pr → babysit-pr → endpoint | Quality proof is part of the work, not later polish. |
| Someone else's work | takeover → earliest valid phase above | Reuse valid spec and credit. |
| Old PR / stale branch | modernize → continue, rework decision or closure recommendation | Relevance before rebasing. |
| One ticket across several repos | the row above per repo, as one [change set](references/change-sets.md): one `[TKT-…]` PR per repo, declared merge order, contract check before any consumer merges | Endpoint = every PR of the set merged in order and verified. |
| Failure at PR or live layer | implement Repair → review incremental → verify → babysit-pr | Same history and clock. |
| Choice only the owner can make | [grilling](../grilling/SKILL.md) | Facts are never the owner's question. |
| Missing/stale test recipe | [create-test-recipes](../create-test-recipes/SKILL.md) | Not for working coverage. |
| Shipped artifact/runtime analysis | [reverse-engineer-anything](../reverse-engineer-anything/SKILL.md) | Not for ordinary source reading. |
| Endpoint reached | [retro](../retro/SKILL.md), proportionate | [workflow-eval](../workflow-eval/SKILL.md) only when a workflow change needs it. A project pack that declares a retro write-back step adds that step; follow its procedure and required proof nodes. |

Load a module when its step starts; do not preload every module. Take the earliest valid row when shapes overlap, and re-route if risk, scope or evidence changes.

When running in T3 Code, use its available native tools for the operation; read the [T3 tool routing](references/coordination.md#t3-code-tools) when choosing transport. This is the existing workflow using its host, not another skill or permission grant.

## Keep the owner posted

The lead, and only the lead, sets the task's status at each step with [`tools/task_status.py`](../../tools/task_status.py) and puts the line it prints in its native thread title (T3: `t3_thread_update`). The status says where the work is; the native thread status only says the agent's turn ended. It lives in the title, so it adds no status database. In a thread holding several tasks, the title shows the active one.

| Status | Set it when | Ping |
|---|---|---|
| 🟡 `IN PROGRESS` | Building, PR review and CI | No |
| 🔵 `DEPLOYED ON STAGE` | It is on the test target and the owner can test now; pass `--url` | Yes |
| 🟣 `REVIEW` | The lead checks the live release, while the owner may test too. It never waits for the owner | No |
| ⚪ `RETRO` | Live proof holds and the retro runs | No |
| 🟢 `DONE` | After `task_kpi.py finish --verified yes`; refused without that proof | Quiet |
| 🔴 `WAITING ON YOU` | At any step, when only the owner can unblock it, or the task ended without its proof | Loud |

Set `DEPLOYED ON PROD` in place of the stage status when a task deploys straight to its own production, and go from `IN PROGRESS` to `REVIEW` when nothing deploys. When a live check fails after the owner was pinged, set `IN PROGRESS` with `--ping` and a note saying not to test yet. An owner's bug report in the thread returns the task to `IN PROGRESS`. A deployed status needs `--url`, the exact page to test, or `--how` when there is no web page. Pass `--pr owner/repo#12` once a PR exists; project, host and thread are filled in when known. A failed ping is reported and never stops the task. Titles and notes carry no secrets.

## Common references

Load only when the step needs them: [coordination](references/coordination.md) (reference numbers, native delegation, delivery authority), [task state](references/task-state.md) (long runs/resume), [project context](references/project-context.md) (project packs, hosts), [access](references/access.md) (BW Locker/login), [quality](references/quality.md) (targets and evidence), [sources](references/sources.md) (provenance and module map), [change sets](references/change-sets.md) (one ticket across repos).

## Invariants the lead keeps

- One lead and one child layer. Children receive the brief in [coordination](references/coordination.md), preserve others' edits and start no agents or top-level chats. Small work stays direct.
- Evidence is labelled EXECUTED, OBSERVED or REASONED and bound to the exact head/build/release. Model agreement is not execution proof. Missing required proof is not completion.
- Determine applicable delivery surfaces from the task and project configuration; missing access is a blocker, not absence. If no remote, PR, CI or deployment applies, the committed and re-verified head is the endpoint: report it as done. Otherwise complete every applicable delivery requirement, and report genuinely absent surfaces as not applicable. **Missing CI is never N/A:** a repo with a remote but no CI is reported as the risk "no CI configured; proof is local only" and recorded with `--node ci=not_run`; [create-test-recipes](../create-test-recipes/SKILL.md) may propose a minimal CI from `examples/ci/`, added only with the repo owner's agreement.
- Author repair is complete when every finding is fixed or answered with evidence on the committed, re-tested head. When requested, mark the PR ready for review yourself and request required re-review. This author action grants no approval or deployment authority; merging follows the [merge rule](references/coordination.md#merge) (the lead merges through the merge gate: Full Send after at least R1, Full Stop after R2 or R3), and final readiness still requires current checks and the selected review.
- Local refs are not evidence of remote state. Before judging CI presence, PR or branch status, merged-or-not, drift or what is on the default branch, fetch first ([`tools/freshness.py`](../../tools/freshness.py) `--fetch` runs `git fetch --prune` and reports age and ahead/behind) or ask the remote (`gh`). Fast-forward only a clean checkout on its default branch; never pull or merge into a dirty tree ([details](references/project-context.md#fetch-before-judging)).
- On CRITICAL and UNCLASSIFIED projects, Full Send grants the established test target only. There, production, and in every tier destructive data/Git actions and explicitly retained human gates need their actual authority.
- Failures at PR or live layers use one repair flow with cumulative attempts and time; three failed normal cycles or earlier stagnation trigger deeper diagnosis and workflow RCA, never automatic abandonment or a new task.
- Native wakeups handle waits; checkpoints preserve work rather than ending it. Complete only after the actual endpoint, evidence, proportionate retro, the recorded KPI outcome and a final comment. When the owner has set targets, `finish` prints the KPI scorecard; the final report ends with it and names each missed target with its gap. Record the outcome with `task_kpi.py finish --id TKT-… --status completed|failed|handed_off|abandoned|cancelled --verified yes|no|unknown --handoff none|planned|requested|unexpected --pack none|<pack>` (`--handoff` is required, `none` when no human had to take over; `--pack` is required, and a named project pack's own rules then judge a completed task's proof nodes) plus `--slices N --review-rounds N`, using `--status completed --handoff planned` for a Full Stop that ends at the ready PR for missing production or destructive-data authority and `--node <proof>=pass|fail|blocked|not_run` per required proof; `yes` needs that proof, and missing proof is `unknown`, never `yes`.
- Modules invoked without a DevStack task run inside the user's request only: they create no ticket and grant no permission. Standalone retro, research, review and evaluation stay unticketed unless the owner designates development.
