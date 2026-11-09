#!/usr/bin/env python3
"""List a ticket's PRs across repositories and check the declared merge order.

  python3 tools/changeset.py TKT-<n> owner/producer owner/consumer-a,owner/consumer-b owner/last [--json]

Repositories are given in the declared merge order; a comma groups repositories of the
same step (any order among them). Every merged PR counts: exit 0 when the order holds, 1 when
a later step merged before an earlier one or an earlier step merged again after a later step
("multi-PR ordering unresolved"), 2 on usage or `gh` errors. Read-only: it only runs `gh pr list`.
Python 3.9+, standard library only.
"""
import argparse
from datetime import datetime
import json
import re
import shutil
import subprocess
import sys

FIELDS = "number,title,state,mergedAt,url,isDraft,headRefName,statusCheckRollup"
TICKET = re.compile(r"TKT-\d+")


class ChangeSetError(RuntimeError):
    pass


def gh_prs(repo, ticket):
    """PRs in REPO whose title starts with [TICKET]."""
    gh = shutil.which("gh")
    if not gh:
        raise ChangeSetError("gh is not installed or not on PATH")
    try:
        out = subprocess.run([gh, "pr", "list", "--repo", repo, "--state", "all", "--limit", "100",
                              "--search", f"{ticket} in:title", "--json", FIELDS],
                             capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise ChangeSetError(f"gh timed out for {repo}") from None
    if out.returncode:
        # gh stderr can carry authenticated URLs; report only the repo and the exit code.
        raise ChangeSetError(f"gh pr list failed for {repo} (exit {out.returncode})")
    try:
        items = json.loads(out.stdout or "[]")
    except ValueError:
        raise ChangeSetError(f"gh returned invalid JSON for {repo}") from None
    prefix = f"[{ticket}]"
    return [item for item in items if str(item.get("title", "")).startswith(prefix)]


def checks(rollup):
    """pass / fail / pending / none for a statusCheckRollup list."""
    if not rollup:
        return "none"
    states = []
    for item in rollup:
        value = (item.get("conclusion") or item.get("state") or item.get("status") or "").upper()
        states.append(value)
    if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE") for s in states):
        return "fail"
    if any(s in ("", "PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED") for s in states):
        return "pending"
    return "pass"


def merged_at(pr):
    value = pr.get("mergedAt")
    if not value or pr.get("state") != "MERGED":
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(ticket, steps, fetch=gh_prs):
    """Report for STEPS (a list of lists of repos in declared order)."""
    repos, violations, notes_open = [], [], []
    for position, step in enumerate(steps, 1):
        for repo in step:
            prs = fetch(repo, ticket)
            merges = [m for m in (merged_at(pr) for pr in prs) if m]
            open_prs = [pr for pr in prs if pr.get("state") == "OPEN"]
            state = "missing" if not prs else "open" if open_prs else "merged" if merges else "closed"
            repos.append({
                "repo": repo, "step": position, "state": state,
                "first_merged_at": min(merges).isoformat() if merges else None,
                "last_merged_at": max(merges).isoformat() if merges else None,
                "merges": sorted(merges),
                "prs": [{"number": pr.get("number"), "state": pr.get("state"), "draft": bool(pr.get("isDraft")),
                         "checks": checks(pr.get("statusCheckRollup")), "merged_at": pr.get("mergedAt"),
                         "url": pr.get("url")} for pr in prs],
                "open_prs": len(open_prs),
            })
    # Every merged PR counts, not only the first: a producer fix-forward that merges after a consumer
    # leaves that consumer built against an older producer, so the order is unresolved.
    unresolved = []
    for later in repos:
        if not later["merges"]:
            continue
        first_later = later["merges"][0]
        for earlier in repos:
            if earlier["step"] >= later["step"]:
                continue
            label = f"{later['repo']} (step {later['step']})", f"{earlier['repo']} (step {earlier['step']})"
            if not earlier["merges"]:
                violations.append(f"{label[0]} merged while {label[1]} is not merged")
            elif earlier["merges"][0] > first_later:
                violations.append(f"{label[0]} merged before {label[1]}")
            elif earlier["merges"][-1] > first_later:
                unresolved.append(f"multi-PR ordering unresolved: {label[1]} merged again at "
                                  f"{earlier['merges'][-1].isoformat()} after {label[0]} merged at {first_later.isoformat()}; "
                                  f"re-verify {later['repo']} against the latest producer or document why it is compatible")
            if earlier["open_prs"] and later["state"] == "merged":
                notes_open.append(f"{earlier['repo']} still has an open PR while {later['repo']} is merged; "
                                  "a later producer merge would leave the order unresolved")
    for repo in repos:
        repo.pop("merges")
    notes = [f"{r['repo']}: {r['open_prs']} open PRs for one ticket; keep one PR per repo"
             for r in repos if r["open_prs"] > 1] + sorted(set(notes_open))
    notes += [f"{r['repo']}: no CI checks reported; proof is local only (a stated risk, not N/A)" for r in repos
              if r["prs"] and all(p["checks"] == "none" for p in r["prs"] if p["state"] != "CLOSED")
              and any(p["state"] != "CLOSED" for p in r["prs"])]
    complete = all(r["state"] == "merged" for r in repos)
    return {"ticket": ticket, "order_ok": not violations and not unresolved, "complete": complete,
            "repos": repos, "violations": violations, "unresolved": unresolved, "notes": notes}


def render(report):
    lines = [f"{report['ticket']}: order {'OK' if report['order_ok'] else 'VIOLATED'}, "
             f"set {'complete' if report['complete'] else 'incomplete'}"]
    for repo in report["repos"]:
        prs = ", ".join(f"#{p['number']} {p['state'].lower()}{' draft' if p['draft'] else ''} checks={p['checks']}"
                        for p in repo["prs"]) or "no PR"
        lines.append(f"  {repo['step']}. {repo['repo']}: {repo['state']} ({prs})")
    lines += [f"  VIOLATION: {v}" for v in report["violations"]]
    lines += [f"  UNRESOLVED: {u}" for u in report["unresolved"]]
    lines += [f"  note: {n}" for n in report["notes"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ticket", help="Ticket reference, TKT-<number>")
    parser.add_argument("steps", nargs="+", help="Repos in merge order; comma-separate repos of the same step")
    parser.add_argument("--json", action="store_true", help="Print the JSON report")
    args = parser.parse_args(argv)
    if not TICKET.fullmatch(args.ticket):
        parser.error("ticket must look like TKT-<number>")
    steps = [[r for r in step.split(",") if r] for step in args.steps]
    if any(not re.fullmatch(r"[\w.-]+/[\w.-]+", r) for step in steps for r in step) or not all(steps):
        parser.error("repos must be owner/name")
    flat = [r for step in steps for r in step]
    if len(flat) != len(set(flat)):
        parser.error("each repo may appear once")
    try:
        report = evaluate(args.ticket, steps)
    except ChangeSetError as error:
        print(f"changeset: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["order_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
