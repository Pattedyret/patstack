---
name: full-stop
description: Full Stop mode for a designated development task - the owner stays involved at meaningful product or approach decisions, the change gets an in-depth review (R2 or R3) published on the PR, and once that review and CI cover the exact head the lead stops at the ready PR for the owner to check and a human to merge, reporting Done/Verified/Unresolved/Next. Use when the owner invokes Full Stop, or on a CRITICAL or unclassified project when the change cannot be undone by a revert (production, destructive or irreversible data operations) or Patstack classifies a high-impact task Full Stop at intake. INTERNAL projects run Full Stop only when the owner asks.
---

# Full Stop

Full Stop is hands-on for decisions that matter and in-depth in review, not slower for everything else. Size and urgency are chosen separately; review is R2, or R3 for broad, irreversible or high-impact changes. A critical task can use the fast path and still keep Full Stop checkpoints.

**Context.** Runs under a Patstack lead with an owned task. Invoked directly for development with no owner yet, apply Patstack's entry (ownership, project binding) first and continue here.

## What the owner decides

Meaningful product and approach choices: user-visible behavior or copy, product rules (who may do what), significant visual direction, data/permission tradeoffs, irreversible or broad-impact design choices. Use [grilling](../grilling/SKILL.md) for these.

The lead still resolves observable facts and ordinary implementation details autonomously: tooling, file layout, test persona already established by the project, equivalent technical options, parallelism.

## Human checkpoint form

One message per decision point, batching everything currently open: the decision, evidence, recommendation, consequences of each option and the work that continues meanwhile. Never a vague "please confirm". Continue independent work while waiting; record the pending decision on the task.

## Endpoint

1. Build and verify as the route requires ([implement](../implement/SKILL.md), [verify](../verify/SKILL.md)); review at R2, or R3 ([council](../council/SKILL.md)) for broad, irreversible or high-impact changes ([review](../review/SKILL.md)).
2. [File the PR](../file-pr/SKILL.md) with the `Patstack-Author:` header line and the Done / Verified / Unresolved / Next handoff in its [evidence comment](../file-pr/SKILL.md#evidence-comment), and [babysit](../babysit-pr/SKILL.md) it until required checks and the R2/R3 review records cover the current head.
3. Stop at the ready PR; a human merges it. Publish the R2/R3 findings on the PR, confirm with `python3 tools/merge_gate.py check --repo OWNER/NAME --pr N` that the [merge rule](../patstack/references/coordination.md#merge) holds for the head, and set `WAITING ON YOU` with `--note` naming the PR to check and merge. The lead never merges a Full Stop PR, and the gate's `merge` refuses one. A merge that deploys to production or applies a destructive or irreversible data operation still needs that explicit authority quoted on the PR. Full Stop supplies no further delivery grant. When the merge will auto-deploy to the established test target, the handoff also asks the owner to reply in the thread once merged: that reply resumes the lead, which verifies the release there. The handoff promises no automatic wake, because the PR watch ends at handoff. Any other deployment needs its own grant.
4. Report Done / Verified / Unresolved / Next with PR link, reviewed head (and merged head once a human has merged), review level and evidence labels.

A deployment-bound task keeps its real waiting lifecycle after handoff; never fake delivery to complete it. Retro runs proportionately once the Full Stop endpoint is reached.
