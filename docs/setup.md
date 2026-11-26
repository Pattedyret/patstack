# Setup — Patstack

Patstack is a set of Markdown skills plus standard-library Python tools. Nothing here installs packages, starts daemons or creates scheduled jobs.

## Prerequisites

| Need | Why | Required? |
|---|---|---|
| Claude Code and/or Codex | Run the skills | Yes |
| Python 3.9+ | Ticket numbering, checks, refresh script | Yes for the Python tools |
| `git`, `gh` | PRs, checks, Issue-based specs | For delivery |
| A private initialized `ticket-ref` store | Allocate new shared reference numbers offline | Only when issuing a new reference; see the [numbering contract](../coordination/README.md). |
| A host exposing the needed delegation or wakeup tools | Child delegation and PR watching | Only for those operations; follow its live tool contract. |
| Two model families (Opus 5.5 and Sol 6.1 by default), preferred | R2/R3 independence | For R2/R3. With only one provider, R2/R3 use fresh sessions of that provider under the [reviewer lenses](../skills/review/references/lenses.md). |
| A password manager client with origin-matched autofill | Secret-safe test logins (the [access reference](../skills/patstack/references/access.md) assumes Bitwarden) | Only for authenticated recipes |
| Playwright or native Computer Use | Browser and UI verification | Only for UI recipes; verify on the actual host |

## 1. Validate the checkout

```bash
python3 scripts/check.py
```

Expected output starts with `OK:`. The check runs offline. It also runs any bundled project pack's own tests; the auth-proxy security tests need Node.js (`node`). Without node the check fails. `python3 scripts/check.py --allow-missing-node` runs everything else and ends with `INCOMPLETE` and exit code 3, never `OK`: use it only where node cannot be installed, and run the full check elsewhere before relying on the pack.

## 2. Expose the skills

The skills link to files outside their own folder (for example `../../../coordination/README.md`). Keep the repository as one tree and point your client at the **whole `skills/` directory**:

```bash
# Claude Code: personal skills directory
ln -s "$PWD/skills/patstack" ~/.claude/skills/patstack
ln -s "$PWD/skills/create-test-recipes" ~/.claude/skills/create-test-recipes
```

Repeat the link for each of the 20 folders listed in the [skill catalog](../README.md#skills). Inspect existing destinations first and preserve any owner-managed installation rather than overwriting it. For Codex, use the skills directory your Codex version discovers and link the same 20 folders. Point both clients to **one shared repository tree**, so Claude and Codex read identical files. Do not keep two edited copies.

Chirp/Xirp aliases are optional app-owned dependencies, outside this catalog. They can remain present on Unix when installed by their owner; Windows does not need unavailable aliases. Native frontend-design and Computer Use must be provided by the actual client. This repository does not vendor their managed payloads.

If a client resolves relative links from the symlink location rather than the real path, cross-references can miss. In that case open the referenced file from the repository root. `scripts/check.py` validates the links inside the repository only.

The 20 modules cooperate under Patstack. Keep retired, overlapping workflow collections out of discovery so an older router does not compete with them. Verify source files, links, fresh native discovery and actual task behavior separately: linking files alone does not establish activation. Windows mirrors can require external Markdown-link adaptation; verify the exact intended adaptation separately from canonical source parity. Existing GUI sessions may still need a reload.

## 3. Add your global instructions

Patstack expects a short global instruction block that loads the coordinator for every change request and names the numbering tool, real authority rules (test and production approvals, no destructive Git without approval), and where project packs live. The template is [examples/global-instructions/AGENTS.md](../examples/global-instructions/AGENTS.md). Claude Code reads `~/.claude/CLAUDE.md`; Codex reads `~/.codex/AGENTS.md`. Both can use the same text.

1. Copy the template and replace `<PATSTACK>` with the absolute path of this checkout:

   ```bash
   global=$(mktemp)
   python3 -c 'import os, sys; sys.stdout.write(open(sys.argv[1]).read().replace("<PATSTACK>", os.getcwd()))' examples/global-instructions/AGENTS.md > "$global"
   ```

2. **No existing file:** install it for each client you use.

   ```bash
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

   To keep one copy, place it once (for example `~/.codex/AGENTS.md`) and make the other path a symlink to it, which is how the upstream setup shares one file between both clients. On Windows, copy instead of linking.

3. **Existing file:** never overwrite it. Back it up (`cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak`), then merge by hand: keep your own rules, add the template's sections, and drop any older workflow block that names a different router. Where your rules and the template disagree, decide deliberately; the stricter authority rule should win. Keep the first line `<!-- patstack-global-instructions -->`, so `scripts/setup_doctor.py` can report the template as installed.

4. Add one line per private project pack you use. Optional [model routing preferences](../MODEL_RANKING.md) describe actual available models. Keep host details and anything private out of this file.

## 4. Add a host capability profile (optional, per host)

```bash
mkdir -p ~/.config/patstack
cp examples/devices.example.json ~/.config/patstack/devices.local.json
chmod 600 ~/.config/patstack/devices.local.json
```

Fill in only aliases, capabilities and timestamped observations. Use SSH config aliases, not addresses. Credentials stay in their existing stores. If the file is absent, Patstack does fresh read-only discovery. Absence proves nothing about a device.

Project tiers (see the patstack skill) work out of the box from the one tier map a bundled project pack ships (`project-packs/<name>/project-tiers.json`; two such maps fail closed). Only if you also work on other projects, add a private map: `cp examples/project-tiers.example.json ~/.config/patstack/project-tiers.json`. It replaces the pack map for you, so copy its entries into it.

## 5. Project packs

Use a private pack shaped like [examples/project-pack](../examples/project-pack/README.md): an `INDEX.md` router plus conditional procedures and verification recipes. Keep packs and their skills outside global discovery. Add a project-matching pointer to the index in global instructions, and follow the steps the index declares, including mandatory intake context and retro write-back. A pack may ship in a private team checkout; it stays out of the public export.

The setup doctor discovers bundled `project-packs/*/INDEX.md` routers and read-only `tools/vault_context.py` tools. The checker admits only packs with an explicit `publication.json` privacy policy; all other pack paths remain rejected. The policy carries the reviewed pack-specific word hashes, branding expression and exact-line exceptions, while the full shared scan still runs.

### Product vault

If a pack declares a product vault, follow its index for the canonical repository, reading scope, word budget and setup variables. Verify the vault's origin and freshness. Intake follows the pack's context step before planning; task and child briefs carry the context and freshness warnings. Use the pack's fetch-only tool; never merge, pull or write in a vault implicitly. After verified delivery, follow its retro write-back and proof-node rules. Vault content stays private.

## 6. Merge guard hook

Patstack installs no hooks on its own (`scripts/start_here.py --apply` adds this one when you run it). The one hook it recommends is the merge guard: it refuses a direct pull request merge through `gh` (also through `gh api`), so pull requests are merged only through `tools/merge_gate.py`. Add it to Claude Code `~/.claude/settings.json` with the absolute path of this checkout; back up the file first and keep your existing hooks:

```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
      "command": "python3 /abs/patstack/tools/merge_guard.py"}]}]
  }
}
```

**Windows:** do not use `python3` there. On Windows it is usually only the Microsoft Store placeholder, which exits with 9009, so the guard never runs. Let PowerShell build the entry, from the checkout; it uses the real `python.exe` and forward slashes, quotes only a path that contains a space, and escapes the JSON. Keep the checkout in a path without spaces: when both paths need quotes, `cmd` strips the outer pair and the guard no longer runs.

```powershell
$py = (Get-Command python).Source.Replace('\', '/')
$guard = (Resolve-Path tools\merge_guard.py).Path.Replace('\', '/')
$q = { param($p) if ($p -match ' ') { "`"$p`"" } else { $p } }
@{ matcher = 'Bash'; hooks = @(@{ type = 'command'; command = "$(& $q $py) $(& $q $guard)" }) } | ConvertTo-Json -Depth 4
```

Put the printed object into the `PreToolUse` list of `~/.claude/settings.json` and save the file as UTF-8 without a byte-order mark (PowerShell 7's `Set-Content` does; in Windows PowerShell 5 use `[IO.File]::WriteAllText`). `setup_doctor.py` warns when the interpreter cannot run or the file has a byte-order mark.

The same entry goes into `~/.codex/hooks.json` when you use Codex on Windows.

**Codex** reads the same hook format from `~/.codex/hooks.json` and blocks the command the same way (observed with Codex CLI 0.167). Codex runs a new or changed hook only after it is trusted: start `codex` in a terminal and choose **Trust all and continue**, or review it under `/hooks`. Until then Codex skips it without a word, and `setup_doctor.py` reports `WARN codex merge guard … not trusted`; it applies Codex 0.167's own rule to `~/.codex/config.toml` (`[hooks.state."<hooks.json>:pre_tool_use:<group>:<hook>"]`): `OK` only when `trusted_hash` equals the current hook's hash and the hook is not `enabled = false`; a hook changed after it was trusted is `WARN` until it is trusted again. Reading that file needs Python 3.11 or newer (`tomllib`); on an older Python the row stays `WARN` (trust unknown) rather than guessing, so check the hook under `/hooks` in Codex. `scripts/start_here.py --apply` adds the hook for both clients, keeping your other hooks and backing up the file first.

The hook points at this checkout. After a move, edit its path in `~/.claude/settings.json` and `~/.codex/hooks.json`; `setup_doctor.py` reports the old path as `FAIL` until you do.

### Windows: keep skill mirrors current

Native Windows clients read copies of each skill folder instead of links. Each copy has CRLF line endings, and its links that leave the skill folder are rewritten to absolute source paths. After any change to a skill, refresh the copies, or Windows agents keep running the old text:

```bash
python scripts/skill_mirrors.py --check     # lists stale or missing mirror files
python scripts/skill_mirrors.py --apply     # refreshes them and backs up what it replaces
```

The setup check reports out-of-date mirrors as `WARN` and missing ones as `FAIL`.

### Check the setup

```bash
python3 scripts/setup_doctor.py --host mac        # add --json for machine-readable output
python3 scripts/setup_doctor.py --host mac --clients claude   # auto (default) | claude | codex | both
```

| Status | Meaning |
|---|---|
| `FAIL` | Broken: a missing source, a skill that is not linked (or mirrored) to the source, a hook pointing to a missing file, or `disableAllHooks`. Fix it before relying on the setup. |
| `WARN` | Works but incomplete: a retired Patstack hook still wired, out-of-date Windows skill mirrors, or a configured pack vault that is missing, on the wrong remote or stale. |
| `INFO` | Present but not verifiable from here, or skipped: a client that is not set up on this host. |
| `OK` | Configured. |

Only clients in use are checked: a client counts as in use when its binary is on `PATH` or its own state exists (`~/.claude.json` or `~/.claude/projects` for Claude Code, `~/.codex/config.toml`, `auth.json` or `sessions` for Codex). A Claude-only host therefore gets `INFO … codex not set up` rows instead of `FAIL`, even when Codex hook files exist. `--clients claude|codex|both` overrides the detection.

The check changes no configuration; run it by hand after setup and after each update. A passing check proves configuration, not that a client loaded a hook in the current session.

### Known limits (observed 2026-10-28)

| Limit | Effect | What to do |
|---|---|---|
| Besides the merge guard, Patstack ships no shell safety hooks | Owner-specific guard hooks are not checked on any host | Shown as one INFO line; nothing to do. |
| An expired client login | The hooks run, but the model never answers | Log in again (`claude`, then `/login`). |
| Windows skill mirrors are copies | A skill change does not reach Windows agents until the mirrors are refreshed | `python scripts/skill_mirrors.py --apply` |

### Setup prompt

Copy-paste prompts for the full install, updates, a read-only health check, ticket numbers, a project's vault and test personas, moving and uninstalling, are in [setup prompts](setup-prompts.md).

## Maintaining the team repository

This repository is its own source. After reviewing edits to the 68 manifest-covered resources, regenerate their local manifest and run the full check:

```bash
python3 scripts/refresh_from_source.py          # update manifest only; copy no files
python3 scripts/refresh_from_source.py --check  # verify exact local coverage and hashes
python3 scripts/check.py
```

No installed private source tree or `PATSTACK_SOURCE` environment variable is used. The manifest records the same local bytes as source and published hashes, with no sanitization. Missing resources, unmapped files, symlinks and privacy findings still reject generation before writing. A passing repository check does not establish client installation or activation.

### Optional upstream-only comparison

To see how a separately reviewed upstream tree differs from this repository, compare it explicitly:

```bash
python3 scripts/refresh_from_source.py --source <upstream-source-tree> --check
```

This is read-only and is not part of normal setup. The comparison maps the upstream owner's name (→ "the owner"), applies the reviewed sanitization anchors for private source trees (an already published upstream copy counts as sanitized), and prints a JSON report:

| Field | Meaning |
|---|---|
| `identical` / `differs` | Resources whose mapped upstream bytes equal or differ from this repository |
| `missing_upstream` | Resources this repository has that the upstream tree lacks |
| `unmapped_upstream_files` | New upstream files in the mirrored folders, shown under their mapped names; add them to `FILES` deliberately or leave them out |
| `sanitization_anchors_unmatched` | A private upstream paragraph changed; review its mapping in `SANITIZE` |
| `privacy_findings` | Redacted path:line findings from the same privacy scan as `scripts/check.py` |

It exits 1 while anything differs. External `--source` without `--check` is rejected, and nothing copies upstream bytes over team edits. A difference is normal where this copy deliberately diverges (team wording, the setup check); review each one rather than aiming for zero.

### Syncing a change from upstream

Skills that the project pack shares with the team's skills repository are kept in step with [`tools/pack_sync.py`](pack-sync.md) (three-way status, safe pull, conflicts left for review); the section below covers the workflow upstream itself.

Upstream changes are imported one reviewed commit at a time. The upstream repository named in [NOTICE.md](../NOTICE.md) shares history with this one:

```bash
git remote add upstream <upstream repository URL>   # once
git fetch upstream
git switch -c sync/<topic> origin/main
git cherry-pick -n <upstream-commit>                 # apply without committing
git status                                           # resolve conflicts
```

Then, before committing:

1. **Owner name.** Replace the upstream owner's name in the picked text with "the owner".
2. **Compare.** `python3 scripts/refresh_from_source.py --source <upstream checkout> --check` should now list only the deliberate team differences.
3. **Manifest.** `python3 scripts/refresh_from_source.py` regenerates `SOURCE-MANIFEST.json` from the local bytes.
4. **Check.** `python3 scripts/check.py` must print `OK:`; it rejects any leftover owner name, private path or other privacy finding.
