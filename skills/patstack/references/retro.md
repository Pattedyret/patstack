# Learn from evidence

## Retro's autonomous improvement contract

Patrick grants retro authority for a significant, evidence-backed improvement, including technical changes to the workflow/skills. Preference changes involve him. This authority applies to the installed workflow; retain causal evidence, independent review where required and a tested rollback.

Before autonomous promotion, retain: the observed failure or measurable friction; a causal explanation; a reproducible failing example or baseline; the proposed change; proof that it fixes/improves the case; relevant non-regression checks; and a version/rollback record. Test the candidate before promotion and report the result in chat/retro history.

Mechanical guardrails, corrected navigation, broken-tool repairs and demonstrated workflow defects can qualify. New naming, desired visual style, acceptable product tradeoffs or changed user goals are preferences/product decisions. Model agreement alone is not cold hard truth. Retro cannot give itself new deployment/data/service authority or lower task acceptance just to make a failing result pass.

Pin the workflow version for a run. A necessary recovery change during an active task is explicitly recorded and revalidated, rather than silently changing the rules underneath its evidence. Use repeatable workflow scenarios to verify the improvement, not only the currently failing task.

Choose review proportionally for retro changes too. Changes to shared decision rules, permissions handling, acceptance or orchestration get at least R2 before promotion and normally take effect on the next pinned run. A demonstrated mechanical repair does not automatically require a full Council. An urgent active-run recovery records the exceptional version change and reruns affected proof; it never retroactively relaxes acceptance or authority.

### Reusable workflow evaluation, outside the task flow

Keep a repeatable evaluation capability for material skill/workflow changes and periodic regression checks. Compare pinned versions on representative tasks under equivalent conditions; hide variant/model labels from the judge, retain actual outcomes and traces, and measure quality, completion, rework, elapsed time and cost where available. Self-reported skill compliance is not execution evidence. This can supply evidence for retro or validate a proposed promotion, but ordinary development tasks do not run a workflow bakeoff. Mechanical fixes need proportionate checks, not the entire scenario suite.

The capability can run on demand, after a meaningful candidate change, or later on an explicitly configured cron/scheduler. No recurring job or cadence is created by this design. A scheduled evaluation should use isolated test workspaces and bounded resource use; its existence grants no application deployment, production/data access or preference-changing authority. Use existing evaluation scenarios rather than inventing a second task-status system. Inspiration: [pstack's blinded evaluation playbook](https://github.com/cursor/plugins/blob/main/pstack/skills/poteto-mode/playbooks/eval.md).


## Workflow KPIs across environments

Before the retro assessment, read the private [KPI contract](../../../monitoring/patstack/README.md), refresh supported discovery and fetch reports for the relevant Mac/devbox/Windows hosts. Inspect workflow/topic/node and delivery-environment breakdowns, sample counts, unknown labels and missing emitters. Record observed workflow metadata at start, meaningful milestones and terminal events; preserve the request ID across resume. Casual research/testing uses telemetry without creating a development ticket. Metrics guide investigation; verify causal claims against the underlying evidence and use proportionate comparisons.
