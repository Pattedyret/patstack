#!/usr/bin/env python3
"""Report how fresh local clones are before judging remote state from them.

  python3 tools/freshness.py REPO [REPO ...] [--fetch] [--max-age-days 2] [--json]

Per repository: branch, default branch, comparison base (the branch's upstream, else
origin's default branch), commits ahead/behind that base, days since the last fetch
(FETCH_HEAD age), uncommitted changes, and whether a fast-forward would be safe (clean,
on the default branch, behind and not ahead). `--fetch` runs `git fetch --prune` first;
that is the only write. It never pulls, merges or fast-forwards: that stays your decision.

A repository is stale when it was never fetched, fetched more than --max-age-days ago,
is behind its base, or the requested fetch failed. Local refs of a stale clone are not
evidence of remote state (CI present, PR or branch status, merged or not, what is on
main): fetch, or ask the remote (`gh`). Exit 0 all fresh, 1 any stale, 2 usage error.
Python 3.9+, standard library only.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MAX_AGE_DAYS = 2


def git(repo, *args, timeout=60):
    """Run git without prompts, optional index locks or fsmonitor; None on failure."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    try:
        result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                                capture_output=True, text=True, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.rstrip("\n") if result.returncode == 0 else None  # porcelain lines start with a space


def default_branch(repo):
    ref = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if ref:
        return ref.rsplit("/", 1)[-1]
    for name in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}") is not None:
            return name
    return None


def repo_state(repo, fetch=False, base=None, max_age_days=MAX_AGE_DAYS):
    """Freshness of one clone. BASE overrides the comparison ref (for example origin/main)."""
    repo = Path(repo)
    state = {"repo": repo.name, "fetched": None, "stale": True, "reasons": []}
    if git(repo, "rev-parse", "--git-dir") is None:
        state["reasons"].append("not a git checkout")
        return state
    if fetch:
        state["fetched"] = git(repo, "fetch", "--prune", "--quiet", "origin") is not None
        if not state["fetched"]:
            state["reasons"].append("git fetch failed (offline or no access); remote state unverified")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    default = default_branch(repo)
    if base is None:
        upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        base = upstream or (f"origin/{default}" if default else None)
    ahead = behind = None
    counts = git(repo, "rev-list", "--left-right", "--count", f"HEAD...{base}") if base else None
    if counts and len(counts.split()) == 2:
        ahead, behind = (int(n) for n in counts.split())
    age = None
    path = git(repo, "rev-parse", "--git-path", "FETCH_HEAD")
    if path:
        fetch_head = Path(path) if Path(path).is_absolute() else repo / path
        if fetch_head.is_file():
            age = round((time.time() - fetch_head.stat().st_mtime) / 86400, 2)
    dirty = (git(repo, "status", "--porcelain", "--untracked-files=all") or "").splitlines()
    if age is None:
        state["reasons"].append("never fetched (no FETCH_HEAD)")
    elif age > max_age_days:
        state["reasons"].append(f"last fetched {age:.1f} days ago (> {max_age_days})")
    if behind:
        state["reasons"].append(f"{behind} commit(s) behind {base}")
    if base and counts is None:
        state["reasons"].append(f"cannot compare with {base}")
    state.update(head=git(repo, "rev-parse", "HEAD"), branch=branch, defaultBranch=default, base=base,
                 ahead=ahead, behind=behind, fetchedDaysAgo=age, dirty=len(dirty),
                 ffSafe=bool(behind) and ahead == 0 and not dirty and branch is not None and branch == default,
                 stale=bool(state["reasons"]))
    state["dirtyLines"] = dirty
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description="Report clone freshness before judging remote state.")
    parser.add_argument("repos", nargs="+", help="local checkouts")
    parser.add_argument("--fetch", action="store_true", help="run git fetch --prune first (never pull/merge)")
    parser.add_argument("--max-age-days", type=float, default=MAX_AGE_DAYS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    states = [repo_state(r, fetch=args.fetch, max_age_days=args.max_age_days) for r in args.repos]
    for state in states:
        state.pop("dirtyLines", None)
    if args.json:
        print(json.dumps(states, indent=2))
    else:
        for s in states:
            verdict = "STALE" if s["stale"] else "FRESH"
            where = f"{s.get('branch')} vs {s.get('base')}: ahead {s.get('ahead')}, behind {s.get('behind')}"
            extra = "; ".join(s["reasons"]) or f"fetched {s.get('fetchedDaysAgo')} days ago"
            ff = "; fast-forward safe" if s.get("ffSafe") else ""
            print(f"{verdict:<5}  {s['repo']:<28}  {where}; dirty {s.get('dirty')}; {extra}{ff}")
    return 1 if any(s["stale"] for s in states) else 0


if __name__ == "__main__":
    sys.exit(main())
