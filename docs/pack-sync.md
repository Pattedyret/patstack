# Pack sync: shared skills from AGENT-SKILLS

A project pack may carry copies of skills owned in a separate upstream repository. [`tools/pack_sync.py`](../tools/pack_sync.py) compares those copies against their recorded upstream base without overwriting local edits. Each private pack keeps its mapping in `pack-sync.json`; see its index for the upstream repository and use `--config` when more than one pack exists.

## Ownership rule

- AGENT-SKILLS is read-only from here. The tool reads its fetched `origin/main` with `git cat-file`, never its working tree, and never writes, commits, pushes or opens PRs there. `--fetch` runs only `git fetch origin`.
- A fix that belongs upstream is proposed in AGENT-SKILLS through that repository's own process by whoever is authorized there; it is not pushed from a DevStack task.
- The pack copy is what DevStack ships. Every byte that enters it passes the same privacy guard as `scripts/check.py`.

## When to run

- At a Retro, or weekly: `status`, to see new upstream changes and skills.
- Before a task using a project pack that touches a mapped skill (or a pack procedure with an upstream successor): `status`, then `diff SKILL` for that skill, so the task starts from the current upstream rules.
- After any `pull`, `resolve` or `adopt`: `python3 scripts/check.py`, then commit the pack files together with `pack-sync.json`.

## Commands

The upstream checkout is looked up in this order: `--upstream PATH`, then `$PACK_SYNC_UPSTREAM`, then `checkout_hint` in `pack-sync.json` (a default for the usual workspace layout, which may not exist on your host). If the chosen checkout is missing, the error names the source it came from and this lookup order, but not the path. Add `--json` for agents. The global options `--upstream`, `--config`, `--json` and `--fetch` work before or after the command (`status --json` and `--json status` are the same).

```bash
python3 tools/pack_sync.py status [--fetch]           # every mapped skill, candidates, pack-only skills
python3 tools/pack_sync.py diff SKILL [--files F ...] # unified diffs, upstream -> pack
python3 tools/pack_sync.py pull SKILL [--files F ...] # fast-forward unchanged pack files
python3 tools/pack_sync.py resolve SKILL [--files F ...]  # record a hand merge (default: conflicts, pending pulls and records)
python3 tools/pack_sync.py adopt SKILL [--as NAME] [--keep-pack]
```

Exit codes: `0` in sync, `1` drift, conflicts or refused files, `2` usage or errors (missing checkout or ref, unknown skill or file).

## How a file is classified

Each file is compared three ways by content and git mode (`100644` or `100755`): its recorded base (`base_sha256` and `base_mode` of upstream at `base_rev`; `null` when upstream did not have it), the upstream ref and the pack (executable bit). A mode-only change counts like a content change, and `pull` applies the upstream mode.

| State | Meaning |
|---|---|
| `identical` / `deleted` | Pack and upstream are equal / both lack a file the base still has. |
| `differs` / `pack-only` / `upstream-only` | Both have it with different bytes / only the pack has it / only upstream has it. |

| Change → action | Meaning |
|---|---|
| `upstream` → `pull` | Upstream changed since the base and the pack did not: `pull` applies it (update, create or delete). Counts as drift. |
| `local` → `keep` | Only the pack changed (an intentional pack edit, addition or omission). Not drift; `pull` leaves it. |
| `both` → `conflict` | Both changed. Nothing is written. Counts as drift until resolved. |
| `type` → `restructure` | Upstream turned a file into a folder of the same name, or the reverse. Never applied automatically; counts as drift (see below). |
| `converged` → `record` | Both sides changed or deleted the file in the same way. `pull` only advances the base (to `null` for a deletion), so a later upstream revert or restoration is not misread as a pack change. Counts as drift until recorded. |

A file can carry `"policy": "ignore"` in `pack-sync.json` to stay out of syncing. A new upstream skill that is neither mapped nor listed under `known_candidates` is drift; pack skills without an upstream counterpart are listed for information only.

## Conflicts and privacy refusals

1. `diff SKILL --files F` shows upstream against the pack.
2. Merge by hand in the pack copy: take the upstream change, keep the pack's neutralization and fixes. Never weaken a pack security fix to match upstream.
3. `resolve SKILL --files F` records the current upstream revision as the new base, after the guard has checked the merged pack file. Declining an upstream change is the same step: leave the pack file as it is and resolve it.

A `pull` whose selection contains any conflict, restructure or unsupported entry (such as a symlink) writes nothing and lists the clean files as `blocked`; pull those alone with `--files`, or resolve the conflicts first.

A restructure (for example `references/notes.md` becoming `references/notes.md/detail.md`, or the reverse) is recovered by hand: `diff` both paths, then delete or rename the old file or folder in the pack, run `pull` to bring in the new shape, and `resolve` any file whose pack-local edits you carried over by hand.

`pull` and `adopt` refuse files that would fail the privacy guard (home or private paths, owner names, emails, hosts, tokens, registry IDs and the other `scripts/check.py` categories); `pack-sync.json` itself is guarded the same way. The report names the redacted finding and line; neutralize the pack copy (for example `<workspace>`, `$DEVSTACK/...`, "the owner") and then `resolve`. A refused file keeps its old base, so it stays visible as pending.

## Write safety

- Every write is one transaction: the selection is checked first (conflicts and privacy findings write nothing), then the original bytes and modes of every target and of `pack-sync.json` are kept, all files are written, read back and guarded again, and the state is saved and guarded. Any failure, including a write error or a failing state save, restores every file and the state. Removing folders emptied by a deletion happens after the commit and is best effort: a folder that cannot be removed is reported as a warning, and the exit code stays that of the successful pull.
- Files are written through a fresh exclusive temporary file in the same folder (`tempfile.mkstemp`), given their final mode and then renamed over the target, so a planted symlink is never followed and the temporary `0600` mode never stays.
- Destinations must be inside the pack's skills folder: skill names, `--as`, `pack_root` and file names are single safe names or relative paths without empty, `.` or `..` parts, absolute paths or control characters. No part of a destination path may be a symlink, and nothing is written inside the upstream checkout.

`adopt SKILL` copies a whole upstream skill only when every file passes; otherwise nothing is written. To adopt such a skill, copy it into the pack by hand, neutralize it and run `adopt SKILL --keep-pack`. Then route to it from the pack `INDEX.md`.

## Initial state

The base was recorded on 2026-10-29 at AGENT-SKILLS `origin/main` `55f503c`. Every difference that existed then is recorded as a known pack-local change, with a note per file in `pack-sync.json`; they are not conflicts. In short:

- The pack copies of the shared intake, auth setup, new-app and workflow skills stem from the English upstream versions of mid-September 2026. Upstream has since rewritten them for its IDD governance and translated them to Norwegian, and deleted the auth templates and new-app scripts that the pack still ships. Adopting that rewrite is a separate, deliberate decision; take it with `diff`, a hand merge and `resolve`.
- **Security fix, pack ahead:** the auth setup skill's `templates/server-proxy.js` builds every proxy target through the pack-only `templates/proxy-target.js` (with tests), so a crafted request path cannot leave the configured origin; the skill text tells existing apps to patch. Upstream's former template used the raw request path.
- **Neutralization and DevStack adaptation:** script paths via `$DEVSTACK/...` instead of a per-user skills folder, the DevStack development-phase pointer at the end of most procedures, and the deploy skill pointing at the repository's own deploy documents instead of copied commands and project references.
- The vault skill was identical. The workflow skill's upstream-only `references/release.md` belongs to the IDD router and is not linked from the pack copy.
- Five upstream skills are listed as known candidates, not adopted, with the reason for each; two of them succeed pack procedures that upstream deleted.

## Adoption of the upstream rewrites (2026-10-29)

On the owner's decision the pack took the upstream rewrites and successors, still at `origin/main` `55f503c`; `pack-sync.json` holds a note for every remaining difference.

- **Pulled by hand-merge, then `resolve`:** the intake, auth setup, new-app and workflow skills (the September bokmål rewrites, plus the workflow's `references/release.md`) and the deploy skill. Each keeps three kinds of pack-local change: links to the DevStack router instead of upstream's IDD governance skill, with the IDD role names mapped to DevStack terms (lead, independent review); the auth setup skill's proxy template with its origin guard, tests and patch-and-rotate note for apps built from the old template; and the deploy skill's pointers to each repository's own deploy documents.
- **Retired with them:** the auth templates and new-app scripts that upstream deleted and the adopted texts no longer reference. The proxy template and its guard stay, because the adopted auth text points at them.
- **Adopted:** the upstream verification skill and the selective sync skill for the hosted app builder, which succeed four retired pack procedures (named in the pack `INDEX.md`). The pack's own back-sync after a stage merge stays the active procedure.
- **Not adopted, by decision:** upstream's IDD governance (DevStack is the workflow), its MCP interpretation rules (customer data) and its generic frontend design skill (DevStack uses the native capability). They are listed under `known_candidates`.
- Pack procedures that never existed upstream stay. So do the ones still linked from other pack documents.
