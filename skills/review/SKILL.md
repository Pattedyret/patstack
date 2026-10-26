---
name: review
description: Choose and run the right review depth for a candidate change - R1 focused author check, R2 fresh opposite-model independent review, or R3 two-model council - with separate acceptance and code verdicts and security scrutiny at trust boundaries. Use before PR readiness, after a repair, or when asked to review a diff. Review never replaces executed tests.
---

# Review

**Context.** Under a Patstack lead, review the task's exact candidate against its spec version and record the level on the task/PR. Invoked directly on a diff, review it within the user's request; no ticket is created, and your own reading is REASONED evidence.

## Select the level

The lead chooses the lowest sufficient level from the actual change, uncertainty and blast radius, without asking Patrick, subject to project-required review and human gates.

| Level | Who and what | Typical fit |
|---|---|---|
| **R1 Focused** | Author checks the diff and targeted result. No separate reviewer, Council, score or loop. Label it author/self-review. | Trivial cosmetic/layout, copy or mechanical edits with understood local effects and no behavior/security/data change. |
| **R2 Independent** | One fresh opposite-model reviewer (Opus work → Sol; Sol work → Opus) checks acceptance and implementation quality with the relevant risks and proof. | Bounded behavior fixes, ordinary features, local API/data logic. **Minimum** for auth/permissions, credentials, shell handling user input, untrusted files, authenticated API calls, production databases, data integrity, destructive operations or important API contracts, with independent security scrutiny of that boundary. |
| **R3 Council** | [council](../council/SKILL.md): fresh Opus and Sol, independent first, then evidence-backed cross-examination. | Broad/high-impact auth or API changes, migrations/irreversible effects, cross-project/shared-system impact, substantial customer-facing change, unresolved material uncertainty or disagreement. |

- Select provisionally at intake, confirm against the actual diff, raise it if new risk appears. A legitimate scope reduction can lower it with a stated reason; rejected findings, time pressure or an unavailable reviewer cannot.
- Record level, short reason and reviewed revision, e.g. `R1 - CSS-only button colour change; no behavior, data or auth changes.`
- An unticketed research/discussion question needs no review level. Every level keeps the applicable quality standard, required repo checks and delivery proof.

## R1

Read the whole diff against the request. Check the targeted result and, for UI, the intended appearance and affected responsive/interaction/accessibility states. Fix what you find; no review loop.

## R2

1. The lead starts a fresh session of the opposite model family that wrote none of the candidate, via the native delegation route in [coordination](../patstack/references/coordination.md#delegate-and-communicate); a child asks its lead for review instead of spawning one. Use the actual model; no silent substitution.
2. Brief it with the task, relevant context, exact head/diff and evidence access. Do not include the author's persuasive summary or any prior score.
3. It returns two distinct verdicts plus findings:
   - **Acceptance:** does the requested behavior work, including counterexamples?
   - **Code:** is this implementation correct, maintainable and safe in this system?
   - Each finding: claim, severity, evidence or reproduction, suggested fix.
4. Blocking findings go to [implement's repair](../implement/SKILL.md#repair). A fresh non-author assessment covers the incremental diff; the author cannot carry an earlier independent approval forward.

## Independence rules

- The author is never the independent reviewer of its own work; independence belongs to the session and its contribution, not just the model name.
- If Opus and Sol both implemented parts, cross-review the contributed areas and have a fresh non-author session cover integration seams. Do not force two complete reviews of every slice.
- Model verdicts are not GitHub human approvals and not execution proof. Agreement between models is not a test result.
- If a required reviewer model is unavailable: continue reversible work, try a verified alternate host/runtime with the same model, never downgrade the level. Otherwise mark the PR not ready, keep the check missing and set one next-attempt event within the task's timebox; hand off at expiry. Do not poll indefinitely.
- Technical disagreement is resolved with evidence, not by asking Patrick; [grilling](../grilling/SKILL.md) is only for choices that are his.
