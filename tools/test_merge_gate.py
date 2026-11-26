"""merge_gate.evaluate and merge_guard on fixed PR objects; no network, no gh."""
import io
import json
import unittest
from unittest import mock

import merge_gate as mg
import merge_guard as guard

HEAD = "0123456789abcdef0123456789abcdef01234567"
BASE = "89abcdef0123456789abcdef0123456789abcdef"


def comment(text, at="2026-11-02T10:00:00Z"):
    return {"body": text, "createdAt": at}


def record(level="R1", verdict="approve", head=HEAD, reviewer="anthropic/claude-opus-5-5", session="s1", lens=None):
    line = "Patstack-Review: level=%s verdict=%s head=%s reviewer=%s session=%s" % (level, verdict, head, reviewer, session)
    return line + (" lens=%s" % lens if lens else "")


def pr(body="Mode: Full Send — copy only; R1; a revert undoes it.", comments=(), checks=None, **extra):
    base = {"number": 7, "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE", "headRefOid": HEAD,
            "baseRefName": "main", "baseTip": BASE, "body": body, "comments": list(comments),
            "statusCheckRollup": checks if checks is not None else
            [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
    base.update(extra)
    return base


def ref_answer(args):
    """GitHub's answer for a branch lookup in the fakes below, or None for any other call."""
    if args[0] == "api" and "/git/ref/heads/" in args[1]:
        return json.dumps({"ref": "refs/heads/main", "object": {"sha": BASE}})
    return None


STOP = "Mode: Full Stop — deletes old drafts; R2.\nPatstack-Author: anthropic/claude-opus-5-5"


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
        for prefix in ("Mode: ", "  patstack-author: ", "Patstack-Level: "):
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
        self.assertIn("Patstack-Author", reasons)

    def test_r3_needs_two_providers(self):
        one = [comment(record("R3", reviewer="openai/gpt-6.1-sol", session="a"))]
        two = one + [comment(record("R3", reviewer="anthropic/claude-opus-5-5", session="b"))]
        body = "Mode: Full Stop — broad auth change; R3.\nPatstack-Author: anthropic/claude-opus-5-5\nPatstack-Level: R3"
        self.assertFalse(self.ready(pr(body=body, comments=one)))
        self.assertTrue(self.ready(pr(body=body, comments=two)))

    def test_same_provider_r2_counts_only_under_a_reviewer_lens(self):
        plain = pr(body=STOP, comments=[comment(record("R2", reviewer="anthropic/claude-opus-5-5", session="r"))])
        self.assertIn("needs at least R2", self.reasons(plain))
        for lens in ("independent", "adversary"):
            lensed = pr(body=STOP, comments=[comment(record("R2", reviewer="anthropic/claude-sonnet-5-5", session="r", lens=lens))])
            self.assertTrue(self.ready(lensed), lens)
        unknown = pr(body=STOP, comments=[comment(record("R2", reviewer="anthropic/claude-opus-5-5", session="r", lens="friendly"))])
        self.assertFalse(self.ready(unknown))  # only the shipped prompts count; the record is ignored
        twice = pr(body=STOP, comments=[comment(record("R2", session="r", lens="independent") + " lens=adversary")])
        self.assertFalse(self.ready(twice))

    def test_single_provider_r3_needs_both_lenses(self):
        body = "Mode: Full Stop — broad auth change; R3.\nPatstack-Author: openai/gpt-6.1-sol\nPatstack-Level: R3"
        one = [comment(record("R3", reviewer="openai/gpt-6.1-sol", session="a", lens="independent"))]
        same_lens = one + [comment(record("R3", reviewer="openai/gpt-6-astra", session="b", lens="independent"))]
        both = one + [comment(record("R3", reviewer="openai/gpt-6-astra", session="b", lens="adversary"))]
        unlensed = one + [comment(record("R3", reviewer="openai/gpt-6-astra", session="b"))]
        self.assertFalse(self.ready(pr(body=body, comments=one)))
        self.assertFalse(self.ready(pr(body=body, comments=same_lens)))
        self.assertFalse(self.ready(pr(body=body, comments=unlensed)))  # the author's provider without a lens is not independent
        self.assertTrue(self.ready(pr(body=body, comments=both)))
        mixed = one + [comment(record("R3", reviewer="anthropic/claude-opus-5-5", session="c"))]
        self.assertTrue(self.ready(pr(body=body, comments=mixed)))  # another provider still counts as before

    def test_r3_needs_two_sessions_on_either_path(self):
        body = "Mode: Full Stop — broad auth change; R3.\nPatstack-Author: anthropic/claude-opus-5-5\nPatstack-Level: R3"
        lenses = [comment(record("R3", reviewer="anthropic/claude-opus-5-5", session="same", lens="independent")),
                  comment(record("R3", reviewer="anthropic/claude-sonnet-5-5", session="same", lens="adversary"))]
        self.assertFalse(self.ready(pr(body=body, comments=lenses)))  # one session switching model names is one side
        providers = [comment(record("R3", reviewer="anthropic/claude-opus-5-5", session="same")),
                     comment(record("R3", reviewer="openai/gpt-6.1-sol", session="same"))]
        self.assertFalse(self.ready(pr(body=body, comments=providers)))

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
        self.assertIn("Patstack-Author", self.reasons(pr(body="Mode: Full Stop — broad; R3.", comments=two)))

    def test_duplicate_author_line_counts_as_missing(self):
        body = STOP + "\nPatstack-Author: openai/gpt-6.1-sol"
        self.assertFalse(self.ready(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])))

    def test_duplicate_or_malformed_level_blocks(self):
        two = "Mode: Full Send — x; R1.\nPatstack-Level: R2\nPatstack-Level: R2"
        bad = "Mode: Full Send — x; R1.\nPatstack-Level: R4"
        self.assertIn("Patstack-Level", self.reasons(pr(body=two, comments=[comment(record())])))
        self.assertIn("Patstack-Level", self.reasons(pr(body=bad, comments=[comment(record())])))

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
        body = "Mode: Full Send — auth fix; R2.\nPatstack-Author: anthropic/claude-opus-5-5\nPatstack-Level: R2"
        self.assertIn("needs at least R2", self.reasons(pr(body=body, comments=[comment(record("R1"))])))
        self.assertTrue(self.ready(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])))

    # A repair after R2 needs R1 on the new head (Full Send, declared R2), not a second independent round.
    R2_BODY = "Mode: Full Send — auth fix; R2.\nPatstack-Author: anthropic/claude-opus-5-5\nPatstack-Level: R2"
    OLD = "aaaaaaaaaaaabbbbbbbbbbbbccccccccccccdddd"
    MID = "eeeeeeeeeeeeffffffffffff0000000000001111"

    def repaired(self, reviewed=None, repair=None, body=None, commits=None, more=()):
        reviewed = reviewed or record("R2", verdict="block", head=self.OLD, reviewer="openai/gpt-6.1-sol", session="rev")
        repair = repair or record("R1", session="lead") + " repairs=" + self.OLD[:12]
        commits = [{"oid": oid} for oid in (commits if commits is not None else [self.OLD, HEAD])]
        return pr(body=body or self.R2_BODY, commits=commits,
                  comments=[comment(reviewed, "2026-11-02T10:00:00Z"), *more, comment(repair, "2026-11-02T11:00:00Z")])

    def test_repair_of_an_r2_reviewed_head_needs_only_the_authors_r1(self):
        self.assertTrue(self.ready(self.repaired()))  # the review blocked; the author repaired and checked
        approve = record("R2", head=self.OLD, reviewer="openai/gpt-6.1-sol", session="rev")
        self.assertTrue(self.ready(self.repaired(reviewed=approve)))  # approved, then the base branch was brought in
        lens = record("R2", verdict="block", head=self.OLD, session="rev", lens="adversary")
        self.assertTrue(self.ready(self.repaired(reviewed=lens)))  # same provider under a reviewer lens
        self.assertEqual(mg.evaluate(self.repaired())[2]["review"], "R2")
        self.assertEqual(mg.evaluate(self.repaired())[2]["repair_of"], self.OLD)

    def test_plain_r1_on_a_new_head_still_does_not_reach_r2(self):
        plain = self.repaired(repair=record("R1", session="lead"))
        self.assertIn("needs at least R2", self.reasons(plain))

    def test_reviewer_can_require_its_own_recheck(self):
        marked = record("R2", verdict="block", head=self.OLD, reviewer="openai/gpt-6.1-sol", session="rev") + " recheck=independent"
        reasons = self.reasons(self.repaired(reviewed=marked))
        self.assertIn("recheck=independent", reasons)
        self.assertIn("needs at least R2", reasons)
        # one reviewer session asking for it is enough, whatever another session on that head says
        other = comment(record("R2", head=self.OLD, reviewer="openai/gpt-6.1-sol", session="rev2"), "2026-11-02T10:30:00Z")
        self.assertFalse(self.ready(self.repaired(reviewed=marked, more=[other])))
        fresh = comment(record("R2", reviewer="openai/gpt-6.1-sol", session="rev3"), "2026-11-02T12:00:00Z")
        self.assertTrue(self.ready(self.repaired(reviewed=marked, more=[fresh])))  # the fresh review itself still counts

    def test_repair_record_must_come_from_the_declared_author_and_name_a_reviewed_head_of_this_pr(self):
        other_author = record("R1", reviewer="anthropic/claude-fable-5-2", session="lead") + " repairs=" + self.OLD[:12]
        self.assertIn("declared author", self.reasons(self.repaired(repair=other_author)))
        gone = self.repaired(commits=[self.MID, HEAD])  # the reviewed head was force-pushed away
        self.assertIn("not a commit of this PR", self.reasons(gone))
        unreviewed = record("R1", session="lead") + " repairs=" + self.MID[:12]
        self.assertIn("no independent R2", self.reasons(self.repaired(repair=unreviewed, commits=[self.OLD, self.MID, HEAD])))
        own = record("R2", verdict="approve", head=self.OLD, session="rev")  # the author's provider, no lens
        self.assertIn("no independent R2", self.reasons(self.repaired(reviewed=own)))
        short = record("R1", session="lead") + " repairs=" + self.OLD[:8]
        self.assertIn("needs at least R2", self.reasons(self.repaired(repair=short)))
        same = record("R1", session="lead") + " repairs=" + HEAD[:12]
        self.assertFalse(self.ready(self.repaired(repair=same)))

    def test_incomplete_commit_history_never_supports_a_repair(self):
        # GitHub's CLI returns at most the first 100 commits; a later reviewed head could fall off the list.
        late = comment(record("R2", verdict="block", head=self.MID, reviewer="openai/gpt-6.1-sol", session="late")
                       + " recheck=independent", "2026-11-02T10:30:00Z")
        full = [self.OLD] + ["%040x" % number for number in range(1, 100)] + [self.MID, HEAD]
        self.assertFalse(self.ready(self.repaired(commits=full, more=[late])))
        cut = self.repaired(commits=full[:100], more=[late])
        self.assertIn("does not reach the head", self.reasons(cut))
        self.assertIn("does not reach the head", self.reasons(self.repaired(commits=[self.OLD])))
        self.assertIn("does not reach the head", self.reasons(self.repaired(commits=[HEAD, self.OLD])))
        self.assertIn("does not reach the head", self.reasons(self.repaired(commits=[])))

    def test_repair_record_is_an_r1_record(self):
        claimed = record("R2", session="lead") + " repairs=" + self.OLD[:12]  # the author cannot post R2 on its own work
        self.assertIn("needs at least R2", self.reasons(self.repaired(repair=claimed)))

    def test_repair_must_name_the_latest_reviewed_head(self):
        later = comment(record("R2", verdict="block", head=self.MID, reviewer="openai/gpt-6.1-sol", session="rev2"), "2026-11-02T10:30:00Z")
        stale = self.repaired(commits=[self.OLD, self.MID, HEAD], more=[later])
        self.assertIn("later head", self.reasons(stale))
        current = record("R1", session="lead") + " repairs=" + self.MID[:12]
        self.assertTrue(self.ready(self.repaired(repair=current, commits=[self.OLD, self.MID, HEAD], more=[later])))

    def test_full_stop_and_r3_keep_a_fresh_review_of_the_exact_head(self):
        stop = self.repaired(body=STOP)
        self.assertIn("Full Stop needs at least R2", self.reasons(stop))
        r3 = self.repaired(body=self.R2_BODY.replace("Patstack-Level: R2", "Patstack-Level: R3"))
        self.assertIn("needs at least R3", self.reasons(r3))

    def test_a_block_on_the_current_head_still_blocks_a_repair(self):
        block = comment(record("R2", verdict="block", reviewer="openai/gpt-6.1-sol", session="rev9"), "2026-11-02T12:00:00Z")
        self.assertIn("standing review block", self.reasons(self.repaired(more=[block])))

    def test_repair_and_recheck_fields_have_one_form(self):
        for bad in (" recheck=maybe", " repairs=nothex000000", " repairs=" + self.OLD[:12] + " repairs=" + self.OLD[:12]):
            line = record("R1", session="lead") + bad
            self.assertIsNone(mg.parse_record(line.split(":", 1)[1].strip()), bad)
        ok = mg.parse_record((record("R2", reviewer="openai/gpt-6.1-sol") + " recheck=independent").split(":", 1)[1].strip())
        self.assertEqual(ok["recheck"], "independent")

    def test_header_has_one_strict_form(self):
        c = [comment(record())]
        for body in ("**Mode: Full Send** — copy; R1", "Intro first.\n\nMode: Full Send — x",
                     "<pre><code>\nMode: Full Send — example\n</code></pre>", "`\nMode: Full Send — x\n`",
                     "Mode: Full Send — `code` here", " Mode: Full Send — indented"):
            self.assertFalse(self.ready(pr(body=body, comments=c)), body)
        self.assertTrue(self.ready(pr(body="\n\nMode: Full Send – copy; R1\n\n## Problem", comments=c)))

    def test_bare_carriage_return_cannot_hide_a_header_line(self):
        body = "Mode: Full Send — x; R1.\rPatstack-Author: anthropic/claude-opus-5-5\rPatstack-Level: R3"
        self.assertIn("needs at least R3", self.reasons(pr(body=body, comments=[comment(record())])))
        crlf = "Mode: Full Send — x\r\nPatstack-Level: R2"
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
        body = "Mode: Full Stop — x; R2.\n\nPatstack-Author: anthropic/claude-opus-5-5"
        self.assertIn("Patstack-Author", self.reasons(pr(body=body, comments=[comment(record("R2", reviewer="openai/gpt-6.1-sol"))])))

    def test_failed_and_pending_checks_block(self):
        failed = [{"__typename": "CheckRun", "name": "lint", "status": "COMPLETED", "conclusion": "FAILURE"}]
        pending = [{"__typename": "CheckRun", "name": "build", "status": "IN_PROGRESS", "conclusion": None}]
        status = [{"__typename": "StatusContext", "context": "ci/legacy", "state": "PENDING"}]
        self.assertIn("checks failed", self.reasons(pr(checks=failed, comments=[comment(record())])))
        self.assertIn("still running", self.reasons(pr(checks=pending, comments=[comment(record())])))
        self.assertIn("still running", self.reasons(pr(checks=status, comments=[comment(record())])))

    def ci_line(self, result="pass", head=HEAD, runner="anthropic/claude-opus-5-5", base=BASE):
        return "Patstack-CI: result=%s head=%s runner=%s base=%s" % (result, head, runner, base)

    def ci(self, line, at="2026-11-02T11:00:00Z", can_write=True):
        return dict(comment(line, at), canWrite=can_write)

    def local(self, *ci, **extra):
        return mg.evaluate(pr(comments=[comment(record())] + list(ci), **extra), local_ci=True)

    def test_local_ci_pass_record_replaces_github_checks(self):
        failed = [{"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": "FAILURE"}]
        for checks in (failed, []):
            ready, reasons, summary = self.local(self.ci(self.ci_line()), checks=checks)
            self.assertTrue(ready, reasons)
            self.assertEqual(summary["checks"], "local pass")

    def test_local_ci_record_must_match_head_and_current_base_exactly(self):
        cases = [("no local CI record", []),
                 ("local CI failed", [self.ci(self.ci_line("fail"))]),
                 ("no local CI record", [self.ci(self.ci_line(head="f" * 40))]),          # another head
                 ("no local CI record", [self.ci(self.ci_line(head=HEAD[:12]))]),         # prefix only
                 ("no local CI record", [self.ci(self.ci_line(base=BASE[:12]))]),         # short base
                 ("no local CI record", [self.ci(self.ci_line().rsplit(" base=", 1)[0])]),  # no base
                 ("is now at", [self.ci(self.ci_line(base="e" * 40))]),                   # base moved
                 ("no local CI record", [self.ci("Ran it.\n" + self.ci_line())]),         # buried in other text
                 ("no local CI record", [self.ci(self.ci_line(runner="nobody"))])]         # malformed runner
        for reason, ci in cases:
            self.assertIn(reason, " | ".join(self.local(*ci)[1]))

    def test_only_accounts_that_can_push_count(self):
        self.assertIn("no local CI record", " | ".join(self.local(self.ci(self.ci_line(), can_write=False))[1]))
        self.assertIn("no local CI record", " | ".join(self.local(comment(self.ci_line()))[1]))  # never looked up
        self.assertTrue(self.local(self.ci(self.ci_line()))[0])

    def test_fetch_marks_ci_records_by_the_authors_repo_permission(self):
        comments = [dict(comment(self.ci_line()), author={"login": login}) for login in ("writer", "reader", "gone")]
        comments.append(dict(comment("looks fine"), author={"login": "writer"}))
        lookups = []

        def fake(args):
            if args[:2] == ["pr", "view"]:
                return json.dumps(pr(comments=comments))
            if args[1].endswith("/git/ref/heads/main"):
                return json.dumps({"ref": "refs/heads/main", "object": {"sha": BASE}})
            lookups.append(args[1])
            login = args[1].split("/")[-2]
            if login == "gone":
                raise RuntimeError("gh: Not Found (HTTP 404)")
            return {"writer": "write", "reader": "read"}[login]
        with mock.patch.object(mg, "gh", fake):
            fetched = mg.fetch("o/r", 7)
        self.assertEqual([c.get("canWrite") for c in fetched["comments"]], [True, False, False, None])
        self.assertEqual(len(lookups), 3)  # one per author, only for CI records
        self.assertEqual(fetched["baseTip"], BASE)

    def test_branch_names_are_encoded_and_the_returned_ref_must_match(self):
        calls = []

        def fake(args):
            calls.append(args[1])
            return json.dumps({"ref": "refs/heads/main", "object": {"sha": BASE}})  # what an unencoded '#' gets
        with mock.patch.object(mg, "gh", fake), self.assertRaises(ValueError):
            mg.branch_tip("o/r", "main#review")
        self.assertEqual(calls, ["repos/o/r/git/ref/heads/main%23review"])
        with mock.patch.object(mg, "gh", fake):
            self.assertEqual(mg.branch_tip("o/r", "main"), BASE)

    def test_latest_local_ci_record_wins(self):
        self.assertIn("local CI failed", " | ".join(self.local(
            self.ci(self.ci_line("pass"), "2026-11-02T10:00:00Z"), self.ci(self.ci_line("fail"), "2026-11-02T11:00:00Z"))[1]))
        self.assertTrue(self.local(
            self.ci(self.ci_line("fail"), "2026-11-02T11:00:00Z"), self.ci(self.ci_line("pass"), "2026-11-02T12:00:00Z"))[0])

    def test_local_ci_keeps_every_other_rule(self):
        reasons = mg.evaluate(pr(comments=[self.ci(self.ci_line())]), local_ci=True)[1]
        self.assertIn("no approving review record", " | ".join(reasons))

    def test_without_checks_a_passing_record_stands_in_for_the_no_ci_line(self):
        self.assertIn("without CI", self.reasons(pr(checks=[], comments=[comment(record())])))
        self.assertTrue(self.ready(pr(checks=[], comments=[comment(record()), self.ci(self.ci_line())])))
        stale = self.ci(self.ci_line(base="e" * 40))
        self.assertIn("without CI", self.reasons(pr(checks=[], comments=[comment(record()), stale])))

    def test_local_ci_switches_on_only_when_the_base_holds_a_script(self):
        def gh_with(contents_error):
            def fake(args):
                if args[0] == "api" and "/contents/" in args[1]:
                    if contents_error:
                        raise RuntimeError(contents_error)
                    return ""
                return json.dumps({"ref": "refs/heads/main", "object": {"sha": BASE}})
            return fake
        with mock.patch.object(mg, "gh", gh_with("gh: Not Found (HTTP 404)")):
            self.assertFalse(mg.base_has_ci_script("o/r", BASE))
        with mock.patch.object(mg, "gh", gh_with(None)):
            self.assertTrue(mg.base_has_ci_script("o/r", BASE))
        for error in ("gh: Bad credentials (HTTP 401)", "error connecting to api.github.com"):
            with mock.patch.object(mg, "gh", gh_with(error)):
                self.assertTrue(mg.base_has_ci_script("o/r", BASE))  # unknown is strict

    def test_main_keeps_the_github_rule_for_a_listed_repo_without_a_script(self):
        no_script = pr(checks=[], comments=[comment(record())], body="Mode: Full Send — x; R1.\nno CI configured; proof is local only")

        def fake(args):
            if args[:2] == ["pr", "view"]:
                return json.dumps(no_script)
            if "/contents/" in args[1]:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            return json.dumps({"ref": "refs/heads/main", "object": {"sha": BASE}})
        with mock.patch.object(mg, "gh", fake), mock.patch.object(mg, "uses_local_ci", lambda repo: True), \
                mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(mg.main(["check", "--repo", "o/r", "--pr", "7"]), 0)

    def merge_run(self, tips, parent):
        ready = pr(checks=[], comments=[comment(record()), self.ci(self.ci_line())])
        calls = []
        tips = list(tips)

        def fake(args):
            calls.append(args)
            if args[:2] == ["pr", "view"]:
                return json.dumps({"mergeCommit": {"oid": "c" * 40}} if "mergeCommit" in args else ready)
            if "/git/ref/heads/" in args[1]:
                return json.dumps({"ref": "refs/heads/main", "object": {"sha": tips.pop(0)}})
            if "/contents/" in args[1] or "/permission" in args[1]:
                return "write"
            if "/commits/" in args[1]:
                return parent
            return ""
        err = io.StringIO()
        with mock.patch.object(mg, "gh", fake), mock.patch.object(mg, "uses_local_ci", lambda repo: True), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", err):
            code = mg.main(["merge", "--repo", "o/r", "--pr", "7"])
        return code, calls, err.getvalue()

    def test_local_ci_repos_never_rebase(self):
        ready = pr(checks=[], comments=[comment(record()), self.ci(self.ci_line())])
        calls = []

        def fake(args):
            calls.append(args)
            if args[:2] == ["pr", "view"]:
                return json.dumps(ready)
            if "/git/ref/heads/" in args[1]:
                return json.dumps({"ref": "refs/heads/main", "object": {"sha": BASE}})
            return "write"
        with mock.patch.object(mg, "gh", fake), mock.patch.object(mg, "uses_local_ci", lambda repo: True), \
                mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(mg.main(["merge", "--repo", "o/r", "--pr", "7", "--method", "rebase"]), 1)
        self.assertFalse(any(c[:2] == ["pr", "merge"] for c in calls))

    def test_merge_refuses_when_the_base_moves_during_the_check(self):
        code, calls, _ = self.merge_run([BASE, "e" * 40], BASE)
        self.assertEqual(code, 1)
        self.assertFalse(any(c[:2] == ["pr", "merge"] for c in calls))

    def test_merge_reports_a_base_that_moved_at_the_last_moment(self):
        code, _, err = self.merge_run([BASE, BASE], "e" * 40)
        self.assertEqual(code, 3)
        self.assertIn("merged tree is untested", err)
        self.assertEqual(self.merge_run([BASE, BASE], BASE)[0], 0)

    def test_github_checks_rule_applies_unless_the_map_lists_the_repo(self):
        data = {"owners": {}, "local_ci": ["example-consulting", "other/one-repo"]}
        with mock.patch("project_tier.load_tiers", return_value=(data, None)):
            self.assertTrue(mg.uses_local_ci("Example-Consulting/anything"))
            self.assertTrue(mg.uses_local_ci("other/one-repo"))
            self.assertFalse(mg.uses_local_ci("other/second-repo"))
        with mock.patch("project_tier.load_tiers", return_value=({}, "invalid tier map")):
            self.assertFalse(mg.uses_local_ci("example-consulting/anything"))
        with mock.patch("project_tier.load_tiers", side_effect=OSError("boom")):
            self.assertFalse(mg.uses_local_ci("example-consulting/anything"))

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
        bad = "Patstack-Review: level=R1 verdict=approve head=%s" % HEAD
        self.assertFalse(self.ready(pr(comments=[comment(bad)])))

    def test_merge_runs_gh_with_match_head_commit_only_when_ready(self):
        calls = []

        def fake(args):
            calls.append(args)
            if args[:2] == ["pr", "view"]:
                return json.dumps(pr(comments=[comment(record())]))
            return ref_answer(args) or ""
        with mock.patch.object(mg, "gh", fake), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(mg.main(["merge", "--repo", "o/r", "--pr", "7"]), 0)
        self.assertEqual(calls[-1], ["pr", "merge", "7", "-R", "o/r", "--merge", "--match-head-commit", HEAD])

    def test_full_stop_is_ready_on_check_but_a_human_merges(self):
        calls = []
        ready_stop = pr(body=STOP, comments=[comment(record(level="R2", reviewer="openai/gpt-6.1-sol"))])

        def fake(args):
            calls.append(args)
            return ref_answer(args) or json.dumps(ready_stop)
        out = io.StringIO()
        with mock.patch.object(mg, "gh", fake), mock.patch("sys.stdout", out):
            self.assertEqual(mg.main(["check", "--repo", "o/r", "--pr", "7"]), 0)
            self.assertEqual(mg.main(["merge", "--repo", "o/r", "--pr", "7"]), 1)
        self.assertTrue(all(args[:2] == ["pr", "view"] or args[:2] == ["api", "repos/o/r/git/ref/heads/main"] for args in calls))  # reads only, never a merge
        self.assertIn("a human merges", out.getvalue())
        self.assertIn("HANDOFF: Full Stop", out.getvalue())

    def test_merge_does_not_call_gh_merge_when_blocked(self):
        calls = []

        def fake(args):
            calls.append(args)
            return ref_answer(args) or json.dumps(pr())
        with mock.patch.object(mg, "gh", fake), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(mg.main(["merge", "--repo", "o/r", "--pr", "7"]), 1)
        self.assertTrue(all(args[:2] == ["pr", "view"] or args[:2] == ["api", "repos/o/r/git/ref/heads/main"] for args in calls))  # reads only, never a merge


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
                    "cd /srv/patstack && python3 tools/merge_gate.py check --repo o/r --pr 3",
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

    def raw(self, data):
        stdin = mock.Mock()
        stdin.buffer = io.BytesIO(data)
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()) as err:
            return guard.main(), err.getvalue()

    def test_unreadable_input_is_refused_not_waved_through(self):
        deep = b"[" * 10000 + b"0" + b"]" * 10000                 # exhausts the JSON parser's recursion
        for data in (b"", b"not json", b"[1, 2]", b'"text"', b"\xff\xfe", b'{"tool_input": "ls"}',
                     b'{"tool_input": {"command": 42}}', b'{"tool_input": false}', b'{"tool_input": []}',
                     b'{"tool_input": null}', b'{"tool_input": {"command": 0}}', b'{"tool_input": {"command": false}}',
                     b'{"tool_input": {"command": null}}', b'{"tool_input": {"command": {}}}',
                     b'{"tool_input": {"command": ["ls", 1]}}', b"0", b"null", deep):
            with self.subTest(data=data):
                code, err = self.raw(data)
                self.assertEqual(code, 2)
                self.assertIn("could not read", err)

    def test_a_stream_that_cannot_be_read_is_refused(self):
        stdin = mock.Mock()
        stdin.buffer.read.side_effect = OSError("gone")
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()) as err:
            self.assertEqual(guard.main(), 2)
        self.assertIn("could not read", err.getvalue())

    def test_events_without_a_command_and_list_commands_pass_or_block_normally(self):
        ok = lambda event: self.raw(json.dumps(event).encode())[0]
        self.assertEqual(ok({}), 0)                                                   # no tool_input at all
        self.assertEqual(ok({"tool_name": "Edit", "tool_input": {"file_path": "x"}}), 0)
        self.assertEqual(ok({"tool_input": {"command": ""}}), 0)
        self.assertEqual(ok({"tool_input": {"command": ["git", "status"]}}), 0)
        self.assertEqual(ok({"tool_input": {"command": ["gh", "pr", "mer" + "ge", "1"]}}), 2)

    def test_a_byte_order_mark_is_read(self):
        event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}).encode()
        self.assertEqual(self.raw(b"\xef\xbb\xbf" + event)[0], 0)
        self.assertEqual(self.raw(json.dumps({"tool_name": "Read", "tool_input": {}}).encode())[0], 0)  # no command

    def test_hook_exit_codes(self):
        def run(cmd):
            return self.raw(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}).encode())[0]
        self.assertEqual(run("gh pr merge 1"), 2)
        self.assertEqual(run("ls"), 0)


if __name__ == "__main__":
    unittest.main()
