#!/usr/bin/env python3
"""Merge a GitHub pull request only when DevStack's merge rule holds for its exact head.

  python3 tools/merge_gate.py check --repo OWNER/NAME --pr N [--json]
  python3 tools/merge_gate.py merge --repo OWNER/NAME --pr N [--method merge|squash|rebase]

Exit 0: ready (check) or merged (merge). Exit 1: blocked, with every reason listed.
Exit 2: usage error or GitHub could not be read.

The rule (skills/devstack/references/coordination.md#merge), read from GitHub for the current head:

- the PR is open, not a draft and has no conflicts;
- the body starts with its header: one mode line, `Mode: Full Send — …` or `Mode: Full Stop — …`,
  then optionally `DevStack-Author: <provider/model>` and `DevStack-Level: R1|R2|R3`, each once;
- the whole body is at most 200 words, so a person reads it;
- the review records on the PR cover the head at the mode's minimum depth:
  Full Send at least R1, Full Stop at least R2, or the higher `DevStack-Level` the header
  declares. A record is a PR comment whose whole body is this one line,
    DevStack-Review: level=R2 verdict=approve head=<sha> reviewer=<provider/model> session=<id>
  Identities are `provider/model`. R2 and R3 need the author header line; R2 needs a reviewer from another provider, R3 approvals from two providers. The latest record of a reviewer session
  replaces its earlier ones; a standing `verdict=block` blocks;
- every check on the head passed (success, neutral or skipped). With no checks at all, the body
  must say "no CI configured; proof is local only".

`merge` re-reads the PR, then merges with `gh pr merge --match-head-commit <head>`, so a push
after the check makes GitHub refuse the merge. All agents share one GitHub account, so records are
self-asserted: the gate proves a record exists for the head at the required depth with a declared
independent provider, not which session wrote it. Standard library only; it runs `gh` and nothing else.
"""
import argparse
import json
import re
import subprocess
import sys

LEVELS = {"R1": 1, "R2": 2, "R3": 3}
MINIMUM = {"Full Send": "R1", "Full Stop": "R2"}
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
NO_CI = "no CI configured; proof is local only"
MAX_BODY_WORDS = 200
FIELDS = "number,state,isDraft,mergeable,headRefOid,body,comments,statusCheckRollup"
RECORD_KEYS = {"level", "verdict", "head", "reviewer", "session"}

HEADER_MODE = re.compile(r"Mode: (Full Send|Full Stop) [—–-] [^`<>\x00-\x1f\x7f]*[^\s`<>\x00-\x1f\x7f]")
HEADER_AUTHOR = re.compile(r"DevStack-Author: (\S+)")
HEADER_LEVEL = re.compile(r"DevStack-Level: (R[123])")
HEADER_WORDS = ("mode:", "devstack-author:", "devstack-level:")
RECORD_COMMENT = re.compile(r"DevStack-Review:[ \t]+(\S.*?)[ \t]*")
TOKEN = re.compile(r"^(\w+)=(\S+)$")
IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$")


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
    by one `DevStack-Author: provider/model` and one `DevStack-Level: R1|R2|R3` line. Nothing else
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
        if key not in RECORD_KEYS or key in fields:
            return None
        fields[key] = value
    if set(fields) != RECORD_KEYS:
        return None
    level, verdict = fields["level"].upper(), fields["verdict"].lower()
    reviewer = identity(fields["reviewer"])
    if level not in LEVELS or verdict not in ("approve", "block") or not reviewer:
        return None
    return {"level": level, "verdict": verdict, "head": fields["head"].lower(),
            "reviewer": reviewer, "session": fields["session"]}


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


def buried_record(comments, head):
    """Whether a comment holds a record line for this head among other text. Diagnostic only: it never counts."""
    return any(line.startswith("DevStack-Review:") and head[:12].lower() in line.lower()
               for comment in comments or [] for line in newlines(comment.get("body")).split("\n"))


def review_depth(recs, author):
    """Highest depth the approvals establish. R2 and R3 need a declared author for independence."""
    approvals = [r for r in recs if r["verdict"] == "approve"]
    if author:
        if len({provider(r["reviewer"]) for r in approvals if r["level"] == "R3"}) >= 2:
            return 3
        if any(LEVELS[r["level"]] >= 2 and provider(r["reviewer"]) != provider(author) for r in approvals):
            return 2
    return 1 if approvals else 0


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


def evaluate(pr):
    """Return (ready, reasons, summary) for a `gh pr view --json` object."""
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
    if needed and depth < LEVELS[needed]:
        detail = "approvals for head %s reach R%d" % (head[:12], depth) if depth else \
            "no approving review record for head %s" % head[:12]
        if not depth and buried_record(pr.get("comments"), head):
            detail += "; a record must be a comment of its own: that one line and nothing else"
        if LEVELS[needed] >= 2 and not author:
            detail += "; R2/R3 also need a `DevStack-Author: <provider/model>` header line"
        reasons.append("%s needs at least %s before merge: %s" % (mode, needed, detail))

    state, names = checks_state(pr.get("statusCheckRollup"))
    if state == "failed":
        reasons.append("checks failed on the head: " + ", ".join(names))
    elif state == "pending":
        reasons.append("checks still running on the head: " + ", ".join(names))
    elif state == "none" and NO_CI.lower() not in body.lower():
        reasons.append('no checks on the head; a repo without CI must say "%s" in the body' % NO_CI)

    summary = {"pr": pr.get("number"), "head": head, "mode": mode, "minimum": needed,
               "review": "R%d" % depth if depth else None, "author": author or None,
               "records": recs, "checks": state, "mergeable": mergeable or None}
    return not reasons, reasons, summary


def gh(args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "gh failed")
    return result.stdout


def fetch(repo, number):
    return json.loads(gh(["pr", "view", str(number), "-R", repo, "--json", FIELDS]))


def report(ready, reasons, summary, as_json):
    if as_json:
        print(json.dumps({"ready": ready, "reasons": reasons, **summary}, indent=2))
        return
    print("PR #%s head %s: mode %s, minimum %s, review %s, checks %s" % (
        summary["pr"], (summary["head"] or "?")[:12], summary["mode"], summary["minimum"],
        summary["review"], summary["checks"]))
    for reason in reasons:
        print("BLOCKED: " + reason)
    if ready:
        print("READY: the merge rule holds for this head")


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
    ready, reasons, summary = evaluate(pr)
    report(ready, reasons, summary, args.json)
    if not ready:
        return 1
    if args.command == "check":
        return 0
    try:
        gh(["pr", "merge", str(args.pr), "-R", args.repo, "--" + args.method,
            "--match-head-commit", summary["head"]])
    except (RuntimeError, OSError) as exc:
        print("ERROR: GitHub refused the merge: %s" % exc, file=sys.stderr)
        return 2
    print("MERGED: PR #%s at %s" % (args.pr, summary["head"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
