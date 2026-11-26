#!/usr/bin/env python3
"""Merge a GitHub pull request only when Patstack's merge rule holds for its exact head.

  python3 tools/merge_gate.py check --repo OWNER/NAME --pr N [--json]
  python3 tools/merge_gate.py merge --repo OWNER/NAME --pr N [--method merge|squash|rebase]

Exit 0: ready (check) or merged (merge). Exit 1: blocked, with every reason listed.
Exit 2: usage error or GitHub could not be read.

The rule (skills/patstack/references/coordination.md#merge), read from GitHub for the current head:

- the PR is open, not a draft and has no conflicts;
- the body starts with its header: one mode line, `Mode: Full Send — …` or `Mode: Full Stop — …`,
  then optionally `Patstack-Author: <provider/model>` and `Patstack-Level: R1|R2|R3`, each once;
- the whole body is at most 200 words, so a person reads it;
- the review records on the PR cover the head at the mode's minimum depth:
  Full Send at least R1, Full Stop at least R2, or the higher `Patstack-Level` the header
  declares. A record is a PR comment whose whole body is this one line,
    Patstack-Review: level=R2 verdict=approve head=<sha> reviewer=<provider/model> session=<id>
  with an optional `lens=independent|adversary` when the reviewer ran under one of the reviewer prompts in
  skills/review/references/lenses.md. Identities are `provider/model`. R2 and R3 need the author header
  line. R2 needs a reviewer from another provider, or one from the author's provider under a lens. R3 needs
  approvals from two sessions: two providers, or one provider under both lenses. The latest record of a reviewer session
  replaces its earlier ones; a standing `verdict=block` blocks;
- a repair after R2 needs R1, not a second independent round: in Full Send with a required depth of R2, the
  declared author's R1 record on the head with `repairs=<reviewed sha>` reaches R2 when that sha is an earlier
  commit of this PR, an independent R2 (or R3) record exists for it, it is the latest reviewed head, and no
  reviewer record on it says `recheck=independent`. A reviewer appends that field when a finding concerns
  security or another trust boundary. The commit list must end at the head (the CLI returns at most 100
  commits). Full Stop and R3 keep a fresh review of the exact head;
- every check on the head passed (success, neutral or skipped). With no checks at all, the body
  must say "no CI configured; proof is local only".
- a repo whose owner or OWNER/NAME the tier map lists under `local_ci` runs its CI in the agent instead:
  GitHub checks are ignored, and the latest local CI record for the head must pass on the base branch's
  current commit. tools/local_ci.py posts it as a comment whose whole body is this one line, full SHAs,
    Patstack-CI: result=pass head=<sha> runner=<provider/model> base=<sha>
  Only comments by accounts with write, maintain or admin permission on the repo count. A new commit on the
  base needs a new run. The rule switches on per repo once its base branch holds scripts/ci-local.sh or
  scripts/ci_local.py, so a listed repo without a script keeps the rule below until one lands; when
  GitHub cannot say, the script counts as present. An unreadable or invalid tier map keeps the GitHub checks rule, where a passing
  record for the current head and base also stands in for a repo with no checks.

In Full Stop a human merges: `check` reports whether the rule holds, and `merge` refuses a Full Stop PR
without calling GitHub, so the lead stops at the ready PR. `merge` re-reads the PR, then merges with `gh pr merge --match-head-commit <head>`, so a push
after the check makes GitHub refuse the merge. Agents post under their person's GitHub account, so records
are self-asserted: the gate proves a record exists for the head at the required depth with a declared
independent provider or reviewer prompt, not which session wrote it. Standard library only; it runs `gh` and nothing else.
"""
import argparse
import json
import re
import subprocess
import sys
from urllib.parse import quote

LEVELS = {"R1": 1, "R2": 2, "R3": 3}
MINIMUM = {"Full Send": "R1", "Full Stop": "R2"}
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
NO_CI = "no CI configured; proof is local only"
MAX_BODY_WORDS = 200
FIELDS = "number,state,isDraft,mergeable,headRefOid,baseRefName,body,comments,commits,statusCheckRollup"
RECORD_KEYS = {"level", "verdict", "head", "reviewer", "session"}
OPTIONAL_KEYS = {"lens", "repairs", "recheck"}
LENSES = {"independent", "adversary"}  # the reviewer prompts in skills/review/references/lenses.md

HEADER_MODE = re.compile(r"Mode: (Full Send|Full Stop) [—–-] [^`<>\x00-\x1f\x7f]*[^\s`<>\x00-\x1f\x7f]")
HEADER_AUTHOR = re.compile(r"Patstack-Author: (\S+)")
HEADER_LEVEL = re.compile(r"Patstack-Level: (R[123])")
HEADER_WORDS = ("mode:", "patstack-author:", "patstack-level:")
RECORD_COMMENT = re.compile(r"Patstack-Review:[ \t]+(\S.*?)[ \t]*")
CI_COMMENT = re.compile(r"Patstack-CI:[ \t]+(\S.*?)[ \t]*")
CI_KEYS = {"result", "head", "runner", "base"}
CI_SCRIPTS = ("scripts/ci-local.sh", "scripts/ci_local.py")  # what tools/local_ci.py runs
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
WRITE_PERMISSIONS = {"admin", "maintain", "write"}  # repo permissions that can push
TOKEN = re.compile(r"^(\w+)=(\S+)$")
IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$")
SHA = re.compile(r"^[0-9a-f]{12,40}$")


def identity(name):
    """Canonical 'provider/model' in lower case, or '' when it is not one."""
    name = (name or "").strip().lower()
    return name if IDENTITY.match(name) else ""


def provider(name):
    return name.split("/", 1)[0]


def newlines(text):
    """One line ending, so a bare CR can never hide a line inside another."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def header(body):
    """(mode, author, level, problems) from the header the body starts with.

    The first non-blank line is `Mode: Full Send — <why>` or `Mode: Full Stop — <why>` (the why is required), optionally followed
    by one `Patstack-Author: provider/model` and one `Patstack-Level: R1|R2|R3` line. Nothing else
    in the body declares anything, so an example in a code block, code span or HTML never counts."""
    lines = [line.rstrip() for line in newlines(body).lstrip("\n").split("\n")]
    match = HEADER_MODE.fullmatch(lines[0]) if lines else None
    if not match:
        problem = "the PR body must start with one mode line: `Mode: Full Send — …` or `Mode: Full Stop — …`"
        if lines and lines[0].startswith("Mode: ") and re.search(r"[`<>]", lines[0]):
            problem += "; the mode line cannot contain backticks or angle brackets"
        return None, "", "", [problem]
    mode = match.group(1)
    problems = []
    if ("full stop" if mode == "Full Send" else "full send") in lines[0].lower():
        problems.append("the mode line names both Full Send and Full Stop; choose one")
    author = level = None
    for line in lines[1:]:
        found_author, found_level = HEADER_AUTHOR.fullmatch(line), HEADER_LEVEL.fullmatch(line)
        if found_author and identity(found_author.group(1)) and author is None:
            author = identity(found_author.group(1))
        elif found_level and level is None:
            level = found_level.group(1)
        elif line.lower().startswith(HEADER_WORDS):
            problems.append("header line repeated or malformed: %r" % line[:60])
        else:
            break
    return mode, author or "", level or "", problems


def parse_record(text):
    """Fields of one record line, or None when a field is missing, unknown, repeated or malformed."""
    fields = {}
    for part in text.split():
        match = TOKEN.match(part.strip("`"))
        if not match:
            return None
        key, value = match.group(1).lower(), match.group(2)
        if key not in RECORD_KEYS | OPTIONAL_KEYS or key in fields:
            return None
        fields[key] = value
    if not RECORD_KEYS <= set(fields):
        return None
    lens = fields.get("lens", "").lower()
    if "lens" in fields and lens not in LENSES:
        return None
    repairs, recheck = fields.get("repairs", "").lower(), fields.get("recheck", "").lower()
    if "repairs" in fields and not SHA.match(repairs) or "recheck" in fields and recheck != "independent":
        return None
    level, verdict = fields["level"].upper(), fields["verdict"].lower()
    reviewer = identity(fields["reviewer"])
    if level not in LEVELS or verdict not in ("approve", "block") or not reviewer:
        return None
    return {"level": level, "verdict": verdict, "head": fields["head"].lower(),
            "reviewer": reviewer, "session": fields["session"], "lens": lens,
            "repairs": repairs, "recheck": recheck}


def records(comments, head):
    """Valid review records for this head, latest per reviewer session, in comment order.

    A record is a comment whose whole body is one record line, nothing else, so an example in a
    code block, a code span, a quote or HTML can never be one. A review summary is its own comment."""
    latest = {}
    for comment in sorted(comments or [], key=lambda c: c.get("createdAt") or ""):
        match = RECORD_COMMENT.fullmatch(newlines(comment.get("body")).strip("\n").rstrip())
        rec = parse_record(match.group(1)) if match else None
        if not rec or len(rec["head"]) < 12 or not head.lower().startswith(rec["head"]):
            continue
        latest[(rec["reviewer"], rec["session"])] = rec
    return list(latest.values())


def parse_ci(text):
    """Fields of one local CI record line, or None when a field is missing, unknown, repeated or malformed."""
    fields = {}
    for part in text.split():
        match = TOKEN.match(part)
        if not match or match.group(1).lower() not in CI_KEYS or match.group(1).lower() in fields:
            return None
        fields[match.group(1).lower()] = match.group(2)
    if set(fields) != CI_KEYS:
        return None
    result, head, base = fields["result"].lower(), fields["head"].lower(), fields["base"].lower()
    if result not in ("pass", "fail") or not FULL_SHA.match(head) or not FULL_SHA.match(base) \
            or not identity(fields["runner"]):
        return None
    return {"result": result, "head": head, "runner": identity(fields["runner"]), "base": base}


def local_ci_record(comments, head):
    """The latest well-formed local CI record for exactly this head from an account with write access,
    or None. A newer record replaces an older one."""
    latest = None
    for comment in sorted(comments or [], key=lambda c: c.get("createdAt") or ""):
        if comment.get("canWrite") is not True:  # set by fetch() from the author's repo permission
            continue
        match = CI_COMMENT.fullmatch(newlines(comment.get("body")).strip("\n").rstrip())
        rec = parse_ci(match.group(1)) if match else None
        if rec and rec["head"] == head.lower():
            latest = rec
    return latest


def local_ci_problem(pr, head):
    """None when the latest local CI record passed on this head and the base's current commit, else why not."""
    ci = local_ci_record(pr.get("comments"), head)
    base = (pr.get("baseTip") or "").lower()
    if not ci:
        return ("no local CI record for head %s; run python3 tools/local_ci.py --path <checkout> "
                "--repo OWNER/NAME --pr N --runner <provider/model>" % head[:12])
    if ci["result"] != "pass":
        return "local CI failed on head %s (%s)" % (head[:12], ci["runner"])
    if not base or ci["base"] != base:
        return ("local CI ran on base %s, but %s is now at %s; run tools/local_ci.py again"
                % (ci["base"][:12], pr.get("baseRefName") or "the base", base[:12] or "?"))
    return None


def buried_record(comments, head):
    """Whether a comment holds a record line for this head among other text. Diagnostic only: it never counts."""
    return any(line.startswith("Patstack-Review:") and head[:12].lower() in line.lower()
               for comment in comments or [] for line in newlines(comment.get("body")).split("\n"))


def review_depth(recs, author):
    """Highest depth the approvals establish. R2 and R3 need a declared author for independence."""
    approvals = [r for r in recs if r["verdict"] == "approve"]
    if author:
        council = [r for r in approvals if r["level"] == "R3"]
        # two sides from two different sessions: two providers, or one provider under the two reviewer prompts
        if any(a["session"] != b["session"] and (provider(a["reviewer"]) != provider(b["reviewer"])
                                                 or a["lens"] and b["lens"] and a["lens"] != b["lens"])
               for i, a in enumerate(council) for b in council[i + 1:]):
            return 3
        # R2: another provider, or the author's provider under a reviewer prompt (lens)
        if any(independent(r, author) for r in approvals):
            return 2
    return 1 if approvals else 0


def independent(rec, author):
    """An R2 or R3 record from another provider than the author, or from the author's provider under a lens."""
    return LEVELS[rec["level"]] >= 2 and (provider(rec["reviewer"]) != provider(author) or bool(rec["lens"]))


def repair_basis(pr, recs, author):
    """(reviewed head, problems) for an R1 repair record on the head that builds on an earlier R2.

    A repair after R2 needs the author's R1, not a second independent round. The author's approving R1
    record on the head names the reviewed head with `repairs=<sha>`. It stands in for R2 only when that
    sha is an earlier commit of this PR, an independent R2 or R3 record (either verdict) exists for it,
    no reviewer record on it says `recheck=independent`, and no later commit before the head has a review
    of its own. The commit list must end at the head: GitHub's CLI returns at most the first 100 commits,
    and a later reviewed head missing from a cut list must never go unseen. Without such a record this
    returns (None, [])."""
    head = (pr.get("headRefOid") or "").lower()
    oids = [(commit.get("oid") or "").lower() for commit in pr.get("commits") or []]
    comments = pr.get("comments")
    problems = []
    for claim in (r for r in recs if r["verdict"] == "approve" and r["repairs"] and r["level"] == "R1"):
        if not oids or oids[-1] != head:
            problems.append("the commit list GitHub returned does not reach the head (a PR with more than 100 "
                            "commits, or none listed), so an earlier review cannot be placed; get a fresh review")
            continue
        if not author or claim["reviewer"] != author:
            problems.append("a repair record counts only from the declared author (the `Patstack-Author` line)")
            continue
        found = [oid for oid in oids if oid.startswith(claim["repairs"]) and oid != head]
        if len(found) != 1:
            problems.append("repairs=%s is not a commit of this PR before the head" % claim["repairs"][:12])
            continue
        reviewed = found[0]
        basis = records(comments, reviewed)
        if not any(independent(r, author) for r in basis):
            problems.append("no independent R2 record for %s, the head the repair record names" % reviewed[:12])
        elif any(r["recheck"] for r in basis):
            problems.append("the reviewer of %s asked for its own re-check of the repair (recheck=independent)"
                            % reviewed[:12])
        else:
            later = [oid for oid in oids[oids.index(reviewed) + 1:]
                     if oid != head and any(LEVELS[r["level"]] >= 2 for r in records(comments, oid))]
            if later:
                problems.append("a later head %s has a review of its own; the repair record must name that one"
                                % later[-1][:12])
            else:
                return reviewed, []
    return None, problems


def checks_state(rollup):
    """('passed'|'none'|'pending'|'failed', names of the checks that are not passed)."""
    if not rollup:
        return "none", []
    pending, failed = [], []
    for item in rollup:
        name = item.get("name") or item.get("context") or "check"
        if item.get("__typename") == "StatusContext" or "state" in item and "conclusion" not in item:
            state = (item.get("state") or "").upper()
            if state in ("PENDING", "EXPECTED"):
                pending.append(name)
            elif state != "SUCCESS":
                failed.append(name)
            continue
        if (item.get("status") or "").upper() != "COMPLETED":
            pending.append(name)
        elif (item.get("conclusion") or "").upper() not in PASSED:
            failed.append(name)
    if failed:
        return "failed", failed
    if pending:
        return "pending", pending
    return "passed", []


def evaluate(pr, local_ci=False):
    """Return (ready, reasons, summary) for a `gh pr view --json` object.
    local_ci=True (a repo the tier map lists under local_ci) replaces GitHub checks with the local CI record."""
    reasons = []
    head = pr.get("headRefOid") or ""
    body = pr.get("body") or ""
    if (pr.get("state") or "").upper() != "OPEN":
        reasons.append("PR is not open")
    if pr.get("isDraft"):
        reasons.append("PR is a draft")
    mergeable = (pr.get("mergeable") or "").upper()
    if mergeable == "CONFLICTING":
        reasons.append("PR has merge conflicts")
    elif mergeable != "MERGEABLE":
        reasons.append("GitHub has not computed mergeability yet; run the gate again")

    mode, author, declared, problems = header(body)
    reasons.extend(problems)
    words = len(body.split())
    if words > MAX_BODY_WORDS:
        reasons.append("the PR body has %d words; the limit is %d. Move evidence and history "
                       "to a PR comment (skills/file-pr/SKILL.md), then run the gate again" % (words, MAX_BODY_WORDS))
    recs = records(pr.get("comments"), head) if head else []
    for r in recs:
        if r["verdict"] == "block":
            reasons.append("standing review block from %s (%s, session %s)" % (r["reviewer"], r["level"], r["session"]))
    depth = review_depth(recs, author)
    needed = None
    if mode:
        needed = max(MINIMUM[mode], declared or "R1", key=LEVELS.get)
    repair_of, repair_problems = None, []
    if mode == "Full Send" and needed == "R2" and depth == 1:
        repair_of, repair_problems = repair_basis(pr, recs, author)
        if repair_of:
            depth = 2
    if needed and depth < LEVELS[needed]:
        detail = "approvals for head %s reach R%d" % (head[:12], depth) if depth else \
            "no approving review record for head %s" % head[:12]
        if not depth and buried_record(pr.get("comments"), head):
            detail += "; a record must be a comment of its own: that one line and nothing else"
        if LEVELS[needed] >= 2 and not author:
            detail += "; R2/R3 also need a `Patstack-Author: <provider/model>` header line"
        if repair_problems:
            detail += "; the R1 repair record does not stand in for R2: " + "; ".join(repair_problems)
        reasons.append("%s needs at least %s before merge: %s" % (mode, needed, detail))

    if local_ci:
        problem = local_ci_problem(pr, head)
        state = "local " + ("pass" if not problem else "not passed")
        if problem:
            reasons.append(problem)
    else:
        state, names = checks_state(pr.get("statusCheckRollup"))
        if state == "failed":
            reasons.append("checks failed on the head: " + ", ".join(names))
        elif state == "pending":
            reasons.append("checks still running on the head: " + ", ".join(names))
        elif state == "none" and NO_CI.lower() not in body.lower() and local_ci_problem(pr, head):
            reasons.append('no checks on the head; a repo without CI must say "%s" in the body' % NO_CI)

    summary = {"pr": pr.get("number"), "head": head, "mode": mode, "minimum": needed,
               "review": "R%d" % depth if depth else None, "repair_of": repair_of, "author": author or None,
               "records": recs, "checks": state, "mergeable": mergeable or None}
    return not reasons, reasons, summary


def uses_local_ci(repo):
    """True only when the tier map lists the repo or its owner under local_ci; any error keeps GitHub checks."""
    try:
        import project_tier
        data, problem = project_tier.load_tiers()
        return problem is None and project_tier.local_ci(data, repo)
    except Exception:
        return False


def gh(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "gh failed")
    return result.stdout


def base_has_ci_script(repo, base):
    """Whether the base commit holds a local CI script. Only GitHub's 404 for every script means no;
    any other answer or error counts as yes, so a lookup problem never relaxes the rule."""
    for script in CI_SCRIPTS:
        try:
            gh(["api", "repos/%s/contents/%s?ref=%s" % (repo, script, base), "--silent"])
            return True
        except (RuntimeError, OSError) as exc:
            if "HTTP 404" not in str(exc):
                return True
    return False


def branch_tip(repo, branch):
    """The commit a branch points at on GitHub. The name is URL-encoded and the answer must name
    exactly that ref, so `main#x` can never resolve to `main`."""
    ref = "refs/heads/" + branch
    found = json.loads(gh(["api", "repos/%s/git/ref/heads/%s" % (repo, quote(branch, safe="/"))]))
    if not isinstance(found, dict) or found.get("ref") != ref or not FULL_SHA.match(found.get("object", {}).get("sha", "")):
        raise ValueError("GitHub did not return %s" % ref)
    return found["object"]["sha"]


def can_write(repo, login, cache):
    """Whether this account may push to the repo; any doubt is no."""
    if login not in cache:
        try:
            permission = gh(["api", "repos/%s/collaborators/%s/permission" % (repo, quote(login, safe="")),
                             "--jq", ".permission"]).strip()
        except (RuntimeError, OSError):
            permission = ""
        cache[login] = permission in WRITE_PERMISSIONS
    return cache[login]


def fetch(repo, number):
    pr = json.loads(gh(["pr", "view", str(number), "-R", repo, "--json", FIELDS]))
    pr["baseTip"] = branch_tip(repo, pr["baseRefName"])
    cache = {}
    for comment in pr.get("comments") or []:
        login = (comment.get("author") or {}).get("login") or ""
        if login and newlines(comment.get("body")).strip().startswith("Patstack-CI:"):
            comment["canWrite"] = can_write(repo, login, cache)
    return pr


def report(ready, reasons, summary, as_json):
    if as_json:
        print(json.dumps({"ready": ready, "reasons": reasons, **summary}, indent=2))
        return
    print("PR #%s head %s: mode %s, minimum %s, review %s, checks %s" % (
        summary["pr"], (summary["head"] or "?")[:12], summary["mode"], summary["minimum"],
        summary["review"], summary["checks"]))
    if summary.get("repair_of"):
        print("R2 holds through the author's R1 repair of reviewed head %s" % summary["repair_of"][:12])
    for reason in reasons:
        print("BLOCKED: " + reason)
    if ready:
        print("READY: the merge rule holds for this head" +
              ("; Full Stop: a human merges it" if summary["mode"] == "Full Stop" else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "merge"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True, help="OWNER/NAME")
        p.add_argument("--pr", required=True, type=int)
        p.add_argument("--json", action="store_true")
        if name == "merge":
            p.add_argument("--method", choices=("merge", "squash", "rebase"), default="merge")
    args = parser.parse_args(argv)
    try:
        pr = fetch(args.repo, args.pr)
    except (RuntimeError, ValueError, OSError) as exc:
        print("ERROR: could not read PR: %s" % exc, file=sys.stderr)
        return 2
    local = uses_local_ci(args.repo) and base_has_ci_script(args.repo, pr["baseTip"])
    ready, reasons, summary = evaluate(pr, local)
    report(ready, reasons, summary, args.json)
    if not ready:
        return 1
    if args.command == "check":
        return 0
    if summary["mode"] == "Full Stop":
        print("HANDOFF: Full Stop: a human merges this PR. Stop at the ready PR and hand it to the owner; "
              "the gate does not merge Full Stop")
        return 1
    if local and args.method == "rebase":
        print("BLOCKED: local CI tested the merge of the head into the base; a rebase lands other commits. "
              "Use --method merge or squash")
        return 1
    try:
        if local and branch_tip(args.repo, pr["baseRefName"]) != pr["baseTip"]:
            print("BLOCKED: %s moved while the gate checked it; run local CI again" % pr["baseRefName"])
            return 1
        gh(["pr", "merge", str(args.pr), "-R", args.repo, "--" + args.method,
            "--match-head-commit", summary["head"]])
    except (RuntimeError, OSError, ValueError) as exc:
        print("ERROR: GitHub refused the merge: %s" % exc, file=sys.stderr)
        return 2
    print("MERGED: PR #%s at %s" % (args.pr, summary["head"]))
    if local:
        return landed_on_tested_base(args.repo, args.pr, pr["baseTip"], pr["baseRefName"])
    return 0


def landed_on_tested_base(repo, number, tested, branch):
    """0 when the merge landed on the base local CI tested; 3, loudly, when the base moved in between.
    GitHub cannot merge on the condition that the base is unchanged, so this race is caught, not prevented."""
    try:
        merged = json.loads(gh(["pr", "view", str(number), "-R", repo, "--json", "mergeCommit"]))["mergeCommit"]["oid"]
        parent = gh(["api", "repos/%s/commits/%s" % (repo, merged), "--jq", ".parents[0].sha"]).strip()
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print("WARNING: could not confirm the merge landed on the tested base %s: %s" % (tested[:12], exc), file=sys.stderr)
        return 3
    if parent != tested:
        print("WARNING: %s moved to %s just before the merge; local CI tested %s, so the merged tree is untested. "
              "Run tools/local_ci.py on %s now." % (branch, parent[:12], tested[:12], branch), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
