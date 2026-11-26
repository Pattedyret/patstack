# Onboarding — Patstack

A first-day guide for a developer who uses Claude Code, Codex or both, on macOS, Linux or Windows. It condenses [setup](setup.md), the [workflow README](../README.md) and your project pack into what you need to start; those documents stay authoritative. Commands are shown for macOS/Linux shells (`python3`); on Windows use `python` and the Windows notes in each step.

## 1. What Patstack is

- **One lead per task.** Ask for a change ("fix X", "add Y") and one lead agent owns it from request to proof: plan, build, review, verify, deliver and learn. It may brief helper agents, but it keeps the outcome, the spec and the repair loop.
- **Full Send is the default.** The lead makes routine decisions itself and carries the work through PR review, required CI, the established test deployment and live proof on that test release.
- **Full Stop** is the hands-on mode: you decide meaningful product and approach questions, the change gets an in-depth **R2 or R3** review, and the lead stops at the ready PR so you can check it; a human merges. Say "Full Stop" to choose it; on a CRITICAL or unclassified project the lead also picks it when a revert cannot undo the change (production, destructive or irreversible data operations, a very large high-impact intake). INTERNAL projects are always Full Send.
- **Review depth follows risk, not size:** R1 is the author's own check, R2 one independent reviewer from the other model family, R3 a two-model council. With only Claude or only Codex, R2 is a fresh session of your provider under a [reviewer lens](../skills/review/references/lenses.md) (another system prompt), and R3 is two such sessions, one per lens. Auth, sessions, proxies, access rules, migrations and patient data take at least R2 (see your project's risk map).
- **Proof, not claims.** Every report labels evidence EXECUTED (tests or assertions ran), OBSERVED (real behaviour seen) or REASONED (reading only), and says whether production was touched. Missing proof is reported as missing.
- **The product vault** (named in the pack's `INDEX.md`) is the context source for each product: hosting, branches, dependencies, known risks and the product contract. Agents read it through the pack's vault procedure when a task needs that context or you ask for it (see 2.3). They write back only through a vault PR. Like every PR it follows the merge rule (Full Send: the lead merges through the merge gate after at least R1; Full Stop: after R2 or R3 the PR stays ready and a human merges). Agents never hand-write `CONTRACT.md`. Where a vault note disagrees with a repo's `DEPLOY.md` or a running system, the note is stale and gets reported.

## 2. Install (about 15 minutes)

You need Python 3.9+, `git`, `gh` (logged in), Node.js (for the pack's security tests) and Claude Code and/or Codex.

**The fast way:** clone (2.1), open Claude Code or Codex in the checkout and run `/start-here` (Codex: `$start-here`, or say "run start-here"). The skill works even before anything is installed, because the checkout ships it in `.claude/skills` and `.agents/skills`. It runs [`scripts/start_here.py`](../scripts/start_here.py) for 2.2 to 2.5 and the bundled project pack, merges what needs judgment with you, and ends with the health check (2.6). You can also run the script yourself: `python3 scripts/start_here.py` (dry run), then `--apply`. The sections below are what it does, by hand. Using T3 Code: read [Patstack in T3](t3.md) first.

### 2.1 Clone and validate

Clone into a folder you will keep: links, hooks and instructions point at this checkout. Moving it later needs the steps in 2.7.

```bash
git clone "https://github.com/OWNER/REPO.git" patstack && cd patstack   # this repository's GitHub path
python3 scripts/check.py
```

Expect a line starting with `OK:`. Run every later command from this folder. **On Windows** the full check does not pass yet: several test suites assume Linux or macOS (shell scripts, symlinks, file permissions). Skip it there and validate your setup with `setup_doctor.py` in 2.6 instead.

### 2.2 Expose the 20 skills

Link each skill folder into the skill folder of each client you use (`~/.claude/skills` for Claude Code, `~/.agents/skills` for Codex). Linking both does no harm. The setup check only looks at clients it finds in use. Existing entries are left alone and listed.

```bash
mkdir -p ~/.claude/skills ~/.agents/skills
for d in skills/*/; do n=$(basename "$d")
  for dest in ~/.claude/skills ~/.agents/skills; do
    if [ -e "$dest/$n" ] || [ -L "$dest/$n" ]; then echo "left alone: $dest/$n"; else ln -s "$PWD/skills/$n" "$dest/$n"; fi
  done
done
```

Anything printed as "left alone" is an older installation: inspect it. A leftover `patstack` link is the coordinator's old name: remove it and link `patstack`. Keep project packs outside global discovery and route each project to its pack index. Preserve owner-managed entries and inspect duplicate procedures before changing them.

**Windows:** native clients read copies, not links. Create and later refresh them with:

```bash
python scripts/skill_mirrors.py --apply    # creates or refreshes the 20 mirrors in both folders, backs up what it replaces
python scripts/skill_mirrors.py --check    # lists stale or missing mirror files
```

Rerun `--apply` after every `git pull`, or Windows agents keep reading the old text.

### 2.3 Install the global instructions without overwriting yours

```bash
global=$(mktemp)
python3 -c 'import os, sys; sys.stdout.write(open(sys.argv[1]).read().replace("<PATSTACK>", os.getcwd()))' examples/global-instructions/AGENTS.md > "$global"
python3 - "$global" <<'PY'
import os, sys
text = open(sys.argv[1]).read()
for name in ("~/.claude/CLAUDE.md", "~/.codex/AGENTS.md"):
    path = os.path.expanduser(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:  # O_EXCL: never replace or follow an existing file or link
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        print("kept your existing", name)
        continue
    with os.fdopen(fd, "w") as out:
        out.write(text)
    print("installed", name)
PY
```

The `[ -e … ] ||` guard copies only where no file exists yet. **If you already have one,** back it up (`cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak`) and merge by hand: keep your own rules, add the template's sections, drop any older workflow block that names another router, and keep the template's first line `<!-- patstack-global-instructions -->` so the setup check recognises it. Where rules disagree, the stricter authority rule wins. Details: [setup step 3](setup.md#3-add-your-global-instructions).

**Windows (PowerShell), from the checkout:** writes each file only where none exists, and backs up and names any existing one for you to merge by hand (copies, never links):

```powershell
$template = (Get-Content examples\global-instructions\AGENTS.md -Raw).Replace('<PATSTACK>', (Get-Location).Path)
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

### 2.4 Add the merge guard hook

`scripts/start_here.py --apply` adds the merge guard for both clients, with a backup. By hand: add it from [setup step 6](setup.md#6-merge-guard-hook) to Claude Code `~/.claude/settings.json` and the same block to Codex `~/.codex/hooks.json`, with the absolute path of your checkout. Back up the file first and keep your existing hooks:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "python3 /abs/patstack/tools/merge_guard.py"}]}]}}
```

It refuses a direct pull request merge from the shell, so merges go through `tools/merge_gate.py`. **Codex runs a new hook only after you trust it**, and skips an untrusted hook without a word: start `codex` once in a terminal and choose **Trust all and continue** (or review it under `/hooks`). The setup check reports a Codex guard that is not trusted yet as `WARN`.

On **Windows**, do not use `python3` (usually only the Store placeholder, so the guard would never run): let PowerShell build the entry with the snippet in [setup step 6](setup.md#6-merge-guard-hook), which gets the real `python.exe`, the slashes and the quoting right.

### 2.5 Ticket numbers

You never run ticket commands; your agent does. On the team board (Monday), the first time it needs a ticket it checks whether your Monday access is set up. If not, it opens Monday's token page in your browser and asks you to paste a personal API token into a private input box; it stores the token on your machine only. Tickets then appear as subitems under the right roadmap item, with their number in the `Ticket Number` column. Continuing existing work needs nothing: the agent reuses the task's `TKT-…` number. The first time an agent on a new machine needs a new number, it asks you which **slot** this machine was given and sets everything up itself ([how](../skills/patstack/references/coordination.md)).

**Team machines:** slots 10–14 are reserved for the team's five machines, with labels `team-dev-10` … `team-dev-14`. The Patstack maintainer hands each machine exactly one of them; never pick one yourself, because two machines on one slot issue the same numbers. Someone outside the team claims a slot (15–99) by PR against [`tools/ticket-ref/slots.json`](../tools/ticket-ref/slots.json), as [SLOTS.md](../tools/ticket-ref/SLOTS.md) describes, before their agent sets up.

Numbers are permanent: to find a task again, ask the agent for it by number, or search GitHub for `TKT-<n>`. Never copy a counter to another machine, reuse a slot or reset it; when you replace a machine, the agent sets the new one up with its own slot.

### 2.6 Check the setup

```bash
python3 scripts/setup_doctor.py --host mac     # mac | devbox (any Linux) | windows; add --json for machine-readable output
```

It changes nothing and exits 1 only on `FAIL`. Run it by hand after setup and after each update. After the steps above every row should be `OK`, except the rows below.

| Line | Meaning and what to do |
|---|---|
| `INFO … codex not set up on this host` (or `claude …`) | That client's binary and its own state were not found, so its rows are skipped. If you do use it, start it once or pass `--clients both`. |
| `WARN ticket-ref … missing` | Only needed to issue new numbers (2.5). |

Any other `WARN` or `INFO` row names its own fix; [setup: check the setup](setup.md#check-the-setup) explains each status. A `FAIL` line names what is broken (an unlinked skill, a missing instruction file, a hook pointing to a missing file, `disableAllHooks`); fix it before relying on the setup. A green check proves configuration only. A `WARN` about a retired Patstack hook means an old hook entry is still wired: remove that entry from the client's hook file.

### 2.7 Move or uninstall

`scripts/detach.py` undoes the setup for one checkout. Without `--apply` it only prints what it would change. It removes:

- skill links that point into the checkout;
- on uninstall, mirror copies that are still identical to what `skill_mirrors.py` writes;
- the retired KPI and session-status hooks that point into that checkout.

It does not remove the merge guard hook; delete or repoint that `PreToolUse` entry in `~/.claude/settings.json` yourself.

It keeps everything else: your own hooks (also ones that mention the checkout), edited or added files, and anything reached through a symlink. It checks every folder from your home down: if `~/.claude`, `~/.codex`, `~/.agents` or one of their `skills` folders is a symlink to a shared folder, nothing under it is touched. When matching Patstack pieces remain behind such a link, the output lists them under `left_in_place` and the exit code is 3. Add `--follow-client-links` only if you keep those folders in a shared place on purpose; the same rules then apply to the shared folder. Every change is backed up to a new folder under `~/.local/state/patstack/detach-backups/`. Run it again and it reports nothing to change.

**Move the checkout:** move the folder, `cd` into the new location, then:

```bash
python3 scripts/detach.py --from <old-path>            # review the plan
python3 scripts/detach.py --from <old-path> --apply    # drop the old links and hooks, repoint both instruction files
```

Then relink the skills (2.2; Windows: `python scripts/skill_mirrors.py --apply`), add the merge guard again with the new path (2.4) and rerun `/start-here`, which also reinstalls the `ticket-ref` launcher for the new path. `setup_doctor.py` must show no `FAIL` and no `points to missing` row. A symlinked instruction file is listed under `kept` and left alone; edit its target yourself.

**Uninstall:** from the checkout, run `python3 scripts/detach.py`, then the same with `--apply`. Delete the template sections from the instruction files it lists under `manual`, or restore your `.bak` copy. In `~/.local/state/patstack/` keep `tickets.sqlite3` if you may come back, so your slot never reissues a number. Then delete the clone.

## 3. Daily use

### How a task flows

You ask in plain language; no keyword is needed. The lead allocates or reuses a `TKT-…` reference, picks the mode and route, and reports at the end with the outcome first.

| You say | What happens |
|---|---|
| "Fix the redirect loop after login in the calendar app" | Bounded fix: red reproduction first, smallest fix, review by risk (auth means R2), PR, CI, test deployment, live proof. |
| "Make the save button use the brand colour" | Tiny route: direct edit, R1, focused visual check, PR. |
| "Build CSV export for reports" | New feature: a spec in the GitHub Issue, slices only where useful, R2/R3, quality proof, delivery. |
| "Full Stop: change how roles are checked" | You decide the meaningful choices; after R2/R3 review the lead stops at the ready PR and reports Done/Verified/Unresolved/Next; a human merges. |
| "Continue TKT-…" / "Take over PR #…" | Resumes the same reference, rechecks the current state instead of trusting the handoff, keeps original credit. |
| "Babysit the PR" | Watches CI and review and repairs findings on the same task. |
| "What do you think about …?" | Discussion only. Nothing changes and no ticket is created. |

Use the reference in branch names, PR titles (`[TKT-…] Short title`) and handoffs. Any capable agent or teammate can continue a referenced task; a number grants no ownership or permission.

### Full Send or Full Stop

**Full Send** is the default and as autonomous as possible: it carries the work through review, merges the ready PR itself and verifies the test release. Sensitive work (auth/permissions, personal data, shared APIs) gets deeper review and proof, not a stop. Choose **Full Stop** when you want to be involved in decisions; on a CRITICAL or unclassified project the agent also picks it when a revert cannot undo the change (production, destructive or irreversible data operations). Neither mode includes production on a CRITICAL or unclassified project; an INTERNAL project's own production is covered by the owner's tier grant.

### What the agent will and will not do

| Will | Will not |
|---|---|
| Make reversible in-scope changes on its own and decide routine technical choices | Deploy to production or run production cut-overs without explicit authority for that task, except an INTERNAL project's own production; change production data without that authority in any tier |
| Open PRs, push its own branches, mark its own PR ready, request re-review and merge through the merge gate under the [merge rule](../skills/patstack/references/coordination.md#merge) (Full Send, after at least R1; a Full Stop PR stays ready after R2 or R3 and a human merges it) | Merge directly with `gh pr merge`, merge without a review record for the head, or merge where production, a destructive data operation, the repo's `AGENTS.md`/`DEPLOY.md`, branch protection or a project approval keeps a human gate |
| Read the product vault, propose vault changes as a PR and merge it under the [merge rule](../skills/patstack/references/coordination.md#merge) (Full Send) | Hand-write `CONTRACT.md` |
| Deploy to the established test target in Full Send (an auto-deploying merge counts as a deploy) | Force-push, `reset --hard`, reset/reseed shared data or delete outside data the task owns |
| Run the repo's CI script on the PR yourself (`tools/local_ci.py`), and add the script when the repo has none | Treat missing proof, a green deploy message or model agreement as proof |
| Stop with one precise request when it needs access, a human gate or a Full Stop decision | Forge approvals, identities or sessions |

### Giving access safely

- **Logins go through your password manager**, not chat. The workflow assumes Bitwarden with origin-matched browser autofill or an approved secret-safe CLI path ([access reference](../skills/patstack/references/access.md)). You unlock the vault and complete MFA yourself; the agent never asks for, prints or stores a password, token, cookie or signed URL.
- **Use the project's test personas.** Follow its persona table for the least-privilege account, allowed origin/environment and secret-safe access path. Missing access is a blocker; never borrow a stronger account. Password-manager collection access is provisioned by the project's account administrator.
- **Never paste secrets** into a prompt, an issue or a PR, even "just this once". If you did, rotate the secret.
- `gh` and the clients use their own logins; Patstack adds no service accounts and no paid services.

### macOS, Linux and Windows notes

| Platform | Note |
|---|---|
| macOS | Claude Code stores its login in the macOS Keychain. In an SSH session the login keychain can be locked, so `claude` may report you as logged out although it works at the desk. Run `security unlock-keychain` in that SSH session and type your password at its prompt, or log in locally. Never hand that password to an agent. |
| Linux | Claude Code keeps its login in a file under `~/.claude/` and Codex under `~/.codex/`, so they work over SSH as the same user. For a machine without a browser use `codex login --device-auth`. |
| Windows | Use `python`, copies instead of links (skill mirrors, instruction files) and `ticket-ref.cmd`. The private stores inherit your user profile's permissions; check that no other account can read your profile. |
| All | If the client's login has expired, hooks still run but the model never answers: log in again (`claude`, then `/login`; `codex login`). |

## 4. Retro

At each task's endpoint the lead runs a proportionate [retro](../skills/retro/SKILL.md). It works from the task's own PR, Issue, CI and review history and checks that evidence before proposing any workflow improvement. Preference and product changes still need a human decision.

## 5. Getting help

| Symptom | First step |
|---|---|
| Agents follow old rules after a team update | `git pull --ff-only`, `scripts/check.py`; Windows: `skill_mirrors.py --apply` |
| `check.py`: `node is not installed` | Install Node.js; `--allow-missing-node` gives `INCOMPLETE` (exit 3), never `OK` |
| `bench.py`: `grading needs bubblewrap (bwrap)` | The benchmark is optional. Install bubblewrap on Linux; on macOS see the [benchmark notes](../bench/README.md#isolation-and-safety) |
| `FAIL … points to missing …` | The checkout moved: follow 2.7 |
| `ticket-ref`: `not initialized` | Step 2.5 (only for new numbers) |
| Not sure what is wrong | Paste the read-only health-check prompt from [setup prompts](setup-prompts.md) |
| The agent stops for access or approval | A real gate: give access through the proper channel, or tell it to skip that part |

More in [setup: check the setup](setup.md#check-the-setup) and [status and limits](status-and-limits.md). When asking a teammate, share the `setup_doctor.py` output: it shows local paths but no secrets.

## 6. Checklist

- [ ] Python 3.9+, `git`, `gh` (logged in), Node.js and Claude Code and/or Codex installed
- [ ] Cloned into a permanent folder; `python3 scripts/check.py` prints `OK:`
- [ ] 20 skills linked into `~/.claude/skills` and `~/.agents/skills` (Windows: `skill_mirrors.py --apply`); no old `patstack` link left
- [ ] Global instructions installed or merged by hand, existing files backed up, first-line marker kept
- [ ] Merge guard hook added to `~/.claude/settings.json`
- [ ] Slot claimed in `tools/ticket-ref/slots.json` by PR and the ticket counter initialised with it, if you will start new tasks
- [ ] `scripts/setup_doctor.py --host …` shows no `FAIL`, and each `WARN` is understood
- [ ] Password manager unlocked by you, test personas available for the apps you work on
- [ ] Read the project's risk map and verification boundaries
- [ ] First small task done end to end, with its proof reported
