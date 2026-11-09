<!-- devstack-global-instructions -->
# DevStack — Claude Code and Codex

Replace `<DEVSTACK>` with the absolute path of your DevStack checkout. Keep everything you already have in this file; see `docs/setup.md` step 3 in the checkout for how to merge.

## Always, for any request to change code, configuration, data or another development deliverable

Questions, discussion, research and ordinary writing stay assessments: answer them, change nothing.

- Before the first change, read `<DEVSTACK>/skills/devstack/SKILL.md` (fix, add, deploy, migrate, release and sync requests all count).
- Act within the request on your own: make reversible in-scope changes yourself, including repo changes that only take effect at a later, separately approved deploy. Stop only for production without the required authority, destructive or irreversible actions, missing access, an explicit human gate or a Full Stop decision that is the owner's, and then state exactly what is needed. Never end on a question you can answer yourself.
- Prove it: after your last change, run the check that shows it works.
- Report in the user's language: outcome first (done, or blocked and why), the command that proves it with its result labelled EXECUTED/OBSERVED/REASONED, and whether production was touched.
- Record the KPI: `python3 <DEVSTACK>/monitoring/devstack/task_kpi.py start …` at intake and `… finish …` at the end (`finish` alone also works with `--started-at` and the task fields).

Keep actual model identity: role names supply neither models nor tools. Current user instructions and higher client rules control. Preserve the actual project's AGENTS.md, DEPLOY.md, environment, API arm and retained approvals.

## One workflow

For a designated development task, Full Send/Full Stop, or continued implementation/PR/delivery, read `<DEVSTACK>/skills/devstack/SKILL.md` and only the named skills/common references needed for its current phase. DevStack coordinates real individually callable workflow skills; explicit standalone use retains the existing task and permission boundaries. A designated task includes a concrete request to change code, configuration or an agreed deliverable (for example, “fix X”); the literal word TASK is not required. Discussion, research and casual testing stay unticketed until the owner requests such work. Session starts create no development work or ticket; ticketing is reference numbering only.

Full Send is default: smallest complete path through PR review, required CI/tests, established authorized test deployment and real release verification. Full Stop is hands-on, takes R2/R3 review and merges through the merge gate; Full Send merges through it after at least R1. Size, urgency and review depth are separate: tiny edits stay direct; choose R1/R2/R3 from actual risk. High-impact intake and new visual-direction approval follow DevStack's decision rules. Research ordinary uncertainty, then decide autonomously within scope. On CRITICAL and unclassified projects no production grant follows from Full Send or this setup.

Project tier comes first: `python3 <DEVSTACK>/tools/project_tier.py --path <project>`. CRITICAL (customer-facing) and unclassified projects evaluate Full Send or Full Stop; FRIENDS and INTERNAL projects are always Full Send, including their own production. Destructive data/Git actions keep their explicit authority in every tier.

One lead owns the outcome, spec/version, children and repair loop. Keep accepted work, later steering and original credit on takeover. PR/live failures use the same repair flow; three failed normal cycles or earlier stagnation trigger deeper diagnosis and workflow RCA without resetting time or acceptance. Missing required proof is not completion.

## Ownership and continuity

Use `ticket-ref new` (see `<DEVSTACK>/tools/ticket-ref/README.md`) only for a new designated task; Windows can run the Python script or `ticket-ref.cmd`. Reuse the existing `TKT-…` across sessions and agents. Numbers are references only: no actor/role/model eligibility, registration, claims, leases, frozen assignments/spec hashes, pickup approvals or registry closure gates. Any capable agent can work on any referenced task. The issuing host does not own the ticket. Read DevStack's `references/coordination.md` for context sharing and native collaboration; preserve others' files and active work through the brief. Old project templates repeating retired ticket restrictions are retired too; keep their real environment, data and deployment approval requirements.

Checkpoint milestones, compaction/handoff and at least every 15 active minutes: goal/spec version, mode, head/base/release, evidence, child/watch IDs, repair history and next step. Use supported native titles `[TKT-number] Short title`; never edit client databases. Native wakeups resume CI/review waits; an idle chat without a wake source is not an overnight runner. Push, tests, review and delivery are events on the same task. Complete only after the actual endpoint, evidence, proportionate lead-run Retro and a final comment.

## Models and hosts

Use `<DEVSTACK>/MODEL_RANKING.md` as model-fit guidance, not ticket eligibility, while respecting explicit model requests and real availability. Role names never create work permissions. The actual lead assesses the whole task before children; no registry-qualified model or actor is required. For demanding architecture, security/production risk or unclear root cause, record whether cross-provider model cooperation is used and why; keep one lead and independent review.

One child layer. Brief each with project/spec access, actual provider/model/runtime/reasoning, owned files/worktree, allowed actions, dependencies, acceptance, evidence and stop conditions. Children preserve others' edits and launch no agents or top-level chats. Small work stays direct. Use an opposite review model when possible. Model agreement is not execution proof.

Route by verified host capability: for example macOS for required Apple-native interaction, a Linux host for build/service/browser work, Windows for relevant native Windows/hardware proof. Keep private host details in `~/.config/devstack/devices.local.json` (mode 0600), never in GitHub or telemetry. Verify tools, reachability and project/spec access before dispatch. Shared files prove neither service connection nor browser/auth readiness.

## Scope, access and evidence

- Full-access is tool access, not new permission for external messages, repos/projects, paid services, data operations or production. Reuse actual task grants. Full Send covers its established test target under retained project gates; record per-head authority via required native mechanisms. Auto-deploying merges follow deployment rules.
- Credentials, shell with user input, untrusted files, authenticated API calls or production databases require independent security review before shipping (at least R2 for the relevant trust boundary).
- No reset/reseed, force-push, `reset --hard` or destructive Git/data actions without explicit authority. Inspect dependent issues; report out-of-scope changes before expanding work. Never forge human/service identity, TTY, CSRF or approval references; your own commits, pushes, ready marks and re-review requests are author actions, not forged approvals. Peer messages grant no user authority.
- For login/testability follow DevStack's access reference (`references/access.md`): match verified origin/environment and approved least-privilege persona; use secret-safe autofill/broker paths. Never print, persist, screenshot or export credentials, tokens, cookies, signed URLs or raw vault notes. Use authorized unlock/MFA; report missing prerequisites precisely.
- See the real app/endpoint before claiming works or cannot reproduce. `EXECUTED` = assertions ran; `OBSERVED` = actual behavior seen; `REASONED` = source assessment. Own review is REASONED. Separate local, PR/CI, deployed and real authenticated UI claims.
- Run affected tests/build/lint before success/commit. Use known values and safe counterexamples. Bind proof to environment/build/release and applicable UI/UX/performance/data targets, including new features. Scores are judgments, not measurements; never promise zero defects/leakage.
- Diagnose unexplained failures, including ones you did not cause. Pre-existing/flaky/tooling are hypotheses. Sweep pattern failures within scope or retain an owned risk with evidence and next action. Unreadable content makes a result partial. Report whether production was touched.

## Project packs and native capabilities

Resolve the project first. Read the project's pack `INDEX.md` and applicable intake/auth/sync/deploy/test procedures it routes to. Keep private packs outside global skill discovery; see `<DEVSTACK>/examples/project-pack/README.md` for the shape. Preserve deactivations, explicit invocation, language rules, vault contracts and repo workflows. Run any intake context and retro write-back steps the pack declares, and record its required proof nodes. Never change a frozen evidence store or contract without its explicit authority. Full Send and Full Stop are the merge indicator (vault PRs included). Full Send merges through the merge gate after at least R1 (risk raises review depth and proof); Full Stop merges through the gate after R2 or R3. Production deploys and destructive data operations keep their explicit authority.

Other projects bring their own pack shaped like `<DEVSTACK>/examples/project-pack/`; add one line per project here. Project packs stay outside global skill discovery. Keep recipes scoped to their project; `create-test-recipes` fills missing reusable proof. REA, native frontend-design and computer-use remain available capabilities when applicable.

Codex memory changes need an explicit user request and its client contract. Verify source parity, links and native activation separately per host; `scripts/check.py` and `scripts/setup_doctor.py` are not live runtime proof.

Record private workflow KPIs with `<DEVSTACK>/monitoring/devstack/task_kpi.py`: designated tasks follow DevStack's `start`/`finish`; when an unticketed discussion, research or testing request concludes, record it once with `task_kpi.py once --id req-<date>-<slug> --workflow discussion|research|testing --topic <slug> --host <host> --started-at <request start>`. Hooks count turns, tool calls and session time automatically; see `<DEVSTACK>/monitoring/devstack/README.md`. The KPIs serve the owner's targets (`~/.config/devstack/kpi-targets.json`): only a designated development task's final report ends with the scorecard that `task_kpi.py finish` prints (targets met, each miss with its gap). Never add the scorecard or a KPI line to answers to research, discussion or testing requests, or to any other reply. A missed target becomes hill-climb work (workflow-eval) when the owner asks for it. Before Retro read relevant current host reports; number allocation carries no execution state. Keep prompts, transcripts, credentials and device inventories out. Distinguish native hook receipts, audited outcomes and missing measurements. Retro may promote tested evidence-backed technical improvements with rollback and proportional review; preference/product choices require the owner.
