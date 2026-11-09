# Reference-only ticket numbering

A ticket number is a way for agents and people to refer to the same work. It is not a task registry or permission system. DevStack 1.4.0 keeps the `TKT-` prefix and numeric references while removing registration, claims, leases, role/model eligibility, pickup and lifecycle gates.

## Reuse before allocating

- Continue with an existing reference when work already has one, including references issued by the retired registry.
- A lead and its subagents normally share the same reference. Include it in the practical brief, Issue, PR, checkpoint and handoff.
- Allocate a new reference for genuinely separate work. Sharing a number does not synchronize context: pass the relevant Issue/PR, goal, scope, evidence and next step explicitly.
- Practical coordination still matters. Check active work and preserve other agents' changes. Review, CI, live proof, Full Send/Full Stop and real project, data, native-client and production authority remain.

## Offline allocator

The standard-library Python implementation and tests are included under [`tools/ticket-ref/`](../tools/ticket-ref/README.md). It stores only a local numeric counter and issuer slot in a private SQLite file. It keeps no task descriptions, actors, roles, models, claims or workflow statuses. No daemon, network or central service is required.

The default private store is `~/.local/state/devstack/tickets.sqlite3`. Set `DEVSTACK_TICKET_DB` to use an isolated store. Never commit or publish a live store.

For a fresh installation, choose a unique issuer slot from 1 through 99 for each host, determine the highest number already issued across the retired stores, and initialize once:

```bash
python3 tools/ticket-ref/ticket_ref.py init --slot <unique-host-slot> --after <legacy-high-water>
python3 tools/ticket-ref/ticket_ref.py new
```

Use `python` in place of `python3` where appropriate on Windows. An installed launcher may expose the same commands as `ticket-ref`.

Each new number is `sequence * 100 + slot`, above the configured legacy high-water mark. Distinct slots prevent collisions between independently allocating hosts. A slot identifies the allocator namespace only: every agent may work on every reference within actual task authority. Initialization refuses a slot change and never resets the counter. Preserve each store and its slot assignment when moving or restoring a host; never clone an active allocator into another independently issuing host.

## What numbering does not do

There are no commands for register, claim, status, pickup, stage authorization or complete. A number grants no permission and proves no outcome. Issues, PRs, agent briefs and observed runtime evidence carry the work's context and progress. The [KPI recorder](../monitoring/devstack/README.md) records explicit audited metadata separately; old registry discovery is historical data, never a prerequisite or outcome proof.

Old registry data and history remain private and preserved. They are not needed to work an existing reference. Native hook trust, login, deployment and destructive-action gates are separate from numbering and must never be fabricated or bypassed.
