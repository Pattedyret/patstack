"""Owner-set benchmark targets and the hill-climb verdict. Standard library only.

Targets live in ~/.config/patstack/bench-targets.json, shaped like examples/bench-targets.example.json:
{"bench": {"overall": ">=90", "security_holes_pct": "<=0"}, "bench_arm": "patstack"}.
"""
import json
import math
from pathlib import Path
import re

TARGETS = Path.home() / ".config/patstack/bench-targets.json"
BENCH_METRICS = ("overall", "resultat", "feller", "aerlighet", "sikkerhet", "kvalitet", "security_holes_pct",
                 "median_minutes", "median_cost_usd", "median_turns", "loaded_pct")
TARGET_SPEC = re.compile(r"^(>=|<=)\s*(-?\d+(?:\.\d+)?)$")
ARM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def load_targets(path=TARGETS):
    """The owner's targets, or None when no file is set. Invalid files raise ValueError."""
    path = Path(path).expanduser()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) - {"bench", "bench_arm"}:
        raise ValueError("Targets file keys: bench, bench_arm")
    specs = data.get("bench", {})
    if not isinstance(specs, dict):
        raise ValueError("bench must be an object of metric targets")
    unknown = [m for m in specs if m not in BENCH_METRICS]
    if unknown:
        raise ValueError(f"Unknown bench metric {', '.join(unknown)}; known: {', '.join(BENCH_METRICS)}")
    for spec in specs.values():
        match = TARGET_SPEC.match(spec.strip()) if isinstance(spec, str) else None
        if not match or not math.isfinite(float(match.group(2))):
            raise ValueError('A target is ">=N" or "<=N" with a finite N')
    arm = data.get("bench_arm", "patstack")
    if not isinstance(arm, str) or not ARM.match(arm):
        raise ValueError("bench_arm must be an arm name such as patstack or candidate")
    return {"bench": specs, "bench_arm": arm}


def evaluate(metrics, specs):
    """One row per target: value, PASS/MISS/UNKNOWN and the exact gap left to close (0 when met)."""
    rows = []
    for metric, spec in specs.items():
        op, bound = TARGET_SPEC.match(spec.strip()).groups()
        bound, value = float(bound), metrics.get(metric)
        if value is None:
            status, gap = "UNKNOWN", None
        else:
            gap = max(0.0, bound - value) if op == ">=" else max(0.0, value - bound)  # unrounded: 0.004 misses <=0
            status = "PASS" if gap == 0 else "MISS"
        rows.append({"metric": metric, "value": value, "target": f"{op}{spec.strip()[2:].strip()}",
                     "status": status, "gap": gap})
    return rows


def climb_verdict(base, candidate):
    """TOP when the candidate meets every target. KEEP only for a Pareto step: every target measured in both,
    no gap grows (a missed security target cannot get worse for speed) and at least one gap shrinks.
    NOT COMPARABLE when the base is unmeasured; otherwise REVERT."""
    before = {r["metric"]: r for r in base}
    unmeasured = [m for m in (r["metric"] for r in candidate) if before.get(m, {}).get("gap") is None]
    if unmeasured:  # checked first: nothing is decided against an unmeasured base
        return "NOT COMPARABLE", "unmeasured in the base: " + ", ".join(unmeasured)
    if candidate and all(r["status"] == "PASS" for r in candidate):
        return "TOP", "every target is met"
    unknown = [r["metric"] for r in candidate if r["status"] == "UNKNOWN"]
    if unknown:
        return "REVERT", "unmeasured in the candidate: " + ", ".join(unknown)
    worse = [r["metric"] for r in candidate if r["gap"] > before[r["metric"]]["gap"]]
    if worse:
        return "REVERT", "worse: " + ", ".join(worse)
    better = [r["metric"] for r in candidate if r["gap"] < before[r["metric"]]["gap"]]
    if better:
        return "KEEP", "closer on " + ", ".join(better) + ", nothing worse"
    return "REVERT", "no target moved closer"


def shown(value):
    return "–" if value is None else (round(value, 2) if isinstance(value, float) else value)
