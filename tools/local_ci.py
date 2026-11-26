#!/usr/bin/env python3
"""Run a repository's CI in the agent instead of on GitHub, and record the result on the PR.

  python3 tools/local_ci.py --path CHECKOUT [--repo OWNER/NAME --pr N --runner PROVIDER/MODEL]
                            [--base REF] [--script PATH]

The CI is the repository's own script, ported from its old hosted workflows: by default
`scripts/ci-local.sh` (run with bash), else `scripts/ci_local.py` (run with the current Python interpreter). The checkout must be clean: CI runs on the committed head, never on
uncommitted edits. It runs in a throwaway detached worktree, so the checkout is not touched.

With --pr, the open PR's head must equal the checkout's HEAD (push first) and origin must be
the PR's repository. The base branch's current commit is read from GitHub, fetched and
checked, and the head is combined with exactly that commit, so CI proves what will land.
The result is posted as a PR comment whose whole body is one line, with full SHAs,
  Patstack-CI: result=pass|fail head=<sha> runner=<provider/model> base=<sha>
which tools/merge_gate.py reads for repositories the tier map lists under `local_ci`; a new
commit on the base means a new run. --base and --script are refused with --pr. Without
--pr they allow an unrecorded run, and nothing is posted.

The CI process runs as the operator: it keeps the operator's files, including the stored
GitHub login under HOME, and only loses environment variables that look like credentials
(by name, or URLs that carry a password). So it trusts the PR's code like the operator's own:
with --pr it refuses PRs from another repository (forks) and PR authors who cannot push.

Exit 0 CI passed, 1 CI failed or the merge into the base conflicted, 2 usage or setup error.
Python 3.9+, standard library only; runs git, bash and gh.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$")
SCRIPTS = ("scripts/ci-local.sh", "scripts/ci_local.py")
GIT_ID = ["-c", "user.name=local-ci", "-c", "user.email=local-ci@invalid", "-c", "commit.gpgsign=false"]


class SetupError(Exception):
    pass


def git(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise SetupError("git %s: %s" % (" ".join(args), (result.stderr or result.stdout).strip()))
    return result.stdout.strip()


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode:
        raise SetupError("gh %s: %s" % (args[0], (result.stderr or result.stdout).strip()))
    return result.stdout


# Names of environment variables that may carry credentials; the CI process does not get them.
SECRET_ENV = re.compile(r"TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE|SESSION|PRIVATE|KEY|DATABASE|_DSN$|JWT|_SK$|_PW$|"
                        r"^(GH|GITHUB|HEROKU|AWS|SUPABASE|EXPO|EAS|NPM_CONFIG__)", re.I)
# A value that carries credentials in a URL (scheme://user:password@host), whatever its name.
SECRET_VALUE = re.compile(r"://[^/\s:@]*:[^/\s@]+@")


def record(passed, head, runner, base):
    return "Patstack-CI: result=%s head=%s runner=%s base=%s" % ("pass" if passed else "fail", head, runner, base)


def ci_env():
    """The environment for the CI process: the operator's, minus anything that looks like a credential."""
    return {name: value for name, value in os.environ.items()
            if name != "GIT_CONFIG_COUNT" and not name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
            and not SECRET_ENV.search(name) and not SECRET_VALUE.search(value)}


def base_tip(repo, branch):
    """The current commit of the PR's base branch on GitHub. The name is URL-encoded and the answer
    must name exactly that ref, so `main#x` can never resolve to `main`."""
    ref = "refs/heads/" + branch
    found = json.loads(gh("api", "repos/%s/git/ref/heads/%s" % (repo, quote(branch, safe="/"))))
    if not isinstance(found, dict) or found.get("ref") != ref or not re.fullmatch(r"[0-9a-f]{40}", found.get("object", {}).get("sha", "")):
        raise SetupError("GitHub did not return %s" % ref)
    return found["object"]["sha"]


def run(path, head, base="", script=None):
    """Whether the CI script passes on head, merged into base when given. Both are full commit SHAs."""
    tmp = tempfile.mkdtemp(prefix="local-ci-")
    work = str(Path(tmp) / "tree")
    try:
        git(path, "worktree", "add", "--detach", work, base or head)
        if base:
            combined = subprocess.run(["git", *GIT_ID, "merge", "--no-ff", "--no-edit", head],
                                      cwd=work, capture_output=True, text=True)
            if combined.returncode:
                print("CONFLICT: head %s does not merge cleanly into base %s" % (head[:12], base[:12]), file=sys.stderr)
                return False
        script = script or next((name for name in SCRIPTS if (Path(work) / name).is_file()), SCRIPTS[0])
        if not (Path(work) / script).is_file():
            raise SetupError("%s not found on this head; port the repo's CI into it first" % script)
        command = [sys.executable if script.endswith(".py") else "bash", script]
        print("== local CI: %s on %s%s" % (script, head[:12], " merged into %s" % base[:12] if base else ""), flush=True)
        passed = subprocess.run(command, cwd=work, env=ci_env()).returncode == 0
        print("== local CI %s on %s" % ("PASSED" if passed else "FAILED", head[:12]), flush=True)
        return passed
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", work], cwd=path, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=path, capture_output=True)
        listed = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=path, capture_output=True, text=True)
        if work in listed.stdout:
            print("WARNING: could not remove the CI worktree %s; run git worktree prune" % work, file=sys.stderr)


def pr_inputs(path, repo, number):
    """(head, base) SHAs for the PR, verified against the checkout and fetched from the PR's own repository."""
    import project_tier
    pr = json.loads(gh("pr", "view", str(number), "-R", repo, "--json",
                       "headRefOid,baseRefName,state,isCrossRepository,author"))
    head = pr["headRefOid"]
    if pr["state"] != "OPEN":
        raise SetupError("PR #%d is not open" % number)
    if pr.get("isCrossRepository") is not False:
        raise SetupError("PR #%d comes from another repository; local CI runs only same-repository PRs" % number)
    author = (pr.get("author") or {}).get("login") or ""
    permission = gh("api", "repos/%s/collaborators/%s/permission" % (repo, quote(author, safe="")),
                    "--jq", ".permission").strip() if author else ""
    if permission not in ("admin", "maintain", "write"):
        raise SetupError("PR #%d's author cannot push to %s; local CI runs only their own team's code" % (number, repo))
    local = git(path, "rev-parse", "HEAD")
    if local != head:
        raise SetupError("PR head %s is not the checkout's HEAD %s; push or check out the PR head" % (head[:12], local[:12]))
    origin = project_tier.identity(git(path, "remote", "get-url", "origin")) or ""
    if origin.lower() != repo.lower():
        raise SetupError("origin is %s, not %s; run CI from a checkout of the PR's repository" % (origin or "?", repo))
    base = base_tip(repo, pr["baseRefName"])
    git(path, "fetch", "--quiet", "origin", pr["baseRefName"])
    if git(path, "rev-parse", "FETCH_HEAD") != base:
        raise SetupError("fetched %s is not GitHub's current %s; fetch again" % (pr["baseRefName"], base[:12]))
    return head, base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", required=True, help="clean checkout at the head to test")
    parser.add_argument("--repo", help="OWNER/NAME, with --pr")
    parser.add_argument("--pr", type=int, help="post the result on this PR")
    parser.add_argument("--runner", help="provider/model of the agent running CI, with --pr")
    parser.add_argument("--base", help="without --pr only: combine with this ref first")
    parser.add_argument("--script", help="without --pr only: CI script relative to the repo root (default: %s)"
                        % " or ".join(SCRIPTS))
    args = parser.parse_args(argv)
    if bool(args.repo) != bool(args.pr) or (args.pr and not IDENTITY.match((args.runner or "").lower())):
        parser.error("--repo and --pr go together, and --pr needs --runner provider/model")
    if args.pr and (args.base or args.script):
        parser.error("--base and --script are for unrecorded runs; with --pr the record names exactly what ran")
    try:
        if git(args.path, "status", "--porcelain", "--untracked-files=no"):
            raise SetupError("the checkout has uncommitted changes; commit them, CI runs on the committed head")
        if args.pr:
            head, base = pr_inputs(args.path, args.repo, args.pr)
        else:
            head = git(args.path, "rev-parse", "HEAD")
            base = git(args.path, "rev-parse", args.base + "^{commit}") if args.base else ""
        passed = run(args.path, head, base, args.script)
        if args.pr:
            gh("pr", "comment", str(args.pr), "-R", args.repo, "-b", record(passed, head, args.runner.lower(), base))
            print("RECORDED on %s#%d: %s" % (args.repo, args.pr, "pass" if passed else "fail"))
    except (SetupError, OSError, ValueError, KeyError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
