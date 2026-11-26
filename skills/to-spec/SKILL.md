---
name: to-spec
description: Plan a new feature or larger change - read the product knowledge, interview the requester critically in rounds (product knowledge looked up before every round, vague or conflicting answers challenged) until nothing about what to build is unclear, grill the draft plan, update the product knowledge with what was settled - then write a versioned spec (problem, goal and non-goals, acceptance, quality targets, test seams and risks) kept in a GitHub Issue or an accessible versioned artifact outside the application repo. Use before implementing a new feature or larger change; a tiny explicit request is its own brief and needs no spec.
---

# To spec

Facts come from the repo, tools, the project's product knowledge and prior tasks; never ask for them. Definitions come from people: who is included, what a term means, what counts as correct. Settle those with the requester through [grilling](../grilling/SKILL.md) before writing the spec.

**Context.** Under a Patstack lead, reuse an accepted spec instead of writing a new one; this skill fills what is missing and versions changes. Invoked directly, write the spec the user asked for; it creates no task and no implementation authority.

## When a spec is needed

- Tiny explicit request: the request is the brief. No spec file, task graph or interview.
- Bounded fix: a short working contract on the task (expected behavior, reproduction, success check) is enough.
- New feature or larger change: run the full planning interview below, then write the spec.

## Plan: understand, interview, grill the plan

Planning is where most of the work on a feature goes, and it is the hands-on part for the requester. A wrong guess about what to build costs a whole build, review and repair cycle; a question costs one round trip. So before anything is built, the lead builds a complete picture of what the requester wants and keeps asking until nothing about *what* to build is unclear. Then it writes the spec, pushes back on it and hands the agreed spec to implementation, which runs hands-off ([push back and hand off](#push-back-and-hand-off)). Run every step below for a new feature or larger change; a bounded fix runs steps 1 and 3 only for what its working contract leaves unclear.

1. **Read the product knowledge first.** Run the project pack's context step (its product vault, where the pack has one) and read the notes for every entity and product decision the work touches: user types, roles, products, units, statuses, existing rules. Note each gap as the pack says. Facts come from here and from the code, never from the requester. The product knowledge drives the whole interview, not only its start (step 3).
2. **Lay out the real categories.** For every scope-defining term, list all categories that exist in the data, with read-only counts, not only the ones the request names. Show what each candidate definition includes and leaves out, with numbers ("active unit = unit with a non-archived profile: leaves out 1,223 institution staff").
3. **Interview stage: ask and challenge until it is clear.** Through [grilling](../grilling/SKILL.md), in rounds. Before every round, look up in the product knowledge each term, group and rule the last answers named, and let each question cite its note or name the gap. Challenge vague answers, conflicts with the product knowledge or between answers, and unstated assumptions, as [grilling](../grilling/SKILL.md#challenge-dont-transcribe) says; an unclear answer settles nothing. Each round batches every open question about what to build: goal and who it is for, which users and data are in scope, behavior in the main flow and at the edges (empty, error, permission denied, many items), what the user sees and in what words, what counts as done and correct, priorities and what can wait, and every product decision the product knowledge does not already answer. Each question names the concrete groups and counts and states a recommendation. Keep running rounds until no question about what to build is open: an answer that opens a new question gets a new round. Questions already settled, including by approving a recommended batch, are not asked again.
4. **Grill the plan.** Write the draft plan in a few lines (what gets built, the route through the product, what is left out, the main risks) and attack it before writing the spec: walk each acceptance criterion through the real product and data, and look for a missing user group, a broken edge, a conflict with an existing rule or product decision, and a cheaper way to the same goal. Put every hole that is the requester's to settle to them as the next grilling round, with your recommendation; fix the rest yourself. Repeat until the plan survives a pass with no new hole.
5. **Record the answers and update the product knowledge.** Each settled definition and product decision goes into `Decisions` with the date and who settled it. Where the product knowledge lacked it or said something else, update it now, under the pack's write-back procedure (for a product vault: a vault PR as soon as the requester has confirmed it), so the next agent finds it instead of asking again.

Close the interview with the settled definitions as one short list in the same message as the next step; a settled item is a record and is never asked again. Then write the spec. Implementation approach, tooling and other technical choices stay the lead's and are not interview questions.

## Write it

1. Explore the affected code. Use the project's domain vocabulary and respect ADRs in the area.
2. Choose test seams: prefer existing ones, as high as possible, as few as possible. In Full Stop, confirm a new seam with the owner only if it changes product behavior; otherwise decide.
3. Derive missing quality targets before implementation from project evidence ([quality](../patstack/references/quality.md)). New features include their UI/UX/performance/data proof as acceptance items. Freeze the measurement protocol now so BEFORE can be captured.
4. Preserve user-selected behavior and any approved visual direction. Significant new visual direction is a browser-options approval point, not something a spec decides.
5. Fill the template; keep it as short as the work allows.

```markdown
## Problem
What the user faces, from their perspective.
## Goal / non-goals
## Acceptance
Numbered, verifiable criteria, including counterexamples and permission/data assertions.
## Quality contract
Per applicable dimension: target, source, test method. N/A with reason.
## Decisions
Settled definitions (date, who settled them), modules and interfaces touched, API/schema contracts, settled choices and recorded assumptions. No file paths or code, except a prototype snippet that states a decision more precisely than prose (say so).
## Testing
Seams, prior art, what a good test asserts (external behavior).
## Delivery and risks
Intended test target, mode, review level, rollback, known risks.
## Out of scope
```

## Push back and hand off

The spec is the handoff from the hands-on part (planning) to the hands-off part (implementation, review and delivery). Before handing it off:

1. **Push back on the spec.** Show the requester the spec in short form: the problem, what gets built, acceptance, what is left out and the main risks. Add the lead's own pushback, with a reason and evidence for each point: where the idea is weaker than it could be, costs more than its value, conflicts with an existing product rule or decision, leaves a user group worse off, or has a simpler way to the same goal. Give each point a recommendation. Do not soften pushback into agreement. A requester who hears the objection and keeps their choice has decided; record it in `Decisions` and do not raise it again.
2. **Settle what the pushback opens.** Answers that change scope or behavior get a grilling round of their own and a new spec version. Settled items stay settled.
3. **Hand off on the requester's yes.** Ask with the native question tool whether the spec says what they want, with options to hand it off (recommended), to change named points, or to hold. Their yes to this version is the handoff. From there implementation runs hands-off in the selected mode against that exact version. A genuinely new product question found while building comes back as one checkpoint. Technical problems, review findings and repairs do not come back to the requester. A tiny edit or a bounded fix needs no separate handoff: the request or working contract is the agreed brief.

When the requester is unavailable, the spec waits at the handoff with its open points named. Implementation does not start on a spec the requester has not agreed to.

## Store and distribute

- GitHub-backed work: the canonical spec is the parent Issue body. It is not a repo file, so it needs no commit and no `.gitignore` entry. Add no per-task spec file to the application repo; project-required intake records, ADRs or requested docs remain real deliverables.
- Deliberately local-only work: one shared, versioned artifact outside the codebase.
- Give every worker/reviewer the reference and exact version. If an agent or host cannot read it, send the content or an accessible copy with the version attached; a path the recipient cannot open is not a handoff. On change, bump the version, send it to affected agents and get acknowledgment. No independently editable forks.
- Keep drafts and caches outside the application repo; clean them once the canonical version and evidence are retained. After completion the Issue keeps the spec, PR links, evidence and retro as history.
