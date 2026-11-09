"""changeset.py against a fake `gh` on PATH; no network, no real repositories."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = Path(__file__).with_name("changeset.py")
FAKE_GH = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    repo = args[args.index("--repo") + 1]
    data = json.load(open(os.environ["FAKE_GH_DATA"]))
    if repo not in data:
        sys.stderr.write("https://token@github.invalid/ failure\\n")
        sys.exit(1)
    print(json.dumps(data[repo]))
''')
OK = [{"conclusion": "SUCCESS", "status": "COMPLETED"}]


def pr(number, title, state="OPEN", merged=None, rollup=OK):
    return {"number": number, "title": title, "state": state, "mergedAt": merged, "url": f"https://github.invalid/pr/{number}",
            "isDraft": False, "headRefName": "tkt-42/x", "statusCheckRollup": rollup}


class ChangeSetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "bin").mkdir()
        gh = root / "bin/gh"
        gh.write_text(FAKE_GH.format(python=sys.executable))
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.data, self.log = root / "data.json", root / "log.jsonl"
        self.env = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ.get("PATH", ""),
                        FAKE_GH_DATA=str(self.data), FAKE_GH_LOG=str(self.log))

    def run_tool(self, data, *args):
        self.data.write_text(json.dumps(data))
        out = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=self.env)
        return out

    def report(self, data, *repos):
        out = self.run_tool(data, "TKT-42", *repos, "--json")
        return out.returncode, (json.loads(out.stdout) if out.stdout.strip() else None), out.stderr

    def test_declared_order_holds_and_set_is_complete(self):
        data = {"o/api": [pr(1, "[TKT-42] API", "MERGED", "2026-10-01T10:00:00Z")],
                "o/admin": [pr(7, "[TKT-42] Admin", "MERGED", "2026-10-01T12:00:00Z")],
                "o/web": [pr(9, "[TKT-42] Web", "MERGED", "2026-10-01T11:00:00Z"),
                          pr(10, "Follow-up to [TKT-42] in another title", "MERGED", "2026-09-01T11:00:00Z")]}
        code, report, _ = self.report(data, "o/api", "o/admin,o/web")
        self.assertEqual(code, 0)
        self.assertTrue(report["order_ok"] and report["complete"])
        self.assertEqual([p["number"] for p in report["repos"][2]["prs"]], [9])  # only titles that start with the prefix
        searched = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertTrue(all(call[:2] == ["pr", "list"] and "TKT-42 in:title" in call for call in searched))

    def test_consumer_merged_before_producer_is_a_violation(self):
        data = {"o/api": [pr(1, "[TKT-42] API", "MERGED", "2026-10-02T10:00:00Z")],
                "o/web": [pr(2, "[TKT-42] Web", "MERGED", "2026-10-01T10:00:00Z")]}
        code, report, _ = self.report(data, "o/api", "o/web")
        self.assertEqual(code, 1)
        self.assertFalse(report["order_ok"])
        self.assertIn("o/web (step 2) merged before o/api (step 1)", report["violations"][0])

    def test_consumer_merged_while_producer_is_open_is_a_violation(self):
        data = {"o/api": [pr(1, "[TKT-42] API")], "o/web": [pr(2, "[TKT-42] Web", "MERGED", "2026-10-01T10:00:00Z")]}
        code, report, _ = self.report(data, "o/api", "o/web")
        self.assertEqual(code, 1)
        self.assertIn("is not merged", report["violations"][0])
        self.assertFalse(report["complete"])

    def test_open_set_in_order_reports_state_checks_and_missing_ci(self):
        data = {"o/api": [pr(1, "[TKT-42] API", "MERGED", "2026-10-01T10:00:00Z")],
                "o/admin": [pr(3, "[TKT-42] Admin", rollup=[{"status": "IN_PROGRESS", "conclusion": None}])],
                "o/mobile": [pr(4, "[TKT-42] Mobile", rollup=[]), pr(5, "[TKT-42] Mobile again", rollup=[])],
                "o/web": []}
        code, report, _ = self.report(data, "o/api", "o/admin,o/mobile", "o/web")
        self.assertEqual(code, 0)
        states = {r["repo"]: r["state"] for r in report["repos"]}
        self.assertEqual(states, {"o/api": "merged", "o/admin": "open", "o/mobile": "open", "o/web": "missing"})
        self.assertEqual(report["repos"][1]["prs"][0]["checks"], "pending")
        notes = " ".join(report["notes"])
        self.assertIn("o/mobile: 2 open PRs", notes)
        self.assertIn("o/mobile: no CI checks reported; proof is local only", notes)
        self.assertFalse(report["complete"])

    def test_producer_merging_again_after_a_consumer_is_unresolved(self):
        # Reviewer probe: producer merges Oct 1 and Oct 3, consumer merges Oct 2.
        data = {"o/api": [pr(1, "[TKT-42] API", "MERGED", "2026-10-01T10:00:00Z"),
                          pr(3, "[TKT-42] API fix-forward", "MERGED", "2026-10-03T10:00:00Z")],
                "o/web": [pr(2, "[TKT-42] Web", "MERGED", "2026-10-02T10:00:00Z")]}
        code, report, _ = self.report(data, "o/api", "o/web")
        self.assertEqual(code, 1)
        self.assertFalse(report["order_ok"])
        self.assertEqual(report["violations"], [])
        self.assertIn("multi-PR ordering unresolved", report["unresolved"][0])
        self.assertEqual(report["repos"][0]["last_merged_at"], "2026-10-03T10:00:00+00:00")
        text = self.run_tool(data, "TKT-42", "o/api", "o/web")
        self.assertEqual(text.returncode, 1)
        self.assertIn("UNRESOLVED: multi-PR ordering unresolved", text.stdout)

    def test_all_producer_merges_before_the_consumer_is_ok(self):
        data = {"o/api": [pr(1, "[TKT-42] API", "MERGED", "2026-10-01T10:00:00Z"),
                          pr(3, "[TKT-42] API fix-forward", "MERGED", "2026-10-02T09:00:00Z")],
                "o/web": [pr(2, "[TKT-42] Web", "MERGED", "2026-10-02T10:00:00Z")]}
        code, report, _ = self.report(data, "o/api", "o/web")
        self.assertEqual((code, report["order_ok"], report["unresolved"]), (0, True, []))

    def test_open_producer_pr_after_a_consumer_merge_is_noted(self):
        data = {"o/api": [pr(1, "[TKT-42] API", "MERGED", "2026-10-01T10:00:00Z"), pr(3, "[TKT-42] API follow-up")],
                "o/web": [pr(2, "[TKT-42] Web", "MERGED", "2026-10-02T10:00:00Z")]}
        code, report, _ = self.report(data, "o/api", "o/web")
        self.assertEqual(code, 0)
        self.assertIn("o/api still has an open PR while o/web is merged", " ".join(report["notes"]))

    def test_failed_checks_are_reported(self):
        data = {"o/api": [pr(1, "[TKT-42] API", rollup=[{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}])]}
        code, report, _ = self.report(data, "o/api")
        self.assertEqual((code, report["repos"][0]["prs"][0]["checks"]), (0, "fail"))

    def test_gh_failure_exits_2_without_echoing_its_stderr(self):
        code, report, stderr = self.report({"o/api": []}, "o/api", "o/unknown")
        self.assertEqual(code, 2)
        self.assertIsNone(report)
        self.assertIn("o/unknown", stderr)
        self.assertNotIn("token", stderr)

    def test_usage_errors(self):
        for args in (["TKT-x", "o/api"], ["TKT-42", "not-a-repo"], ["TKT-42", "o/api", "o/api"]):
            with self.subTest(args=args):
                self.assertEqual(self.run_tool({}, *args).returncode, 2)

    def test_text_output_names_the_violation(self):
        data = {"o/api": [], "o/web": [pr(2, "[TKT-42] Web", "MERGED", "2026-10-01T10:00:00Z")]}
        out = self.run_tool(data, "TKT-42", "o/api", "o/web")
        self.assertEqual(out.returncode, 1)
        self.assertIn("order VIOLATED", out.stdout)
        self.assertIn("o/api: missing (no PR)", out.stdout)


if __name__ == "__main__":
    unittest.main()
