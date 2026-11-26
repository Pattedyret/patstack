---
name: patstack
description: Use for any request to change code, configuration, data or another development deliverable (fix, add, deploy, migrate, release, sync), when Full Send or Full Stop is invoked, or to continue an existing implementation, PR or delivery task. Not for questions, discussion, research or non-development writing such as emails. Coordinates the lead, mode and which Patstack modules run; not needed for unticketed discussion, research or a standalone module request.
---

# Patstack

Workflow version: **1.6.0**. BIG TASK is the lead agent, not a separate role or skill. One lead owns the requested outcome through verified handoff, using the smallest complete path. Patstack chooses mode, route and modules; each module owns its procedure. Modules return results to the lead and never invoke Patstack again.

A concrete request to change code, configuration or an agreed deliverable designates a task; the literal word TASK is not required. Discussion, research and casual testing stay outside development intake until such a request.

## Enter or resume

Bind the actual workspace, project procedures and existing task. For a designated task, load [coordination](references/coordination.md) to reuse or allocate its reference number and share its brief. Title the native chat `[TKT-…] Short title` as soon as the reference is known, and retitle a generic or continued thread when it turns out to belong to a reference (in T3: `t3_thread_update`). The title carries no status; progress lives in the [task list](#keep-the-owner-posted). Session starts create no development ticket; numbering imposes no eligibility, ownership or execution gate. Preserve its accepted spec and scope. The owner's latest explicit steering supersedes earlier constraints within retained authority gates. For project procedures, spec distribution or host choices, read [project context](references/project-context.md). When a project pack declares an intake context step, intake runs the pack's [product vault context](references/project-context.md#product-vault-context) step before planning; its light context pack (printed to stdout and saved in the task directory, never in the vault) goes into the task brief and every child brief. On long work or resume, read [task state](references/task-state.md); reconcile actual PR/build/release state before continuing. Work owned by someone else or stale work enters through [takeover](../takeover/SKILL.md) or [modernize](../modernize/SKILL.md).

## Choose the mode

Mode controls the owner's involvement and the endpoint. Size, urgency and review depth (R1/R2/R3) are separate choices; R3 does not by itself mean Full Stop.

The project's tier comes first. At intake run `python3 tools/project_tier.py --path <project>` from this workflow's checkout. Your private map decides when you have one, otherwise the one tier map a bundled project pack ships ([shape](../../examples/project-tiers.example.json)). CRITICAL and INTERNAL are the only classification choices; UNCLASSIFIED is the fallback.

**The owner** in this workflow is the person who asked for the task and runs its agents. Decisions, clearances and pings go to that person.

| Tier | Who a failure reaches | Mode |
|---|---|---|
| CRITICAL | Customers: products for consulting work or other customers | Evaluate Full Send or Full Stop, as below |
| INTERNAL | Any internal tool for your own team, including shared team tooling | Full Send always |
| UNCLASSIFIED | Not in the map | Evaluate as CRITICAL, and report the project so the owner can classify it |

Full Send always means the Full Stop triggers below do not apply: INTERNAL projects have no critical production, so nothing there stops for review, and Full Stop runs only when the owner asks for it on that task. The project's own production deployment is part of the task, under the owner's standing grant; name the tier in the PR's mode line. The grant covers only that project: a change that also deploys a CRITICAL or UNCLASSIFIED project follows that project's rules. Risk still raises review depth and proof (trust boundaries stay at least R2), and a tier never replaces the explicit authority for a destructive action (reset, reseed, force-push, deleting real data) or a stricter rule in the project itself.

- **[Full Send](../full-send/SKILL.md)** is the default: the lead owns routine decisions and continues through PR review, required CI/tests, the established authorized test deployment and real release proof.
- **[Full Stop](../full-stop/SKILL.md)**: the owner decides meaningful product/approach choices; the change gets an in-depth review (R2 or R3) published on the PR, the lead stops at the ready PR, and a human merges.
- The mode sets the minimum review before merge, always checked by the merge gate ([merge rule](references/coordination.md#merge)): Full Send at least R1 (R2 at trust boundaries, R3 rare), and the lead merges; Full Stop R2 or R3, and a human merges. Risk raises review depth and proof instead of stopping. On CRITICAL and UNCLASSIFIED projects, Full Stop is for what a revert cannot undo (production, destructive or irreversible data operations, a very large high-impact intake) or when the owner asks.
- At intake on those projects, Full Stop is chosen only for work a revert cannot undo or a very large high-impact intake (for example a broad rewrite of shared auth across products); explain the actual impact. Sensitive but revertible work stays Full Send with deeper review and proof. A cosmetic edit in such a repo does not qualify by filename alone.
- The owner's explicit Full Send for the task stays in effect within its scope and retained gates; its PRs merge through the merge gate under the merge rule; on a CRITICAL or UNCLASSIFIED project a change a revert cannot undo becomes Full Stop. Once selected, ordinary uncertainty or two viable technical options never switch the mode. A verified new high-impact dependency during execution raises review depth and, on a CRITICAL or UNCLASSIFIED project, gets one human checkpoint for that decision; unaffected work continues.

**Planning carries most of the work.** For a new feature or larger change, what to build is settled with the requester before anything is built. Planning is an interview stage: the lead reads the product knowledge, interviews critically in rounds, looking up what each answer names in the product knowledge before the next round and challenging vague or conflicting answers, until nothing about what to build is unclear, grills the draft plan and writes back what was settled ([to-spec](../to-spec/SKILL.md#plan-understand-interview-grill-the-plan)). The interview covers three things: everything in the product knowledge the lead does not understand or that the request conflicts with, the goal, and everything else that is unclear about what to build. A bounded fix and a new wish in a running thread get one short round on the same three things before building, whenever one of them is open; a tiny explicit edit gets none. This holds in both modes; Full Send's autonomy covers how to build, not guesses about what. **Quality is never an interview question.** Good UI and UX, thorough testing, performance on every system the product runs on and privacy are a standing bar on every task: the lead derives the targets from the task and the project and proves them ([quality](references/quality.md#the-standing-bar)). For how to build, research, check prior tasks and test assumptions where useful, then make and record the best supported in-scope choice. Significant new visual direction is presented as browser-viewable options for the owner's approval; an explicit requested colour/layout change is already directed.

## Route the work

| Task shape | Modules, in order | Notes |
|---|---|---|
| Tiny edit (copy, colour, small layout) | [ponytail](../ponytail/SKILL.md) → [implement](../implement/SKILL.md) direct → [review](../review/SKILL.md) R1 → [verify](../verify/SKILL.md) focused → file-pr/babysit-pr where the repo delivers through PRs → endpoint | No spec, subtickets, Council or benchmark matrix. Required repo checks still run. |
| Bounded bug fix or follow-up wish | one short [interview](../to-spec/SKILL.md#when-a-spec-is-needed) round when the goal or anything else is unclear → implement (reproduce first) → review R1/R2 by risk → verify → [file-pr](../file-pr/SKILL.md) → [babysit-pr](../babysit-pr/SKILL.md) → endpoint | Trust-boundary or data changes take at least R2. |
| Critical incident | implement critical path → review R2 (R3 if broad) in parallel → verify → file-pr → babysit-pr → endpoint → retro | Triage/route within ~5 min; no long spec first. |
| New feature / substantial change | [to-spec](../to-spec/SKILL.md) planning interview ([grilling](../grilling/SKILL.md) rounds and plan grilling) → spec → [to-tickets](../to-tickets/SKILL.md) only for real parallel slices → implement → review (R3 via [council](../council/SKILL.md)) → verify incl. quality → file-pr → babysit-pr → endpoint | Most of the effort goes into planning. Quality proof is part of the work, not later polish. |
| Someone else's work | takeover → earliest valid phase above | Reuse valid spec and credit. |
| Old PR / stale branch | modernize → continue, rework decision or closure recommendation | Relevance before rebasing. |
| One ticket across several repos | the row above per repo, as one [change set](references/change-sets.md): one `[TKT-…]` PR per repo, declared merge order, contract check before any consumer merges | Endpoint = every PR of the set merged in order and verified. |
| Failure at PR or live layer | implement Repair → review incremental → verify → babysit-pr | Same history and clock. |
| Choice only the owner can make | [grilling](../grilling/SKILL.md) | Facts are never the owner's question. |
| Missing/stale test recipe | [create-test-recipes](../create-test-recipes/SKILL.md) | Not for working coverage. |
| Shipped artifact/runtime analysis | [reverse-engineer-anything](../reverse-engineer-anything/SKILL.md) | Not for ordinary source reading. |
| Endpoint reached | [retro](../retro/SKILL.md), proportionate | The lead runs it and carries out its technical findings itself, without asking. [workflow-eval](../workflow-eval/SKILL.md) only when a workflow change needs it. A project pack that declares a retro write-back step adds that step; follow its procedure and required proof. |

Load a module when its step starts; do not preload every module. Take the earliest valid row when shapes overlap, and re-route if risk, scope or evidence changes.

When running in T3 Code, use its available native tools for the operation; read the [T3 tool routing](references/coordination.md#t3-code-tools) when choosing transport. This is the existing workflow using its host, not another skill or permission grant.

## Keep the owner posted

**The thread title is the ticket.** It stays `[TKT-…] Short title`, with no status in it.

**The native task list shows where the work is.** The lead keeps the whole plan in its client's native task list: in Claude Code its task tools (TaskCreate/TaskUpdate, or TodoWrite where that is the tool offered), in Codex `update_plan`. T3 and the terminal show the list in the thread. Create the list as soon as the route is chosen. Name the steps in the owner's words, from planning through the endpoint. For a feature that is, for example: read the product knowledge, interview, grill the plan, spec, build, review, PR and CI, stage, live check, retro. Update it every time a step starts or finishes, the plan changes, or the work starts waiting. Exactly one step is in progress. A wait names who or what it waits on in that step ("Waiting on you: questions 1–4", "CI on the PR"). A tiny edit gets a short list too. Children keep their own lists; the lead's list is the one the owner reads. With a board configured, the lead sends the same list with [`tools/task_steps.py`](../../tools/task_steps.py) (`[x]` done, `[>]` in progress, `[ ]` to come, one line of proof after ` | `). It never pings, and an owner who uses Tally sees it as the task's progress.

**Pings and the board.** The lead, and only the lead, also sends the task's status at each phase with [`tools/task_status.py`](../../tools/task_status.py). That reaches the owner's phone and board and mirrors the status to the ticket. The line it prints is not put in the title.

| Status | Set it when | Ping |
|---|---|---|
| 🟡 `IN PROGRESS` | Building, PR review and CI | No |
| 🔵 `DEPLOYED ON STAGE` | It is on the test target and the owner can test now; pass `--url` | Yes |
| 🟣 `REVIEW` | The lead checks the live release, while the owner may test too. It never waits for the owner | No |
| ⚪ `RETRO` | Live proof holds and the retro runs | No |
| 🟢 `DONE` | After the endpoint's proof is reported | Quiet |
| 🔴 `WAITING ON YOU` | At any step, when only the owner can unblock it, or the task ended without its proof | Loud |
| ⏸ `PARKED` | Put aside on purpose to come back to; `--note` says why and what resumes it | No |

Set `DEPLOYED ON PROD` in place of the stage status when a task deploys straight to its own production and that release is verified: the owner reads it as done, so while any proof or work remains, use `REVIEW`. Go from `IN PROGRESS` to `REVIEW` when nothing deploys. When a live check fails after the owner was pinged, set `IN PROGRESS` with `--ping` and a note saying not to test yet. An owner's bug report in the thread returns the task to `IN PROGRESS`. A deployed status needs `--url`, the exact page to test, or `--how` when there is no web page. Pass `--pr owner/repo#12` once a PR exists; project, host and thread are filled in when known. A failed ping is reported and never stops the task. Titles and notes carry no secrets.

Everything only the owner can settle must reach them in a form they can act on. Ask a decision or clearance with the native question tool (in T3, the agent's ask-the-user question) with concrete options, the recommended one first; an owner who uses Tally sees it in Tally's To do as a one-tap answer. For an action only the owner can take, such as a login, a payment or a test, set `WAITING ON YOU` with `--note` naming that exact action. Never leave a question for the owner only in chat text. Status words name the step the work is on.

On a CRITICAL project (customer work), the owner tells the customer before work reaches stage. Before a task's first deploy to stage, ask with the question tool: header `Stage`, question `Ready for stage: <title>`, then on a new line two to four plain sentences the owner can send the customer (what changes for them; no ticket numbers, tools, model names or internals), options `Deploy to stage` (recommended) and `Hold`. Deploy only after `Deploy to stage`; on `Hold`, set `PARKED` with the reason. INTERNAL projects deploy without asking.

## Common references

Load only when the step needs them: [coordination](references/coordination.md) (reference numbers, native delegation, delivery authority), [task state](references/task-state.md) (long runs/resume), [project context](references/project-context.md) (project packs, hosts), [access](references/access.md) (BW Locker/login), [quality](references/quality.md) (targets and evidence), [sources](references/sources.md) (provenance and module map), [change sets](references/change-sets.md) (one ticket across repos).

## Invariants the lead keeps

- Changes are committed only in the task's own worktree, never in a repo's shared main checkout ([implement](../implement/SKILL.md#parallel-slices)); the branch is confirmed before each commit and push.
- One lead and one child layer. Children receive the brief in [coordination](references/coordination.md), preserve others' edits and start no agents or top-level chats. Small work stays direct.
- Evidence is labelled EXECUTED, OBSERVED or REASONED and bound to the exact head/build/release. Model agreement is not execution proof. Missing required proof is not completion.
- Determine applicable delivery surfaces from the task and project configuration; missing access is a blocker, not absence. If no remote, PR, CI or deployment applies, the committed and re-verified head is the endpoint: report it as done. Otherwise complete every applicable delivery requirement, and report genuinely absent surfaces as not applicable. **CI is never absent and never added on GitHub:** every repo's CI is its own script, run by the lead on the task's PR ([CI](references/coordination.md#merge)). A repo without the script gets one in the same PR, with no question to the owner. No repo gains a GitHub Actions workflow, and a repo the tier map lists under `local_ci` keeps none.
- Author repair is complete when every finding is fixed or answered with evidence on the committed, re-tested head. When requested, mark the PR ready for review yourself and request required re-review. This author action grants no approval or deployment authority; merging follows the [merge rule](references/coordination.md#merge) (Full Send: the lead merges through the merge gate after at least R1; Full Stop: after R2 or R3 the PR stays ready and a human merges), and final readiness still requires current checks and the selected review.
- Local refs are not evidence of remote state. Before judging CI presence, PR or branch status, merged-or-not, drift or what is on the default branch, fetch first ([`tools/freshness.py`](../../tools/freshness.py) `--fetch` runs `git fetch --prune` and reports age and ahead/behind) or ask the remote (`gh`). Fast-forward only a clean checkout on its default branch; never pull or merge into a dirty tree ([details](references/project-context.md#fetch-before-judging)).
- On CRITICAL and UNCLASSIFIED projects, Full Send grants the established test target only. There, production, and in every tier destructive data/Git actions and explicitly retained human gates need their actual authority.
- Failures at PR or live layers use one repair flow with cumulative attempts and time; three failed normal cycles or earlier stagnation trigger deeper diagnosis and workflow RCA, never automatic abandonment or a new task.
- Native wakeups handle waits; checkpoints preserve work rather than ending it. Complete only after the actual endpoint, evidence, proportionate retro and a final comment.
- Modules invoked without a Patstack task run inside the user's request only: they create no ticket and grant no permission. Standalone retro, research, review and evaluation stay unticketed unless the owner designates development.
