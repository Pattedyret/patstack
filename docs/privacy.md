# Privacy boundary

This repository is a publication of a private working setup. It contains the reusable workflow and nothing that identifies customers, accounts, devices or sessions.

## Included

- The two workflow skills, refreshed byte for byte from the private source, except for three paragraphs of `project-context.md` that named private project procedures. Those are replaced by generic text through hash-anchored rules in [`scripts/refresh_from_source.py`](../scripts/refresh_from_source.py).
- The KPI recorder, installer and tests. The test file uses a fictional Windows path as a fixture.
- Authored contracts, docs, visuals and sanitized examples.

## Never included

| Excluded | Where it stays |
|---|---|
| Real project packs, customer procedures, vault notes | Private local packs and vaults |
| Host addresses, SSH identities, device inventories | `~/.config/patstack/devices.local.json` (mode 0600) per host |
| Credentials, tokens, password-manager items | The owner's credential stores |
| Task registry database, board, KPI database, telemetry | Local state on each host |
| Transcripts, session IDs, ticket IDs | Client and registry storage |
| Client configuration, native and managed skill payloads | The clients' own locations |
| Rollback archives, previous skill collections | Private backups outside discovery |

## How it is enforced

`python3 scripts/check.py` fails on:

- home-directory paths, email addresses, IPv4 addresses (except loopback), private keys, common token formats, SSH public keys, tailnet hostnames, registry and session identifiers;
- forbidden file types (`*.sqlite3`, `*.db`, `*.jsonl`, `.env`, `devices.local.json`, keys);
- private names, matched by SHA-256 of each lowercase word so the checker does not publish the names it guards against;
- optional extra plain-text terms from a local file kept outside the repository: `~/.config/patstack/privacy-denylist.txt`, or the path in `PATSTACK_PRIVACY_DENYLIST`.

A scanner reduces mistakes; it cannot prove absence. Review the diff before every publication.
