# Privacy boundary

This repository maintains a reusable workflow. Original author attribution is retained; customer, account, device and session details stay private. Private project packs are excluded from the public distribution.

## Included

- All 19 actual skill folders and their reviewed resources, including REA's files with their MIT notice and provenance. The team maintains these files directly. Optional upstream-only comparison retains fail-closed hash anchors for the original private paragraphs in `project-context.md`; normal manifest generation hashes local bytes without replacing them.
- The ticket-number allocator and its tests, plus the KPI recorder, installer and tests. The test file uses a fictional Windows path as a fixture.
- Authored contracts, docs, visuals and sanitized examples. The one generated workflow GIF is accepted only at its exact known path with a reviewed SHA-256, signature, byte size and dimensions; every other binary format remains rejected.

## Never included

| Excluded | Where it stays |
|---|---|
| Other projects' packs, credentials, personal and customer data, vault notes | Private local packs, password managers and vaults. Any bundled private pack holds procedures only and gets the full privacy scan before team delivery. |
| Host addresses, SSH identities, device inventories | `~/.config/devstack/devices.local.json` (mode 0600) per host |
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
- personal instruction names outside the exact author-credit line in `NOTICE.md`;
- private names, matched by SHA-256 of each lowercase word so the checker does not publish the names it guards against; explicit pack-declared branding phrases and exact author-credit line are narrowly allowed;
- optional extra plain-text terms from a local file kept outside the repository: `~/.config/devstack/privacy-denylist.txt`, or the path in `DEVSTACK_PRIVACY_DENYLIST`.

A scanner reduces mistakes; it cannot prove absence. Review the diff before every publication.

Manifest generation checks every resource before writing the manifest, and never rewrites resources. Optional upstream comparison checks transformed bytes without writing any file. The source inventory must match the explicit approved file list, including every resource under each required skill. Generated interpreter caches and the monitor installer's exact private runtime tree `monitoring/devstack/backups/` are excluded deliberately; a backup inside a skill still fails coverage. Changed or duplicated sanitization anchors reject the refresh. Package tests inject private values, extra files, stale hashes, broken links and changed anchors to prove those failures remain detectable.
