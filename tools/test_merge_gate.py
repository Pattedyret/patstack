"""merge_gate.evaluate and merge_guard on fixed PR objects; no network, no gh."""
import io
import json
import unittest
from unittest import mock

import merge_gate as mg
import merge_guard as guard

HEAD = "0123456789abcdef0123456789abcdef01234567"


def comment(text, at="2026-11-02T10:00:00Z"):
    return {"body": text, "createdAt": at}


def record(level="R1", verdict="approve", head=HEAD, reviewer="anthropic/claude-opus-5-5", session="s1"):
    return "DevStack-Review: level=%s verdict=%s head=%s reviewer=%s session=%s" % (level, verdict, head, reviewer, session)


def pr(body="Mode: Full Send — copy only; R1; a revert undoes it.", comments=(), checks=None, **extra):
    base = {"number": 7, "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE", "headRefOid": HEAD,
            "body": body, "comments": list(comments),
            "statusCheckRollup": checks if checks is not None else
            [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
    base.update(extra)
    return base


STOP = "Mode: Full Stop — deletes old drafts; R2.\nDevStack-Author: anthropic/claude-opus-5-5"


class GateTests(unittest.TestCase):
    def ready(self, p):
        return mg.evaluate(p)[0]

    def reasons(self, p):
        return " | ".join(mg.evaluate(p)[1])

    def test_full_send_with_r1_on_head_and_green_checks_is_ready(self):
        self.assertTrue(self.ready(pr(comments=[comment(record())])))

    def test_body_at_the_word_limit_merges(self):
        head = "Mode: Full Send — copy; R1.\n\n"
        body = head + "word " * (mg.MAX_BODY_WORDS - len(head.split()))
        self.assertTrue(self.ready(pr(body=body, comments=[comment(record())])))

    def test_body_over_the_word_limit_blocks_and_says_where_the_text_goes(self):
        head = "Mode: Full Send — copy; R1.\n\n"
        body = head + "word " * (mg.MAX_BODY_WORDS + 1 - len(head.split()))
        reasons = self.reasons(pr(body=body, comments=[comment(record())]))
        self.assertIn("201 words", reasons)
        self.assertIn("PR comment", reasons)

    def test_header_like_paragraphs_count_toward_the_limit(self):
        for prefix in ("Mode: ", "  devstack-author: ", "DevStack-Level: "):
            body = "Mode: Full Send — copy; R1.\n\n" + prefix + "word " * 500
            self.assertIn("words; the limit", self.reasons(pr(body=body, comments=[comment(record())])))

    def test_a_long_mode_line_counts_toward_the_limit(self):
        body = "Mode: Full Send — %s\n\nShort." % " ".join(["why"] * 300)
        self.assertIn("words; the limit", self.reasons(pr(body=body, comments=[comment(record())])))

    def test_long_evidence_in_a_comment_does_not_count(self):
        long_comment = comment("evidence " * 2000)
        self.assertTrue(self.ready(pr(comments=[long_comment, comment(record())])))

    def test_no_review_record_blocks(self):
        self.assertIn("needs at least R1", self.reasons(pr()))

    def test_record_for_another_head_does_not_count(self):
        self.assertFalse(self.ready(pr(comments=[comment(record(head="ffffffffffff"))])))

    def test_short_head_prefix_is_refused(self):
        self.assertFalse(self.ready(pr(comments=[comment(record(head=HEAD[:7]))])))

    def test_twelve_character_prefix_counts(self):
        self.assertTrue(self.ready(pr(comments=[comment(record(head=HEAD[:12]))])))

    def test_full_stop_needs_independent_r2(self):
        same = pr(body=STOP, comments=[comment(record("R2", reviewer="anthropic/claude-opus-5-5"))])
        self.assertIn("needs at least R2", self.reasons(same))
        other = pr(body=STOP, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])
        self.assertTrue(self.ready(other))

    def test_full_stop_r1_is_not_enough(self):
        self.assertFalse(self.ready(pr(body=STOP, comments=[comment(record("R1"))])))

    def test_r2_without_author_line_is_not_independent(self):
        body = "Mode: Full Stop — irreversible; R2."
        reasons = self.reasons(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))]))
        self.assertIn("DevStack-Author", reasons)

    def test_r3_needs_two_providers(self):
        one = [comment(record("R3", reviewer="openai/gpt-6.1-sol", session="a"))]
        two = one + [comment(record("R3", reviewer="anthropic/claude-opus-5-5", session="b"))]
        body = "Mode: Full Stop — broad auth change; R3.\nDevStack-Author: anthropic/claude-opus-5-5\nDevStack-Level: R3"
        self.assertFalse(self.ready(pr(body=body, comments=one)))
        self.assertTrue(self.ready(pr(body=body, comments=two)))

    def test_standing_block_blocks_and_later_approve_from_same_session_clears(self):
        blocked = [comment(record("R2", "block", reviewer="openai/gpt-6.1-sol"), "2026-11-02T10:00:00Z")]
        self.assertIn("standing review block", self.reasons(pr(body=STOP, comments=blocked)))
        cleared = blocked + [comment(record("R2", "approve", reviewer="openai/gpt-6.1-sol"), "2026-11-02T11:00:00Z")]
        self.assertTrue(self.ready(pr(body=STOP, comments=cleared)))

    def test_block_from_other_session_still_blocks(self):
        comments = [comment(record("R2", "block", reviewer="openai/gpt-6.1-sol", session="a")),
                    comment(record("R2", "approve", reviewer="openai/gpt-6.1-sol", session="b"), "2026-11-02T11:00:00Z")]
        self.assertFalse(self.ready(pr(body=STOP, comments=comments)))

    def test_mode_line_in_comment_does_not_count(self):
        p = pr(body="No mode here", comments=[comment("Mode: Full Send — reclassified"), comment(record())])
        self.assertIn("must start", self.reasons(p))

    def test_two_mode_lines_are_refused_even_when_equal(self):
        c = [comment(record())]
        self.assertIn("repeated or malformed", self.reasons(pr(body="Mode: Full Send — a\nMode: Full Send — b", comments=c)))
        self.assertIn("repeated or malformed", self.reasons(pr(body="Mode: Full Send — a\nMode: Full Stop — b", comments=c)))

    def test_unfilled_template_mode_line_is_refused(self):
        self.assertIn("must start", self.reasons(pr(body="Mode: Full Send|Full Stop — <risk>", comments=[comment(record())])))
        self.assertIn("names both", self.reasons(pr(body="Mode: Full Send — not Full Stop", comments=[comment(record())])))

    def test_mode_line_inside_code_block_or_quote_does_not_count(self):
        c = [comment(record())]
        self.assertIn("must start", self.reasons(pr(body="```\nMode: Full Send — example\n```", comments=c)))
        self.assertIn("must start", self.reasons(pr(body="> Mode: Full Send — quoted", comments=c)))

    def test_record_inside_code_block_or_quote_does_not_count(self):
        fenced = "Example:\n```\n%s\n```" % record("R2", reviewer="openai/gpt-6.1-sol")
        quoted = "> " + record("R2", reviewer="openai/gpt-6.1-sol")
        self.assertFalse(self.ready(pr(body=STOP, comments=[comment(fenced)])))
        self.assertFalse(self.ready(pr(body=STOP, comments=[comment(quoted)])))

    def test_record_with_repeated_unknown_or_bare_fields_is_ignored(self):
        repeated = record("R2", reviewer="openai/gpt-6.1-sol") + " level=R3"
        unknown = record("R2", reviewer="openai/gpt-6.1-sol") + " note=x"
        bare = record("R2", reviewer="claude-opus-5-5")
        for text in (repeated, unknown, bare):
            self.assertFalse(self.ready(pr(body=STOP, comments=[comment(text)])), text)

    def test_r3_needs_the_author_line(self):
        two = [comment(record("R3", reviewer="openai/gpt-6.1-sol", session="a")),
               comment(record("R3", reviewer="anthropic/claude-opus-5-5", session="b"))]
        self.assertIn("DevStack-Author", self.reasons(pr(body="Mode: Full Stop — broad; R3.", comments=two)))

    def test_duplicate_author_line_counts_as_missing(self):
        body = STOP + "\nDevStack-Author: openai/gpt-6.1-sol"
        self.assertFalse(self.ready(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])))

    def test_duplicate_or_malformed_level_blocks(self):
        two = "Mode: Full Send — x; R1.\nDevStack-Level: R2\nDevStack-Level: R2"
        bad = "Mode: Full Send — x; R1.\nDevStack-Level: R4"
        self.assertIn("DevStack-Level", self.reasons(pr(body=two, comments=[comment(record())])))
        self.assertIn("DevStack-Level", self.reasons(pr(body=bad, comments=[comment(record())])))

    def test_markdown_examples_never_count(self):
        rec = record("R2", reviewer="openai/gpt-6.1-sol")
        for text in ("```\n%s\n````" % rec, "```\n%s" % rec, "> quoted\n%s" % rec,
                     "<!-- %s -->" % rec, "    %s" % rec, "~~~~\n%s\n~~~" % rec):
            self.assertFalse(self.ready(pr(body=STOP, comments=[comment(text)])), text)

    def test_record_must_be_its_own_one_line_comment(self):
        rec = record("R2", reviewer="openai/gpt-6.1-sol")
        for text in ("Summary of findings.\n\n" + rec, rec + "\nmore", "<pre><code>%s</code></pre>" % rec,
                     "`%s`" % rec, "**%s**" % rec, "- " + rec):
            self.assertFalse(self.ready(pr(body=STOP, comments=[comment(text)])), text)
        self.assertFalse(self.ready(pr(body=STOP, comments=[comment("  %s" % rec)])))
        self.assertTrue(self.ready(pr(body=STOP, comments=[comment("\n%s  \n" % rec)])))

    def test_declared_level_raises_the_full_send_floor(self):
        body = "Mode: Full Send — auth fix; R2.\nDevStack-Author: anthropic/claude-opus-5-5\nDevStack-Level: R2"
        self.assertIn("needs at least R2", self.reasons(pr(body=body, comments=[comment(record("R1"))])))
        self.assertTrue(self.ready(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])))

    def test_header_has_one_strict_form(self):
        c = [comment(record())]
        for body in ("**Mode: Full Send** — copy; R1", "Intro first.\n\nMode: Full Send — x",
                     "<pre><code>\nMode: Full Send — example\n</code></pre>", "`\nMode: Full Send — x\n`",
                     "Mode: Full Send — `code` here", " Mode: Full Send — indented"):
            self.assertFalse(self.ready(pr(body=body, comments=c)), body)
        self.assertTrue(self.ready(pr(body="\n\nMode: Full Send – copy; R1\n\n## Problem", comments=c)))

    def test_bare_carriage_return_cannot_hide_a_header_line(self):
        body = "Mode: Full Send — x; R1.\rDevStack-Author: anthropic/claude-opus-5-5\rDevStack-Level: R3"
        self.assertIn("needs at least R3", self.reasons(pr(body=body, comments=[comment(record())])))
        crlf = "Mode: Full Send — x\r\nDevStack-Level: R2"
        self.assertIn("needs at least R2", self.reasons(pr(body=crlf, comments=[comment(record())])))

    def test_backtick_in_mode_line_says_so_and_still_blocks(self):
        p = pr(body="Mode: Full Send — keeps `FLAG` off; R1.", comments=[comment(record())])
        self.assertIn("backticks", self.reasons(p))
        self.assertFalse(self.ready(p))

    def test_record_inside_a_longer_comment_says_so_and_still_blocks(self):
        p = pr(comments=[comment(record() + "\n\nReview summary follows.")])
        self.assertIn("comment of its own", self.reasons(p))
        self.assertFalse(self.ready(p))

    def test_record_for_another_head_gets_no_own_comment_hint(self):
        p = pr(comments=[comment(record(head="f" * 40) + "\n\nsummary")])
        self.assertNotIn("comment of its own", self.reasons(p))

    def test_mode_line_needs_its_reason(self):
        for body in ("Mode: Full Send", "Mode: Full Send — ", "Mode: Full Send —\tx", "Mode: Full Stop"):
            self.assertIn("must start", self.reasons(pr(body=body, comments=[comment(record())])), body)

    def test_declarations_after_the_header_do_not_count(self):
        body = "Mode: Full Stop — x; R2.\n\nDevStack-Author: anthropic/claude-opus-5-5"
        self.assertIn("DevStack-Author", self.reasons(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])))

    def test_failed_and_pending_checks_block(self):
        failed = [{"__typename": "CheckRun", "name": "lint", "status": "COMPLETED", "conclusion": "FAILURE"}]
        pending = [{"__typename": "CheckRun", "name": "build", "status": "IN_PROGRESS", "conclusion": None}]
        status = [{"__typename": "StatusContext", "context": "ci/legacy", "state": "PENDING"}]
        self.assertIn("checks failed", self.reasons(pr(checks=failed, comments=[comment(record())])))
        self.assertIn("still running", self.reasons(pr(checks=pending, comments=[comment(record())])))
        self.assertIn("still running", self.reasons(pr(checks=status, comments=[comment(record())])))

    def test_skipped_and_neutral_checks_pass(self):
        checks = [{"__typename": "CheckRun", "name": "a", "status": "COMPLETED", "conclusion": "SKIPPED"},
                  {"__typename": "CheckRun", "name": "b", "status": "COMPLETED", "conclusion": "NEUTRAL"},
                  {"__typename": "StatusContext", "context": "c", "state": "SUCCESS"}]
        self.assertTrue(self.ready(pr(checks=checks, comments=[comment(record())])))

    def test_no_checks_needs_the_no_ci_statement(self):
        self.assertIn("without CI", self.reasons(pr(checks=[], comments=[comment(record())])))
        body = "Mode: Full Send — tooling; R1.\nNo CI configured; proof is local only."
        self.assertTrue(self.ready(pr(body=body, checks=[], comments=[comment(record())])))

    def test_draft_closed_conflicting_and_unknown_block(self):
        c = [comment(record())]
        self.assertIn("draft", self.reasons(pr(isDraft=True, comments=c)))
        self.assertIn("not open", self.reasons(pr(state="MERGED", comments=c)))
        self.assertIn("conflicts", self.reasons(pr(mergeable="CONFLICTING", comments=c)))
        self.assertIn("mergeability", self.reasons(pr(mergeable="UNKNOWN", comments=c)))

    def test_incomplete_record_is_ignored(self):
        bad = "DevStack-Review: level=R1 verdict=approve head=%s" % HEAD
        self.assertFalse(self.ready(pr(comments=[comment(bad)])))

    def test_merge_runs_gh_with_match_head_commit_only_when_ready(self):
        calls = []

        def fake(args):
            calls.append(args)
            if args[:2] == ["pr", "view"]:
                return json.dumps(pr(comments=[comment(record())]))
            return ""
        with mock.patch.object(mg, "gh", fake), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(mg.main(["merge", "--repo", "o/r", "--pr", "7"]), 0)
        self.assertEqual(calls[-1], ["pr", "merge", "7", "-R", "o/r", "--merge", "--match-head-commit", HEAD])

    def test_merge_does_not_call_gh_merge_when_blocked(self):
        calls = []

        def fake(args):
            calls.append(args)
            return json.dumps(pr())
        with mock.patch.object(mg, "gh", fake), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(mg.main(["merge", "--repo", "o/r", "--pr", "7"]), 1)
        self.assertEqual(len(calls), 1)


class GuardTests(unittest.TestCase):
    def test_refuses_direct_merges_in_any_shell_form(self):
        for cmd in ("gh pr merge 12 --squash", "cd repo && gh pr merge 3", "sudo gh pr merge 1",
                    "env GH_TOKEN=x gh pr merge 4", "GH_REPO=o/r gh pr merge 1", "command gh pr merge 1",
                    "/usr/bin/gh pr merge 1", "x=$(gh pr merge 1)", "echo `gh pr merge 2`",
                    "bash -c 'gh pr merge 1'", 'sh -lc "cd r && gh pr merge 2"', "eval 'gh pr merge 3'",
                    "echo ok; GH_PR=1\ngh pr merge 9", "gh pr \\\nmerge 1", "time nohup gh pr merge 5",
                    "if true; then gh pr merge 27 --squash; fi", "! gh pr merge 1", "timeout 60 gh pr merge 1",
                    "echo 1 | xargs -I PR gh pr merge PR", "env -C /tmp gh pr merge 1",
                    "bash <<'EOF'\ngh pr merge 1\nEOF", "cat <<EOF\n$(gh pr merge 1)\nEOF",
                    'gh p""r merge 1', "gh pr m\\erge 1", "GH pr MERGE 1",
                    "gh api -X PUT repos/o/r/pulls/5/merge", "gh api --method PUT repos/o/r/pulls/5/merge",
                    'gh api "repos/o/r/pulls/5/merge" -X "PUT"', "gh api repos/o/r/pulls/5/merge --method=PUT",
                    "gh api -XPUT /repos/o/r/pulls/5/merge", "gh pr --repo o/r merge 27 --squash",
                    "gh pr -R o/r merge 1", "gh pr --repo=o/r merge 1", "gh pr -Ro/r merge 1",
                    "gh api -X PUT 'repos/o/r/pulls/5/merge?merge_method=squash'", "gh api repos/o/r/pulls/5/merge#x -X PUT",
                    "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"X\"}) { clientMutationId } }'",
                    "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {pullRequestId: \"X\"}) { clientMutationId } }'",
                    "gh api -X POST repos/o/r/merges -f base=main -f head=feature",
                    "gh.exe pr merge 27 --squash", 'GH.EXE pr merge 1', '"C:\\Program Files\\GitHub CLI\\gh.exe" pr merge 1',
                    "& 'C:/Program Files/GitHub CLI/gh.exe' pr merge 2",
                    "gh.exe api -X PUT repos/o/r/pulls/5/merge", "gh pr ^\r\n  merge 27 --squash",
                    "gh pr m^erge 1", "gh pr m`erge 1", "gh pr `\r\n  merge 1", "gh pr -- merge 1",
                    "gh pr 2>/dev/null merge 27 --squash", "gh pr >out.txt merge 1", "gh pr 2>&1 merge 1",
                    "gh pr mer\\\nge 27 --squash", "gh pr mer^\r\nge 1", "gh pr mer`\r\nge 1",
                    "g\\\nh pr merge 1", "gh p\\\nr merge 1", "gh api pulls/1/mer\\\nge -X PUT",
                    "gh api graphql -X POST --input /tmp/request.json", "gh api graphql -F query=@mutation.graphql",
                    "cat q.json | gh api graphql --input -", "gh api graphql -f query=@-",
                    'gh api graphql -f query="$(cat /tmp/request.graphql)"', "gh api graphql -f query=\"$Q\"",
                    "gh api graphql -f query='query { viewer { login } }'",
                    "gh api https://api.github.com/graphql --input /tmp/request.json", "gh api /graphql --input r.json"):
            self.assertTrue(guard.refused(cmd), cmd)

    def test_allows_the_gate_reads_and_unrelated_merges(self):
        for cmd in ("python3 tools/merge_gate.py merge --repo o/r --pr 3",
                    "cd /srv/devstack && python3 tools/merge_gate.py check --repo o/r --pr 3",
                    "gh pr view 3", "gh pr view 3 --json mergeable,state", "gh api repos/o/r/pulls/5",
                    "git fetch && git merge --ff-only origin/main && gh pr view 3",
                    "gh pr list --state merged",
                    "grep -n 'pr merge' README.md", "gh pr comment 3 --body-file /tmp/review.md"):
            self.assertFalse(guard.refused(cmd), cmd)

    def test_text_naming_gh_with_pr_merge_is_refused_by_design(self):
        for cmd in ("git commit -m 'never run gh pr merge directly'", "grep 'gh pr merge' notes.md",
                    "echo \"bash -c 'gh pr merge 27'\"", "gh api repos/o/r/pulls/5/merge",
                    "gh pr view 3 && git merge --ff-only origin/main"):
            self.assertTrue(guard.refused(cmd), cmd)

    def test_hook_exit_codes(self):
        def run(cmd):
            with mock.patch("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))), \
                    mock.patch("sys.stderr", io.StringIO()):
                return guard.main()
        self.assertEqual(run("gh pr merge 1"), 2)
        self.assertEqual(run("ls"), 0)


if __name__ == "__main__":
    unittest.main()
