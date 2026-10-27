# Privacy boundary

This repository is a publication of a private working setup. It contains the reusable workflow and nothing that identifies customers, accounts, devices or sessions.

## Included

- All 19 actual skill folders and their reviewed resources, including REA's seven existing files. Bytes are preserved except for explicitly mapped private paragraphs in `project-context.md`, replaced by generic text through fail-closed hash anchors in [`scripts/refresh_from_source.py`](../scripts/refresh_from_source.py).
- The ticket-number allocator and its tests, plus the KPI recorder, installer and tests. The test file uses a fictional Windows path as a fixture.
- Authored contracts, docs, visuals and sanitized examples. The one generated workflow GIF is accepted only at its exact known path with a reviewed SHA-256, signature, byte size and dimensions; every other binary format remains rejected.

## Never included

| Excluded | Where it stays |
|---|---|
| Real project packs, customer procedures, vault notes | Private local packs and vaults |
| Host addresses, SSH identities, device inventories | `~/.config/patstack/devices.local.json` (mode 0600) per host |
| Credentials, tokens, password-manager items | The owner's credential stores |
| Ticket-number SQLite store, retired registry data and board, KPI database, telemetry | Private local state on each host |
| Transcripts, session IDs, real ticket IDs | Private client, task and historical registry storage |
| Client configuration, native and managed skill payloads | The clients' own locations |
| Rollback archives, previous skill collections | Private backups outside discovery |

## How it is enforced

`python3 scripts/check.py` fails on:

- home-directory paths, email addresses, IPv4 addresses (except loopback), private keys, common token formats, SSH public keys, tailnet hostnames, registry and session identifiers;
- forbidden file types (`*.sqlite3`, `*.db`, `*.jsonl`, `.env`, `devices.local.json`, keys);
- archive, backup, transcript, private project-pack and host-config paths, symlinks, unreadable text and unreviewed file formats;
- private names, matched by SHA-256 of each lowercase word so the checker does not publish the names it guards against;
- optional extra plain-text terms from a local file kept outside the repository: `~/.config/patstack/privacy-denylist.txt`, or the path in `PATSTACK_PRIVACY_DENYLIST`.

A scanner reduces mistakes; it cannot prove absence. Review the diff before every publication.

Refresh checks every transformed file before its first write. The source inventory must match the explicit approved file list, including every resource under each required skill. Generated interpreter caches and the monitor installer's exact private runtime tree `monitoring/patstack/backups/` are excluded deliberately; a backup inside a skill still fails coverage. Changed or duplicated sanitization anchors reject the refresh. Package tests inject private values, extra files, stale hashes, broken links and changed anchors to prove those failures remain detectable.
