---
name: grilling
description: Sharpen a plan, design or decision by interviewing the owner critically - batched, numbered rounds of questions, each with a recommended answer and grounded in the project's product knowledge looked up before every round, asked only about choices that are genuinely the owner's, challenging vague answers, conflicts with the product knowledge and unstated assumptions until nothing about what to build is unclear, then attacking the draft plan for holes. Use for the planning interview of a new feature, grill me, poke holes in my plan, have I thought this through, a Full Stop decision checkpoint, or before an approach that is costly to reverse. For model critique of finished work use review or council.
---

# Grilling

The goal is a complete shared understanding of what to build before anything is built. Ask every question that is genuinely the owner's, each round batched so it takes as few round trips as possible; asking the wrong kind of question (a fact, a technical choice) wastes the owner's time, and leaving a real question unasked wastes a build.

**Context.** Under a Patstack task, this is the planning interview of [to-spec](../to-spec/SKILL.md#plan-understand-interview-grill-the-plan), and how Full Stop checkpoints and genuine product decisions reach the owner. Invoked directly, it is unticketed discussion.

## Filter every draft question

1. **Has the owner already decided it?** Re-read the owner's messages. Preserve the owner's framing and vocabulary verbatim; a clear stated definition is the definition, not a starting position. A vague one is not yet a definition: [challenge it](#challenge-dont-transcribe).
2. **Can a tool answer it?** Facts are your job: code, history, configs, running apps, prior tasks, the project's product knowledge, a subagent. Look in the product knowledge before every round, not only before the first. A pending lookup blocks only the questions downstream of it. Counts are facts; a definition is not. Who is included and what a term means stay the owner's even when the data could suggest an answer.
3. **Does the answer change what gets built?** If both branches lead to the same work, pick one, say which, move on.

A structured bug report (environment, area, severity, steps) is a complete spec; act on it.

## What is the owner's call

Ask about: target environment when not established, anything user-visible or deployed (copy, behavior), money (paid tiers, new services), creating repos or infrastructure, launch timing, product rules (who may do what, what counts as correct), significant new visual direction.

Own without asking: implementation approach, an established test persona, tooling, parallelism, file layout, number of agents.

## Ask in batched rounds

- Directional or product questions: prose, with your recommendation stated.
- Bounded operational picks between known alternatives: two to four concrete options, recommended one first. The recommendation must be a real call, not a hedge.
- Batch the whole current frontier into one numbered list per round. Start the next round when the answers open new questions, a question depended on an earlier answer, or grilling the plan finds a hole; never hold a question back to save a round.
- In a planning interview, cover what to build from every side before stopping: goal and who it is for, users and data in scope, main flow and edges (empty, error, no permission, many items), what the user sees and in what words, what counts as done, and priorities. Ask about each side the request and the product knowledge leave open.
- Ground every scope question in the real data: name each group with its count and say what each option includes and leaves out. A requester outside the product team cannot see what a technical term hides; spell it out in their words.
- When the answers are in, restate the settled definitions as one short list alongside what you do next; it goes into the spec. It is a record, not a new approval round: ask again only about what is still unsettled.

```text
1. <question> - recommend: <answer, and why in one clause>
2. <question> - recommend: <...>
```

State the approach in a short paragraph, the questions that matter, and what you will do next, in one message.

## Challenge, don't transcribe

The interview is critical. Its job is to find what the requester has not thought through, not to write down what they say.

- **Product knowledge before every round.** Before the first round and again after each round's answers, look up every term, user group, rule and product the request or the answers named, in the project's product knowledge (the project pack's vault step, where there is one) and the code. Each question names what it rests on: the note (`vault: <note>`) or the gap (`vault: gap`). Do not ask what the product knowledge answers; state it as fact, and ask only where the request conflicts with it.
- **Challenge what is unclear.** Each of these gets a pointed question in the next round, with a concrete reading, what it means for users, and a recommendation:
  - a vague word ("all users", "simple", "quick", "as today", "like X"): offer the concrete version with its groups and counts and what it leaves out;
  - a conflict with the product knowledge: quote the note and ask which holds; the answer is a product decision and is written back;
  - a conflict between two answers, or between an answer and the request;
  - an unstated assumption the plan depends on (the data exists, the users have access, another team or system does its part);
  - a product decision handed back ("you decide", "whatever is standard"): make it as a recommendation, say what it means for users, and ask for a yes;
  - the premise, when evidence says the problem is small, already solved or better solved another way.
- **An unclear answer settles nothing.** It comes back sharper in the next round. Once the requester has heard the challenge and makes a clear choice, it is settled: record it and do not raise it again.
- Challenge with evidence and a recommendation, never by repeating the same question or arguing for its own sake.

## Read the answer

- Interpret an explicit reply within its clear scope. A numbered answer settles that item; clear approval of the entire described batch settles that batch. Do not re-confirm a decision already made.
- Unanswered human-gated product, permission or visual choices remain pending. Silence creates no approval. Ordinary implementation defaults may proceed under existing authority; state the assumption and keep independent work moving.
- A scope redirect is a decision, not an objection to argue with.
- If the owner contradicts what you believe, the owner's environment statement outranks your inference. Verify against the live system; if you were right, show the evidence.

## When the owner is unavailable

Record the open question, recommendation and next action on the task as a block, and continue independent work within scope. A missing answer grants no product authority.

## Grill the plan

Once the answers give a draft plan, attack it before anything is built: state it in a few lines, walk each acceptance criterion through the real product and data, and look for a missing user group, an edge that breaks, a conflict with an existing rule or product decision, and a cheaper way to the same goal. Holes that are the owner's go into the next round with your recommendation; fix the rest yourself. When the owner asks you to grill *their* plan, do the same to it and ask about each hole found.

## Stop

The interview ends when nothing about what to build is both unsettled and the owner's to settle, no challenge is left unanswered, and the plan has survived a grilling pass with no new hole. Say so and move on. Under a Patstack task the next step is the spec, its pushback and the requester's yes at the [handoff](../to-spec/SKILL.md#push-back-and-hand-off); implementation starts only after that.

When changing approval interpretation, replay the [approval scenarios](references/approval-scenarios.md).
