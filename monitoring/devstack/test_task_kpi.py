"""task_kpi tests against a temporary KPI store; never the live one."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import task_kpi  # noqa: E402

SCRIPT = Path(__file__).with_name("task_kpi.py")
MONITOR = Path(__file__).with_name("kpi_monitor.py")


RULES = """
def claims(topic):
    return topic == "alpha-api"


def check(status, nodes):
    if status == "completed" and "proof" not in nodes:
        raise ValueError("needs proof")
"""


class PackRuleTests(unittest.TestCase):
    """How finish asks a pack: any pack, so this uses a throwaway one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "demo/tools").mkdir(parents=True)
        (self.root / "demo/tools/finish_rules.py").write_text(RULES, encoding="utf-8")

    def check(self, pack, topic="devstack", status="completed", nodes=()):
        task_kpi.check_pack(pack, topic, status, dict.fromkeys(nodes, "pass"), root=self.root)

    def test_the_pack_must_be_stated_on_every_finish(self):
        for status in ("completed", "cancelled"):
            with self.assertRaisesRegex(ValueError, "needs --pack"):
                self.check(None, status=status)

    def test_an_unknown_pack_lists_the_known_ones(self):
        with self.assertRaisesRegex(ValueError, "known: none, demo"):
            self.check("demox")

    def test_the_pack_judges_its_own_tasks(self):
        self.check("demo", nodes=("proof",))
        with self.assertRaisesRegex(ValueError, "needs proof"):
            self.check("demo")

    def test_none_is_refused_for_a_topic_a_pack_claims(self):
        self.check("none")
        with self.assertRaisesRegex(ValueError, "use --pack demo"):
            self.check("none", topic="alpha-api")
        with self.assertRaisesRegex(ValueError, "use --pack demo"):
            self.check("none", topic="alpha-api", status="cancelled")  # its nodes count in the rates too

    def test_a_copy_without_packs_accepts_none_only(self):
        empty = self.root / "absent"
        task_kpi.check_pack("none", "alpha-api", "completed", {}, root=empty)
        with self.assertRaisesRegex(ValueError, "known: none$"):
            task_kpi.check_pack("demo", "alpha-api", "completed", {}, root=empty)

    def test_loading_a_pack_leaves_no_bytecode(self):
        before = sys.dont_write_bytecode
        self.check("demo", nodes=("proof",))
        self.assertEqual(before, sys.dont_write_bytecode)
        self.assertFalse(list(self.root.rglob("__pycache__")))


class TaskKpiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "kpis.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, ok=True):
        out = subprocess.run([sys.executable, str(SCRIPT), "--db", str(self.db), *args], capture_output=True, text=True)
        self.assertEqual(out.returncode == 0, ok, out.stderr or out.stdout)
        return json.loads(out.stdout) if ok else json.loads(out.stderr)

    def test_finish_without_pack_says_what_is_missing_and_writes_nothing(self):
        self.run_cli("start", "--id", "TKT-1", "--workflow", "feature", "--topic", "devstack", "--mode", "full_send", "--host", "devbox")
        error = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", ok=False)
        self.assertIn("needs --pack", error["error"])
        self.assertEqual("open", self.run_cli("show", "--id", "TKT-1")["status"])

    def report(self):
        out = subprocess.run([sys.executable, str(MONITOR), "--db", str(self.db), "report"],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def start(self, task="TKT-1"):
        return self.run_cli("start", "--id", task, "--workflow", "feature", "--topic", "tastebuds",
                            "--mode", "full_send", "--host", "devbox")

    def test_finish_prints_the_scorecard_when_the_owner_set_targets(self):
        self.start()
        home = Path(self.tmp.name) / "home"
        (home / ".config/devstack").mkdir(parents=True)
        (home / ".config/devstack/kpi-targets.json").write_text(json.dumps({"work": {"verified_success_pct": ">=95", "tasks": ">=2"}, "min_samples": 1}))
        env = {**__import__("os").environ, "HOME": str(home), "USERPROFILE": str(home)}
        out = subprocess.run([sys.executable, str(SCRIPT), "--db", str(self.db), "finish", "--id", "TKT-1", "--status", "completed",
                              "--verified", "yes", "--handoff", "none", "--pack", "none"], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        json.loads(out.stdout)  # stdout stays the JSON snapshot
        self.assertIn("🎯 targets 1/2 met · MISS tasks 1 (>=2)", out.stderr)
        self.assertIn("PASS    verified_success_pct", out.stderr)
        self.assertIn("n=1", out.stderr)

    def test_finish_requires_an_explicit_handoff(self):
        # An unset handoff left unexpected_handoff_pct unknown for a whole week (retro 2026-11-02).
        self.start()
        out = subprocess.run([sys.executable, str(SCRIPT), "--db", str(self.db), "finish", "--id", "TKT-1",
                              "--status", "completed", "--verified", "yes"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("TKT-1", out.stdout)
        for value in ("none", "planned", "requested", "unexpected"):
            done = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", value, "--pack", "none")
            self.assertEqual(done["status"], "completed")

    def test_start_then_verified_finish_counts_as_verified_completion(self):
        self.assertTrue(self.start()["recorded"])
        before = self.report()["overall"]["counts"]
        self.assertEqual(before["open"], 1)
        done = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none",
                            "--human-interventions", "0", "--handoff", "none", "--pack", "none", "--node", "unit-tests=pass",
                            "--node", "live-ui=not_run")
        self.assertEqual((done["revision"], done["verified_success"]), (2, True))
        overall = self.report()["overall"]
        self.assertEqual(overall["counts"]["completed"], 1)
        self.assertEqual(overall["task_completion_rate"]["missing"], 0)
        self.assertEqual(overall["task_completion_rate"]["numerator"], 1)
        shown = self.run_cli("show", "--id", "TKT-1")
        self.assertEqual(shown["nodes"], [{"id": "unit-tests", "status": "pass"}, {"id": "live-ui", "status": "not_run"}])

    def test_unknown_verification_stays_missing_not_false(self):
        self.start()
        done = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "unknown", "--handoff", "none", "--pack", "none")
        self.assertIsNone(done["verified_success"])
        self.assertEqual(self.report()["overall"]["task_completion_rate"]["missing"], 1)

    def test_finish_keeps_identity_and_start_is_idempotent(self):
        self.start()
        first = self.run_cli("show", "--id", "TKT-1")
        again = self.start()
        self.assertFalse(again["recorded"])
        self.run_cli("finish", "--id", "TKT-1", "--status", "failed", "--verified", "no", "--handoff", "none", "--pack", "none")
        last = self.run_cli("show", "--id", "TKT-1")
        for key in ("started_at", "workflow", "host", "environment", "topic", "mode"):
            self.assertEqual(last[key], first[key], key)
        self.assertEqual((last["status"], last["verified_success"]), ("failed", False))

    def test_once_records_a_closed_unticketed_request(self):
        done = self.run_cli("once", "--id", "req-20261028-kpi", "--workflow", "discussion", "--topic", "devstack",
                            "--host", "devbox", "--started-at", "2026-10-28T09:00:00+00:00")
        self.assertEqual((done["status"], done["verified_success"]), ("completed", None))
        shown = self.run_cli("show", "--id", "req-20261028-kpi")
        self.assertEqual((shown["mode"], shown["started_at"], shown["handoff"]), ("other", "2026-10-28T09:00:00+00:00", "none"))
        self.assertIn("already recorded", self.run_cli("once", "--id", "req-20261028-kpi", "--workflow", "discussion",
                                                       "--topic", "devstack", "--host", "devbox", ok=False)["error"])
        self.run_cli("once", "--id", "req-2", "--workflow", "discussion", "--topic", "x", "--host", "devbox",
                     "--started-at", "2999-01-01T00:00:00+00:00", ok=False)  # start after end is rejected

    def test_unticketed_requests_never_count_as_missing_verification(self):
        self.run_cli("once", "--id", "req-a", "--workflow", "discussion", "--topic", "devstack", "--host", "devbox",
                     "--started-at", "2026-10-28T09:00:00+00:00")
        self.run_cli("once", "--id", "req-b", "--workflow", "question", "--topic", "devstack", "--host", "devbox",
                     "--started-at", "2026-10-28T09:00:00+00:00")  # any workflow name: the marker decides
        self.assertEqual("not_applicable", self.run_cli("show", "--id", "req-b")["verification"])
        self.assertEqual(0, self.report()["overall"]["verification_missing"])

    def test_a_designated_task_without_verification_still_counts(self):
        self.run_cli("start", "--id", "TKT-2", "--workflow", "research", "--topic", "devstack",
                     "--mode", "full_send", "--host", "devbox")  # a ticketed task, even with a once-style name
        self.run_cli("finish", "--id", "TKT-2", "--status", "completed", "--verified", "unknown", "--handoff", "none", "--pack", "none")
        self.assertEqual("required", self.run_cli("show", "--id", "TKT-2")["verification"])
        self.assertEqual(1, self.report()["overall"]["verification_missing"])

    def test_finishing_a_legacy_open_task_still_requires_verification(self):
        legacy = {"id": "TKT-legacy", "revision": 1, "workflow": "research", "topic": "devstack", "mode": "full_send",
                  "status": "open", "started_at": "2026-10-28T09:00:00+00:00",
                  "updated_at": "2026-10-28T09:00:00+00:00"}  # written before the marker existed
        subprocess.run([sys.executable, str(MONITOR), "--db", str(self.db), "record"], input=json.dumps(legacy),
                       text=True, check=True, capture_output=True)
        self.run_cli("finish", "--id", "TKT-legacy", "--status", "completed", "--verified", "unknown", "--handoff", "none", "--pack", "none")
        self.assertEqual("required", self.run_cli("show", "--id", "TKT-legacy")["verification"])
        self.assertEqual(1, self.report()["overall"]["verification_missing"])

    def test_old_snapshots_without_the_marker_use_the_workflow(self):
        for task, workflow in (("req-old", "research"), ("TKT-3", "bugfix")):
            row = {"id": task, "revision": 1, "workflow": workflow, "topic": "devstack", "mode": "other",
                   "status": "completed", "started_at": "2026-10-28T09:00:00+00:00",
                   "updated_at": "2026-10-28T10:00:00+00:00", "ended_at": "2026-10-28T10:00:00+00:00"}
            subprocess.run([sys.executable, str(MONITOR), "--db", str(self.db), "record"], input=json.dumps(row),
                           text=True, check=True, capture_output=True)
        self.assertEqual(1, self.report()["overall"]["verification_missing"])  # only the old bugfix task

    def test_repeated_finish_keeps_history_and_is_idempotent(self):
        self.start()
        first = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "planned", "--pack", "none",
                             "--human-interventions", "1", "--node", "unit-tests=pass")
        ended = self.run_cli("show", "--id", "TKT-1")["ended_at"]
        retry = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "planned", "--pack", "none")
        self.assertEqual((first["revision"], retry["recorded"], retry["revision"]), (2, False, 2))
        later = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "unknown", "--handoff", "planned", "--pack", "none",
                             "--node", "live-ui=pass")
        shown = self.run_cli("show", "--id", "TKT-1")
        self.assertEqual(later["revision"], 3)
        self.assertEqual((shown["ended_at"], shown["handoff"], shown["human_interventions"], shown["verified_success"]),
                         (ended, "planned", 1, True))

    def test_new_proof_nodes_merge_with_earlier_ones(self):
        self.start()
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", "--node", "unit=pass", "--node", "ui=not_run")
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", "--node", "ui=pass", "--node", "ci=pass")
        nodes = {n["id"]: n["status"] for n in self.run_cli("show", "--id", "TKT-1")["nodes"]}
        self.assertEqual(nodes, {"unit": "pass", "ui": "pass", "ci": "pass"})

    def test_finish_without_start_records_the_outcome(self):
        task = ["--workflow", "bugfix", "--topic", "orders", "--mode", "full_send", "--host", "devbox"]
        done = self.run_cli("finish", "--id", "TKT-7", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", *task,
                            "--started-at", "2026-10-28T10:00:00+00:00", "--node", "health=pass")
        self.assertEqual((done["revision"], done["verified_success"]), (2, True))
        shown = self.run_cli("show", "--id", "TKT-7")
        self.assertEqual((shown["status"], shown["started_at"], shown["nodes"]),
                         ("completed", "2026-10-28T10:00:00+00:00", [{"id": "health", "status": "pass"}]))
        # no invented start time
        self.assertIn("--started-at", self.run_cli("finish", "--id", "TKT-8", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", *task, ok=False)["error"])
        # invalid outcome or future start: nothing at all is written
        self.run_cli("finish", "--id", "TKT-9", "--status", "failed", "--verified", "yes", "--handoff", "none", "--pack", "none", *task, "--started-at", "2026-10-28T10:00:00+00:00", ok=False)
        self.run_cli("finish", "--id", "TKT-10", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", *task, "--started-at", "2999-01-01T00:00:00+00:00", ok=False)
        self.assertEqual(self.run_cli("show", "--id", "TKT-9"), {"missing": "TKT-9"})
        self.assertEqual(self.run_cli("show", "--id", "TKT-10"), {"missing": "TKT-10"})

    def test_cli_never_echoes_free_text(self):
        for args in (["show", "--id", "private prose here"], ["finish", "--id", "TKT-1", "--status", "secret-word", "--verified", "yes", "--handoff", "none", "--pack", "none"]):
            out = subprocess.run([sys.executable, str(SCRIPT), "--db", str(self.db), *args], capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)
            self.assertNotIn("private prose", out.stdout + out.stderr)
            self.assertNotIn("secret-word", out.stdout + out.stderr)

    def test_invalid_outcomes_are_rejected_by_the_recorder(self):
        self.assertIn("No start", self.run_cli("finish", "--id", "TKT-9", "--status", "completed",
                                               "--verified", "yes", "--handoff", "none", "--pack", "none", ok=False)["error"])
        self.start()
        self.run_cli("finish", "--id", "TKT-1", "--status", "failed", "--verified", "yes", "--handoff", "none", "--pack", "none", ok=False)  # verified needs completion
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none",
                     "--node", "x=maybe", ok=False)
        self.assertEqual(self.run_cli("show", "--id", "TKT-1")["revision"], 1)  # nothing half-written


    def test_slices_review_rounds_and_missing_ci_show_per_topic(self):
        self.start()
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", "--slices", "3",
                     "--review-rounds", "2", "--node", "ci=not_run")
        self.run_cli("start", "--id", "TKT-2", "--workflow", "bugfix", "--topic", "other-repo", "--mode", "full_send", "--host", "devbox")
        self.run_cli("finish", "--id", "TKT-2", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", "--slices", "1", "--node", "ci=pass")
        latest = self.run_cli("show", "--id", "TKT-1")
        self.assertEqual((latest["slices"], latest["review_rounds"]), (3, 2))
        topics = self.report()["by_topic"]
        self.assertEqual(topics["tastebuds"]["slices"]["mean"], 3)
        self.assertEqual(topics["tastebuds"]["review_rounds"]["median"], 2)
        self.assertEqual(topics["tastebuds"]["nodes"]["ci"]["not_run"], 1)
        self.assertEqual(topics["tastebuds"]["task_completion_rate"]["percent"], 100.0)
        self.assertEqual(topics["other-repo"]["review_rounds"]["missing"], 1)  # not recorded stays missing, never zero
        self.assertEqual(topics["other-repo"]["nodes"]["ci"]["pass"], 1)
        # A later finish without the flags keeps the earlier observations.
        again = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none")
        self.assertFalse(again["recorded"])

    def test_negative_observations_are_rejected(self):
        self.start()
        for flag in ("--slices", "--review-rounds"):
            with self.subTest(flag=flag):
                self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "none", "--pack", "none", flag, "-1", ok=False)
        self.assertEqual(self.run_cli("show", "--id", "TKT-1")["revision"], 1)

    def test_development_topic_is_a_repo_or_project_slug(self):
        for topic in ("General", "general", "misc", "my repo", "a" * 65):
            with self.subTest(topic=topic):
                error = self.run_cli("start", "--id", "TKT-3", "--workflow", "feature", "--topic", topic,
                                     "--mode", "full_send", "--host", "devbox", ok=False)
                self.assertIn("repo or project slug", error["error"])
        self.run_cli("start", "--id", "TKT-3", "--workflow", "feature", "--topic", "auth-api", "--mode", "full_send", "--host", "devbox")
        self.assertIn("topic=<repo-or-project-slug>", subprocess.run([sys.executable, str(SCRIPT), "start", "--help"],
                                                                     capture_output=True, text=True).stdout)


if __name__ == "__main__":
    unittest.main()
