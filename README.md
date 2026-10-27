# Patstack

**One lead agent owns a development task from request to proof.** Patstack coordinates 19 individually callable skills for Claude Code and Codex. It binds the real project, picks the smallest complete route, chooses review depth by risk, and requires proof of the agreed endpoint: a verified test release (Full Send) or a ready, unmerged PR (Full Stop).

![Illustrative Patstack feature route: shared reference, Plan, Build, Check, Deliver, repair and Learn](docs/assets/patstack-workflow.gif)

*Illustrative workflow, not live task progress or measured results.* [Static diagram](docs/assets/patstack-workflow.svg) · [Interactive walkthrough with pause and reduced-motion support](docs/workflow.html)

## Skills

Each row is an actual `skills/<name>/SKILL.md` folder with its own workflow. Invoke a skill by name in your client's supported syntax or ask in plain language. Patstack coordinates them on the same task; calling a module does not create a second lead, ticket or permission grant.

| Skill | Say | Does |
|---|---|---|
| [patstack](skills/patstack/SKILL.md) | “Fix this and carry it through” | Owns intake, routing, evidence, repair and delivery. |
| [ponytail](skills/ponytail/SKILL.md) | “Use the smallest complete solution” | Reuses existing code, avoids speculative complexity and keeps required validation and proof. |
| [to-spec](skills/to-spec/SKILL.md) | “Turn this idea into a spec” | Resolves the problem, scope, acceptance and proof before implementation. |
| [to-tickets](skills/to-tickets/SKILL.md) | “Split this spec into delivery slices” | Creates independently verifiable slices with dependencies and one shared spec. |
| [implement](skills/implement/SKILL.md) | “Implement the agreed spec” | Builds the smallest complete change within the agreed scope. |
| [review](skills/review/SKILL.md) | “Review this candidate” | Chooses R1/R2/R3 by risk and records actionable findings. |
| [council](skills/council/SKILL.md) | “Run a council on this decision” | Uses independent Opus and Sol judgments followed by cross-examination. |
| [verify](skills/verify/SKILL.md) | “Prove this works” | Runs relevant checks and binds behavior and quality proof to the actual candidate or release. |
| [full-send](skills/full-send/SKILL.md) | “Full Send” | Carries authorized work through the established test target and live proof. |
| [full-stop](skills/full-stop/SKILL.md) | “Full Stop” | Keeps meaningful decisions hands-on and ends at a ready, unmerged PR. |
| [file-pr](skills/file-pr/SKILL.md) | “File a PR” | Prepares the reviewable diff, problem-first PR and required native links. |
| [babysit-pr](skills/babysit-pr/SKILL.md) | “Babysit this PR” | Uses native wakeups to handle checks, review and repair on the same task. |
| [takeover](skills/takeover/SKILL.md) | “Take over this work” | Checks active work, accepted decisions and current evidence, preserving original credit. |
| [modernize](skills/modernize/SKILL.md) | “Is this old PR still worth it?” | Rechecks relevance before updating old work. |
| [retro](skills/retro/SKILL.md) | “Run the retro” | Audits outcomes and missing proof, then proposes or promotes checked technical improvements. |
| [grilling](skills/grilling/SKILL.md) | “Grill me on this plan” | Asks one numbered batch of meaningful decision questions, each with a recommended answer. |
| [workflow-eval](skills/workflow-eval/SKILL.md) | “Evaluate this workflow” | Runs bounded, blinded comparisons of pinned versions on representative scenarios. |
| [create-test-recipes](skills/create-test-recipes/SKILL.md) | “Make testing repeatable” | Creates project-local Launch / Doctor / Run / Evidence / Cleanup recipes. |
| [reverse-engineer-anything](skills/reverse-engineer-anything/SKILL.md) | “Explain this shipped artifact” | Investigates artifacts and observed runtime behavior with REA. |

The [private KPI recorder](monitoring/patstack/README.md) is a separate standard-library Python package with a lifecycle audit hook, installer and tests. Native frontend-design, Computer Use, and optional app-owned Chirp/Xirp aliases remain external dependencies; their proprietary or owner-managed payloads are not copied here.

In T3 Code, the existing skills follow the live injected tool contract for delegation, PR linking, wakeups and other available capabilities. Each operation uses the actual runtime's supported transport. This adds no skill or permission; see [native tool routing](skills/patstack/references/coordination.md#t3-code-tools).

**Interactive walkthrough:** open [`docs/workflow.html`](docs/workflow.html) locally in a browser. It is self-contained, pausable, keyboard-operable and respects reduced-motion settings. GitHub shows HTML files as source, so clone or download the file to view it.

> **Status:** **1.2.0** is installed on Mac, devbox and Windows. The rollout lead reports all **19 skills** in fresh Claude Code and Codex initialization catalogs on each host, with all **52 canonical source files** matching the reviewed manifest. Local publication checks also pass. Fresh catalogs do not prove existing GUI sessions reloaded or a full overnight development run. See [Status and limits](docs/status-and-limits.md).

---

## What you say, what happens

Patstack triggers when a request designates development work. The modules above can also be called individually using the client's supported skill invocation. Phrases below are examples, not required keywords.

| You say | Patstack does |
|---|---|
| "Make the save button use the brand colour" | **Tiny route.** Edits directly, checks R1 and the affected states, then ships through the PR and test target in Full Send. |
| "Fix the redirect loop after login" | **Bounded fix.** Builds a red reproduction, makes the smallest fix, and adds R2 review when risk warrants. |
| "Build CSV export for reports" | **New feature.** Writes a brief, derives quality targets, splits into slices only where useful, runs R2, delivers, and proves it live. |
| "Checkout is down" | **Critical route.** Writes a short recovery contract and chooses the fastest safe fix or mitigation. Runs the full retro after recovery. |
| "Full Stop: change how sessions are shared" | **Full Stop.** The owner joins meaningful decisions. Review is R3 where warranted, and work ends at a ready, unmerged PR. |
| "Take over PR #123" | **Takeover.** Reads what exists and verifies it rather than trusting it. Resumes at the earliest valid phase and keeps original credit. |
| "Is this old PR still worth it?" | **Modernize.** Checks the problem still exists before reviving it, or recommends closure with evidence. |
| "File a PR" / "Babysit it" | **Delivery steps** inside the same task. These are not separate orchestrators. |
| "We keep re-figuring out how to test this" | Runs **`create-test-recipes`**: writes project-local Launch / Doctor / Run / Evidence / Cleanup recipes. |
| "What do you think about X?" | **Nothing.** Discussion, research and casual testing create no development ticket. |

## One reference across agents

A ticket is a shared reference in the form `TKT-` followed by at least four digits. Reuse an existing reference when continuing work; a lead and its subagents normally use the same number in briefs, Issues, PRs and handoffs. A genuinely separate task may receive a new reference.

The bundled `ticket-ref` tool allocates numbers offline from a private local SQLite store. Each issuing host uses a distinct numeric slot; the slot prevents allocation collisions and says nothing about who may work on a ticket. References carry no actor, role, model, lease, claim, workflow status, pickup or completion gate. Practical task briefs, review, tests, CI, live proof and real project authority still apply. See the [numbering contract](coordination/README.md).

## Two modes

| | **Full Send** (default) | **Full Stop** |
|---|---|---|
| Who decides routine choices | The lead: it researches, picks the safest useful reversible option and records it | The lead for facts and routine details; the owner for meaningful product and approach decisions |
| Endpoint | Verified test release with live proof | Evidenced, ready, **unmerged** PR handed over |
| When | Every development task unless classified otherwise | Very large or important work touching sensitive auth or permissions, an important shared API, or broad customer-facing behavior |
| What does *not* switch modes | Uncertainty alone, two equivalent technical options | A cosmetic edit in a sensitive repo |

Size, urgency and review depth are separate choices from the mode. A Full Send grant covers the task's established test target and repair revisions. **Production always needs its own explicit authority.** [Full Send →](skills/full-send/SKILL.md) · [Full Stop →](skills/full-stop/SKILL.md)

## Phases

| Phase | Done when |
|---|---|
| **Plan** | Brief, relevant quality targets and the proof method are enough to implement. Accepted specs are reused, not rebuilt. |
| **Build** | The smallest complete candidate and its relevant tests exist. Work is parallelized only for ready, independent scopes with one owner each. |
| **Check** | The current candidate has the required review level, CI, and acceptance and quality evidence. |
| **Deliver** | Full Send: the intended test release works, with proof. Full Stop: the ready, unmerged PR is handed over. |
| **Learn** | Proportionate retro. Only justified, tested technical improvements are promoted. |

## Review levels

| Level | Who | Typical fit |
|---|---|---|
| **R1 Focused** | The author checks the diff and the targeted result. Labelled author review, never independent. | Trivial cosmetic, copy or mechanical edits |
| **R2 Independent** | One fresh opposite-model reviewer (Opus work → Sol, Sol work → Opus) | Behavior fixes and features. **Minimum** for auth, credentials, shell with user input, untrusted files, authenticated APIs, production databases, destructive operations and important API contracts. |
| **R3 Council** | Fresh Opus **and** Sol sessions judge independently first, then cross-examine | Broad auth/API changes, migrations, shared systems, unresolved material disagreement |

Depth follows behavior and blast radius, not filenames. A missing required reviewer is reported as missing. There is no silent downgrade. [Review rules →](skills/review/SKILL.md) · [Council →](skills/council/SKILL.md)

## One repair flow for PR and live failures

```mermaid
flowchart LR
  B[Build] --> C[Check]
  C --> D[Deliver]
  C -- PR / CI / review failure --> R{Repair}
  D -- live failure on verified release --> R
  R -- smallest fix, incremental review --> B
  R -- 3 normal cycles or stagnation --> X[Deep diagnosis:<br/>new hypothesis, same clock]
  X --> B
  D -- Full Send --> L[Verified test release]
  D -- Full Stop --> P[Ready unmerged PR]
```

Every failure records its layer, criterion, exact candidate or release, evidence and next action. Attempts and elapsed time carry across layers, PRs and models. Switching any of them does not reset the count. A merged PR is never reopened as a repair mechanism: fix-forward goes in a new linked PR on the same task. [Verify →](skills/verify/SKILL.md) · [Babysit PR →](skills/babysit-pr/SKILL.md)

## Quality proof, not scores

Every feature gets two verdicts: **"Feature works? Y/N"** and **"Meets the quality standard? Y/N"**. Evidence that is required but missing is reported as *not verified*. It is never counted as a Yes. Targets are derived by the agent before implementation and frozen; they are not retuned after results arrive.

| Task | Derived target and proof (examples from the [quality reference](skills/patstack/references/quality.md)) |
|---|---|
| New web page | Project budgets first. Where applicable, LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at p75 as initial field targets. Lab runs are proxies, not field proof. |
| New form or dialog | Existing components; keyboard completion; visible focus; contrast ≥ 4.5:1 for normal text; no horizontal overflow at supported widths |
| API or search endpoint | Before/after latency (median, p95), queries per request, payload, errors, and executed permission and leakage counterexamples on the same workload |
| Data change | Exact records, fields and permissions. Counts or sums alone prove nothing. |
| Tiny colour fix | Requested appearance and affected contrast, focus, hover and disabled states. No benchmark. |

These are engineering examples to derive per project, not universal thresholds. Patstack's own documents contain **no measured benchmark results**.

## Continuing other work

- **Takeover:** read the spec, PR, handoff, later corrections and current head. Check active work and uncommitted changes before writing. A handoff describes context, not correctness.
- **Modernize:** first ask whether the original problem still exists. A conflict-free rebase does not prove the PR is still relevant.
- **File PR → Babysit:** write a problem-first PR. Only the PR-owning lead watches it, through the native T3 PR watcher. A wake brings new state, and the latest head and checks are re-read before any readiness call.

Neither route grants force-push, merge, close or deploy rights.

## Specs live in GitHub, not in your repo

The canonical task spec goes in the **parent GitHub Issue body**. Delivery slices are native sub-issues, and dependencies use native blocking relationships. Nothing per task is committed to the application repository. There are no spec files, no planning folders, and no `.gitignore` churn. The lead hands each worker the shared ticket reference, Issue reference and spec version. If a worker cannot read it, the lead sends the content itself, because a path the worker cannot open is not a handoff. [Project context →](skills/patstack/references/project-context.md)

## Native, project and private layers

| Layer | Lives in | Published here? |
|---|---|---|
| Coordinator and 18 callable workflow/capability modules | This repository's `skills/` | Yes, exactly 19 folders |
| Optional Chirp/Xirp aliases | App-owned installation | No; optional on Unix and unavailable on the current Windows host |
| Native client capabilities (Claude/Codex system skills, plugins, Computer Use, browser tools) | The client's own managed locations | **No**. They are owned and updated by the client. Patstack uses them when the actual runtime exposes them. |
| Project packs (intake, auth, deploy and sync procedures, verification recipes) | Private, per project | **No**. See the sanitized [example project pack](examples/project-pack/README.md). |
| Host capability profile | `~/.config/patstack/devices.local.json`, mode 0600, per host | **No**. Only the [template](examples/devices.example.json). |
| Ticket-number store, historical registry, KPI database, telemetry, transcripts | Private local state on each host | **No**. The numbering tool and [contract](coordination/README.md) are included; private data is excluded. |

More in [docs/architecture.md](docs/architecture.md).

## Long runs and checkpoints

The lead keeps one compact record on the existing ticket: goal and spec version, completed criteria with evidence, candidate head/base/release, active scopes and agent briefs, the next concrete action, and cumulative attempts and time. It checkpoints at milestones, before compaction or handoff, and at least every 15 minutes. While waiting on CI or review, it ends only the current turn, and the native PR watcher wakes it. If no durable wake mechanism exists, it reports that gap; it does not pretend an idle chat will restart. Phases show up in native plans and checkpoints. **A T3 progress bar or taskbar phase display is a possible future UI integration and is not implemented.** [Task state →](skills/patstack/references/task-state.md)

## KPI monitoring

```bash
python3 monitoring/patstack/kpi_monitor.py record < examples/kpi-snapshot.example.json
python3 monitoring/patstack/kpi_monitor.py report
```

Snapshots are allowlisted metadata only: IDs, mode, status, timestamps, counts and node outcomes. They never hold prompts, transcripts or credentials. Missing labels stay *unknown*, never zero. The lifecycle hook records audit receipts (hashed session identity and event counts) and **does not** infer outcomes. Retro reads the report and then checks the underlying evidence. [KPI contract →](monitoring/patstack/README.md)

## Quick start

```bash
git clone <this repository> patstack && cd patstack
python3 scripts/check.py        # links, privacy scan, formats, KPI example, unit tests
```

Then follow [docs/setup.md](docs/setup.md) to expose the skills to Claude Code or Codex, add your host profile and optionally wire the audit hook.

## Repository map

```
skills/patstack/                 coordinator + progressive shared references
skills/<module>/                18 individually callable workflows/capabilities
monitoring/patstack/             KPI recorder, audit hook, installer, tests
coordination/README.md           reference-only ticket numbering contract
tools/ticket-ref/               offline numeric allocator and tests
MODEL_RANKING.md                 optional model preferences (example)
examples/                        project pack, host profile and KPI snapshot templates
docs/                            setup, architecture, status, privacy, visuals
scripts/refresh_from_source.py   refresh published files from the private source
scripts/check.py                 exact coverage, links, privacy, formats and tests
scripts/test_package.py          source/parity/privacy mutation counterexamples
SOURCE-MANIFEST.json             source and published SHA-256 per refreshed file
```

## Credits and license

Patstack draws on [Theo's tstack](https://github.com/t3dotgg/tstack), [Matt Pocock's skills](https://github.com/mattpocock/skills), [Poteto's pstack](https://github.com/cursor/plugins/tree/main/pstack), [Zeroshot's review loop](https://github.com/the-open-engine/zeroshot/blob/main/docs/guides/review-loop.md) and [Ponytail](https://github.com/DietrichGebert/ponytail). Recipe and Ponytail adaptations retain their MIT notices and provenance. REA's existing source has no license supplied; its inclusion does not invent a reuse grant. See [`sources.md`](skills/patstack/references/sources.md) and [NOTICE.md](NOTICE.md).

**No license has been selected for this repository as a whole.** See [NOTICE.md](NOTICE.md).
