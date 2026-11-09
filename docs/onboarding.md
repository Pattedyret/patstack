# Onboarding — DevStack

A first-day guide for a developer who uses Claude Code, Codex or both, on macOS, Linux or Windows. It condenses [setup](setup.md), the [workflow README](../README.md) and your project pack into what you need to start; those documents stay authoritative. Commands are shown for macOS/Linux shells (`python3`); on Windows use `python` and the Windows notes in each step.

## 1. What DevStack is

- **One lead per task.** Ask for a change ("fix X", "add Y") and one lead agent owns it from request to proof: plan, build, review, verify, deliver and learn. It may brief helper agents, but it keeps the outcome, the spec and the repair loop.
- **Full Send is the default.** The lead makes routine decisions itself and carries the work through PR review, required CI, the established test deployment and live proof on that test release.
- **Full Stop** is the hands-on mode: you decide meaningful product and approach questions, the change gets an in-depth **R2 or R3** review, and the lead merges it through the merge gate. Say "Full Stop" to choose it; on a CRITICAL or unclassified project the lead also picks it when a revert cannot undo the change (production, destructive or irreversible data operations, a very large high-impact intake). FRIENDS and INTERNAL projects are always Full Send.
- **Review depth follows risk, not size:** R1 is the author's own check, R2 one independent reviewer from the other model family, R3 a two-model council. Auth, sessions, proxies, access rules, migrations and patient data take at least R2 (see your project's risk map).
- **Proof, not claims.** Every report labels evidence EXECUTED (tests or assertions ran), OBSERVED (real behaviour seen) or REASONED (reading only), and says whether production was touched. Missing proof is reported as missing.
- **The product vault** (named in the pack's `INDEX.md`) is the context source for each product: hosting, branches, dependencies, known risks and the product contract. Agents read it through the pack's vault procedure when a task needs that context or you ask for it (see 2.3). They write back only through a vault PR. Like every PR it follows the merge rule: the lead merges through the merge gate: Full Send after at least R1, Full Stop after R2 or R3. Agents never hand-write `CONTRACT.md`. Where a vault note disagrees with a repo's `DEPLOY.md` or a running system, the note is stale and gets reported.

## 2. Install (about 15 minutes)

You need Python 3.9+, `git`, `gh` (logged in), Node.js (for the pack's security tests) and Claude Code and/or Codex. Codex should be 0.160 or newer, because older versions skip the KPI hooks.

Rather let an agent do it? Paste the install prompt from [setup prompts](setup-prompts.md) into a new session; it follows this section, backs up what it changes and hands back the steps that need you.

### 2.1 Clone and validate

Clone into a folder you will keep: links, hooks and instructions point at this checkout. Moving it later needs the steps in 2.8; rerunning the installer alone leaves the old hooks behind.

```bash
git clone https://github.com/<owner>/devstack.git devstack && cd devstack
python3 scripts/check.py
```

Expect a line starting with `OK:`. Run every later command from this folder.

### 2.2 Expose the 19 skills

Link each skill folder into the skill folder of each client you use (`~/.claude/skills` for Claude Code, `~/.agents/skills` for Codex). Linking both does no harm. The setup check only looks at clients it finds in use. Existing entries are left alone and listed.

```bash
mkdir -p ~/.claude/skills ~/.agents/skills
for d in skills/*/; do n=$(basename "$d")
  for dest in ~/.claude/skills ~/.agents/skills; do
    if [ -e "$dest/$n" ] || [ -L "$dest/$n" ]; then echo "left alone: $dest/$n"; else ln -s "$PWD/skills/$n" "$dest/$n"; fi
  done
done
```

Anything printed as "left alone" is an older installation: inspect it. A leftover `patstack` link is the pre-rename coordinator; see the [migration note](setup.md#migrating-from-the-old-name). Keep project packs outside global discovery and route each project to its pack index. Preserve owner-managed entries and inspect duplicate procedures before changing them.

**Windows:** native clients read copies, not links. Create and later refresh them with:

```bash
python scripts/skill_mirrors.py --apply    # creates or refreshes the 19 mirrors in both folders, backs up what it replaces
python scripts/skill_mirrors.py --check    # lists stale or missing mirror files
```

Rerun `--apply` after every `git pull`, or Windows agents keep reading the old text.

### 2.3 Install the global instructions without overwriting yours

```bash
sed "s#<DEVSTACK>#$PWD#g" examples/global-instructions/AGENTS.md > /tmp/devstack-global.md
mkdir -p ~/.claude ~/.codex
[ -e ~/.claude/CLAUDE.md ] || cp /tmp/devstack-global.md ~/.claude/CLAUDE.md
[ -e ~/.codex/AGENTS.md ]  || cp /tmp/devstack-global.md ~/.codex/AGENTS.md
```

The `[ -e … ] ||` guard copies only where no file exists yet. **If you already have one,** back it up (`cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak`) and merge by hand: keep your own rules, add the template's sections, drop any older workflow block that names another router, and keep the template's first line `<!-- devstack-global-instructions -->` so the setup check recognises it. Where rules disagree, the stricter authority rule wins. Details: [setup step 3](setup.md#3-add-your-global-instructions).

**Windows (PowerShell), from the checkout:** writes each file only where none exists, and backs up and names any existing one for you to merge by hand (copies, never links):

```powershell
$template = (Get-Content examples\global-instructions\AGENTS.md -Raw).Replace('<DEVSTACK>', (Get-Location).Path)
foreach ($file in "$HOME\.claude\CLAUDE.md", "$HOME\.codex\AGENTS.md") {
  New-Item -ItemType Directory -Force (Split-Path $file) | Out-Null
  if (Test-Path $file) {
    $backup = "$file.$(Get-Date -Format yyyyMMddHHmmss).bak"
    Copy-Item $file $backup
    Write-Output "Exists, left unchanged (backup: $backup). Merge the template by hand: $file"
  } else {
    Set-Content -Path $file -Value $template -Encoding utf8 -NoNewline
  }
}
```

**Product-vault context** is configured through the project's pack. Follow its index for mandatory intake context, reading limits and retro write-back. A setup install does not establish that those steps ran for a task.

### 2.4 Install the KPI and status hooks

```bash
python3 monitoring/devstack/install.py --host mac       # Linux: --host devbox; Windows: python … --host windows
```

`devbox` is the host name for any Linux machine. The installer keeps every existing hook, never adds a second copy, backs up every file it changes to `~/.local/state/devstack/install-backups/<time>/` and adds a short KPI pointer block to both instruction files. It prints the files it changed. Use `--skip-codex-hook` only if your Codex hook file is managed by someone else.

### 2.5 Approve the hooks in Codex

Codex runs a new or changed hook only after you approve it. Start `codex` once on this host, then either run `/hooks` inside Codex and approve the three DevStack hooks, or:

```bash
python3 scripts/codex_hook_trust.py --dry-run   # list DevStack hooks and their trust status
python3 scripts/codex_hook_trust.py             # show each full command, ask, then approve
```

The script approves only the installer's own hook commands. Approve again after any reinstall that changes a hook. Claude Code needs no approval step.

### 2.6 Ticket numbers (only if you will start new tasks)

Continuing existing work needs nothing here: reuse its `TKT-…` reference. To issue new references on this machine, first claim a slot (10–99) that **no other machine on the team uses**: open a PR against [`tools/ticket-ref/slots.json`](../tools/ticket-ref/slots.json) with an opaque owner label, as described in [SLOTS.md](../tools/ticket-ref/SLOTS.md), which also explains how to choose `--after`. After the PR is merged:

```bash
python3 tools/ticket-ref/ticket_ref.py init --slot <your-slot> --after <highest-number> --owner <your-label>
python3 scripts/ticket_launcher.py install            # dry run: shows what it would write
python3 scripts/ticket_launcher.py install --apply    # writes ~/.local/bin/ticket-ref (Windows: ticket-ref.cmd)
```

On Windows use `python`. An existing launcher is kept under a new `ticket-ref.<time>.bak` name before it is replaced, and nothing is ever written through a symlink. If `~/.local/bin` (or a folder above it) is itself a symlink to a shared folder, it refuses (exit code 3) unless you add `--follow-client-links`. If `~/.local/bin` is not on your `PATH`, the output says how to add it. Never copy a counter to another machine, reuse a slot or reset it. The counter holds only a slot and a sequence; see the [numbering contract](../tools/ticket-ref/README.md).

### 2.7 Check the setup

```bash
python3 scripts/setup_doctor.py --host mac     # same --host as in 2.4; add --json for machine-readable output
```

It changes nothing and exits 1 only on `FAIL`. After the steps above every row should be `OK`, except the rows below. Each new session also starts with a one-line version of this check (`📈 DevStack monitoring on …` or `⚠ DevStack setup broken …`).

| Line | Meaning and what to do |
|---|---|
| `WARN claude receipts` / `WARN codex receipts … never fired` | That client has not run a turn since the install. Start a fresh session, send one message, rerun the check; in Codex approve the hooks first (2.5). |
| `WARN kpi outcomes  no workflow snapshots recorded yet` | Normal on day one; clears after the first finished task. |
| `WARN codex trust  config.toml unavailable` / `… hook not trusted` | Start `codex` once and approve the hooks (2.5). |
| `INFO … codex not set up on this host` (or `claude …`) | That client's binary and its own state were not found, so its rows are skipped. If you do use it, start it once or pass `--clients both`. |
| `WARN ticket-ref … missing` | Only needed to issue new numbers (2.6). |

Any other `WARN` or `INFO` row names its own fix; [setup: check the setup](setup.md#check-the-setup) explains each status. A `FAIL` line names what is broken (an unlinked skill, a missing instruction file, a missing KPI `Stop` hook, a hook pointing to a missing file, `disableAllHooks`); fix it before relying on the setup. A green check proves configuration only: confirm in a fresh session that the status line appears and the receipt count rises.

### 2.8 Move or uninstall

`scripts/detach.py` undoes the setup for one checkout. Without `--apply` it only prints what it would change. It removes:

- skill links that point into the checkout;
- on uninstall, mirror copies that are still identical to what `skill_mirrors.py` writes;
- the hooks that `install.py` wrote for that checkout.

It keeps everything else: your own hooks (also ones that mention the checkout), edited or added files, and anything reached through a symlink. It checks every folder from your home down: if `~/.claude`, `~/.codex`, `~/.agents` or one of their `skills` folders is a symlink to a shared folder, nothing under it is touched. When matching DevStack pieces remain behind such a link, the output lists them under `left_in_place` and the exit code is 3. Add `--follow-client-links` only if you keep those folders in a shared place on purpose; the same rules then apply to the shared folder. Every change is backed up to a new folder under `~/.local/state/devstack/detach-backups/`. Run it again and it reports nothing to change.

**Move the checkout:** move the folder, `cd` into the new location, then:

```bash
python3 scripts/detach.py --from <old-path>            # review the plan
python3 scripts/detach.py --from <old-path> --apply    # drop the old links and hooks, repoint both instruction files
```

When you rerun `install.py` without detaching first, it names the old checkout and prints this `detach.py --from` command as a hint; it never removes anything itself. Then relink the skills (2.2; Windows: `python scripts/skill_mirrors.py --apply`), rerun `install.py` (2.4), approve the changed hooks in Codex (2.5) and rerun `ticket_launcher.py install --apply` if you use it. `setup_doctor.py` must show no `FAIL` and no `points to missing` row. A symlinked instruction file is listed under `kept` and left alone; edit its target yourself.

**Uninstall:** from the checkout, run `python3 scripts/detach.py`, then the same with `--apply`. Delete the block between `<!-- devstack-kpi:start -->` and `<!-- devstack-kpi:end -->` and the template sections from the instruction files it lists under `manual`, or restore your `.bak` copy. In `~/.local/state/devstack/` you may delete the KPI store (`kpis.sqlite3*`); keep `tickets.sqlite3` if you may come back, so your slot never reissues a number. Then delete the clone.

## 3. Daily use

### How a task flows

You ask in plain language; no keyword is needed. The lead allocates or reuses a `TKT-…` reference, records the KPI start, picks the mode and route, and reports at the end with the outcome first.

| You say | What happens |
|---|---|
| "Fix the redirect loop after login in the calendar app" | Bounded fix: red reproduction first, smallest fix, review by risk (auth means R2), PR, CI, test deployment, live proof. |
| "Make the save button use the brand colour" | Tiny route: direct edit, R1, focused visual check, PR. |
| "Build CSV export for reports" | New feature: a spec in the GitHub Issue, slices only where useful, R2/R3, quality proof, delivery. |
| "Full Stop: change how roles are checked" | You decide the meaningful choices; after R2/R3 review the lead merges through the merge gate and reports Done/Verified/Unresolved/Next. |
| "Continue TKT-…" / "Take over PR #…" | Resumes the same reference, rechecks the current state instead of trusting the handoff, keeps original credit. |
| "Babysit the PR" | Watches CI and review and repairs findings on the same task. |
| "What do you think about …?" | Discussion only. Nothing changes and no ticket is created. |

Use the reference in branch names, PR titles (`[TKT-…] Short title`) and handoffs. Any capable agent or teammate can continue a referenced task; a number grants no ownership or permission.

### Full Send or Full Stop

**Full Send** is the default and as autonomous as possible: it carries the work through review, merges the ready PR itself and verifies the test release. Sensitive work (auth/permissions, personal data, shared APIs) gets deeper review and proof, not a stop. Choose **Full Stop** when you want to be involved in decisions; on a CRITICAL or unclassified project the agent also picks it when a revert cannot undo the change (production, destructive or irreversible data operations). Neither mode includes production on a CRITICAL or unclassified project; a FRIENDS or INTERNAL project's own production is covered by the owner's tier grant.

### What the agent will and will not do

| Will | Will not |
|---|---|
| Make reversible in-scope changes on its own and decide routine technical choices | Deploy to production or run production cut-overs without explicit authority for that task, except a FRIENDS or INTERNAL project's own production; change production data without that authority in any tier |
| Open PRs, push its own branches, mark its own PR ready, request re-review and merge through the merge gate under the [merge rule](../skills/devstack/references/coordination.md#merge) (Full Send after at least R1, Full Stop after R2 or R3) | Merge directly with `gh pr merge`, merge without a review record for the head, or merge where production, a destructive data operation, the repo's `AGENTS.md`/`DEPLOY.md`, branch protection or a project approval keeps a human gate |
| Read the product vault, propose vault changes as a PR and merge it under the [merge rule](../skills/devstack/references/coordination.md#merge) (Full Send) | Hand-write `CONTRACT.md` |
| Deploy to the established test target in Full Send (an auto-deploying merge counts as a deploy) | Force-push, `reset --hard`, reset/reseed shared data or delete outside data the task owns |
| Report missing CI as a risk ("no CI configured; proof is local only") | Treat missing proof, a green deploy message or model agreement as proof |
| Stop with one precise request when it needs access, a human gate or a Full Stop decision | Forge approvals, identities or sessions |

### Giving access safely

- **Logins go through your password manager**, not chat. The workflow assumes Bitwarden with origin-matched browser autofill or an approved secret-safe CLI path ([access reference](../skills/devstack/references/access.md)). You unlock the vault and complete MFA yourself; the agent never asks for, prints or stores a password, token, cookie or signed URL.
- **Use the project's test personas.** Follow its persona table for the least-privilege account, allowed origin/environment and secret-safe access path. Missing access is a blocker; never borrow a stronger account. Password-manager collection access is provisioned by the project's account administrator.
- **Never paste secrets** into a prompt, an issue or a PR, even "just this once". If you did, rotate the secret.
- `gh` and the clients use their own logins; DevStack adds no service accounts and no paid services.

### macOS, Linux and Windows notes

| Platform | Note |
|---|---|
| macOS | Claude Code stores its login in the macOS Keychain. In an SSH session the login keychain can be locked, so `claude` may report you as logged out although it works at the desk. Run `security unlock-keychain` in that SSH session and type your password at its prompt, or log in locally. Never hand that password to an agent. |
| Linux | Claude Code keeps its login in a file under `~/.claude/` and Codex under `~/.codex/`, so they work over SSH as the same user. For a machine without a browser use `codex login --device-auth`. |
| Windows | Use `python`, copies instead of links (skill mirrors, instruction files) and `ticket-ref.cmd`. The private stores inherit your user profile's permissions; check that no other account can read your profile. |
| All | If the client's login has expired, hooks still run but the model never answers: log in again (`claude`, then `/login`; `codex login`). |

## 4. KPIs and Retro

- **What is recorded:** per session, a hashed session ID, host, client, turn and tool-call counts and times (from the hooks); per task, the reference, workflow, topic, mode, status, verified yes/no/unknown, slices, review rounds and named proof results (recorded by the lead with `task_kpi.py start`/`finish`). **Never** prompts, tool input or output, transcripts, file contents or credentials. Everything stays in `~/.local/state/devstack/kpis.sqlite3` on your machine.
- **`topic=<repo>`:** each task records the repo name as its topic (for example `auth-api`), or the project slug when one ticket spans several repos. Generic topics such as `general` are rejected, so Retro can compare each repo with its own history.
- **Look at your own numbers:** `python3 monitoring/devstack/kpi_monitor.py report` (`by_topic`, `session_kpis` and more).
- **Opt-in team sharing:** `python3 monitoring/devstack/kpi_monitor.py export --aggregate` prints counts only per topic, workflow, status and host, with the day and no IDs, times or free text. Check the topic names, then share the output if you choose to. Never share the store itself or the `report` output.
- **Where Retro reads them:** at each task's endpoint the lead runs a proportionate [retro](../skills/retro/SKILL.md), which reads the current host report (per-topic verified success, slices, review rounds, missing CI) and then checks the underlying evidence before proposing any workflow improvement. Preference and product changes still need a human decision.

## 5. Getting help

| Symptom | First step |
|---|---|
| No status line, or receipts `never fired` | Fresh session; approve hooks in Codex (`/hooks`); `codex --version` (0.160+); `scripts/setup_doctor.py --host …` |
| Agents follow old rules after a team update | `git pull --ff-only`, `scripts/check.py`; Windows: `skill_mirrors.py --apply`; rerun the installer if a hook changed |
| `check.py`: `node is not installed` | Install Node.js; `--allow-missing-node` gives `INCOMPLETE` (exit 3), never `OK` |
| `bench.py`: `grading needs bubblewrap (bwrap)` | The benchmark is optional. Install bubblewrap on Linux; on macOS see the [benchmark notes](../bench/README.md#isolation-and-safety) |
| `FAIL … points to missing …` | The checkout moved: follow 2.8 |
| `ticket-ref`: `not initialized` | Step 2.6 (only for new numbers) |
| Not sure what is wrong | Paste the read-only health-check prompt from [setup prompts](setup-prompts.md) |
| The agent stops for access or approval | A real gate: give access through the proper channel, or tell it to skip that part |

More in [setup troubleshooting](setup.md#troubleshooting) and [status and limits](status-and-limits.md). When asking a teammate, share the `setup_doctor.py` output: it shows local paths but no secrets.

## 6. Checklist

- [ ] Python 3.9+, `git`, `gh` (logged in), Node.js and Claude Code and/or Codex (0.160+) installed
- [ ] Cloned into a permanent folder; `python3 scripts/check.py` prints `OK:`
- [ ] 19 skills linked into `~/.claude/skills` and `~/.agents/skills` (Windows: `skill_mirrors.py --apply`); no old `patstack` link left
- [ ] Global instructions installed or merged by hand, existing files backed up, first-line marker kept
- [ ] `monitoring/devstack/install.py --host …` run with the right host
- [ ] Codex hooks approved (`/hooks` or `scripts/codex_hook_trust.py`)
- [ ] Slot claimed in `tools/ticket-ref/slots.json` by PR and the ticket counter initialised with it, if you will start new tasks
- [ ] `scripts/setup_doctor.py --host …` shows no `FAIL`, and each `WARN` is understood
- [ ] A fresh session shows the DevStack status line and the receipt count rises
- [ ] Password manager unlocked by you, test personas available for the apps you work on
- [ ] Read the project's risk map and verification boundaries
- [ ] First small task done end to end, with its KPI outcome recorded
