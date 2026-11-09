---
name: workflow-eval
description: Repeatable, bounded, blinded evaluation of pinned skill or workflow versions on representative scenarios - isolated workspaces, hidden variant labels for the judge, measured quality, completion, rework, time and cost. Use on demand to validate a material workflow/skill change or a retro promotion, to hill-climb the owner's KPI targets, or from an explicitly authorized schedule; not a step of ordinary development tasks.
---

# Workflow eval

Answer "is variant B better than A on the work we actually do?" with outcomes, not self-reported compliance. Adapted from [pstack's blinded evaluation playbook](https://github.com/cursor/plugins/blob/main/pstack/skills/poteto-mode/playbooks/eval.md).

**Context.** Runs on demand, after a meaningful candidate change, or from a schedule the owner explicitly configured. It is unticketed unless the owner designates it as development work. It creates no recurring job, deploys nothing, touches no production or real customer data, and changes no preferences.

## 1. Define the run

- **Variants:** each pinned by commit/hash of the skill files and the model/runtime used. Same models across variants unless the model is what is being compared.
- **Scenarios:** representative tasks with known acceptance; start from [scenarios](references/scenarios.md) and add ones that reproduce the failure under study. Reuse existing scenarios; do not build a second task-status system.
- **Metrics:** acceptance pass, quality verdicts, rework/repair cycles, unnecessary ceremony, elapsed time, tokens/cost where available, permission or gate violations (any violation fails the run).
- **Budget:** a cap on runs, time and spend, stated up front. Stop at the cap and report partial results as partial.

## 2. Execute

1. One isolated workspace per scenario × variant (temporary checkout or fixture copy); no shared state between runs and nothing written into real repos.
2. Same prompt, fixtures, tools and conditions per variant; alternate or randomize order.
3. Retain actual outcomes: diffs, test output, transcripts/traces, timings.
4. Repeat where variance matters; report sample counts.

## 3. Judge blind

- A fresh judge session that ran none of the variants sees outcomes with variant and model labels stripped, scored against a rubric fixed before the run.
- Executed acceptance results outrank judge scores. Judge scores are labelled judgments.
- Report per scenario and aggregate: metric per variant, sample count, spread, and where variants differ beyond noise.

## 4. Use the result

Results feed [retro](../retro/SKILL.md) or a promotion decision as evidence. A mechanical fix needs proportionate checks, not the whole suite. Record the variants, scenario set version, raw artifact location and limitations so the run can be repeated.

## 5. Hill-climb to the owner's targets

KPIs and benchmarks exist to reach goals the owner sets, for example "security holes 0 %, Kvalitet at least 95, at most 4 minutes". The targets live in `~/.config/devstack/kpi-targets.json` (shape: [`examples/kpi-targets.example.json`](../../examples/kpi-targets.example.json)). Setting or changing a target is the owner's choice; the climb toward it is yours.

1. **Measure.** Run the benchmark on the current tree (`bench/bench.py run --arms devstack --trials 3`, with `--review` whenever Kvalitet is a target) and read the targets table (`bench/bench.py score`, or `monitoring/devstack/kpi_monitor.py scorecard`). Record the starting values.
2. **Pick the largest gap.** Take the missed target furthest from its bound, read the per-task rows and transcripts behind it, and name one cause with evidence.
3. **Change one thing** in a candidate worktree: a skill, reference or tool, never the bench tasks, graders or the targets. Keep it the smallest change that addresses that cause.
4. **Re-measure as A/B.** `bench/bench.py run --arms devstack candidate --candidate <worktree> --trials 3` (plus `--review` when Kvalitet is a target) on the full task set (all targets, not only the one you aimed at), then `bench/bench.py gate`.
5. **Keep or revert.** `gate` prints **KEEP** (a Pareto step: no target's gap grows and at least one shrinks, so security is never traded for speed), **REVERT**, **TOP** (every target met) or **NOT COMPARABLE** (different workloads, an incomplete run or an unmeasured base: fix the measurement, it is not an iteration). KEEP or TOP ships the candidate as a normal PR under the [merge rule](../devstack/references/coordination.md#merge) and becomes the new baseline. REVERT discards the worktree, and the finding goes into the next hypothesis.
6. **Stop** at TOP, after three iterations in a row without a KEEP (a plateau: report the best values and what limits them), or at the stated budget. Report each iteration's values, verdict and change.

An unmeasured target is UNKNOWN, never met. With n = 3 per arm, a one-task difference can be noise: rerun before keeping a gain that rests on a single task.

