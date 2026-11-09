---
name: babysit-pr
description: Watch an open PR through CI and review using native PR wakeups, route genuine failures and findings into focused repair and incremental re-review, and give a readiness verdict on the latest head before the mode's endpoint. Use after filing or updating a PR, or when asked to watch, babysit or shepherd a PR. Does not poll.
---

# Babysit PR

**Context.** Under a DevStack lead, only the PR-owning lead watches; the task keeps ownership and the exact next action while waiting. Invoked directly on a PR, watch it within the user's request; if fixes are needed, that is development work and follows DevStack's entry.

## Wait natively

Inspect current checks and handle existing review comments before waiting; T3 comment wakes cover only comments posted after the watch starts. When work is pending, call the exposed `watch_pull_request` tool and end the current turn; its event wakes the lead. Do not poll, sleep-loop or create a recurring job. If no durable wake mechanism exists, report that exact liveness gap instead of pretending an idle chat will resume.

## On each wake

1. Read the latest PR head, base, required checks, mergeability and new review comments. A wake carries new state; it is not a verdict.
2. Classify each signal:
   - **Genuine failure or valid finding** → [implement's repair](../implement/SKILL.md#repair) → incremental review at the selected level → affected checks → push to the same PR.
   - **Flaky/infra/pre-existing** is a hypothesis: diagnose it with evidence before rerunning or dismissing. Sweep the same pattern within scope or record an owned risk with next action.
   - **Non-blocking suggestion** → follow-up note, no repair loop.
   - **Conflict with base** → update the branch under the project's Git permissions; no force-push without authority.
3. Keep the cumulative repair count and elapsed time; three failed normal cycles or earlier stagnation trigger deep diagnosis.
4. Re-establish the watch and end the turn while anything is pending.

## Readiness verdict

Ready only when, on the current head: required CI passes, the selected review level covers the incremental diff and its `DevStack-Review` records are on the PR, required acceptance/quality evidence is current, and no blocking finding is unresolved. Then merge through the merge gate in either mode (`python3 tools/merge_gate.py merge --repo OWNER/NAME --pr N`, [merge rule](../devstack/references/coordination.md#merge)): it confirms the mode line, the review records for the head at the mode's minimum (Full Send R1, Full Stop R2) and CI before it merges that head. [Full Send](../full-send/SKILL.md) continues test delivery within its grant; [Full Stop](../full-stop/SKILL.md) reports its handoff.

Repairs push to the slice's existing worktree and branch. After the PR merges, remove that worktree (`python3 tools/worktrees.py <repo> --apply` removes only merged, clean and pushed ones). For a [change set](../devstack/references/change-sets.md), check the declared merge order with `tools/changeset.py` before each merge.

Call the exposed `unwatch_pull_request` at handoff or completion so the thread returns to the owner. Model verdicts are not human GitHub approvals.
