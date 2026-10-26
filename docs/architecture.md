# Architecture

Patstack keeps the workflow small and pushes everything else to the layer that already owns it.

## One entrypoint, progressive references

`skills/patstack/SKILL.md` is under 4 KB. It routes to phase references that are loaded only when the phase needs them:

| Reference | Load when |
|---|---|
| [coordination](../skills/patstack/references/coordination.md) | Creating, resuming, delegating or delivering a designated task |
| [decisions](../skills/patstack/references/decisions.md) | Choosing Full Send or Full Stop, or facing uncertainty |
| [planning](../skills/patstack/references/planning.md) | Writing a brief for larger work |
| [build-review](../skills/patstack/references/build-review.md) | Building, choosing R1/R2/R3, critical fast path, time and iteration limits |
| [testing-delivery](../skills/patstack/references/testing-delivery.md) | Checks, PR and live repair, shared targets, takeover/modernize, file-PR/babysit |
| [quality](../skills/patstack/references/quality.md) | Only for the quality dimensions a task actually touches |
| [access](../skills/patstack/references/access.md) | Login or test identity needed |
| [project-context](../skills/patstack/references/project-context.md) | Spec distribution, project packs, host routing |
| [task-state](../skills/patstack/references/task-state.md) | Long runs, compaction, resume |
| [retro](../skills/patstack/references/retro.md) | Closing the loop |
| [sources](../skills/patstack/references/sources.md) | Why a rule looks the way it does |

## Who owns what

| Concern | Authority | Patstack's role |
|---|---|---|
| Product spec, slices, dependencies, PRs, required checks | GitHub (Issue body, sub-issues, blocking links, branch protection) | Writes and reads them; never bypasses protection or impersonates approvers |
| Runtime ownership, leases, blockers, child runs, delivery records | Task registry ([contract](../coordination/README.md)) | Registers, claims, checkpoints, completes with evidence |
| Delegation, PR wakeups, phases in plans and checkpoints | The agent host (T3 Code: `delegate_task`, native PR watcher) | Uses native features; a dedicated progress bar or taskbar phase display is a possible future integration, **not implemented** |
| Native skills, plugins, Computer Use, browser tools | The client (Claude Code, Codex) and its updates | Uses what the actual runtime exposes; never copies managed payloads |
| Project procedures and verification recipes | Private project packs | Reads `INDEX.md`, loads only matching procedures |
| Host capabilities | Private per-host profile plus fresh discovery | Routes by verified capability, not by an old inventory |
| Workflow measurement | Private per-host KPI cache | Derived evidence only; never task status or authority |

One authority per field. A plan, case file or KPI row is evidence, never a second editable status.

## Delegation shape

Only the lead (actual Opus 5.5 or Sol 6.1) starts children, and only one layer deep. Each child gets the task and parent, goal, project/worktree, the accessible versioned spec, owned scope, model/runtime, allowed actions, dependencies, acceptance, proof and stop conditions. Children return findings and objections. They do not start agents or new top-level chats. Every fresh review round is a new delegation that carries prior findings and responses.

## Host routing

| Need | Eligible host |
|---|---|
| macOS APIs, Xcode, Apple builds, native Mac UI | macOS host with the tools verified |
| Linux services, builds, headless browser automation | Linux host with the stack available |
| Native Windows behavior, desktop, games, hardware | Windows host, verified in that environment |
| GPU work | Host with suitable hardware **and** a working driver and toolchain |
| Mobile | Host exposing the verified simulator, emulator or device actually tested |

A working SSH ping does not prove Computer Use. An installed Docker CLI does not prove a running daemon. A configured environment does not prove a deployed app.

## Why GitHub Issues for specs

Specs are written by the speccing agent and shared through the parent Issue body. An Issue is not a repository file, so specs add no commits and no `.gitignore` entries to the application repository. Drafts and caches live outside the repository and can be cleaned once the canonical version and required evidence are retained.
