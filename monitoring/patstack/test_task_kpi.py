"""task_kpi tests against a temporary KPI store; never the live one."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("task_kpi.py")
MONITOR = Path(__file__).with_name("kpi_monitor.py")


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

    def report(self):
        out = subprocess.run([sys.executable, str(MONITOR), "--db", str(self.db), "report"],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def start(self, task="TKT-1"):
        return self.run_cli("start", "--id", task, "--workflow", "feature", "--topic", "tastebuds",
                            "--mode", "full_send", "--host", "devbox")

    def test_start_then_verified_finish_counts_as_verified_completion(self):
        self.assertTrue(self.start()["recorded"])
        before = self.report()["overall"]["counts"]
        self.assertEqual(before["open"], 1)
        done = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes",
                            "--human-interventions", "0", "--handoff", "none", "--node", "unit-tests=pass",
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
        done = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "unknown")
        self.assertIsNone(done["verified_success"])
        self.assertEqual(self.report()["overall"]["task_completion_rate"]["missing"], 1)

    def test_finish_keeps_identity_and_start_is_idempotent(self):
        self.start()
        first = self.run_cli("show", "--id", "TKT-1")
        again = self.start()
        self.assertFalse(again["recorded"])
        self.run_cli("finish", "--id", "TKT-1", "--status", "failed", "--verified", "no")
        last = self.run_cli("show", "--id", "TKT-1")
        for key in ("started_at", "workflow", "host", "environment", "topic", "mode"):
            self.assertEqual(last[key], first[key], key)
        self.assertEqual((last["status"], last["verified_success"]), ("failed", False))

    def test_once_records_a_closed_unticketed_request(self):
        done = self.run_cli("once", "--id", "req-20261028-kpi", "--workflow", "discussion", "--topic", "patstack",
                            "--host", "devbox", "--started-at", "2026-10-28T09:00:00+00:00")
        self.assertEqual((done["status"], done["verified_success"]), ("completed", None))
        shown = self.run_cli("show", "--id", "req-20261028-kpi")
        self.assertEqual((shown["mode"], shown["started_at"], shown["handoff"]), ("other", "2026-10-28T09:00:00+00:00", "none"))
        self.assertIn("already recorded", self.run_cli("once", "--id", "req-20261028-kpi", "--workflow", "discussion",
                                                       "--topic", "patstack", "--host", "devbox", ok=False)["error"])
        self.run_cli("once", "--id", "req-2", "--workflow", "discussion", "--topic", "x", "--host", "devbox",
                     "--started-at", "2999-01-01T00:00:00+00:00", ok=False)  # start after end is rejected

    def test_repeated_finish_keeps_history_and_is_idempotent(self):
        self.start()
        first = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--handoff", "planned",
                             "--human-interventions", "1", "--node", "unit-tests=pass")
        ended = self.run_cli("show", "--id", "TKT-1")["ended_at"]
        retry = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes")
        self.assertEqual((first["revision"], retry["recorded"], retry["revision"]), (2, False, 2))
        later = self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "unknown",
                             "--node", "live-ui=pass")
        shown = self.run_cli("show", "--id", "TKT-1")
        self.assertEqual(later["revision"], 3)
        self.assertEqual((shown["ended_at"], shown["handoff"], shown["human_interventions"], shown["verified_success"]),
                         (ended, "planned", 1, True))

    def test_new_proof_nodes_merge_with_earlier_ones(self):
        self.start()
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--node", "unit=pass", "--node", "ui=not_run")
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes", "--node", "ui=pass", "--node", "ci=pass")
        nodes = {n["id"]: n["status"] for n in self.run_cli("show", "--id", "TKT-1")["nodes"]}
        self.assertEqual(nodes, {"unit": "pass", "ui": "pass", "ci": "pass"})

    def test_cli_never_echoes_free_text(self):
        for args in (["show", "--id", "private prose here"], ["finish", "--id", "TKT-1", "--status", "secret-word", "--verified", "yes"]):
            out = subprocess.run([sys.executable, str(SCRIPT), "--db", str(self.db), *args], capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)
            self.assertNotIn("private prose", out.stdout + out.stderr)
            self.assertNotIn("secret-word", out.stdout + out.stderr)

    def test_invalid_outcomes_are_rejected_by_the_recorder(self):
        self.assertIn("No start", self.run_cli("finish", "--id", "TKT-9", "--status", "completed",
                                               "--verified", "yes", ok=False)["error"])
        self.start()
        self.run_cli("finish", "--id", "TKT-1", "--status", "failed", "--verified", "yes", ok=False)  # verified needs completion
        self.run_cli("finish", "--id", "TKT-1", "--status", "completed", "--verified", "yes",
                     "--node", "x=maybe", ok=False)
        self.assertEqual(self.run_cli("show", "--id", "TKT-1")["revision"], 1)  # nothing half-written


if __name__ == "__main__":
    unittest.main()
