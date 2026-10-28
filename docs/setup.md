# Setup

Patstack is a set of Markdown skills plus standard-library Python tools. Nothing here installs packages, starts daemons or creates scheduled jobs.

## Prerequisites

| Need | Why | Required? |
|---|---|---|
| Claude Code and/or Codex | Run the skills | Yes |
| Python 3.9+ | Ticket numbering, KPI recorder, checks, refresh script | Yes for the Python tools |
| `git`, `gh` | PRs, checks, Issue-based specs | For delivery |
| A private initialized `ticket-ref` store | Allocate new shared reference numbers offline | Only when issuing a new reference; see the [numbering contract](../coordination/README.md). |
| A host exposing the needed delegation or wakeup tools | Child delegation and PR watching | Only for those operations; follow its live tool contract. |
| Two model families (Opus 5.5 and Sol 6.1 by default) | R2/R3 independence | For R2/R3. A missing family is reported, not substituted. |
| A password manager client with origin-matched autofill | Secret-safe test logins (the [access reference](../skills/patstack/references/access.md) assumes Bitwarden) | Only for authenticated recipes |
| Playwright or native Computer Use | Browser and UI verification | Only for UI recipes; verify on the actual host |

## 1. Validate the checkout

```bash
python3 scripts/check.py
```

Expected output starts with `OK:`. The check runs offline.

## 2. Expose the skills

The skills link to files outside their own folder (`../../monitoring/…`, `../../../coordination/README.md`). Keep the repository as one tree and point your client at the **whole `skills/` directory**:

```bash
# Claude Code: personal skills directory
ln -s "$PWD/skills/patstack" ~/.claude/skills/patstack
ln -s "$PWD/skills/create-test-recipes" ~/.claude/skills/create-test-recipes
```

Repeat the link for each of the 19 folders listed in the [skill catalog](../README.md#skills). Inspect existing destinations first and preserve any owner-managed installation rather than overwriting it. For Codex, use the skills directory your Codex version discovers and link the same 19 folders. The source setup links both clients to **one shared directory**, so Claude and Codex read identical files. Do not keep two edited copies.

Chirp/Xirp aliases are optional app-owned dependencies, outside this catalog. They can remain present on Unix when installed by their owner; Windows does not need unavailable aliases. Native frontend-design and Computer Use must be provided by the actual client. This repository does not vendor their managed payloads.

If a client resolves relative links from the symlink location rather than the real path, cross-references can miss. In that case open the referenced file from the repository root. `scripts/check.py` validates the links inside the repository only.

The 19 modules cooperate under Patstack. Keep retired, overlapping workflow collections out of discovery so an older router does not compete with them. Verify source files, links, fresh native discovery and actual task behavior separately: linking files alone does not establish activation. Windows mirrors can require external Markdown-link adaptation; verify the exact intended adaptation separately from canonical source parity. The source owner has completed the 1.2.0 rollout and fresh initialization-catalog checks on Mac, devbox and Windows; see the reported [host evidence](status-and-limits.md#reported-host-rollout-evidence). Existing GUI sessions may still need a reload.

## 3. Add your global instructions

Patstack expects a short global instruction block that names the numbering tool, real authority rules (test and production approvals, no destructive Git without approval), and where project packs live. Optional [model routing preferences](../MODEL_RANKING.md) describe actual available models; they do not decide ticket eligibility. Keep the real setup private.

## 4. Add a host capability profile (optional, per host)

```bash
mkdir -p ~/.config/patstack
cp examples/devices.example.json ~/.config/patstack/devices.local.json
chmod 600 ~/.config/patstack/devices.local.json
```

Fill in only aliases, capabilities and timestamped observations. Use SSH config aliases, not addresses. Credentials stay in their existing stores. If the file is absent, Patstack does fresh read-only discovery. Absence proves nothing about a device.

## 5. Add project packs (private)

For each project, keep a pack shaped like [examples/project-pack](../examples/project-pack/README.md): an `INDEX.md` router plus conditional procedures and a `verify-<app>` skill. `create-test-recipes` generates and maintains the verification part. Packs stay outside global skill discovery and outside this repository.

## 6. Session status, KPI hooks and outcomes

This step makes every session report whether the setup works, and records private, content-free KPIs. It is optional, but without it Retro has nothing to measure.

### What gets installed

| Client | Event | Command (installer form) | What it does |
|---|---|---|---|
| Claude, Codex | `SessionStart` | `python3 /abs/path/scripts/setup_doctor.py --host HOST --hook claude\|codex` | One status line at the start of every session, for example `📈 Patstack monitoring on (96 claude receipts) · WARN codex trust …`. Always exits 0 and gives up after 4 s, so it never blocks a session. |
| Claude, Codex | `Stop` | `python3 /abs/path/monitoring/patstack/kpi_monitor.py audit-hook --host HOST --runtime RUNTIME --event Stop` | One private receipt per turn: a hashed session ID, host, runtime and time. |
| Claude, Codex | `PostToolUse` | same, `--event PostToolUse`, matcher `*` (Claude) or `.*` (Codex) | Counts tool calls per session. |
| Claude | `PostToolUseFailure` | same, `--event PostToolUseFailure`, matcher `*` | Counts failed tool calls. Codex has no failure event, so its failures are reported as unmeasured. |

All KPI hooks are `async` with a 5 s timeout. No hook stores prompts, tool input or output, transcripts or file content. Tool payloads up to 64 MB are parsed only for the top-level session ID, and larger payloads are skipped.

### Install

**Source setup** (`~/.harnesses-shared/agent-setup`):

```bash
python3 monitoring/patstack/install.py --host mac      # devbox | windows; Windows uses python
```

It keeps every existing hook, backs up changed files, never adds a second copy, and removes only its own counters when they sit under a narrower matcher (which would double-count). It also adds a KPI pointer to the global instructions if they lack one.

**Plain checkout:** add the hooks yourself in the exact form above, using absolute paths and an interpreter that exists, with no wrappers such as `env`, `VAR=1`, `-c` or `-m`. Claude Code `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "timeout": 5,
      "command": "python3 /abs/patstack/scripts/setup_doctor.py --host mac --hook claude"}]}],
    "Stop": [{"hooks": [{"type": "command", "timeout": 5, "async": true,
      "command": "python3 /abs/patstack/monitoring/patstack/kpi_monitor.py audit-hook --host mac --runtime claude --event Stop"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "timeout": 5, "async": true,
      "command": "python3 /abs/patstack/monitoring/patstack/kpi_monitor.py audit-hook --host mac --runtime claude --event PostToolUse"}]}],
    "PostToolUseFailure": [{"matcher": "*", "hooks": [{"type": "command", "timeout": 5, "async": true,
      "command": "python3 /abs/patstack/monitoring/patstack/kpi_monitor.py audit-hook --host mac --runtime claude --event PostToolUseFailure"}]}]
  }
}
```

For Codex, put the same `SessionStart`, `Stop` and `PostToolUse` entries in `~/.codex/hooks.json`, with `--runtime codex`, `--hook codex` and matcher `.*`. The setup check recognises a Patstack hook only in exactly this form, so a hand-written variant shows up as missing rather than as a false OK.

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
python3 scripts/codex_hook_trust.py --dry-run   # list the Patstack hooks and their trust status
python3 scripts/codex_hook_trust.py             # show each full command, ask, then approve
```

or start `codex`, run `/hooks` and approve them by hand. The script does exactly what `/hooks` does: it asks Codex's own app-server for the hook inventory and its hashes, and writes the approval through Codex's own config API. It only ever approves hooks in your `~/.codex/hooks.json` whose command is exactly the installer's form, run by one of this machine's Python installations against this setup's own scripts; it never invents a hash and never touches plugin or project hooks. Approve again after any reinstall that changes a hook.

### Check the setup

```bash
python3 scripts/setup_doctor.py --host mac        # add --json for machine-readable output
```

| Status | Meaning |
|---|---|
| `FAIL` | Broken: a missing source, a skill that is not linked (or mirrored) to the source, a missing KPI `Stop` hook, a hook pointing to a missing file, or `disableAllHooks`. Fix it before relying on the setup. |
| `WARN` | Works but incomplete: a missing status or tool-count hook, a hook not yet approved in Codex or never fired, duplicate counters, out-of-date Windows skill mirrors, or completed tasks without a recorded outcome. |
| `INFO` | Present but not verifiable from here, for example a Codex trust entry, whose hash cannot be recomputed outside Codex. |
| `OK` | Configured, and for receipts, actually observed. |

The check changes no configuration. The SessionStart status line is the same check in one line: `WARN` and `FAIL` items are named there, and `INFO` items are not.

**Proof that it runs:** a passing check proves configuration and recorded receipts. It does not prove that a client loaded a hook in the current session. Confirm in a fresh session that the status line appears and that the receipt count rises.

### Record task outcomes

Hooks count activity. Only the lead agent can record whether work succeeded. The Patstack skill requires this at intake and at the endpoint:

```bash
python3 monitoring/patstack/task_kpi.py start  --id TKT-<number> --workflow feature --topic <project> --mode full_send --host mac
python3 monitoring/patstack/task_kpi.py finish --id TKT-<number> --status completed --verified yes --node unit-tests=pass --node live-ui=pass
python3 monitoring/patstack/task_kpi.py finish --id TKT-<number> --status completed --verified yes --handoff planned   # Full Stop PR handover
python3 monitoring/patstack/task_kpi.py once   --id req-<date>-<slug> --workflow research --topic <slug> --host mac --started-at <ISO time>   # unticketed request
python3 monitoring/patstack/task_kpi.py show   --id TKT-<number>
```

Use `--verified yes` only when the required proof exists. Missing proof is `unknown`, never `yes`. A repeated `finish` keeps the original end time and earlier proof nodes, and an unchanged retry records nothing.

### Read the KPIs

```bash
python3 monitoring/patstack/kpi_monitor.py report
```

`session_kpis` gives per host and runtime: sessions, turns, session minutes (median and mean, first to last receipt), tool calls and tool failures. `overall` and `by_*` summarise recorded task outcomes. Each host keeps its own private store at `~/.local/state/patstack/kpis.sqlite3`. Retro reads each host's report and never adds the same request from two hosts together.

### Known limits (observed 2026-10-28)

| Limit | Effect | What to do |
|---|---|---|
| Codex older than about 0.160 skips `async` hooks (`async hooks are not supported yet`) | No Codex receipts or tool counts on that host | Update Codex. Verified on 0.160.0, 0.162.1 and 0.164.0. |
| One-shot `claude -p` runs record no `Stop` receipt | Turns undercount scripted runs. Status and tool counts still work. | None needed for interactive sessions. |
| Codex has no tool-failure event | `tool_failures` is unmeasured (null) for Codex | Reported as unmeasured, never as zero. |
| Shell safety hooks are Unix scripts | Not applicable on Windows | Shown as INFO on Windows. |
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

Paste this into a new session on the host you are setting up:

```text
Set up Patstack's session status and KPI hooks on this host (HOST = mac | devbox | windows),
following docs/setup.md step 6. Run scripts/setup_doctor.py first and fix only what it reports.
Keep existing hooks and settings, back up before changing client configuration, and show me any
diff that replaces an existing file. Do not edit Codex trust hashes: tell me when to approve hooks
in Codex /hooks. Create no ticket, touch no project or production system, and never print
credentials. Finish with the final setup_doctor.py output, a fresh session showing the status
line, and the items that still need me.
```

## Keeping the package in sync with the private source

```bash
python3 scripts/refresh_from_source.py --source ~/.harnesses-shared/agent-setup --check   # drift report
python3 scripts/refresh_from_source.py --source ~/.harnesses-shared/agent-setup           # refresh + manifest
python3 scripts/check.py
```

The default is the installed source tree. This publication was checked against the installed Mac source after the three-host rollout; all 52 source files match the manifest. During preparation of a later version, pass its exact approved candidate tree explicitly. Packaging a candidate establishes neither installation nor native activation. Refresh fails if any required skill/resource is absent, a new source file is unmapped, a source symlink appears, privacy preflight fails or a sanitization anchor changes. Review the changed source and update the publication mapping or exact transformation deliberately. Do not edit the private source merely to make publication pass. `--check` compares exact manifest coverage, both hashes and actual published bytes without writing.
