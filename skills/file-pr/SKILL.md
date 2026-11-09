---
name: file-pr
description: File or update a concise problem-first pull request for the current candidate, link it to its Issue, task and T3 thread, and record the reviewed head, review level and evidence. Use when a candidate is ready for PR review or an existing open PR needs updating after repair; continue with babysit-pr.
---

# File PR

**Context.** Under a DevStack lead, the PR belongs to the existing task; record its URL there. Invoked directly, open or update the PR the user asked for; that is a development delivery step, so apply DevStack's entry first if no task owns the work. Opening a PR publishes to GitHub: confirm the target repo/base is the intended one.

## Before filing

- Reuse the open PR when it is still the correct continuation; push to it instead of opening another. Never reopen a merged PR; a fix-forward or revert gets a new PR linked to the same task.
- Check current head/base, that required local checks ran on this head, and that the branch contains only this task's changes.

## Body: written for a person

Write for someone who reads it once and has not seen the task: what changed, whether it works, what is still open. Aim for 100 words; the [merge gate](../devstack/references/coordination.md#merge) refuses more than 200, header included. Use plain sentences. Leave out finding codes, repair history, test commands and messages to other agents.

The body starts with its header, which the merge gate reads and nothing else replaces: the mode line first, then the author line for R2/R3 and the level line when review is above the mode's floor, each once, plain text at column 0. Keep it current when the head changes, and choose one mode in the mode line.

```markdown
Mode: Full Send|Full Stop — <project tier, risk, the review depth and proof it got, and whether a revert undoes it>
DevStack-Author: <provider/model that wrote the change>
DevStack-Level: R2|R3

What was wrong or missing and what changed, in two or three sentences. Link the Issue/spec.

The one check that best shows it works, with its label and head or environment.

Open risks: what is still unresolved, most serious first. Leave out when nothing is.

no CI configured; proof is local only
```

To change a filed body, use `gh api -X PATCH repos/OWNER/NAME/pulls/N -F body=@file` and read it back: `gh pr edit` can fail on GitHub's Projects classic sunset and leave the old text.

Keep the no-CI line when the repo has no CI: it is a risk, not N/A, and the gate reads it. A change set adds its one-line merge order here too.

## Evidence comment

Everything else goes in one PR comment, updated when the head changes. Post it right after filing:

- Evidence card: what ran (EXECUTED), what was seen (OBSERVED), what is reasoning (REASONED), for which head/environment. Feature works? Y/N. Quality standard? Y/N per applicable dimension (new features/improvements).
- Review level (R1/R2/R3) with a one-line reason; reviewer model/session where independent. Each verdict is also a separate one-line `DevStack-Review:` comment for the head, which the merge gate reads.
- Blast radius, migrations, rollback route, retained human gates, and any data classification [review](../review/SKILL.md) requires.
- Repair history and anything deliberately not done.

Link raw artifacts instead of pasting them. No secrets, private device details or vault output, in the body or the comment.

## After filing

1. Link the PR to its Issue (avoid auto-closing a parent whose acceptance needs live verification) and, when exposed in T3, call `link_pull_request` immediately with the PR URL (each stack layer separately). A CLI-created PR is not automatically linked. Before handoff, inspect `list_thread_pull_requests` and link any missing PR from this work.
2. Record the PR URL and head on the task.
3. Continue with [babysit-pr](../babysit-pr/SKILL.md). Only the PR-owning lead watches it.

Model review reports are not GitHub human approvals. Never bypass branch protection or impersonate an approver.
