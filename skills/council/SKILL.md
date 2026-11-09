---
name: council
description: Two-model R3 council - fresh judgments from the two configured model families (Opus and Sol by default) formed independently, then concrete evidence-backed cross-examination and a joint verdict with per-model scores per round. Use for broad or high-impact changes, irreversible effects, unresolved material disagreement, or when asked for a council on a candidate, plan or technical decision.
---

# Council

Exactly two configured model families (default: Opus and Sol; see [model routing](../../MODEL_RANKING.md)). Several narrowly scoped sessions per family are fine; a third family or a role-named panel is not. Agreement is a judgment, never execution proof.

**Context.** Under a DevStack lead this is the R3 level of [review](../review/SKILL.md) for the task's exact candidate. Invoked directly on a plan or technical decision, run it within the user's request; it creates no ticket. Choices only the owner can make go to [grilling](../grilling/SKILL.md), not to a council vote.

## Setup

- Two fresh non-author sessions, one per family, started by the lead (never by a child) via native delegation ([coordination](../devstack/references/coordination.md#delegate-and-communicate)) with the actual model. If a required model is unavailable, follow review's unavailable-reviewer rule; never substitute or downgrade silently.
- Same brief to both: task/spec version, relevant context, exact candidate (head/diff or document version), evidence access, and the questions that decide readiness. No author summary, no other model's view.
- Add narrowly targeted expertise (for example a security pass on a trust boundary) only when the change warrants it, still from one of the two families.

## Round 1: independent judgments

Each session returns, without seeing the other:

- Acceptance verdict and code/approach verdict, kept separate.
- A score per verdict with a one-line basis (a score communicates judgment; it does not decide readiness).
- Findings: claim, severity, evidence/reproduction, suggested fix.

## Round 2: cross-examination

Give each session the other's findings. For every disputed or blocking claim, record:

| Claim | Severity | Evidence / reproduction | Response | Resolution |
|---|---|---|---|---|

Resolve with evidence: run the reproduction, read the code path, execute the check. A claim that neither side can support with evidence is labelled REASONED and cannot by itself block or clear readiness.

## Joint assessment

Report per-model scores by round, resolved findings, unresolved objections with owner and next action, and the two verdicts. Required acceptance checks and unresolved blocking findings decide readiness; two high scores cannot offset a failed permission test or missing behavior. Each family's session posts its own `DevStack-Review: level=R3 …` record for the head on the PR ([merge rule](../devstack/references/coordination.md#merge)); the gate counts R3 only with approvals from both.

## After repair

Blocking findings go to [implement's repair](../implement/SKILL.md#repair). A fresh non-author assessment covers the changed diff. Repeat a full council only when the repair changes high-impact behavior or leaves a material objection unresolved; otherwise retain the valid prior judgments. Review repairs follow the same three-cycle/early-diagnosis limit. Do not stack an R2 pass and a council on an unchanged candidate.
