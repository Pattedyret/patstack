# Setup prompts

Copy-paste prompts for setting up and maintaining Patstack with Claude Code or Codex. Each prompt hands the agent one job. The steps stay in [setup](setup.md) and [onboarding](onboarding.md). The prompt names its doc section, its limits and the proof to finish with. Paste it into a new session on the host you are setting up. Replace `HOST` with `mac`, `devbox` (any Linux machine) or `windows`.

Every prompt keeps the same limits: no ticket, no project or production change, no credentials in chat or files, and a backup before any client configuration changes. Steps that need you (passwords, logins) come back to you as a short list.

## Install Patstack on a new host

The simplest way is the skill: open Claude Code or Codex in a fresh clone and run `/start-here`. The prompt below does the same by hand.

```text
Install Patstack on this host (HOST = mac | devbox | windows) for Claude Code and/or Codex,
following docs/onboarding.md section 2 in your Patstack checkout. If no checkout exists,
clone it into a permanent folder (for example code/patstack in my home folder) and tell me the path.
1. Check the prerequisites (Python 3.9+, git, gh logged in, Node.js) and
   report what is missing instead of installing paid or system software without asking.
2. Run scripts/check.py and stop if it does not print OK.
3. Expose the 20 skills (2.2; Windows: scripts/skill_mirrors.py --apply). Leave existing entries
   alone and list them; flag any old patstack link. Never link private project packs into global discovery.
4. Install the global instructions (2.3) from examples/global-instructions/AGENTS.md. Where
   ~/.claude/CLAUDE.md or ~/.codex/AGENTS.md exists, back it up, show me the merge as a diff and
   keep my own rules and the first-line marker.
5. Add the merge guard hook (2.4) to ~/.claude/settings.json.
6. Run scripts/setup_doctor.py --host HOST and fix only what it reports.
Create no ticket, touch no project or production system, never print credentials. Finish with the final
setup_doctor.py output and the items that still need me.
```

## Update after a Patstack change

```text
Update Patstack on this host (HOST = mac | devbox | windows) to the latest main of
your Patstack repository. Fetch first; fast-forward the checkout only if it is clean and on main,
otherwise stop and tell me what is in the way. Then run scripts/check.py. On Windows run
scripts/skill_mirrors.py --apply and --check. Compare my ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md
with examples/global-instructions/AGENTS.md and show me new or changed template sections as a
diff; merge them only after a backup and keep my own rules. Update the merge guard hook (setup step 6)
only if its form changed. Finish
with scripts/setup_doctor.py --host HOST and the commit the checkout is now on. Create no ticket
and touch no project or production system.
```

## Health check (read-only)

```text
Check Patstack on this host (HOST = mac | devbox | windows) without changing anything. Run
scripts/check.py, scripts/setup_doctor.py --host HOST and tools/freshness.py --fetch . in the
checkout. Report every FAIL and WARN with its cause and the exact fix from docs/onboarding.md 2.6
or docs/setup.md "Check the setup", and whether the checkout is behind origin/main. Fix nothing, create no ticket, never print credentials.
```

## Set my bench targets

```text
Set my Patstack bench targets on this host, following bench/README.md "Targets and the hill-climb
gate". If ~/.config/patstack/bench-targets.json is missing, copy examples/bench-targets.example.json
there, then set these targets: <for example: security_holes_pct <=0, kvalitet >=95,
median_minutes <=4>. Use only the metric names listed in bench/README.md. Tell me which targets
have no measurement yet and what produces it (a bench run, or --review for kvalitet).
```

## Hill-climb to my targets

```text
Hill-climb Patstack to my bench targets, following skills/workflow-eval/SKILL.md section 5.
Budget: <for example 6 iterations or 4 hours>. Start with a baseline bench run and its Targets table,
then per iteration: pick the largest gap, change one thing in a candidate worktree (never the
bench tasks, graders or my targets), run the A/B bench with --trials 3 (and --review when kvalitet
is a target) and let bench/bench.py gate
decide. Ship a KEEP or TOP as a normal PR; revert the rest. Stop at TOP, a plateau of three
iterations without KEEP, or the budget. Report a table per iteration: values, verdict, change.
```

## Ticket numbers on this machine

```text
Prepare this machine to issue new Patstack ticket references, following docs/onboarding.md 2.5.
Follow skills/patstack/references/coordination.md "Set up a machine": ask me for this machine's
slot (team machines 10-14, handed out by the maintainer; never pick one yourself), derive --after
from GitHub history plus the margin, run ticket_ref.py init and scripts/ticket_launcher.py install --apply.
Never copy a counter from another machine, reuse a slot or reset it. Finish with ticket-ref running
from PATH.
```

## Move or uninstall

```text
Move my Patstack checkout from OLD_PATH to its current folder (or: uninstall Patstack from this
host), following docs/onboarding.md 2.7. Run scripts/detach.py (with --from OLD_PATH for a move)
without --apply first and show me the plan, then apply it. For a move, relink the skills, add the
merge guard hook again with the new path and run scripts/ticket_launcher.py install --apply if
ticket-ref is installed. Keep my own
hooks, files and anything behind a symlink. Finish with scripts/setup_doctor.py --host HOST
showing no FAIL and no "points to missing" row.
```

## Your first tasks

Patstack needs no special prompt for work. A concrete change request starts a task, and Full Send is the default:

```text
Fix <what is wrong> in <repo>. <Where it shows and how to see it.>
```

```text
Full Stop: <change> in <repo>. I want to decide <the product or approach question> before you build it.
```

Under [Full Send](../skills/full-send/SKILL.md) the lead carries the work through review, CI, the established test deployment and live proof, and merges its own ready PR ([merge rule](../skills/patstack/references/coordination.md#merge)). Higher risk raises review depth and proof instead of stopping. [Full Stop](../skills/full-stop/SKILL.md) adds your decisions and an in-depth R2 or R3 review, then stops at the ready PR so you can check and merge it. It applies when you ask for it or when a revert cannot undo the change (production, destructive or irreversible data operations, a very large high-impact intake). Production deploys always need your explicit authority.
