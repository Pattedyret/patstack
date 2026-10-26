# Coordination runtime contract

Patstack's [coordination adapter](../skills/patstack/references/coordination.md) expects a local task registry CLI at `~/.local/bin/agent-work`. This file describes the **contract** the skill relies on. The registry implementation, its SQLite database and its board are private runtime components and are **not included** in this package.

If you run Patstack without such a registry, the skill still works as a workflow, but nothing durably records ownership, leases or delivery evidence. Report that as a missing prerequisite. Do not pretend a task is owned.

## Shape

- One registry per host, one SQLite file, one CLI.
- Reads: `agent-work list`, `agent-work show <task>`, `agent-work inbox <actor>`, `agent-work events <task>`.
- Mutations: `agent-work request` with **one JSON object on stdin**, so no user text is interpolated into shell arguments. The result is JSON on stdout. An error exits 2 and leaves the task unchanged.
- Every mutation after `create` carries `actor`, `id` and the **current `revision`** (compare-and-swap). On a stale revision, re-read; never edit the database directly.

```bash
~/.local/bin/agent-work request <<'JSON'
{"op":"checkpoint","actor":"ACTUAL-ACTOR","id":"ACTUAL-TASK","revision":7,
 "summary":"What changed and what was verified","next_action":"Concrete next step",
 "evidence":["path/or/url/to/evidence"]}
JSON
```

## Operations Patstack uses

| Group | Operations | Purpose |
|---|---|---|
| Identity | `register` | Bind actual runtime, native session ID, role and model. Idempotent per runtime + session. |
| Intake | `create`, `edit`, `classify` | One root per designated development task: project, title, acceptance, kind, area, work type, priority, deploy target, exact write scopes. |
| Ownership | `claim`, `checkpoint`, `block`, `unblock`, `handoff`, `recover` | Single owner with a lease renewed at milestones (at least every 15 minutes). Expired lease is not takeover permission. |
| Context | `packet`, `ack_context` | Compact resume packet; acknowledge changed requirements. |
| Delegation | `record_spec`, `provider_packet`, `child_run`, `child_run_update`, `dispatch_spec`, `claim` with `direct:true` | Lead records a spec, reserves a child run per slice with explicit provider/model, binds the spawned run; the child registers and claims. One child layer. |
| Delivery | `stage_authorize_chat`, `stage_begin`, `delivery` | Bind a quoted user instruction to an exact repo/PR/head, then record observed release evidence. Never a production grant. |
| Close | `comment`, `complete`, `cancel` | `complete` needs a summary and non-empty evidence; deployment-bound tasks need a recorded delivery. |
| Batches | `pickup_continue`, `bind_self` | Continue an already approved pickup batch under the actual lead. |

## Guarantees and non-guarantees

- The registry checks **shape and ownership**, not truth. Evidence fields prove that something was recorded, not that it is correct.
- Actor, role and model registration is a cooperative attestation under one OS user. It is not cryptographic identity.
- Scopes are absolute write paths. They protect cooperating agents from each other, not the file system from an agent that ignores them.
- The registry owns runtime ownership, blockers and execution records. GitHub owns the product spec and delivery visibility. The private [KPI cache](../monitoring/patstack/README.md) is derived measurement, never status.

## Host support

The supported registry runs on macOS and Linux hosts. There is **no native Windows adapter**: on Windows, use a verified route through a supported host for task ownership, or report the registry as a blocker. Never invent a Windows registration.
