# Ticket-reference slots

Every machine that issues new `TKT-…` references needs its own issuer slot (1–99), so machines can allocate offline without collisions: a number is `sequence * 100 + slot`. A slot belongs to one machine for good. It is never shared, reused or reset. Continuing an existing ticket needs no slot.

[`slots.json`](slots.json) is the source of truth, and `ticket_ref.py init` reads it. It refuses a slot listed for another owner label. The table below mirrors it, and the numbering tests keep the two in sync.

| Slot | Owner label | Holder (role) |
|---:|---|---|
| 1 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 2 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 3 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 4 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 5 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 6 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 7 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 8 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |
| 9 | `reserved-maintainer` | Reserved for the upstream maintainer's machines |

## Claim a slot

1. Pick the lowest number from 10 to 99 that is not in `slots.json`.
2. Choose an opaque owner label of lowercase letters, digits and hyphens, such as `dev-07-laptop`. Never use a name, an email address or a host name: this file is public to the team and checked by the privacy scan.
3. Open a PR that adds `{"slot": <n>, "owner": "<label>"}` to `slots.json` and the same row to the table above, with the role in the last column (for example "Developer laptop"). Wait until it is merged, so that two people cannot claim the same slot at once.
4. Initialise your machine:

   ```bash
   python3 tools/ticket-ref/ticket_ref.py init --slot <n> --after <highest-number> --owner <label>
   ```

   Without `--owner`, a listed slot is refused. An unlisted slot is accepted with a reminder to claim it. Re-running `init` on a machine that already has its counter is always allowed.

A machine you retire keeps its row, so the slot is never handed out again. A replacement machine gets a new slot, unless you move the private counter file across as described in the [README](README.md).

## Choosing `--after`

`--after` must be at least the highest `TKT-` number the team has used anywhere: PR and issue titles in every repository, branch names and handoffs. The first number the machine issues is above it, so a new number can never repeat an old one. For this repository:

```bash
gh pr list -R <owner>/devstack --state all --limit 500 --json title -q '.[].title' | grep -oE 'TKT-[0-9]+' | sort -t- -k2 -n | tail -1
```

Run the same query for the other repositories you work in, and take the largest result. A value that is too high only leaves a gap, which is harmless. A value that is too low can reissue a number.
