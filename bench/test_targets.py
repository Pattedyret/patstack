import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import targets as k  # noqa: E402


class TargetsTests(unittest.TestCase):
    """Owner-set bench targets and the hill-climb verdict."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def targets(self, data):
        path = self.dir / "targets.json"
        path.write_text(json.dumps(data))
        return path

    def test_evaluate_reports_pass_miss_unknown_and_the_gap(self):
        rows = k.evaluate({"kvalitet": 90, "security_holes_pct": 0, "median_minutes": 5.5},
                          {"kvalitet": ">=95", "security_holes_pct": "<=0", "median_minutes": "<= 4", "overall": ">=80"})
        self.assertEqual([(r["metric"], r["status"], r["gap"]) for r in rows],
                         [("kvalitet", "MISS", 5.0), ("security_holes_pct", "PASS", 0.0),
                          ("median_minutes", "MISS", 1.5), ("overall", "UNKNOWN", None)])
        self.assertEqual(rows[2]["target"], "<=4")

    def test_verdict_keeps_only_a_pareto_climb(self):
        specs = {"kvalitet": ">=95", "security_holes_pct": "<=0", "median_minutes": "<=4"}
        rows = lambda **values: k.evaluate(values, specs)
        base = rows(kvalitet=90, security_holes_pct=10, median_minutes=6)
        self.assertEqual(k.climb_verdict(base, rows(kvalitet=93, security_holes_pct=0, median_minutes=6))[0], "KEEP")
        self.assertEqual(k.climb_verdict(base, rows(kvalitet=96, security_holes_pct=0, median_minutes=3.5))[0], "TOP")
        self.assertEqual(k.climb_verdict(base, base)[0], "REVERT")  # no improvement is not a climb
        verdict, reason = k.climb_verdict(rows(kvalitet=93, security_holes_pct=0, median_minutes=6),
                                          rows(kvalitet=99, security_holes_pct=10, median_minutes=3))
        self.assertEqual((verdict, reason), ("REVERT", "worse: security_holes_pct"))
        # a missed security target cannot get worse in exchange for speed
        self.assertEqual(k.climb_verdict(rows(kvalitet=96, security_holes_pct=20, median_minutes=100),
                                         rows(kvalitet=96, security_holes_pct=30, median_minutes=5))[0], "REVERT")
        self.assertEqual(k.climb_verdict(base, rows(security_holes_pct=0, median_minutes=3))[0], "REVERT")  # unknown is never met
        # an unmeasured base proves nothing about a measured candidate
        self.assertEqual(k.climb_verdict(rows(security_holes_pct=0, median_minutes=3),
                                         rows(kvalitet=1, security_holes_pct=0, median_minutes=3))[0], "NOT COMPARABLE")
        self.assertEqual(k.climb_verdict(rows(median_minutes=3), rows(median_minutes=3))[0], "NOT COMPARABLE")

    def test_zero_tolerance_targets_compare_exact_values(self):
        self.assertEqual(k.evaluate({"security_holes_pct": 100 / 201}, {"security_holes_pct": "<=0"})[0]["status"], "MISS")
        self.assertEqual(k.evaluate({"security_holes_pct": 0.004}, {"security_holes_pct": "<=0"})[0]["status"], "MISS")

    def test_load_targets_rejects_unknown_metrics_and_bad_specs(self):
        self.assertIsNone(k.load_targets(self.dir / "missing.json"))
        for bad in ({"bench": {"speed": "<=4"}}, {"bench": {"overall": "90"}}, {"work": {"tasks": ">=1"}},
                    {"bench_arm": "../x"}, {"extra": 1}, {"bench": {"overall": ">= 1; rm"}},
                    {"bench": {"overall": ">=" + "9" * 400}}, {"bench": {"kpi_correct_pct": ">=90"}}):
            with self.assertRaises(ValueError, msg=bad):
                k.load_targets(self.targets(bad))
        loaded = k.load_targets(self.targets({"bench": {"overall": ">=90"}}))
        self.assertEqual(loaded, {"bench": {"overall": ">=90"}, "bench_arm": "patstack"})

    def test_example_file_is_valid(self):
        example = Path(__file__).resolve().parent.parent / "examples/bench-targets.example.json"
        self.assertTrue(k.load_targets(example)["bench"])


if __name__ == "__main__":
    unittest.main()
