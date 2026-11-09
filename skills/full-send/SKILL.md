---
name: full-send
description: Full Send mode for a designated development task - the lead owns routine decisions and continues hands-off through PR review, required CI/tests, the established authorized test deployment and real release verification. Use when the owner invokes Full Send, as the default DevStack mode, and always on FRIENDS and INTERNAL projects. Grants no production access on CRITICAL or unclassified projects.
---

# Full Send

Full Send decides the owner's involvement and the endpoint, not task size or review depth. A tiny edit in Full Send stays tiny; a risky change still gets R2/R3.

**Context.** Runs under a DevStack lead with an owned task. Invoked directly for development with no owner yet, apply DevStack's entry (ownership, project binding) first and continue here.

## Own the answer

1. Use the brief, project conventions and prior relevant tasks/decisions.
2. Resolve unresolved facts through source, the actual runtime, primary research or a cheap discriminating experiment, whichever fits. These are options, not a mandatory research ceremony.
3. If ordinary uncertainty remains, choose the safest useful, reversible in-scope default. Record the assumption and validate the outcome. Prefer an existing approved product/design pattern when taste is unsettled.
4. Do not ask the owner about routine architecture, technical targets, equivalent implementation options or facts the lead can establish.

Proceeding under uncertainty means a defensible action that is then checked. It never means calling missing proof a pass, bypassing permissions, guessing the target environment or ignoring a failed security/acceptance check. Failures enter [implement's repair loop](../implement/SKILL.md#repair); an exhausted ordinary approach calls for a new hypothesis, not abandonment or another interview.

## Gates Full Send keeps

- Significant new visual direction: browser-viewable alternatives for the owner's approval.
- Preference changes to the shared workflow involve the owner.
- Production on CRITICAL and unclassified projects, destructive/out-of-scope actions in every tier and stricter project gates keep their actual permissions. Reuse approvals already given.
- Full Send merges its own ready PR through the merge gate under the [merge rule](../devstack/references/coordination.md#merge) once at least R1 (R2 at trust boundaries) covers the head; a sensitive change gets deeper review and proof, not a stop. On a CRITICAL or unclassified project, a change that a revert cannot undo continues as Full Stop, with R2 or R3 before the merge.
- Vault unlock/MFA that no available authorized mechanism can complete is an access dependency ([access](../devstack/references/access.md)), not a product question.
- On a CRITICAL or unclassified project, a verified new high-impact dependency (sensitive auth/permissions, important shared API, broad customer impact) gets one human checkpoint for that decision. Ordinary uncertainty does not qualify. Continue unaffected work while it waits.

## Test-delivery authority

The owner assigning a concrete task in Full Send (explicit or default) authorizes that task's established, unambiguous test target and its repair revisions. Record the real task grant, target and applicable head in the Issue/PR/brief, preserving the project's real approval mechanism and [coordination's delivery rules](../devstack/references/coordination.md#delivery-and-authority).

Authority record: `DevStack 1.4.0 Full Send (explicit|default)` naming the actual mode basis, established target and retained project gates in the task record. This is evidence of the real grant, not an actor-role or ticket-registry approval. Quote the real assignment with its native reference; never relabel a default as an explicit stage instruction. Full Stop and ordinary research do not supply this grant. An auto-deploying merge is a deployment. Production needs explicit task-specific authority, except on FRIENDS and INTERNAL projects, where the owner's standing tier grant covers the project's own production ([tiers](../devstack/SKILL.md#choose-the-mode)).

## Endpoint

Continue until all hold: acceptance met on the intended test release, required review and CI cover the current head, required project sync verified, live proof bound to the actual release ([verify](../verify/SKILL.md)), then proportionate [retro](../retro/SKILL.md) and a final comment. A checkpoint, child completion, PR opening or third ordinary repair failure is not completion.

Stop short only for a retained human gate, a genuine unavailable prerequisite or an applicable execution limit. Then hand off Done / Verified / Unresolved / Next, naming the exact decision or prerequisite, and keep the task in its real waiting lifecycle rather than faking delivery.
