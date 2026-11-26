---
name: babysit-pr
description: Watch an open PR through CI and review using native PR wakeups, route genuine failures and findings into focused repair and incremental re-review, and give a readiness verdict on the latest head before the mode's endpoint. Use after filing or updating a PR, or when asked to watch, babysit or shepherd a PR. Does not poll.
---

# Babysit PR

**Context.** Under a Patstack lead, only the PR-owning lead watches; the task keeps ownership and the exact next action while waiting. Invoked directly on a PR, watch it within the user's request; if fixes are needed, that is development work and follows Patstack's entry.

## Wait natively

Inspect current checks and handle existing review comments before waiting; T3 comment wakes cover only comments posted after the watch starts. When work is pending, call the exposed `watch_pull_request` tool and end the current turn; its event wakes the lead. Do not poll, sleep-loop or create a recurring job. If no durable wake mechanism exists, report that exact liveness gap instead of pretending an idle chat will resume.

## On each wake

1. Read the latest PR head, base, local CI record, mergeability and new review comments. A wake carries new state; it is not a verdict.
2. Classify each signal:
   - **Genuine failure or valid finding** → [implement's repair](../implement/SKILL.md#repair) → review of the repair (R1 after an R2 where [review](../review/SKILL.md#r2) allows it, otherwise at the selected level) → affected checks → push to the same PR.
   - **Flaky/infra/pre-existing** is a hypothesis: diagnose it with evidence before rerunning or dismissing. Sweep the same pattern within scope or record an owned risk with next action.
   - **Non-blocking suggestion** → follow-up note, no repair loop.
   - **Conflict with base** → update the branch under the project's Git permissions; no force-push without authority.
3. Keep the cumulative repair count and elapsed time; three failed normal cycles or earlier stagnation trigger deep diagnosis.
4. Re-establish the watch and end the turn while anything is pending.

## Readiness verdict

Ready only when, on the current head: CI passes (the agent's own `tools/local_ci.py` run on the head and the base's current commit, posted as its `Patstack-CI` record; no GitHub check is waited on: [CI](../patstack/references/coordination.md#merge)), the selected review level covers the head (after an R2, the author's R1 repair record counts within the limits in [review](../review/SKILL.md#r2): not when the reviewer asked for its own re-check, not at R3 and not in Full Stop) and its `Patstack-Review` records are on the PR, required acceptance/quality evidence is current, and no blocking finding is unresolved. Then, in Full Send, merge through the merge gate (`python3 tools/merge_gate.py merge --repo OWNER/NAME --pr N`, [merge rule](../patstack/references/coordination.md#merge)): it confirms the mode line, the review records for the head at the mode's minimum (Full Send R1, Full Stop R2) and CI before it merges that head. In Full Stop, run the gate's `check` instead and stop at the ready PR: a human merges it. [Full Send](../full-send/SKILL.md) continues test delivery within its grant; [Full Stop](../full-stop/SKILL.md) reports its handoff.

Repairs push to the slice's existing worktree and branch. After the PR merges, remove that worktree (`python3 tools/worktrees.py <repo> --apply` removes only merged, clean and pushed ones). For a [change set](../patstack/references/change-sets.md), check the declared merge order with `tools/changeset.py` before each merge.

Call the exposed `unwatch_pull_request` at handoff or completion so the thread returns to the owner. A Full Stop handoff whose merge will deploy says so and asks the owner to reply in the thread after merging; that reply, not the ended watch, resumes the lead for release verification. Model verdicts are not human GitHub approvals.
