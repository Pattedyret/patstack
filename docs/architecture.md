# Architecture

Patstack keeps the workflow small and pushes everything else to the layer that already owns it.

## One coordinator, 19 callable skills

`skills/patstack/SKILL.md` coordinates the task. The other 18 folders under `skills/` have actual skill entrypoints and actionable workflows: planning (`to-spec`, `to-tickets`, `grilling`), building (`ponytail`, `implement`), checks (`review`, `council`, `verify`), modes (`full-send`, `full-stop`), delivery (`file-pr`, `babysit-pr`), continuity (`takeover`, `modernize`), learning (`retro`, `workflow-eval`) and capabilities (`create-test-recipes`, `reverse-engineer-anything`). See the [per-skill table](../README.md#skills).

A caller can enter a module directly. During development it binds the existing task and accepted spec, applies the shared rules and returns its result to the same lead. Standalone review, research, retro and evaluation stay within the user's request without creating a ticket. Modules do not invoke the coordinator recursively, create another lead or reset permissions, elapsed time, repair attempts or authority. Shared references are resources used by the actual skills, not substitutes for their entrypoints. They are loaded only when needed:

| Reference | Load when |
|---|---|
| [coordination](../skills/patstack/references/coordination.md) | Creating, resuming, delegating or delivering a designated task |
| [quality](../skills/patstack/references/quality.md) | Only for the quality dimensions a task actually touches |
| [access](../skills/patstack/references/access.md) | Login or test identity needed |
| [project-context](../skills/patstack/references/project-context.md) | Spec distribution, project packs, host routing |
| [task-state](../skills/patstack/references/task-state.md) | Long runs, compaction, resume |
| [sources](../skills/patstack/references/sources.md) | Why a rule looks the way it does |

Mode decisions now live in the actual [full-send](../skills/full-send/SKILL.md) and [full-stop](../skills/full-stop/SKILL.md) skills; planning in [to-spec](../skills/to-spec/SKILL.md) and [to-tickets](../skills/to-tickets/SKILL.md); build/review in [implement](../skills/implement/SKILL.md), [review](../skills/review/SKILL.md) and [council](../skills/council/SKILL.md); proof in [verify](../skills/verify/SKILL.md); learning in [retro](../skills/retro/SKILL.md). These are callable modules, not renamed reference files.

Five old phase-reference paths remain as short compatibility links for already-running 1.0 consumers during upgrade. They point to the actual modules and contain no duplicate workflow procedures. They are included in exact source coverage like every other resource; they are not counted as callable skills.

## Who owns what

| Concern | Authority | Patstack's role |
|---|---|---|
| Product spec, slices, dependencies, PRs, required checks | GitHub (Issue body, sub-issues, blocking links, branch protection) | Writes and reads them; never bypasses protection or impersonates approvers |
| Shared task reference numbers | Private local `ticket-ref` allocator ([contract](../coordination/README.md)) | Reuses an existing reference or allocates a new number; enforces no work eligibility or lifecycle |
| Delegation, PR wakeups, phases in plans and checkpoints | The agent host and its live tool contract | Uses native features; a dedicated progress bar or taskbar phase display is a possible future integration, **not implemented** |
| Native skills, plugins, Computer Use, browser tools | The client (Claude Code, Codex) and its updates | Uses what the actual runtime exposes; never copies managed payloads |
| Optional Chirp/Xirp app aliases | Their native app installer | May be discovered where installed; not part of the required 19 or required on Windows |
| Project procedures and verification recipes | Private project packs | Reads `INDEX.md`, loads only matching procedures |
| Host capabilities | Private per-host profile plus fresh discovery | Routes by verified capability, not by an old inventory |
| Workflow measurement | Private per-host KPI cache | Derived evidence only; never task status or authority |

One authority per field. A plan, case file or KPI row is evidence, never a second editable status.

T3 Code is a host adapter within these modules, not a separate skill. [Tool routing](../skills/patstack/references/coordination.md#t3-code-tools) follows its live injected contract rather than hardcoding a universal tool transport. Capability discovery, delegation, PR links and watches use only the operations actually exposed. A shared ticket reference creates no permission to execute them.

## Publication boundary

The approved catalog is exactly 19 skill directories. Every regular resource in those source directories, the monitor source package and the ticket-number tool is explicitly mapped by `scripts/refresh_from_source.py`; new resources cause a coverage failure until reviewed. Generated interpreter caches and the monitor installer's exact private backup tree are excluded explicitly. The manifest records source and published SHA-256 for every mapped file. Only exact, hash-anchored private paragraphs are transformed, and transformed bytes pass privacy preflight before any file is written. `--check` recomputes the transformation and compares exact path coverage, both hashes and the actual published bytes.

Project packs, accounts, private host configuration, databases, archives and transcripts remain outside the publication. Native frontend-design and Computer Use stay in their owner-managed locations. REA's seven existing files are included and scanned like every other resource; their absent license is documented separately from the MIT-licensed recipe and Ponytail adaptations.

## Delegation shape

The lead keeps one child layer. Each child gets the shared ticket reference, goal, project/worktree, the accessible agreed spec when needed, its exact scope, actual model/runtime, allowed actions, dependencies, acceptance, proof and stop conditions. Model choice is a task judgment, never a registry or ticket eligibility gate. Children return findings and objections. They do not start agents or new top-level chats. Every fresh review round is a new delegation that carries prior findings and responses.

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
