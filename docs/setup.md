# Setup

Patstack is a set of Markdown skills plus one standard-library Python tool. Nothing here installs packages, starts daemons or creates scheduled jobs.

## Prerequisites

| Need | Why | Required? |
|---|---|---|
| Claude Code and/or Codex | Run the skills | Yes |
| Python 3.9+ | KPI recorder, checks, refresh script | Yes for KPIs and checks |
| `git`, `gh` | PRs, checks, Issue-based specs | For delivery |
| A task registry implementing the [coordination contract](../coordination/README.md) at `~/.local/bin/agent-work` | Durable ownership, leases, child runs, delivery records | Strongly recommended. Without it, report the missing prerequisite instead of pretending ownership. |
| T3 Code (or another host with native delegation and PR wakeups) | One-layer child delegation, native PR watcher | For delegation and babysitting as written |
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

The 19 modules cooperate under Patstack. Keep retired, overlapping workflow collections out of discovery so an older router does not compete with them. Verify source files, links, fresh native discovery and actual task behavior separately: linking files alone does not establish activation.

## 3. Add your global instructions

Patstack expects a short global instruction block that names the lead models, authority rules (stage and production approvals, no destructive Git without approval) and where project packs live. Adapt the [model routing contract](../MODEL_RANKING.md). Keep the real file private.

## 4. Add a host capability profile (optional, per host)

```bash
mkdir -p ~/.config/patstack
cp examples/devices.example.json ~/.config/patstack/devices.local.json
chmod 600 ~/.config/patstack/devices.local.json
```

Fill in only aliases, capabilities and timestamped observations. Use SSH config aliases, not addresses. Credentials stay in their existing stores. If the file is absent, Patstack does fresh read-only discovery. Absence proves nothing about a device.

## 5. Add project packs (private)

For each project, keep a pack shaped like [examples/project-pack](../examples/project-pack/README.md): an `INDEX.md` router plus conditional procedures and a `verify-<app>` skill. `create-test-recipes` generates and maintains the verification part. Packs stay outside global skill discovery and outside this repository.

## 6. KPI recorder and audit hook (optional)

Record and report by hand:

```bash
python3 monitoring/patstack/kpi_monitor.py record < examples/kpi-snapshot.example.json
python3 monitoring/patstack/kpi_monitor.py report
```

The default store is `~/.local/state/patstack/kpis.sqlite3`. Pass `--db PATH` before the command for a test store.

**Audit hook.** `monitoring/patstack/install.py` is the installer used by the source setup. It assumes that setup's layout under `~/.harnesses-shared/agent-setup` and edits global instruction files there. Read it before running it. For a plain checkout, add the hook to your client's hook configuration yourself, for example in Claude Code `settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {"hooks": [{"type": "command", "timeout": 5, "async": true,
        "command": "python3 /absolute/path/to/patstack/monitoring/patstack/kpi_monitor.py audit-hook --host mac --runtime claude --event Stop"}]}
    ]
  }
}
```

Keep existing hooks. Codex requires its native hook trust for new definitions. Verify that the client actually loads the hook: a shell smoke test does not prove activation.

## Keeping the package in sync with the private source

```bash
python3 scripts/refresh_from_source.py --source ~/.harnesses-shared/agent-setup --check   # drift report
python3 scripts/refresh_from_source.py --source ~/.harnesses-shared/agent-setup           # refresh + manifest
python3 scripts/check.py
```

The default is the installed source tree. Before modular activation, use the complete reviewed candidate explicitly, including its version-aware monitor installer and tests:

```bash
python3 scripts/refresh_from_source.py \
  --source ~/.harnesses-shared/agent-setup/drafts/patstack-modular/candidate
python3 scripts/refresh_from_source.py \
  --source ~/.harnesses-shared/agent-setup/drafts/patstack-modular/candidate --check
```

Candidate refresh is packaging, not installation. The 1.0 baseline's earlier installation proof does not prove modular 1.1 activation. Refresh fails if any required skill/resource is absent, a new source file is unmapped, a source symlink appears, privacy preflight fails or a sanitization anchor changes. Review the changed source and update the publication mapping or exact transformation deliberately. Do not edit the private source merely to make publication pass. `--check` compares exact manifest coverage, both hashes and actual published bytes without writing.
