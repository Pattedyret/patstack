#!/usr/bin/env python3
"""Report git worktrees by repository and ticket; optionally remove the merged, clean ones.

  python3 tools/worktrees.py REPO [REPO ...] [--base REF] [--apply] [--json]

Dry run by default. A worktree is removable only when all of these hold: it is not the
main worktree, not locked, its directory exists, it has no uncommitted, untracked or ignored
files (ignored files such as .env or local databases would be deleted with it),
its HEAD is merged into the base (default: origin/HEAD, else main, else master), and no
commit on it is missing from every remote-tracking branch (nothing unpushed). `--apply`
runs `git worktree remove` (never `--force`) for exactly those; branches are kept.
Squash-merged branches are not ancestors of the base and therefore stay; remove them by
hand after checking. Tickets are read from `tkt<digits>` in the branch or path. A ticket
with more than 8 worktrees gets a warning: re-plan the slices instead of adding more.
Python 3.9+, standard library only.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SLICE_LIMIT = 8
TICKET = re.compile(r"tkt[-_]?(\d+)", re.I)


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed in {repo} (exit {result.returncode})")
    return result


def worktrees(repo):
    entries, current = [], {}
    for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines() + [""]:
        if not line:
            if current:
                entries.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value if value else True
    return entries


def base_ref(repo, requested=None):
    candidates = [requested] if requested else []
    if not requested:
        head = git(repo, "symbolic-ref", "-q", "refs/remotes/origin/HEAD", check=False).stdout.strip()
        candidates += [head, "main", "master"]
    for ref in candidates:
        if ref and not git(repo, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False).returncode:
            return ref
    return None


def ticket_of(*texts):
    for text in texts:
        match = TICKET.search(text or "")
        if match:
            return f"TKT-{match.group(1)}"
    return "unticketed"


def inspect(repo, base=None):
    repo = Path(repo).resolve()
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    ref = base_ref(repo, base)
    items = []
    for index, entry in enumerate(worktrees(repo)):
        path = Path(entry["worktree"])
        branch = entry.get("branch", "")
        branch = branch[len("refs/heads/"):] if isinstance(branch, str) and branch.startswith("refs/heads/") else None
        item = {"path": str(path), "branch": branch, "head": (entry.get("HEAD") or "")[:12],
                "ticket": ticket_of(branch, path.name), "main": index == 0,
                "locked": "locked" in entry, "exists": path.is_dir() and "prunable" not in entry}
        reasons = []
        if item["main"]:
            reasons.append("main worktree")
        if item["locked"]:
            reasons.append("locked")
        if not item["exists"]:
            reasons.append("directory missing (git worktree prune)")
        if item["exists"]:
            # Ignored files count too (.env, local databases, kept data): removing the worktree would delete them.
            status = git(path, "status", "--porcelain", "--ignored", "--untracked-files=all").stdout.splitlines()
            changed = [line[3:] for line in status if line[:2] not in ("??", "!!")]
            untracked = [line[3:] for line in status if line[:2] == "??"]
            ignored = [line[3:] for line in status if line[:2] == "!!"]
            item["clean"] = not status
            item["blocking_files"] = (changed + untracked + ignored)[:20]
            if changed:
                reasons.append(f"{len(changed)} uncommitted changes")
            if untracked:
                reasons.append(f"{len(untracked)} untracked files")
            if ignored:
                reasons.append(f"{len(ignored)} ignored files (e.g. {ignored[0]})")
            head = entry.get("HEAD")
            if ref and head:
                item["merged"] = not git(repo, "merge-base", "--is-ancestor", head, ref, check=False).returncode
            else:
                item["merged"] = False
            if not item["merged"]:
                reasons.append(f"not merged into {ref}" if ref else "no base ref")
            unpushed = git(repo, "rev-list", "--count", head, "--not", "--remotes").stdout.strip() if head else "0"
            item["unpushed"] = int(unpushed or 0)
            if item["unpushed"]:
                reasons.append(f"{item['unpushed']} commits on no remote")
        item["removable"] = not reasons
        item["keep_reasons"] = reasons
        items.append(item)
    tickets = {}
    for item in items:
        if not item["main"]:
            tickets.setdefault(item["ticket"], []).append(item)
    warnings = [f"{ticket}: {len(group)} worktrees exceed {SLICE_LIMIT} slices; re-plan instead of adding more"
                for ticket, group in sorted(tickets.items()) if ticket != "unticketed" and len(group) > SLICE_LIMIT]
    return {"repo": str(repo), "common_dir": str(common), "base": ref,
            "tickets": {t: [i["path"] for i in g] for t, g in sorted(tickets.items())},
            "worktrees": items, "warnings": warnings}


def apply(report):
    removed, failed = [], []
    for item in report["worktrees"]:
        if not item["removable"]:
            continue
        result = git(report["repo"], "worktree", "remove", item["path"], check=False)
        (failed if result.returncode else removed).append(item["path"])
    return removed, failed


def render(report):
    lines = [f"{report['repo']} (base {report['base'] or 'none'})"]
    for ticket, paths in report["tickets"].items():
        lines.append(f"  {ticket}: {len(paths)}")
        for item in report["worktrees"]:
            if item["path"] in paths:
                state = "REMOVABLE" if item["removable"] else "keep: " + ", ".join(item["keep_reasons"])
                lines.append(f"    {item['path']} [{item['branch'] or 'detached'}] {state}")
    lines += [f"  WARNING: {w}" for w in report["warnings"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="+", type=Path, help="Any checkout or worktree of each repository")
    parser.add_argument("--base", help="Merged-into reference (default origin/HEAD, main, master)")
    parser.add_argument("--apply", action="store_true", help="Remove the removable worktrees (never --force)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    reports, seen, code = [], set(), 0
    for repo in args.repos:
        try:
            report = inspect(repo, args.base)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            print(f"worktrees: {error}", file=sys.stderr)
            code = 2
            continue
        if report["common_dir"] in seen:  # two paths of the same repository
            continue
        seen.add(report["common_dir"])
        if args.apply:
            report["removed"], report["remove_failed"] = apply(report)
            code = code or (2 if report["remove_failed"] else 0)
        reports.append(report)
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print(render(report))
            for path in report.get("removed", []):
                print(f"  removed {path}")
            for path in report.get("remove_failed", []):
                print(f"  NOT removed (git refused) {path}")
        if not args.apply and any(i["removable"] for r in reports for i in r["worktrees"]):
            print("Dry run: pass --apply to remove the REMOVABLE worktrees.")
    return code


if __name__ == "__main__":
    sys.exit(main())
