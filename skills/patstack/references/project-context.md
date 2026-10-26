# Bind the actual project

Resolve the workspace, project pack, environment, applicable permissions and host capabilities. Preserve project procedures; load detailed host routing only when host/tool choice matters.

## Spec storage, GitHub and cleanup

The speccing agent is the author; GitHub is a place to retain and share its output. Patrick delegated the distribution choice to the agents and requires no routine per-task spec clutter in the application codebase. For GitHub-backed work, put the canonical task spec directly in the parent Issue body. An Issue is not a repository file, so this requires neither a Git commit nor a `.gitignore` entry. Keep drafts and working caches outside the application repository.

BIG TASK owns distribution: give each worker/reviewer the Issue reference and exact spec version/snapshot. If that agent/host cannot read the canonical location, send the actual spec content in the task brief or transfer an accessible document, with the version attached. A local path that the recipient cannot open is not a successful handoff. On changes, distribute the new version to affected agents and obtain their acknowledgment; avoid independently editable spec forks. A full spec need not be pasted repeatedly when the shared reference is verifiably accessible.

After completion, close the Issue and retain its spec, PR links, benchmark evidence and retro as history. Temporary local drafts/caches can be cleaned after the canonical version and required evidence are safely retained. For a deliberately local-only task, use a shared artifact outside the codebase and the same handoff/version rules. Project-required intake records, ADRs or intentionally requested documentation remain actual deliverables; Patstack adds no extra tracked spec file for every task.

Use a parent Issue for the goal/spec, [native sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues) for independently verifiable delivery slices, and [native blocking relationships](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies) for dependencies. Reuse each repo's issue types/labels; API work can be an area label rather than assuming a special native type exists everywhere.

Use Projects for delivery visibility where useful; keep session ownership/leases and app-native orchestration in the runtime layer. Assign one authority per field and surface sync failures, rather than keeping two editable product-status registries. Keep reviewers and QA as checks on the existing work, not a new development issue for every review pass.

Link the PR to the issue and T3 thread, record the exact reviewed head, use the existing required checks/[branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), and use native PR wakeups. Model review reports are not GitHub human approvals. Do not bypass protections or impersonate a human approver.

Avoid auto-closing a parent on merge when its acceptance includes later release/live verification. An intermediate implementation issue may close while the parent remains open for its full outcome.

## Project workflows are part of the task contract

Before work, resolve the actual repo/workspace and applicable project pack, instructions, auth conventions, CI, branch rules, test/deploy target and required follow-through. Use available tools and repo evidence rather than asking Patrick for facts already present. Bind every worker to that context and its owned workspace. Verify described hooks and tools are actually configured; documentation alone does not prove execution.

Assess size and impact separately. Shared auth/session or permission behavior, important API contracts and broad effects on customer-facing production products are strong Full Stop signals even when the diff is small. A live production target never follows merely from working on the source of a production app. BIG TASK uses product inventories, system maps, dependency evidence and existing rules to identify affected products; ask Patrick only where business criticality or a product decision remains ambiguous. A newly discovered high-impact dependency during implementation triggers reassessment of the affected work.

Project packs are resolved from the shared setup source, never from this package: read the matching `project-skills/<project>/INDEX.md` and only the procedures it routes to for the actual change (for example new-surface intake, auth setup, deployment or synchronization). Use the canonical project workflow. These are conditional procedures, not mandatory scaffolding for every bug fix. Real project packs stay private and local; see `examples/project-pack/` in the published package for the shape.

Some project packs define post-merge synchronization to another branch or hosted builder, with drift checks and project-specific exclusions. Preserve those constraints. If the established path includes a PR hook, verify its actual result for the delivered revision; if that step has not run, the affected Full Send delivery is not complete. The procedure alone does not prove that a live hook ran for this revision.

Project workflows can include real human gates, such as intake decisions or new infrastructure; Full Send should reuse settled answers and approved project settings, not silently remove those gates. Report stale or conflicting procedure guidance against the actual project contract rather than copying it blindly.

## Private device and capability map

Keep the generic routing contract in Patstack and actual device details in a private local profile. Read `~/.config/patstack/devices.local.json` on the current host when needed. This private, mode-0600 profile is excluded from the shared setup and GitHub. If the profile is absent, perform fresh read-only discovery of relevant capabilities; absence proves nothing about device availability. Refresh the relevant observations before dispatch. Never attach the profile, addresses, SSH identities, private paths or session inventories to Issues/PRs.

The profile distinguishes user-declared ownership, configured capabilities and timestamped observations. Store OS/architecture, relevant CPU/RAM/GPU, installed tools, transport reachability, available simulator/emulator platforms, host-specific project locations, runtime/model availability and capability verification state. Keep credentials outside this profile in their existing credential stores.

Route by the task's needs and current capability/resource availability:

| Requirement | Eligible host |
|---|---|
| macOS APIs, Xcode, Apple-platform builds, native Mac interaction | macOS host with the required tools verified |
| Linux behavior, service/build work and Linux browser automation | Linux host when the needed stack is available |
| Native Windows behavior, Windows desktop/Steam/game/hardware tests | Windows host, verified in that actual environment |
| GPU workloads | A host with detected suitable hardware plus the required working driver/toolchain; presence of a GPU alone is insufficient |
| Frontend/browser testing | Any host/runtime that provides the required real browser/Computer Use proof; use the actual target OS when behavior depends on it |
| Mobile | Host exposing the relevant verified simulator/emulator/physical-device capability; report which was actually tested |

Check capability and project/spec access before dispatch. Use fresh reachability/tool verification for the chosen host instead of treating an old inventory as live status. Reserve shared GUI/device resources and avoid other users/agents' active contexts. Same-model/tool availability can differ by host and runtime. A working SSH/T3 ping does not establish Computer Use, an installed Docker CLI does not establish a running daemon, and a configured environment does not establish a deployed app.

### Devbox browser capability

Patrick explicitly requires browser testing on devbox and authorizes obtaining a browser if it lacks one. Reuse a working installed/bundled browser and matching automation runtime first. Provision missing browser binaries and only the needed runtime dependencies when required. [Playwright's browser guidance](https://playwright.dev/docs/browsers) describes version-matched binaries and Linux dependencies.

Headless Chromium on Linux can provide interaction assertions, screenshots, traces and relevant performance measurements. Record that actual platform/browser; native Windows/macOS behavior still needs its own target environment. Keep before/after benchmarking on equivalent conditions. Interactive visual-direction approval should use a view Patrick can actually inspect.

Use isolated task-owned browser sessions, profiles, fixtures and artifact directories. Do not reuse or close another session's browser. Keep the browser version/runtime and a verified launch recipe in the private capability profile. A synthetic browser smoke test establishes infrastructure readiness; it does not establish that a project feature or production behavior passes. Native Computer Use capability is recorded separately from Playwright automation.

