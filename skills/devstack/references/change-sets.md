# Cross-repo change sets

One ticket can need changes in several repositories, for example an auth API, an admin app, a dashboard, a mobile app and a public web app. Treat them as **one change set**: one ticket, one lead, one endpoint.

## Shape

- **One ticket.** Every PR in the set carries the same reference and is titled `[TKT-…] <short title>`. No second ticket per repo; repo slices are slices of the same task.
- **One PR per repo.** A repo gets exactly one open PR for the set at a time. A fix-forward after merge is a new PR in that repo with the same title prefix.
- **Declared order.** Before the first merge, record the merge/deploy order in the brief and in each PR body, producer before consumer: for example `auth-api → admin, dashboard, web → mobile`. Repos that may merge in any order are listed in the same step. Backward-compatible producer changes (expand first) let consumers merge later; a breaking change needs expand → consumers → contract.
- **Contract check before any consumer merges.** The producer's API/contract change (routes, request/response shape, auth claims, error codes, schema/RLS) is checked against every consumer's actual use: a contract or schema test in the producer, the consumer's tests against the producer's candidate (preview or local build) and a negative case for removed or tightened fields. Record the check as a proof node, for example `--node contract-auth-api=pass`. A consumer PR is not ready while the producer contract it depends on is unmerged, undeployed to the test target or unchecked.
- **Endpoint = the whole set.** The task is complete only when every PR of the set is merged in the declared order and each repo's delivery is verified on its own surface (CI, test deployment, live proof) per [verify](../../verify/SKILL.md). One verified repo is a partial result; report the others as open, never as done.

## Tooling

`python3 tools/changeset.py TKT-… owner/producer owner/consumer-a owner/consumer-b` lists the set's PRs across the repos (given in declared merge order), with state, CI summary and merge times, and exits 1 when a later repo merged before an earlier one, or when an earlier repo merged again (for example a producer fix-forward) after a later one had merged: "multi-PR ordering unresolved" means the consumer must be re-verified against the latest producer. Repos merged in the same step can be grouped with a comma: `owner/auth-api owner/admin,owner/web`. It needs an authenticated `gh` and reads only. `--json` prints the machine-readable report.

## Review and KPIs

Review level follows the riskiest repo in the set ([review](../../review/SKILL.md)); the contract seam is reviewed once with both sides in view. Record the KPI once for the ticket with `--topic` set to the project slug (or the producer repo when one repo dominates) and `--slices` counting the repos, so Retro sees the set as one task ([KPI contract](../../../monitoring/devstack/README.md)).
