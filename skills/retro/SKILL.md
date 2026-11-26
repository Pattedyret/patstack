---
name: retro
description: Proportionate, autonomous retrospective on a finished task or a session - find real friction in navigation, checks, review, tools and information access, and carry out the technical findings without asking - close merged branches and finished worktrees, turn a mechanical mistake into a check in the repo where it happened, and promote evidence-backed, tested workflow fixes with rollback - while only preferences, new authority and destructive actions go to the owner. Use at a task's endpoint or when asked for a retro on a session.
---

# Retro

Retro improves the agent's environment for future runs. It acts on evidence and does not re-litigate the task.

**Context.** At a Patstack endpoint the lead runs it before `complete`, automatically, without a separate child and without being asked. Invoked directly on a session, it stays unticketed unless the owner designates development; promoting a change into shared skills is then a designated change and follows the contract below.

## Act, don't propose

Retro is autonomous. The lead carries out every technical finding in the same run and reports what it did, with proof and rollback. It does not ask first and does not leave a proposal for the owner to approve:

- merged branches and finished worktrees are removed ([below](#close-merged-branches));
- a mechanical mistake becomes a check in the repo where it happened, as a PR the lead merges under that repo's rules ([step 4](#4-put-a-check-in-the-repo-where-the-mistake-happened));
- a technical defect in the workflow, its skills, tools or the agent setup is fixed by PR, reviewed by risk, merged through the gate and rolled out to the hosts ([step 5](#5-promote-a-workflow-change));
- the project's product knowledge is written back where the pack says so.

Only four things go to the owner, batched as one question with the native question tool after everything else is done, and never holding the rest back: a preference or product choice (naming, visual style, a product tradeoff, a changed goal); new or wider authority (permissions, production, deploys, data, spend, new repos or services); a destructive action beyond the cleanup below; and a refactor large enough to be its own task. A finding with nothing to act on is reported as such; a retro never invents work to look thorough.

## Size it

- **Tiny task:** 2-4 lines in the closing comment: what cost time or went wrong and one concrete environment improvement, or "Retro: no findings". No extra agent or report.
- **Larger task (spec, children, PR, repair loop):** the steps below; ranked candidates go in the task comment and final reply.
- **After a critical recovery:** the full retro runs once restoration is verified, not on the critical path.

## Close merged branches

Every retro, tiny ones included, closes the merged branches of each repo the task touched, other people's included. First run `python3 tools/worktrees.py <repo> --apply` to remove merged, clean worktrees so their branches are free; a squash-merged worktree stays and is removed by hand after checking. Then run [`tools/branches.py`](../../tools/branches.py) `<repo> --apply` from this workflow's checkout. On origin it deletes only branches whose merged pull request holds their exact tip, so GitHub can restore each one from its PR. Locally it deletes branches whose tip is inside such a pull request, or whose upstream is gone and whose tip is in the default branch. The default branch, branches an open PR uses, branches checked out in a worktree and branches with later commits stay, each with its reason. Put the deleted and kept counts in the retro; a refused deletion is reported, never forced. This standing cleanup grant covers this tool's deletions only, no other destructive Git action.

## 1. Read primary sources

The session transcript(s) the user names (default: current), task events and the task's own PR, Issue, CI and review history and repair records, including any deep-diagnosis workflow RCA from [implement](../implement/SKILL.md#repair). Where it helps, compare the task with the same repo's earlier PRs rather than with all work, and treat a repo without a [CI script](../create-test-recipes/SKILL.md#the-repos-ci-script), or a repo the tier map lists under `local_ci` that still holds GitHub workflow files, as a guardrail finding to fix. Verify causal claims against the underlying evidence.

## 2. Find candidates

- **Navigation:** time lost finding files or facts; a pointer or index would fix it.
- **Automated checks:** a mistake a lint/type/test/filesystem check could catch. Read the repo's own check scripts and CI first: an existing check that is unwired or silently broken is the finding. A repo with no guardrail at all is itself a finding.
- **Review standards:** a mechanical violation (banned API, import shape, file location) gets a deterministic check rather than a rule; reserve written standards for real judgment calls. The reviewer, not the implementer, enforces standards.
- **Steering files:** instructions that change no behavior, belong in a check, or bloat always-loaded context.
- **Tool economy:** expensive or token-heavy tool use that a cheaper path would replace.
- **Information access:** a crucial fact was unavailable (logs, read-only service access).
- **Workflow:** process that delayed a small task, a loop that stagnated, a gate that did not catch the defect.

- **Project vault:** when the project's pack declares a write-back step, after verified delivery, name the vault update candidates under that pack's write-back procedure: only what changes what someone does next, with its source, and go through every `Vault-hull:` line from the brief, since each gap is a candidate. Propose a vault PR (merged under the [merge rule](../patstack/references/coordination.md#merge)) or record "vault: no update" with the reason.

Rank by severity and evidence.

## 3. Fix at the highest level that holds

A mistake that happened twice, or once at a cost that justifies it, is fixed at the first level below that works. Say which level you chose and why a higher one did not work.

1. **Architecture.** Make the mistake impossible: one owner for the state, one supported way to do the task, internals hidden so the wrong import fails, the old way deleted so nothing copies it.
2. **Types, lint or a CI check.** When bad code still compiles, a check refuses it and its error names the file, type or function to use instead. Where the pattern is already common, the check fails only when a change adds more.
3. **A test** of the behavior, one that fails when the behavior breaks and survives a change to the internals.
4. **Prose** (a skill, an instruction file, a comment) last, and only for a judgment call. Nothing fails when an agent skips it.

A reviewer, human or model, catching the same mistake on every PR is not a level: it is the cost this removes.

## 4. Put a check in the repo where the mistake happened

A fix at level 2 or 3, and a level 1 fix no larger than the check it replaces, belongs in the repo where the mistake happened, not in a skill. The lead opens a PR there on the task's ticket. It holds:

- the check, as a step of the repo's [CI script](../create-test-recipes/SKILL.md#the-repos-ci-script), so one command runs it locally and on every PR. A repo with no script gets one in the same PR; no workflow file is added on GitHub;
- its proof: red on the real past mistake (the offending commit, or a faithful reconstruction when that commit cannot be checked out), green on the fixed code, and no new failure on the default branch;
- any exception on the offending line, with its reason.

The PR is an ordinary change in that repo: its tier, mode, review level and [merge rule](../patstack/references/coordination.md#merge) apply, and it carries no deploy, data or production authority of its own. The lead merges it under those rules (in Full Stop it stops at the ready PR for the human merge, as any PR there does). A larger level 1 change, such as a refactor that removes the pattern, goes to the owner as its own task.

When the repo's agent instruction file holds a prose rule that the check now enforces, the same PR replaces the rule with one line naming the check. Drop a rule once its mistake cannot happen.

## 5. Promote a workflow change

An evidence-backed **technical** improvement to the installed workflow, its skills, tools or the agent setup is promoted by the lead itself: a PR in the repo that holds it, reviewed by risk, merged through the gate and rolled out to every host. Before promoting, retain:

1. the observed failure or measurable friction and its causal explanation;
2. a reproducible failing example or baseline;
3. the proposed change and proof it fixes/improves that case;
4. relevant non-regression checks ([workflow-eval](../workflow-eval/SKILL.md) for material workflow changes; a mechanical fix needs only proportionate checks);
5. a version and rollback record.

- Mechanical guardrails, corrected navigation, broken-tool repairs and demonstrated workflow defects can qualify. New naming, visual style, product tradeoffs or changed goals are **preferences**: they go to the owner in the retro's one batched question.
- Changes to shared decision rules, permissions handling, acceptance or orchestration get at least R2 ([review](../review/SKILL.md)) and take effect on the next pinned run. A mechanical repair does not need a council.
- Pin the workflow version per run. A recovery change during an active task is recorded and its affected proof rerun; it never retroactively relaxes acceptance or authority.
- Retro cannot grant itself deployment, data, service or production authority, and cannot lower acceptance to make a result pass. Model agreement alone is not evidence.

Report each repo check (finding, level, PR and its proof), what was promoted in the workflow (evidence, test, rollback, version), what went to the owner, and what was not checked.
