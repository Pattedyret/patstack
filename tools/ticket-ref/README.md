# Ticket references only

`ticket-ref new` allocates one `TKT-…` number for a new designated task. Reuse an existing number on resume and pass the same reference to its agents, Issue, PR and handoff. Reviews and session starts do not get new numbers. Discussion, research and casual testing remain unticketed unless designated as work.

There are no agents, roles, assignments, claims, leases, approvals, pickup rules, execution states or completion gates in this tool. Any capable agent on any host can work on any referenced task. Coordinate files through the brief and preserve others' changes. The Issue/brief and actual delivery evidence describe the work; the number grants no data, service or deployment authority.

## Bootstrap and use

Use the standard-library Python script on each host:

```sh
python3 tools/ticket-ref/ticket_ref.py init --slot <n> --after <highest-number> --owner <label>
python3 tools/ticket-ref/ticket_ref.py new
```

Every machine needs its own slot from 1 through 99. Claim one by PR in the team's slot table, [`slots.json`](slots.json), which is explained in [SLOTS.md](SLOTS.md) together with how to choose `--after`: above the largest historical ticket number. `init` refuses a slot that the table lists for another owner label. Slots are private issuer namespaces, never agent ownership or eligibility. Numbers use `sequence * 100 + slot`, so hosts can allocate independently and offline without collisions. Gaps are expected. Do not clone a private counter to another host, reuse a slot or reset its sequence.

The private counter defaults to `~/.local/state/devstack/tickets.sqlite3`; `DEVSTACK_TICKET_DB` selects an isolated test store. It holds only slot and sequence, with no task content, identity or permissions. SQLite transactions serialize concurrent allocation. Repeating initialization with the same slot never lowers the sequence; a different slot is rejected. Back up the private counter when replacing a machine. Historical `TKT-…` references remain valid and are never renumbered.

An installed Unix launcher is `~/.local/bin/ticket-ref`; Windows uses its installed `ticket-ref.cmd` or `python` with the script path. `python3 scripts/ticket_launcher.py install --apply` writes either one safely. No daemon, browser or task-registry adapter is needed. A missing counter is an allocator setup problem, not a restriction on working on an already numbered task.

Run checks with `python3 -m unittest discover -s tools/ticket-ref -p 'test_*.py'`. Never commit the private counter to GitHub.
