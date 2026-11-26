---
name: review
description: Choose and run the right review depth for a candidate change - R1 focused author check, R2 fresh independent review (opposite model, or the same provider under a reviewer lens), or R3 council - with separate acceptance and code verdicts and security scrutiny at trust boundaries. Use before PR readiness, after a repair, or when asked to review a diff. Review never replaces executed tests.
---

# Review

**Context.** Under a Patstack lead, review the task's exact candidate against its spec version and record the level on the task/PR. Invoked directly on a diff, review it within the user's request; no ticket is created, and your own reading is REASONED evidence.

## Select the level

The lead chooses the lowest sufficient level from the actual change, uncertainty and blast radius, without asking the owner, subject to project-required review and human gates.

| Level | Who and what | Typical fit |
|---|---|---|
| **R1 Focused** | Author checks the diff and targeted result. No separate reviewer, Council, score or loop. Label it author/self-review. | Trivial cosmetic/layout, copy or mechanical edits with understood local effects and no behavior/security/data change. |
| **R2 Independent** | One fresh opposite-model reviewer (between the two configured model families, the person's `reviewPair` in `~/.config/patstack/preferences.json`; default: Opus work → Sol, Sol work → Opus) checks acceptance and implementation quality with the relevant risks and proof. With only one provider available, a fresh session of that provider under a [reviewer lens](references/lenses.md). | Bounded behavior fixes, ordinary features, local API/data logic. **Minimum** for auth/permissions, credentials, shell handling user input, untrusted files, authenticated API calls, production databases, data integrity, destructive operations or important API contracts, with independent security scrutiny of that boundary. |
| **R3 Council** | [council](../council/SKILL.md): fresh sessions from the two configured model families (default: Opus and Sol), or with one provider two sessions under the two [lenses](references/lenses.md), independent first, then evidence-backed cross-examination. | Broad/high-impact auth or API changes, migrations/irreversible effects, cross-project/shared-system impact, substantial customer-facing change, unresolved material uncertainty or disagreement. |

- Select provisionally at intake, confirm against the actual diff, raise it if new risk appears. A legitimate scope reduction can lower it with a stated reason; rejected findings, time pressure or an unavailable reviewer cannot.
- Record level, short reason and reviewed revision, e.g. `R1 - CSS-only button colour change; no behavior, data or auth changes.`
- **Mode floor.** Full Send needs at least R1 (R2 where this table's minimum applies; R3 is rare). Full Stop needs R2 or R3. The [merge gate](../patstack/references/coordination.md#merge) enforces the floor.
- **Record the verdict on the PR.** Each review session posts its verdict for the exact head as a separate PR comment whose whole body is one line, with findings in another comment: `Patstack-Review: level=R2 verdict=approve|block head=<sha> reviewer=<provider/model> session=<id>`, plus ` lens=independent|adversary` when the session ran under a [lens](references/lenses.md); the author posts R1. Without a record for the current head, the gate treats the review as not done.
- **Sensitive data and auth:** a change touching authentication, sessions, proxies or credential forwarding, permission/RLS policies, or health, patient or other special-category personal data takes **at least R2** and records (1) a written data classification in the PR (which data, its class, who may read/write it, where it flows) and (2) a permission test with an allowed (positive) and a denied (negative) persona on the changed path. Project packs may map repos/paths to these classes (risk map) and name the test personas. Classify by actual behavior: a copy change on a login page is not an auth change.
- An unticketed research/discussion question needs no review level. Every level keeps the applicable quality standard, required repo checks and delivery proof.

## R1

Read the whole diff against the request. Check the targeted result and, for UI, the intended appearance and affected responsive/interaction/accessibility states. Fix what you find; no review loop.

## R2

1. The lead starts a fresh session of the opposite model family that wrote none of the candidate, via the native delegation route in [coordination](../patstack/references/coordination.md#delegate-and-communicate); a child asks its lead for review instead of spawning one. Use the actual model; no silent substitution. When the opposite family is not available to this person or host, start a fresh session of the author's provider instead, preferably another model, with the [independent lens](references/lenses.md#independent) as its first instruction (the [adversary lens](references/lenses.md#adversary) at trust boundaries), and record `lens=` on the review line.
2. Brief it with the task, relevant context, exact head/diff and evidence access. Do not include the author's persuasive summary or any prior score.
3. It returns two distinct verdicts plus findings:
   - **Acceptance:** does the requested behavior work, including counterexamples?
   - **Code:** is this implementation correct, maintainable and safe in this system?
   - Each finding: claim, severity, evidence or reproduction, suggested fix.
   - **Re-check:** whether a repair of its findings needs its own re-check. The reviewer appends ` recheck=independent` to its record when a blocking finding concerns security or another trust boundary (credentials, authorization, untrusted input, production data). Without it, the author's R1 covers the repair.
4. Blocking findings go to [implement's repair](../implement/SKILL.md#repair). **A repair after R2 needs R1, not a second independent round:** the review already covered the rest of the candidate, so a repair that only fixes its findings, or brings in the base branch, is checked by the author. The author reads the repair diff, reruns the reviewer's reproductions and the affected checks, and posts an R1 record on the new head with ` repairs=<reviewed sha>` ([merge rule](../patstack/references/coordination.md#merge)).
5. A fresh non-author assessment of the repair is still required when the reviewer's record says `recheck=independent`, when the repair changes the approach or adds behaviour beyond the findings (that is a new candidate), when the lead disputes a blocker instead of fixing it, and always at R3 and in Full Stop.

## What may block

The lead puts this bar in every reviewer brief, and the reviewer applies it to every finding. It applies at R2 and R3 alike.

- **Block on** agreed acceptance (cite the criterion, decision or request), an applicable mandatory standard, or a material safety, security, data-integrity or regression risk supported by concrete evidence. Evidence may be an executed reproduction or a demonstrated code or data-flow path; an unsupported suspicion is not enough. Everything else is recorded as a follow-up with its severity and does not decide the verdict.
- **Judge acceptance against the agreed written contract**, not a stronger property the reviewer would prefer. A case outside that contract is not an acceptance failure by itself, but neither a spec exclusion nor a follow-up label waives applicable standards, security requirements, retained authority gates or an independently substantiated material risk. Report a missing necessary property as a blocking spec gap to the lead instead of inventing it.
- **Name the consequence** of each blocker: what goes wrong, for whom, in which environment, the assumptions, and any missing execution proof. "The property can be violated in a constructed case" is not enough by itself.
- **From the fourth review round of the same candidate**, link each blocker to the earlier finding it continues and show what remains unresolved on the current head; for a genuinely new blocker, explain why earlier coverage missed it or which repair introduced it. Earlier reporting or a follow-up classification never disqualifies an otherwise valid blocker, and new evidence may change its severity. The lead triages before such a round (see [repair](../implement/SKILL.md#repair)).

## Independence rules

- The author is never the independent reviewer of its own work; independence belongs to the session and its contribution, not just the model name.
- If both configured model families (default: Opus and Sol) implemented parts, cross-review the contributed areas and have a fresh non-author session cover integration seams. Do not force two complete reviews of every slice.
- Model verdicts are not GitHub human approvals and not execution proof. Agreement between models is not a test result.
- If a required reviewer model is unavailable and no [lens](references/lenses.md) session can stand in for it: continue reversible work, try a verified alternate host/runtime with the same model, never downgrade the level. Otherwise mark the PR not ready, keep the check missing and set one next-attempt event within the task's timebox; hand off at expiry. Do not poll indefinitely.
- Technical disagreement is resolved with evidence, not by asking the owner; [grilling](../grilling/SKILL.md) is only for choices that are the owner's.
