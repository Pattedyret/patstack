#!/usr/bin/env python3
"""Report branches whose pull request has merged; optionally delete them on origin and locally.

  python3 tools/branches.py REPO [REPO ...] [--apply] [--json]

Dry run by default. It runs `git fetch --prune origin`, then reads the repository's merged
and open pull requests with `gh`. A branch is deletable only when all of these hold:

- it is not the default branch and no open pull request uses it as head or base
  (deleting a stacked PR's base would close that PR);
- origin: a merged pull request from this repository has it as head, and the branch tip
  is exactly that pull request's head commit, so nothing was pushed after the merge.
  Squash and rebase merges count, because the PR record is read, not ancestry;
- local: it is not checked out in any worktree, and either its tip is contained in such a
  merged pull request's head, or its upstream is gone and its tip is contained in the
  default branch.

`--apply` deletes exactly those: origin with `git push --force-with-lease=<ref>:<tip>
origin :<ref>` and local ones with `git update-ref -d <ref> <tip>`, so a branch that moved
since the check is refused. Nothing is lost: every deleted commit is in a merged pull request (GitHub
keeps its head and offers Restore branch on the PR) or in the default branch.
It covers every branch of the repository, not only one task's. Python 3.9+, standard library only;
needs origin on GitHub and `gh` signed in to an account that can read the repo.
"""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys

PR_LIMIT = "2000"


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed in {repo} (exit {result.returncode}): {result.stderr.strip()[:200]}")
    return result


def gh(repo, *args):
    result = subprocess.run(["gh", *args], cwd=str(repo), capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed in {repo}: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


def refs(repo, prefix, fields):
    out = git(repo, "for-each-ref", "--format=" + "%00".join(fields), prefix).stdout
    return [line.split("\0") for line in out.splitlines() if line]


def contains(repo, ancestor, descendant):
    return ancestor == descendant or not git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode


def within(repo, tip, pr_head):
    """True when every commit of tip is in pr_head; an unknown pr_head (never fetched) only matches itself."""
    if tip == pr_head:
        return True
    known = not git(repo, "cat-file", "-e", pr_head + "^{commit}", check=False).returncode
    return known and contains(repo, tip, pr_head)


def origin_slug(repo):
    """OWNER/NAME of origin on GitHub, so the PRs read are those of the branches deleted (never gh's default repo)."""
    url = git(repo, "remote", "get-url", "origin").stdout.strip()
    match = re.fullmatch(r"(?:https://(?:[^@/]+@)?github\.com/|(?:ssh://)?git@github\.com[:/])([^/]+/[^/]+?)(?:\.git)?/?", url)
    if not match:
        raise RuntimeError(f"origin of {repo} is not a GitHub repository")
    return match.group(1)


def inspect(repo, gh=gh):
    repo = Path(repo).resolve()
    git(repo, "fetch", "--prune", "--quiet", "origin")
    meta = gh(repo, "repo", "view", origin_slug(repo), "--json", "nameWithOwner,defaultBranchRef")
    slug, default = meta["nameWithOwner"], meta["defaultBranchRef"]["name"]
    merged = {}
    for pr in gh(repo, "pr", "list", "-R", slug, "--state", "merged", "--limit", PR_LIMIT,
                 "--json", "number,headRefName,headRefOid,isCrossRepository"):
        if not pr["isCrossRepository"]:
            merged.setdefault(pr["headRefName"], []).append(pr)
    in_use = {}
    for pr in gh(repo, "pr", "list", "-R", slug, "--state", "open", "--limit", PR_LIMIT,
                 "--json", "number,headRefName,baseRefName,isCrossRepository"):
        if not pr["isCrossRepository"]:
            in_use.setdefault(pr["headRefName"], pr["number"])
        in_use.setdefault(pr["baseRefName"], pr["number"])

    def common(name):
        if name == default:
            return "default branch"
        if name in in_use:
            return f"open PR #{in_use[name]} uses it"
        return None

    remote = []
    for name, tip in refs(repo, "refs/remotes/origin", ["%(refname:strip=3)", "%(objectname)"]):
        if name == "HEAD":
            continue
        reason = common(name)
        prs = merged.get(name, [])
        match = next((pr for pr in prs if pr["headRefOid"] == tip), None)
        if not reason and not match:
            reason = (f"commits after merged PR #{prs[0]['number']}" if prs else "no merged PR")
        remote.append({"branch": name, "tip": tip, "pr": match and match["number"],
                       "deletable": not reason, "keep_reason": reason})

    local = []
    base = f"refs/remotes/origin/{default}"
    for name, tip, worktree, track in refs(repo, "refs/heads", ["%(refname:strip=2)", "%(objectname)",
                                                                "%(worktreepath)", "%(upstream:track)"]):
        reason = common(name) or (f"checked out in {worktree}" if worktree else None)
        match = next((pr for pr in merged.get(name, []) if within(repo, tip, pr["headRefOid"])), None)
        gone_and_merged = track == "[gone]" and contains(repo, tip, base)
        if not reason and not (match or gone_and_merged):
            reason = "commits after merged PR" if merged.get(name) else "no merged PR"
        local.append({"branch": name, "tip": tip, "pr": match and match["number"],
                      "deletable": not reason, "keep_reason": reason})
    return {"repo": str(repo), "github": slug, "default": default, "origin": remote, "local": local}


def run(repo, *args):
    try:
        return git(repo, *args, check=False).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def apply(report):
    repo, done, failed = report["repo"], [], []
    for item in report["origin"]:
        if item["deletable"]:
            ref = "refs/heads/" + item["branch"]
            ok = run(repo, "push", "--quiet", f"--force-with-lease={ref}:{item['tip']}", "origin", ":" + ref)
            (done if ok else failed).append("origin/" + item["branch"])
    for item in report["local"]:
        if item["deletable"]:  # like the push lease: refused if the branch moved since the check
            ok = run(repo, "update-ref", "-d", "refs/heads/" + item["branch"], item["tip"])
            (done if ok else failed).append(item["branch"])
            if ok:
                run(repo, "config", "--remove-section", "branch." + item["branch"])
    report["deleted"], report["delete_failed"] = done, failed
    return not failed


def render(report):
    lines = [f"{report['repo']} ({report['github']}, default {report['default']})"]
    for side in ("origin", "local"):
        items = report[side]
        deletable = [i for i in items if i["deletable"]]
        lines.append(f"  {side}: {len(deletable)} of {len(items)} deletable")
        for item in items:
            state = f"DELETABLE (PR #{item['pr']})" if item["deletable"] and item["pr"] else \
                "DELETABLE" if item["deletable"] else "keep: " + item["keep_reason"]
            lines.append(f"    {item['branch']} {state}")
    lines += [f"  deleted {name}" for name in report.get("deleted", [])]
    lines += [f"  NOT deleted (git refused) {name}" for name in report.get("delete_failed", [])]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="+", type=Path, help="A checkout of each repository")
    parser.add_argument("--apply", action="store_true", help="Delete the deletable branches")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    reports, code = [], 0
    for repo in args.repos:
        try:
            report = inspect(repo)
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            print(f"branches: {error}", file=sys.stderr)
            code = 2
            continue
        if args.apply and not apply(report):
            code = 2
        reports.append(report)
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print(render(report))
        if not args.apply and any(i["deletable"] for r in reports for side in ("origin", "local") for i in r[side]):
            print("Dry run: pass --apply to delete the DELETABLE branches.")
    return code


if __name__ == "__main__":
    sys.exit(main())
