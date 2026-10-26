# Model routing policy (example)

Patstack's [coordination adapter](skills/patstack/references/coordination.md) asks the lead to read a model routing policy before choosing models for children. The owner's real policy is a private, dated preference document and stays local. This file shows the **contract** that policy must satisfy, using the defaults Patstack itself assumes.

This is a routing preference, not a benchmark. No scores here describe model quality.

## Roles Patstack assumes

| Need | Default | Rule |
|---|---|---|
| Whole-task lead (spec, assignment, integration, verdict) | `claude-opus-5-5` or `gpt-6.1-sol` | Another model hands over to a qualified lead before any child starts. |
| Frontend design and backend architecture | Opus 5.5 | New design/architecture choices return to this owner. |
| Implementation, integrations, tests, analysis | Sol 6.1 | Follows the agreed spec; no new design direction. |
| Interactive UI verification with Computer Use | A runtime that actually exposes Computer Use | A model name never grants tool access; verify the runtime. |
| R2 independent review | The opposite family of the author | Opus work → Sol review; Sol work → Opus review. |
| R3 Council | Fresh Opus **and** Sol sessions that wrote none of the candidate | Independent first judgment, then cross-examination. |

## Selection contract

1. Check the live model catalog on the actual host and runtime. Do not send an alias another host may resolve differently.
2. Record `provider`, actual `model`, `role` and a one-line reason for every assignment.
3. If a required model is unavailable, say so. **No silent fallback** to another family or a lower review level.
4. Choose quality and fit first; use cost or latency only to break ties, from current documentation or your own measurement.
5. Launching an agent grants no new right to push, merge, deploy or send external messages.

## Adapting it

Copy this file into your private setup, replace the model IDs with the ones your runtimes expose, and date each preference. Keep historical scores out of current routing decisions.
