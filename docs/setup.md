# Setup — DevStack

DevStack is a set of Markdown skills plus standard-library Python tools. Nothing here installs packages, starts daemons or creates scheduled jobs.

## Prerequisites

| Need | Why | Required? |
|---|---|---|
| Claude Code and/or Codex | Run the skills | Yes |
| Python 3.9+ | Ticket numbering, KPI recorder, checks, refresh script | Yes for the Python tools |
| `git`, `gh` | PRs, checks, Issue-based specs | For delivery |
| A private initialized `ticket-ref` store | Allocate new shared reference numbers offline | Only when issuing a new reference; see the [numbering contract](../coordination/README.md). |
| A host exposing the needed delegation or wakeup tools | Child delegation and PR watching | Only for those operations; follow its live tool contract. |
| Two model families (Opus 5.5 and Sol 6.1 by default) | R2/R3 independence | For R2/R3. A missing family is reported, not substituted. |
| A password manager client with origin-matched autofill | Secret-safe test logins (the [access reference](../skills/devstack/references/access.md) assumes Bitwarden) | Only for authenticated recipes |
| Playwright or native Computer Use | Browser and UI verification | Only for UI recipes; verify on the actual host |

## 1. Validate the checkout

```bash
python3 scripts/check.py
```

Expected output starts with `OK:`. The check runs offline. It also runs any bundled project pack's own tests; the auth-proxy security tests need Node.js (`node`). Without node the check fails. `python3 scripts/check.py --allow-missing-node` runs everything else and ends with `INCOMPLETE` and exit code 3, never `OK`: use it only where node cannot be installed, and run the full check elsewhere before relying on the pack.

## 2. Expose the skills

The skills link to files outside their own folder (`../../monitoring/…`, `../../../coordination/README.md`). Keep the repository as one tree and point your client at the **whole `skills/` directory**:

```bash
# Claude Code: personal skills directory
ln -s "$PWD/skills/devstack" ~/.claude/skills/devstack
ln -s "$PWD/skills/create-test-recipes" ~/.claude/skills/create-test-recipes
```

Repeat the link for each of the 19 folders listed in the [skill catalog](../README.md#skills). Inspect existing destinations first and preserve any owner-managed installation rather than overwriting it. For Codex, use the skills directory your Codex version discovers and link the same 19 folders. Point both clients to **one shared repository tree**, so Claude and Codex read identical files. Do not keep two edited copies.

Chirp/Xirp aliases are optional app-owned dependencies, outside this catalog. They can remain present on Unix when installed by their owner; Windows does not need unavailable aliases. Native frontend-design and Computer Use must be provided by the actual client. This repository does not vendor their managed payloads.

If a client resolves relative links from the symlink location rather than the real path, cross-references can miss. In that case open the referenced file from the repository root. `scripts/check.py` validates the links inside the repository only.

The 19 modules cooperate under DevStack. Keep retired, overlapping workflow collections out of discovery so an older router does not compete with them. Verify source files, links, fresh native discovery and actual task behavior separately: linking files alone does not establish activation. Windows mirrors can require external Markdown-link adaptation; verify the exact intended adaptation separately from canonical source parity. The reported Mac, Linux devbox and Windows checks are [upstream rollout history](status-and-limits.md#upstream-rollout-history); they establish no installation or activation of this team copy on your hosts. Existing GUI sessions may still need a reload.

## 3. Add your global instructions

DevStack expects a short global instruction block that loads the coordinator for every change request and names the numbering tool, real authority rules (test and production approvals, no destructive Git without approval), and where project packs live. The template is [examples/global-instructions/AGENTS.md](../examples/global-instructions/AGENTS.md). Claude Code reads `~/.claude/CLAUDE.md`; Codex reads `~/.codex/AGENTS.md`. Both can use the same text.

1. Copy the template and replace `<DEVSTACK>` with the absolute path of this checkout:

   ```bash
   global=$(mktemp)
   python3 -c 'import os, sys; sys.stdout.write(open(sys.argv[1]).read().replace("<DEVSTACK>", os.getcwd()))' examples/global-instructions/AGENTS.md > "$global"
   ```

2. **No existing file:** install it for each client you use.

   ```bash
   mkdir -p ~/.claude ~/.codex
   [ -e ~/.claude/CLAUDE.md ] || [ -L ~/.claude/CLAUDE.md ] || cp "$global" ~/.claude/CLAUDE.md
   [ -e ~/.codex/AGENTS.md ]  || [ -L ~/.codex/AGENTS.md ] || cp "$global" ~/.codex/AGENTS.md
   ```

   To keep one copy, place it once (for example `~/.codex/AGENTS.md`) and make the other path a symlink to it, which is how the upstream setup shares one file between both clients. On Windows, copy instead of linking.

3. **Existing file:** never overwrite it. Back it up (`cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak`), then merge by hand: keep your own rules, add the template's sections, and drop any older workflow block that names a different router (for example a pre-rename `patstack` block). Where your rules and the template disagree, decide deliberately; the stricter authority rule should win. Keep the first line `<!-- devstack-global-instructions -->`, so `scripts/setup_doctor.py` can report the template as installed.

4. Add one line per private project pack you use. Optional [model routing preferences](../MODEL_RANKING.md) describe actual available models; they do not decide ticket eligibility. Keep host details and anything private out of this file.

The KPI installer (step 6) appends its own short pointer block to the same files; it never replaces the rest.

## 4. Add a host capability profile (optional, per host)

```bash
mkdir -p ~/.config/devstack
cp examples/devices.example.json ~/.config/devstack/devices.local.json
chmod 600 ~/.config/devstack/devices.local.json
```

Fill in only aliases, capabilities and timestamped observations. Use SSH config aliases, not addresses. Credentials stay in their existing stores. If the file is absent, DevStack does fresh read-only discovery. Absence proves nothing about a device.

## 5. Project packs

Use a private pack shaped like [examples/project-pack](../examples/project-pack/README.md): an `INDEX.md` router plus conditional procedures and verification recipes. Keep packs and their skills outside global discovery. Add a project-matching pointer to the index in global instructions, and follow the steps the index declares, including mandatory intake context and retro write-back. A pack may ship in a private team checkout; it stays out of the public export.

The setup doctor discovers bundled `project-packs/*/INDEX.md` routers and read-only `tools/vault_context.py` tools. The checker admits only packs with an explicit `publication.json` privacy policy; all other pack paths remain rejected. The policy carries the reviewed pack-specific word hashes, branding expression and exact-line exceptions, while the full shared scan still runs.

### Product vault

If a pack declares a product vault, follow its index for the canonical repository, reading scope, word budget and setup variables. Verify the vault's origin and freshness. Intake follows the pack's context step before planning; task and child briefs carry the context and freshness warnings. Use the pack's fetch-only tool; never merge, pull or write in a vault implicitly. After verified delivery, follow its retro write-back and proof-node rules. Vault content stays private.

## 6. Session status, KPI hooks and outcomes

This step makes every session report whether the setup works, and records private, content-free KPIs. It is optional, but without it Retro has nothing to measure.

### What gets installed

| Client | Event | Command (installer form) | What it does |
|---|---|---|---|
| Claude, Codex | `SessionStart` | `python3 /abs/path/scripts/setup_doctor.py --host HOST --hook claude\|codex` | One status line at the start of every session, for example `📈 DevStack monitoring on (96 claude receipts) · WARN codex trust …`. Always exits 0 and gives up after 4 s, so it never blocks a session. |
| Claude, Codex | `Stop` | `python3 /abs/path/monitoring/devstack/kpi_monitor.py audit-hook --host HOST --runtime RUNTIME --event Stop` | One private receipt per turn: a hashed session ID, host, runtime and time. |
| Claude, Codex | `PostToolUse` | same, `--event PostToolUse`, matcher `*` (Claude) or `.*` (Codex) | Counts tool calls per session. |
| Claude | `PostToolUseFailure` | same, `--event PostToolUseFailure`, matcher `*` | Counts failed tool calls. Codex has no failure event, so its failures are reported as unmeasured. |

All KPI hooks are `async` with a 5 s timeout. No hook stores prompts, tool input or output, transcripts or file content. Tool payloads up to 64 MB are parsed only for the top-level session ID, and larger payloads are skipped.

### Install

From the checkout:

```bash
python3 monitoring/devstack/install.py --host mac      # devbox | windows; Windows uses python
```

By default the hooks point at this checkout's own `monitoring/devstack/kpi_monitor.py` and `scripts/setup_doctor.py`, so keep the checkout where it is. After a move, run `python3 scripts/detach.py --from OLD_PATH` from the new location (dry run, then `--apply`) and rerun the installer; the installer names hooks of another checkout and prints that command, but never removes them itself. `--root PATH` selects another reviewed setup tree instead; the monitor package is then copied into `PATH/monitoring/devstack`. The installer keeps every existing hook, backs up every file it changes to `~/.local/state/devstack/install-backups/`, never adds a second copy, and removes only its own counters when they sit under a narrower matcher (which would double-count). It also adds a KPI pointer block to the global instructions (`PATH/AGENTS.md` when the setup tree has one, otherwise `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`) if they lack one.

**By hand:** add the hooks yourself in the exact form above, using absolute paths and an interpreter that exists, with no wrappers such as `env`, `VAR=1`, `-c` or `-m`. Claude Code `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "timeout": 5,
      "command": "python3 /abs/devstack/scripts/setup_doctor.py --host mac --hook claude"}]}],
    "Stop": [{"hooks": [{"type": "command", "timeout": 5, "async": true,
      "command": "python3 /abs/devstack/monitoring/devstack/kpi_monitor.py audit-hook --host mac --runtime claude --event Stop"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "timeout": 5, "async": true,
      "command": "python3 /abs/devstack/monitoring/devstack/kpi_monitor.py audit-hook --host mac --runtime claude --event PostToolUse"}]}],
    "PostToolUseFailure": [{"matcher": "*", "hooks": [{"type": "command", "timeout": 5, "async": true,
      "command": "python3 /abs/devstack/monitoring/devstack/kpi_monitor.py audit-hook --host mac --runtime claude --event PostToolUseFailure"}]}]
  }
}
```

For Codex, put the same `SessionStart`, `Stop` and `PostToolUse` entries in `~/.codex/hooks.json`, with `--runtime codex`, `--hook codex` and matcher `.*`. The setup check recognises a DevStack hook only in exactly this form, so a hand-written variant shows up as missing rather than as a false OK.

### Windows: keep skill mirrors current

Native Windows clients read copies of each skill folder instead of links. Each copy has CRLF line endings, and its links that leave the skill folder are rewritten to absolute source paths. After any change to a skill, refresh the copies, or Windows agents keep running the old text:

```bash
python scripts/skill_mirrors.py --check     # lists stale or missing mirror files
python scripts/skill_mirrors.py --apply     # refreshes them and backs up what it replaces
```

The setup check reports out-of-date mirrors as `WARN` and missing ones as `FAIL`.

### Approve the hooks in Codex

Codex runs a new or changed hook only after you approve it. Either:

```bash
python3 scripts/codex_hook_trust.py --dry-run   # list the DevStack hooks and their trust status
python3 scripts/codex_hook_trust.py             # show each full command, ask, then approve
```

or start `codex`, run `/hooks` and approve them by hand. The script does exactly what `/hooks` does: it asks Codex's own app-server for the hook inventory and its hashes, and writes the approval through Codex's own config API. It only ever approves hooks in your `~/.codex/hooks.json` whose command is exactly the installer's form, run by one of this machine's Python installations against this setup's own scripts; it never invents a hash and never touches plugin or project hooks. Approve again after any reinstall that changes a hook.

### Check the setup

```bash
python3 scripts/setup_doctor.py --host mac        # add --json for machine-readable output
python3 scripts/setup_doctor.py --host mac --clients claude   # auto (default) | claude | codex | both
```

| Status | Meaning |
|---|---|
| `FAIL` | Broken: a missing source, a skill that is not linked (or mirrored) to the source, a missing KPI `Stop` hook, a hook pointing to a missing file, or `disableAllHooks`. Fix it before relying on the setup. |
| `WARN` | Works but incomplete: a missing status or tool-count hook, a hook not yet approved in Codex or never fired, duplicate counters, out-of-date Windows skill mirrors, completed tasks without a recorded outcome, or a configured pack vault that is missing, on the wrong remote or stale. |
| `INFO` | Present but not verifiable from here (for example a Codex trust entry, whose hash cannot be recomputed outside Codex), or skipped: a client that is not set up on this host. |

Only clients in use are checked: a client counts as in use when its binary is on `PATH` or its own state exists (`~/.claude.json` or `~/.claude/projects` for Claude Code, `~/.codex/config.toml`, `auth.json` or `sessions` for Codex). A Claude-only host therefore gets `INFO … codex not set up` rows instead of `FAIL`, even when the installer wrote Codex hook files. `--clients claude|codex|both` overrides the detection.
| `OK` | Configured, and for receipts, actually observed. |

The check changes no configuration. The SessionStart status line is the same check in one line: `WARN` and `FAIL` items are named there, and `INFO` items are not.

**Proof that it runs:** a passing check proves configuration and recorded receipts. It does not prove that a client loaded a hook in the current session. Confirm in a fresh session that the status line appears and that the receipt count rises.

### Record task outcomes

Hooks count activity. Only the lead agent can record whether work succeeded. The DevStack skill requires this at intake and at the endpoint:

```bash
python3 monitoring/devstack/task_kpi.py start  --id TKT-<number> --workflow feature --topic <repo-or-project-slug> --mode full_send --host mac
python3 monitoring/devstack/task_kpi.py finish --id TKT-<number> --status completed --verified yes --handoff none --pack none --slices 2 --review-rounds 1 --node unit-tests=pass --node live-ui=pass
python3 monitoring/devstack/task_kpi.py finish --id TKT-<number> --status completed --verified yes --handoff planned --pack none   # Full Stop stopped at the ready PR: authority missing
python3 monitoring/devstack/task_kpi.py once   --id req-<date>-<slug> --workflow research --topic <slug> --host mac --started-at <ISO time>   # unticketed request
python3 monitoring/devstack/task_kpi.py show   --id TKT-<number>
```

The topic is the repo or project slug, so Retro can compare per project. A repo without CI adds `--node ci=not_run`. `python3 monitoring/devstack/kpi_monitor.py export --aggregate` prints counts only (no IDs or times finer than a day) for opt-in sharing.

Use `--verified yes` only when the required proof exists. Missing proof is `unknown`, never `yes`. A repeated `finish` keeps the original end time and earlier proof nodes, and an unchanged retry records nothing.

### Read the KPIs

```bash
python3 monitoring/devstack/kpi_monitor.py report
```

`session_kpis` gives per host and runtime: sessions, turns, session minutes (median and mean, first to last receipt), tool calls and tool failures. `overall` and `by_*` summarise recorded task outcomes. Each host keeps its own private store at `~/.local/state/devstack/kpis.sqlite3`. Retro reads each host's report and never adds the same request from two hosts together.

### Set your targets

```bash
mkdir -p ~/.config/devstack && cp examples/kpi-targets.example.json ~/.config/devstack/kpi-targets.json
cp examples/project-tiers.example.json ~/.config/devstack/project-tiers.json  # project tiers: see the devstack skill
python3 monitoring/devstack/kpi_monitor.py scorecard
```

Edit the numbers to your goals. From then on every `task_kpi.py finish` (the end of a designated development task) and every benchmark scoreboard shows the targets met and the misses with their gap; research and discussion answers and the session status line do not ([targets and hill-climbing](../monitoring/devstack/README.md#targets-and-hill-climbing)).

### Known limits (observed 2026-10-28)

| Limit | Effect | What to do |
|---|---|---|
| Codex older than about 0.160 skips `async` hooks (`async hooks are not supported yet`) | No Codex receipts or tool counts on that host | Update Codex. Verified on 0.160.0, 0.162.1 and 0.164.0. |
| One-shot `claude -p` runs record no `Stop` receipt | Turns undercount scripted runs. Status and tool counts still work. | None needed for interactive sessions. |
| Codex has no tool-failure event | `tool_failures` is unmeasured (null) for Codex | Reported as unmeasured, never as zero. |
| DevStack ships no shell safety hooks | Owner-specific guard hooks are not checked on any host | Shown as one INFO line; nothing to do. |
| An expired client login | The hooks run, but the model never answers | Log in again (`claude`, then `/login`). |
| Windows skill mirrors are copies | A skill change does not reach Windows agents until the mirrors are refreshed | `python scripts/skill_mirrors.py --apply` |

### Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| No status line in Codex | The hook is not approved | `/hooks` in Codex |
| `WARN … receipts … never fired` | The client has not run since install, or Codex is too old or the hook unapproved | Start a fresh session, `codex --version` |
| `N … counters would double-count` | An extra counter under another matcher | Rerun the installer or remove the duplicate |
| `… lack verified_success` | A task ended without `task_kpi.py finish` | Record the real outcome with `finish` |

### Setup prompt

The copy-paste prompt for this step, and prompts for the full install, updates, a read-only health check, ticket numbers, a project's vault and test personas, moving and uninstalling, are in [setup prompts](setup-prompts.md).

## Maintaining the team repository

This repository is its own source. After reviewing edits to the 69 manifest-covered resources, regenerate their local manifest and run the full check:

```bash
python3 scripts/refresh_from_source.py          # update manifest only; copy no files
python3 scripts/refresh_from_source.py --check  # verify exact local coverage and hashes
python3 scripts/check.py
```

No installed private source tree or `DEVSTACK_SOURCE` environment variable is used. The manifest records the same local bytes as source and published hashes, with no sanitization. Missing resources, unmapped files, symlinks and privacy findings still reject generation before writing. A passing repository check does not establish client installation or activation.

### Optional upstream-only comparison

The upstream workflow still uses the names this copy had before the rename. To see how a separately reviewed upstream tree differs from this repository, compare it explicitly:

```bash
python3 scripts/refresh_from_source.py --source <upstream-source-tree> --check
```

This is read-only and is not part of normal setup. The comparison maps the upstream layout (`skills/patstack/` → `skills/devstack/`, `monitoring/patstack/` → `monitoring/devstack/`), brand words (`Patstack`/`patstack` → `DevStack`/`devstack`) and the upstream owner's name (→ "the owner"), applies the reviewed sanitization anchors for private source trees (an already published upstream copy counts as sanitized), and prints a JSON report:

| Field | Meaning |
|---|---|
| `identical` / `differs` | Resources whose mapped upstream bytes equal or differ from this repository |
| `missing_upstream` | Resources this repository has that the upstream tree lacks |
| `unmapped_upstream_files` | New upstream files in the mirrored folders, shown under their mapped names; add them to `FILES` deliberately or leave them out |
| `sanitization_anchors_unmatched` | A private upstream paragraph changed; review its mapping in `SANITIZE` |
| `privacy_findings` | Redacted path:line findings from the same privacy scan as `scripts/check.py` |

It exits 1 while anything differs. External `--source` without `--check` is rejected, and nothing copies upstream bytes over team edits. A difference is normal where this copy deliberately diverges (team wording, the installer, the setup check); review each one rather than aiming for zero.

### Syncing a change from upstream

Skills that the project pack shares with the team's skills repository are kept in step with [`tools/pack_sync.py`](pack-sync.md) (three-way status, safe pull, conflicts left for review); the section below covers the workflow upstream itself.

Upstream changes are imported one reviewed commit at a time. The upstream repository named in [NOTICE.md](../NOTICE.md) shares history with this one, so Git's rename detection usually carries a change to `skills/patstack/…` onto `skills/devstack/…`:

```bash
git remote add upstream <upstream repository URL>   # once
git fetch upstream
git switch -c sync/<topic> origin/main
git cherry-pick -n <upstream-commit>                 # apply without committing
git status                                           # resolve conflicts; files must land under the new names
```

Then, before committing:

1. **Rename map.** Move anything that landed under an old path into its new folder (`skills/patstack/` → `skills/devstack/`, `monitoring/patstack/` → `monitoring/devstack/`), and replace the upstream brand words and owner name in the picked text with `DevStack`/`devstack` and "the owner". `git diff --cached` and a case-insensitive search for the old brand show what is left; only the intentional mentions listed in the [migration note](#migrating-from-the-old-name) may remain.
2. **Compare.** `python3 scripts/refresh_from_source.py --source <upstream checkout> --check` should now list only the deliberate team differences.
3. **Manifest.** `python3 scripts/refresh_from_source.py` regenerates `SOURCE-MANIFEST.json` from the local bytes.
4. **Check.** `python3 scripts/check.py` must print `OK:`; it rejects any leftover owner name, private path or other privacy finding.

If rename detection fails for a commit, apply it as a patch with the paths rewritten instead: `git format-patch -1 <upstream-commit> --stdout | sed -e 's#skills/patstack/#skills/devstack/#g' -e 's#monitoring/patstack/#monitoring/devstack/#g' | git apply -3`, then continue with step 1.

## Migrating from the old name

A pre-rename checkout may still use the old coordinator name. Update the remote to your maintained DevStack repository and follow the migration steps above.

| What changed | Old | New | What to do |
|---|---|---|---|
| Coordinator skill | `skills/patstack/`, name `patstack` | `skills/devstack/`, name `devstack` | Remove the old `patstack` skill link or mirror from `~/.claude/skills` and `~/.agents/skills`, then link `devstack` (step 2). Windows: rerun `python scripts/skill_mirrors.py --apply`. |
| Global instructions | text that selects `patstack` | selects `devstack` | Update your instructions, or merge the [template](../examples/global-instructions/AGENTS.md) (step 3). |
| KPI package and hooks | `monitoring/patstack/` | `monitoring/devstack/` | Rerun the installer (step 6). It replaces a `patstack-kpi` pointer block in place, but hooks that still point at the old `monitoring/patstack/kpi_monitor.py` path are not recognised; delete those entries from `~/.claude/settings.json` and `~/.codex/hooks.json`, run `scripts/setup_doctor.py`, and approve the new Codex hooks. |
| KPI store | `~/.local/state/patstack/kpis.sqlite3` | `~/.local/state/devstack/kpis.sqlite3` | **Not migrated automatically.** To keep history, move it before the first new receipt: `mkdir -p ~/.local/state/devstack && mv ~/.local/state/patstack/kpis.sqlite3* ~/.local/state/devstack/` (includes the `-wal`/`-shm` files). Otherwise pass `--db` with the old path. Old snapshots keep `source: patstack`. |
| Ticket counter | `~/.local/state/patstack/tickets.sqlite3`, `PATSTACK_TICKET_DB` | `~/.local/state/devstack/tickets.sqlite3`, `DEVSTACK_TICKET_DB` | Move the file the same way. A host without a counter at the new path refuses to allocate (`not initialized`), so numbers are never reissued; never `init` a second counter for the same slot. |
| Host profile and privacy denylist | `~/.config/patstack/` | `~/.config/devstack/` | Move `devices.local.json` and `privacy-denylist.txt` (mode 0600). `PATSTACK_PRIVACY_DENYLIST` is now `DEVSTACK_PRIVACY_DENYLIST`. |
| Status line | `📈 Patstack monitoring on` | `📈 DevStack monitoring on` | Nothing; the new text appears after the hooks point at the new path. |

The remaining mentions of the old name in this repository are intentional: the upstream credit in [NOTICE.md](../NOTICE.md), this migration note and the sync procedure above, the upstream comparison map in `scripts/refresh_from_source.py`, the installer's legacy pointer marker, and the tests for both.
