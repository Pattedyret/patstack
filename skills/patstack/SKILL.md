---
name: patstack
description: Use when Patrick designates a development task, invokes Full Send or Full Stop, or continues an existing implementation, PR or delivery task.
---

# Patstack

BIG TASK is the lead agent, not a separate role or skill. One lead owns the requested outcome through verified handoff. Use the smallest complete path. A concrete request to change code, configuration or an agreed deliverable designates a task; the literal word TASK is not required. Discussion, research and casual testing stay outside development intake until such a request.

## Enter or resume

Bind the actual workspace, project procedures and existing task. For a designated task, load [coordination](references/coordination.md) to create/resume ownership; session registration alone creates no development ticket. Preserve its accepted spec and scope. Patrick’s latest explicit steering supersedes earlier constraints within retained authority gates. For project/spec distribution or host choices, read [project context](references/project-context.md). Record minimal private [workflow KPI metadata](../../monitoring/patstack/README.md) at start and meaningful boundaries, without creating extra tickets. On long work or resume, read [task state](references/task-state.md); reconcile actual PR/build/release state before continuing.

Choose Full Send or Full Stop using [decision ownership](references/decisions.md). Full Send is default; retain Patrick's specified high-impact Full Stop classification at intake. Once mode is selected, uncertainty alone does not switch it. Size, urgency and review depth are separate choices. Research, check prior tasks and test assumptions where useful; then make and record the best supported in-scope choice.

## Follow the current phase

| Phase | Load when needed | Done when |
|---|---|---|
| Plan | [Planning](references/planning.md) | Brief, relevant quality targets and proof method are sufficient to implement. |
| Build | [Build/review](references/build-review.md) | Smallest complete candidate and relevant tests exist. Parallelize only ready independent scopes. |
| Check | Build/review for R1/R2/R3; [testing/delivery](references/testing-delivery.md) | Current candidate has the required review, CI and acceptance/quality evidence. |
| Deliver | Testing/delivery; [access](references/access.md) for login/test accounts | Full Send: intended test release works with proof. Full Stop: ready unmerged PR handed over. |
| Learn | [Retro](references/retro.md) | Record proportionate lessons; promote only justified, checked technical improvements. |

A tiny edit stays direct with R1 and affected checks. Critical work uses the short recovery route; do not wait for a large spec or task graph. Takeover resumes the earliest valid phase, preserving settled decisions and credit. Modernize reassesses old work's relevance first. File/update PR and Babysit are delivery steps, not competing orchestrators.

Use existing project tests/recipes. For a genuine missing/stale recipe, use create-test-recipes. Read [quality](references/quality.md) only for relevant targets or evidence. Check BW Locker before calling a login problem a blocker; account selection follows the access reference.

Failures at PR or live layers return to the same repair flow. Keep cumulative time/attempts; after three failed normal cycles or earlier stagnation, change the hypothesis through deeper diagnosis. Native wakeups handle waits; checkpoints preserve work rather than ending it. Report proof honestly. Production, destructive data operations and explicitly retained human gates require their actual authority.

Workflow version: **1.0.0**. This is the single installed development workflow entrypoint. Read phase references progressively; do not preload the historical design or every reference.
