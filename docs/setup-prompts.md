# Setup prompts

Copy-paste prompts for setting up and maintaining DevStack with Claude Code or Codex. Each prompt hands the agent one job. The steps stay in [setup](setup.md) and [onboarding](onboarding.md). The prompt names its doc section, its limits and the proof to finish with. Paste it into a new session on the host you are setting up. Replace `HOST` with `mac`, `devbox` (any Linux machine) or `windows`.

Every prompt keeps the same limits: no ticket, no project or production change, no credentials in chat or files, a backup before any client configuration changes, and no edits to Codex trust hashes. Steps that need you (passwords, logins, `/hooks` approval) come back to you as a short list.

## Install DevStack on a new host

```text
Install DevStack on this host (HOST = mac | devbox | windows) for Claude Code and/or Codex,
following docs/onboarding.md section 2 in your DevStack checkout. If no checkout exists,
clone it into a permanent folder (for example code/devstack in my home folder) and tell me the path.
1. Check the prerequisites (Python 3.9+, git, gh logged in, Node.js, Codex 0.160+ if used) and
   report what is missing instead of installing paid or system software without asking.
2. Run scripts/check.py and stop if it does not print OK.
3. Expose the 19 skills (2.2; Windows: scripts/skill_mirrors.py --apply). Leave existing entries
   alone and list them; flag any old patstack link. Never link private project packs into global discovery.
4. Install the global instructions (2.3) from examples/global-instructions/AGENTS.md. Where
   ~/.claude/CLAUDE.md or ~/.codex/AGENTS.md exists, back it up, show me the merge as a diff and
   keep my own rules and the first-line marker.
5. Install the KPI and status hooks (2.4) with the right --host.
6. Run scripts/setup_doctor.py --host HOST and fix only what it reports.
Do not edit Codex trust hashes: tell me when to approve the hooks in Codex /hooks. Create no
ticket, touch no project or production system, never print credentials. Finish with the final
setup_doctor.py output and the items that still need me.
```

Afterwards, open a fresh session: it must start with the `📈 DevStack monitoring on …` line.

## Hooks and session status only

```text
Set up DevStack's session status and KPI hooks on this host (HOST = mac | devbox | windows),
following docs/setup.md step 6. Run scripts/setup_doctor.py first and fix only what it reports.
Keep existing hooks and settings, back up before changing client configuration, and show me any
diff that replaces an existing file. Do not edit Codex trust hashes: tell me when to approve hooks
in Codex /hooks. Create no ticket, touch no project or production system, and never print
credentials. Finish with the final setup_doctor.py output, a fresh session showing the status
line, and the items that still need me.
```

## Update after a DevStack change

```text
Update DevStack on this host (HOST = mac | devbox | windows) to the latest main of
your DevStack repository. Fetch first; fast-forward the checkout only if it is clean and on main,
otherwise stop and tell me what is in the way. Then run scripts/check.py. On Windows run
scripts/skill_mirrors.py --apply and --check. Compare my ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md
with examples/global-instructions/AGENTS.md and show me new or changed template sections as a
diff; merge them only after a backup and keep my own rules. Rerun monitoring/devstack/install.py
--host HOST only if the hooks changed, and tell me if Codex needs /hooks approval again. Finish
with scripts/setup_doctor.py --host HOST and the commit the checkout is now on. Create no ticket
and touch no project or production system.
```

## Health check (read-only)

```text
Check DevStack on this host (HOST = mac | devbox | windows) without changing anything. Run
scripts/check.py, scripts/setup_doctor.py --host HOST and tools/freshness.py --fetch . in the
checkout. Report every FAIL and WARN with its cause and the exact fix from docs/onboarding.md 2.7
or docs/setup.md troubleshooting, whether the checkout is behind origin/main, and whether this
session showed the DevStack status line. Fix nothing, create no ticket, never print credentials.
```

## Set my KPI targets

```text
Set my DevStack KPI targets on this host, following docs/setup.md "Set your targets". If
~/.config/devstack/kpi-targets.json is missing, copy examples/kpi-targets.example.json there, then
set these targets: <for example: security_holes_pct <=0, kvalitet >=95, bench median_minutes <=4,
verified_success_pct >=95>. Use only metric names from monitoring/devstack/README.md "Targets and
hill-climbing". Finish with kpi_monitor.py scorecard and tell me which targets have no
measurement yet and what produces it (a bench run, --review for kvalitet, or recorded tasks).
```

## Hill-climb to my targets

```text
Hill-climb DevStack to my KPI targets, following skills/workflow-eval/SKILL.md section 5.
Budget: <for example 6 iterations or 4 hours>. Start with a baseline bench run and the scorecard,
then per iteration: pick the largest gap, change one thing in a candidate worktree (never the
bench tasks, graders or my targets), run the A/B bench with --trials 3 (and --review when kvalitet
is a target) and let bench/bench.py gate
decide. Ship a KEEP or TOP as a normal PR; revert the rest. Stop at TOP, a plateau of three
iterations without KEEP, or the budget. Report a table per iteration: values, verdict, change.
```

## Ticket numbers on this machine

```text
Prepare this machine to issue new DevStack ticket references, following docs/onboarding.md 2.6.
Read tools/ticket-ref/SLOTS.md and slots.json, propose a free slot (10–99) and an --after value,
and open the slots.json PR for me with an opaque owner label (no name, email or host details).
After it is merged, run ticket_ref.py init with that slot and scripts/ticket_launcher.py install
(dry run first, then --apply). Never copy a counter from another machine, reuse a slot or reset
it. Finish with ticket-ref running from PATH.
```

## Move or uninstall

```text
Move my DevStack checkout from OLD_PATH to its current folder (or: uninstall DevStack from this
host), following docs/onboarding.md 2.8. Run scripts/detach.py (with --from OLD_PATH for a move)
without --apply first and show me the plan, then apply it. For a move, relink the skills, rerun
monitoring/devstack/install.py --host HOST and scripts/ticket_launcher.py install --apply if
ticket-ref is installed, and tell me when to approve the changed hooks in Codex. Keep my own
hooks, files and anything behind a symlink. Finish with scripts/setup_doctor.py --host HOST
showing no FAIL and no "points to missing" row.
```

## Your first tasks

DevStack needs no special prompt for work. A concrete change request starts a task, and Full Send is the default:

```text
Fix <what is wrong> in <repo>. <Where it shows and how to see it.>
```

```text
Full Stop: <change> in <repo>. I want to decide <the product or approach question> before you build it.
```

Under [Full Send](../skills/full-send/SKILL.md) the lead carries the work through review, CI, the established test deployment and live proof, and merges its own ready PR ([merge rule](../skills/devstack/references/coordination.md#merge)). Higher risk raises review depth and proof instead of stopping. [Full Stop](../skills/full-stop/SKILL.md) adds your decisions and an in-depth R2 or R3 review before the lead merges through the merge gate. It applies when you ask for it or when a revert cannot undo the change (production, destructive or irreversible data operations, a very large high-impact intake). Production deploys always need your explicit authority.
