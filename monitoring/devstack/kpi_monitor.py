#!/usr/bin/env python3
"""Private, derived workflow KPI snapshots. Python 3.9+, standard library only."""
import argparse
import hashlib
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import sys


HOSTS = ("mac", "devbox", "windows")
ENVIRONMENTS = ("local", "pr_preview", "test", "stage", "production")
STATUSES = ("open", "completed", "failed", "handed_off", "abandoned", "cancelled")
BOOLS = ("verified_success", "support_eligible", "repeat_contact",
         "unsupported", "frustration_signal", "frustration_confirmed")
COUNTS = ("human_interventions", "contacts", "turns", "questions",
          "responses_reviewed", "response_errors", "hallucinations", "tool_calls",
          "invalid_tool_calls", "tool_failures", "outputs_reviewed", "outputs_kept",
          "slices", "review_rounds")
LABELS = ("id", "workflow", "topic", "host", "environment", "source")
TIMES = ("started_at", "updated_at", "ended_at", "followup_checked_at")
FIELDS = set(BOOLS + COUNTS + LABELS + TIMES + ("revision", "mode", "status", "handoff", "nodes", "verification"))
# Unticketed requests recorded with task_kpi.py once have no verification step. Snapshots written before the
# explicit "verification" marker existed are recognised by these workflow names.
ONCE_WORKFLOWS = ("discussion", "research", "testing")
NODE_STATUSES = ("pass", "fail", "blocked", "not_run")
REQUIRED = {"id", "revision", "workflow", "topic", "mode", "status", "started_at", "updated_at"}


class MetadataParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid command arguments")


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("Expected timezone-aware ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("Expected timezone-aware ISO timestamp") from None


def label(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value)


def validate(row):
    if not isinstance(row, dict) or set(row) - FIELDS:
        raise ValueError("Unknown or missing fields; supply metadata only")
    row = {key: value for key, value in row.items() if value is not None}
    if REQUIRED - set(row):
        raise ValueError("Missing required metadata")
    for key in LABELS:
        if key in row and not label(row[key]):
            raise ValueError("Invalid metadata label")
    for key in BOOLS:
        if row.get(key) is not None and type(row[key]) is not bool:
            raise ValueError("Boolean label required")
    for key in COUNTS + ("revision",):
        value = row.get(key)
        if value is not None and (type(value) is not int or value < 0 or value > 2**53):
            raise ValueError("Nonnegative integer required")
    if row["revision"] is None or row["revision"] < 1:
        raise ValueError("Positive revision required")
    for key, choices in (("mode", ("full_send", "full_stop", "other")),
                         ("status", STATUSES),
                         ("handoff", ("none", "planned", "requested", "unexpected")),
                         ("verification", ("required", "not_applicable"))):
        if key in row and row[key] not in choices:
            raise ValueError("Invalid categorical value")
    for key, choices in (("host", HOSTS), ("environment", ENVIRONMENTS)):
        if key in row and row[key] not in choices:
            raise ValueError("Invalid host/environment")
    parsed = {}
    for key in TIMES:
        if row.get(key) is not None:
            parsed[key] = stamp(row[key])
            row[key] = parsed[key].isoformat()
    start, updated = parsed["started_at"], parsed["updated_at"]
    end = parsed.get("ended_at")
    if updated < start or (end and not start <= end <= updated):
        raise ValueError("Invalid event chronology")
    if row["status"] == "open" and end or row["status"] != "open" and not end:
        raise ValueError("Terminal statuses require an end; open work has no end")
    if row.get("verified_success") is True and row["status"] != "completed":
        raise ValueError("Verified success requires completion")
    if row["status"] == "handed_off" and row.get("handoff") == "none":
        raise ValueError("Unfinished transfer requires a handoff classification")
    if parsed.get("followup_checked_at", updated) > updated:
        raise ValueError("Follow-up exceeds snapshot observation time")
    for numerator, denominator in (("response_errors", "responses_reviewed"),
                                   ("hallucinations", "responses_reviewed"),
                                   ("invalid_tool_calls", "tool_calls"),
                                   ("tool_failures", "tool_calls"),
                                   ("outputs_kept", "outputs_reviewed")):
        if row.get(numerator) is not None and (row.get(denominator) is None or row[numerator] > row[denominator]):
            raise ValueError("Count exceeds or lacks its audited denominator")
    nodes = row.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) > 100:
        raise ValueError("Invalid node observations")
    seen = set()
    for node in nodes:
        if (not isinstance(node, dict) or set(node) != {"id", "status"}
                or not label(node["id"]) or node["id"] in seen
                or node["status"] not in NODE_STATUSES):
            raise ValueError("Invalid or duplicate node observation")
        seen.add(node["id"])
    return row


def record(db, row):
    row = validate(row)
    db = Path(db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = json.dumps(row, sort_keys=True, separators=(",", ":"))
    with closing(sqlite3.connect(db, timeout=15)) as con, con:
        if os.name != "nt":
            db.chmod(0o600)
        con.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT, revision INTEGER, updated TEXT, body TEXT, PRIMARY KEY(id, revision))")
        con.execute("BEGIN IMMEDIATE")
        previous = con.execute("SELECT body FROM snapshots WHERE id=? AND revision=?", (row["id"], row["revision"])).fetchone()
        if previous:
            if previous[0] != body:
                raise ValueError("Conflicting snapshot revision")
            return False
        history = [json.loads(x[0]) for x in con.execute("SELECT body FROM snapshots WHERE id=?", (row["id"],))]
        for other in history:
            if any(other.get(key) != row.get(key) for key in ("started_at", "workflow", "host", "environment")):
                raise ValueError("Workflow identity changed")
            direction = row["revision"] - other["revision"]
            if direction * (stamp(row["updated_at"]) - stamp(other["updated_at"])).total_seconds() < 0:
                raise ValueError("Revision chronology changed")
        con.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?)", (row["id"], row["revision"], row["updated_at"], body))
    return True


def latest(db, as_of):
    cutoff = stamp(as_of)
    db = Path(db).expanduser()
    if not db.exists():
        return []
    chosen = {}
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='snapshots'").fetchone():
            return []
        for (body,) in con.execute("SELECT body FROM snapshots"):
            row = validate(json.loads(body))
            if stamp(row["updated_at"]) <= cutoff and row["revision"] > chosen.get(row["id"], {}).get("revision", 0):
                chosen[row["id"]] = row
    return list(chosen.values())


def rate(values, eligible):
    known = [v for v in values if v is not None]
    return {"percent": round(100 * sum(known) / len(known), 2) if known else None,
            "numerator": sum(known), "observed": len(known), "eligible": eligible,
            "missing": eligible - len(known)}


def distribution(values, excluded=0):
    return {"count": len(values), "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None, "excluded": excluded}


def success(row):
    if row["status"] in ("failed", "handed_off", "abandoned"):
        return False
    return row.get("verified_success")


def needs_verification(row):
    """A designated task must end with verified_success; an unticketed request has nothing to verify."""
    if row.get("verification") is not None:
        return row["verification"] == "required"
    return row["workflow"] not in ONCE_WORKFLOWS  # older snapshots without the marker


def autonomous(row):
    ok = success(row)
    interventions = row.get("human_interventions")
    if ok is False or interventions is not None and interventions > 0:
        return False
    return True if ok is True and interventions == 0 else None


def summarize(rows, as_of, max_duration=None):
    now = stamp(as_of)
    terminal = [r for r in rows if r["status"] not in ("open", "cancelled")]
    auto = [r for r in terminal if r["mode"] == "full_send"]
    support = [r for r in terminal if r.get("support_eligible") is True]
    durations = [(stamp(r["ended_at"]) - stamp(r["started_at"])).total_seconds()
                 for r in terminal if r["status"] == "completed" and success(r) is True]
    included = [v for v in durations if max_duration is None or v <= max_duration]
    fcr = []
    for r in terminal:
        if success(r) is False or r.get("contacts", 0) > 1 or r.get("repeat_contact") is True:
            fcr.append(False)
            continue
        followup = r.get("followup_checked_at")
        mature = stamp(r["ended_at"]) + timedelta(days=7)
        if (followup and mature <= stamp(followup) <= now
                and r.get("contacts") is not None and r.get("repeat_contact") is not None):
            ok = success(r)
            fcr.append(ok and r["contacts"] == 1 and not r["repeat_contact"] if ok is not None else None)
        else:
            fcr.append(None)
    result = {
        "counts": {"total": len(rows), **{s: sum(r["status"] == s for r in rows) for s in STATUSES}},
        "task_completion_rate": rate([success(r) for r in terminal], len(terminal)),
        # Closed snapshots that need a verification label and lack one (the setup check warns on these).
        "verification_missing": sum(1 for r in terminal if needs_verification(r) and success(r) is None),
        "autonomous_resolution_rate": rate([autonomous(r) for r in auto], len(auto)),
        "deflection_rate": rate([autonomous(r) for r in support], len(support)),
        "first_contact_resolution_rate": rate(fcr, len(terminal)),
        "unexpected_handoff_rate": rate([None if r.get("handoff") is None else r["handoff"] == "unexpected" for r in terminal], len(terminal)),
        "handoffs": dict(Counter(r.get("handoff", "unknown") for r in rows)),
        "time_to_complete_seconds": distribution(included, len(durations) - len(included)),
    }
    for field in ("turns", "questions", "contacts", "slices", "review_rounds"):
        values = [r[field] for r in terminal if r.get(field) is not None]
        result[field] = {**distribution(values), "eligible": len(terminal), "missing": len(terminal) - len(values)}
    nodes = {}
    for row in rows:  # per-cohort proof nodes, e.g. ci=not_run marks "no CI configured" for Retro
        for node in row.get("nodes", []):
            nodes.setdefault(node["id"], {s: 0 for s in NODE_STATUSES})[node["status"]] += 1
    result["nodes"] = dict(sorted(nodes.items()))
    for name, field in (("unsupported_request_rate", "unsupported"),
                        ("frustration_signal_rate", "frustration_signal"),
                        ("confirmed_frustration_rate", "frustration_confirmed")):
        result[name] = rate([r.get(field) for r in rows], len(rows))
    for name, num, den in (("response_error_rate", "response_errors", "responses_reviewed"),
                           ("hallucination_rate", "hallucinations", "responses_reviewed"),
                           ("invalid_tool_call_rate", "invalid_tool_calls", "tool_calls"),
                           ("tool_failure_rate", "tool_failures", "tool_calls"),
                           ("output_retention_rate", "outputs_kept", "outputs_reviewed")):
        measured = [r for r in rows if r.get(num) is not None and r.get(den) is not None]
        numerator = sum(r[num] for r in measured)
        denominator = sum(r[den] for r in measured)
        result[name] = {"percent": round(100 * numerator / denominator, 2) if denominator else None,
                        "numerator": numerator, "denominator": denominator,
                        "observed_workflows": len(measured), "eligible_workflows": len(rows)}
    return result


def report(rows, as_of, max_duration=None):
    observations = [r for r in rows if r["workflow"] == "registry_observation"]
    rows = [r for r in rows if r["workflow"] != "registry_observation"]
    result = {"schema_version": 1, "as_of": as_of,
              "overall": summarize(rows, as_of, max_duration),
              "registry_observations": {"count": len(observations),
                  "by_host": {host: {"total": sum(r["host"] == host for r in observations),
                       "closed": sum(r["host"] == host and r["nodes"][0]["status"] == "pass" for r in observations),
                       "open": sum(r["host"] == host and r["nodes"][0]["status"] != "pass" for r in observations)} for host in HOSTS},
                  "note": "Historical registry discovery only; the execution registry is retired. Not verified outcomes or durations."},
              "coverage_note": "Only recorded workflows are known. Missing emitters are unmeasured; rates use observed labels, not all eligible records.",
              "by_node": {}}
    for field, expected in (("host", HOSTS), ("environment", ENVIRONMENTS), ("workflow", ()), ("topic", ())):
        groups = set(expected) | {r.get(field, "unknown") for r in rows}
        result["by_" + field] = {}
        for key in sorted(groups):
            selected = [r for r in rows if r.get(field, "unknown") == key]
            result["by_" + field][key] = {"coverage": "recorded" if selected else "unmeasured",
                                            **summarize(selected, as_of, max_duration)}
    for row in rows:
        for node in row.get("nodes", []):
            counts = result["by_node"].setdefault(node["id"], {s: 0 for s in NODE_STATUSES})
            counts[node["status"]] += 1
    return result


def aggregate(rows, as_of):
    """Counts only, for opt-in sharing: no ids, no free text, no time finer than the as-of day."""
    groups = {}
    for row in rows:
        if row["workflow"] == "registry_observation":
            continue
        key = (row["topic"], row["workflow"], row["status"], row.get("host", "unknown"))
        item = groups.setdefault(key, {"count": 0, "verified_yes": 0, "verified_no": 0, "verified_unknown": 0,
                                       "full_send": 0, "full_stop": 0, "other_mode": 0,
                                       "slices_total": 0, "slices_observed": 0,
                                       "review_rounds_total": 0, "review_rounds_observed": 0, "ci_not_run": 0})
        item["count"] += 1
        verified = success(row) if row["status"] not in ("open", "cancelled") else row.get("verified_success")
        item["verified_" + {True: "yes", False: "no", None: "unknown"}[verified]] += 1
        item[{"full_send": "full_send", "full_stop": "full_stop"}.get(row["mode"], "other_mode")] += 1
        for field in ("slices", "review_rounds"):
            if row.get(field) is not None:
                item[field + "_total"] += row[field]
                item[field + "_observed"] += 1
        item["ci_not_run"] += any(n["id"] == "ci" and n["status"] == "not_run" for n in row.get("nodes", []))
    return {"schema": "devstack-kpi-aggregate/1", "as_of_day": stamp(as_of).date().isoformat(),
            "note": "Counts per topic/workflow/status/host only. Topics are repo or project slugs; share only with consent.",
            "groups": [dict(zip(("topic", "workflow", "status", "host"), key), **value)
                       for key, value in sorted(groups.items())]}


def registry_snapshot(task, host):
    """Only registry facts; complete is not independently verified success."""
    state = task["state"]
    closed = state in ("done", "cancelled", "handoff")
    # Updated time can include post-completion comments, so it is NOT an end time.
    # Keep registry completion as an open, unverified observation until audited.
    row = {"id": "registry:" + host + ":" + task["id"], "revision": task["revision"],
           "workflow": "registry_observation", "topic": task.get("work_type") or "general",
           "host": host, "source": "agent-work", "mode": "other", "status": "open",
           "started_at": datetime.fromtimestamp(task["created_at"], timezone.utc).isoformat(),
           "updated_at": datetime.fromtimestamp(task["updated_at"], timezone.utc).isoformat(),
           "nodes": [{"id": "registry-closed", "status": "pass" if closed else "not_run"}]}
    return validate(row)


def collect(db, host):
    # Number allocation contains no execution state; do not resurrect the old registry.
    return {"source": "ticket-references", "coverage": "numbering_only", "inserted": 0,
            "note": "No task states or outcomes can be inferred from reference numbers. "
                    "Use audited record snapshots and native lifecycle receipts on every host."}


def audit_pulse(db, payload, host, runtime, event, now=None):
    """Lifecycle receipt only. Never open transcript_path or copy message/tool data."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid hook envelope")
    identity = payload.get("session_id") or payload.get("thread_id")
    if not isinstance(identity, str) or not 1 <= len(identity) <= 256:
        raise ValueError("Missing native session identity")
    key = hashlib.sha256((host + ":" + runtime + ":" + identity).encode()).hexdigest()[:32]
    at = now or datetime.now(timezone.utc).isoformat()
    stamp(at)
    db = Path(db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(db, timeout=3)) as con, con:
        if os.name != "nt":
            db.chmod(0o600)
        con.execute("CREATE TABLE IF NOT EXISTS audit_receipts (session TEXT, host TEXT, runtime TEXT, event TEXT, first_seen TEXT, last_seen TEXT, receipts INTEGER, PRIMARY KEY(session, event))")
        con.execute("INSERT INTO audit_receipts VALUES (?,?,?,?,?,?,1) ON CONFLICT(session,event) DO UPDATE SET last_seen=excluded.last_seen, receipts=receipts+1",
                    (key, host, runtime, event, at, at))
    return {"recorded": True, "note": "Lifecycle receipt, not task completion or audited correctness"}


TOOL_EVENTS = ("PostToolUse", "PostToolUseFailure")
HOOK_ENVELOPE_LIMIT = 64 * 1024 * 1024  # tool payloads can carry whole files; only the top-level id is kept


def session_kpis(db):
    """Per host/runtime session metrics from lifecycle receipts only: counts and times, never content."""
    db = Path(db).expanduser()
    if not db.exists():
        return []
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='audit_receipts'").fetchone():
            return []
        rows = con.execute("SELECT host, runtime, session, event, first_seen, last_seen, receipts FROM audit_receipts").fetchall()
    sessions = {}
    for host, runtime, session, event, first, last, receipts in rows:
        item = sessions.setdefault((host, runtime, session), {"first": first, "last": last, "events": Counter()})
        item["first"], item["last"] = min(item["first"], first, key=stamp), max(item["last"], last, key=stamp)
        item["events"][event] += receipts
    result = []
    for host, runtime in sorted({(h, r) for h, r, _ in sessions}):
        group = [v for (h, r, _), v in sessions.items() if (h, r) == (host, runtime)]
        minutes = [(stamp(v["last"]) - stamp(v["first"])).total_seconds() / 60 for v in group]
        tool_sessions = [v for v in group if any(v["events"][e] for e in TOOL_EVENTS)]
        calls = sum(v["events"]["PostToolUse"] + v["events"]["PostToolUseFailure"] for v in group)
        failures = sum(v["events"]["PostToolUseFailure"] for v in group) if runtime == "claude" else None
        result.append({"host": host, "runtime": runtime, "sessions": len(group),
                       "turns": sum(v["events"]["Stop"] for v in group),
                       "session_minutes": {"median": round(statistics.median(minutes), 1), "mean": round(statistics.fmean(minutes), 1)},
                       "tool_sessions": len(tool_sessions), "tool_calls": calls if tool_sessions else None,
                       "tool_failures": failures if tool_sessions else None,
                       "note": "Times span first to last receipt, so single-turn sessions read 0. Tool counts start when the tool hooks are installed; "
                               + ("failures come from PostToolUseFailure." if runtime == "claude" else "Codex has no failure event, so failures are unmeasured.")})
    return result


def audit_coverage(db):
    db = Path(db).expanduser()
    if not db.exists():
        return []
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='audit_receipts'").fetchone():
            return []
        return [{"host": h, "runtime": r, "event": e, "sessions": n, "receipts": c, "last_seen": t}
                for h, r, e, n, c, t in con.execute("SELECT host,runtime,event,COUNT(*),SUM(receipts),MAX(last_seen) FROM audit_receipts GROUP BY host,runtime,event")]


# ---------------------------------------------------------------- owner-set targets (hill-climbing)

TARGETS = Path.home() / ".config/devstack/kpi-targets.json"
BENCH_RUNS = Path(os.environ.get("DEVSTACK_BENCH_RUNS", Path.home() / ".local/state/devstack/bench-runs")).expanduser()
BENCH_METRICS = ("overall", "resultat", "feller", "aerlighet", "sikkerhet", "kvalitet", "security_holes_pct",
                 "median_minutes", "median_cost_usd", "median_turns", "loaded_pct", "kpi_correct_pct")
WORK_METRICS = ("tasks", "verified_success_pct", "autonomous_resolution_pct", "unexpected_handoff_pct",
                "median_minutes", "review_rounds_mean", "verification_missing", "ci_missing")
TARGET_SPEC = re.compile(r"^(>=|<=)\s*(-?\d+(?:\.\d+)?)$")
NODE_METRIC = re.compile(r"^node:([a-z0-9][a-z0-9-]{0,63})$")  # pass rate of one proof node, e.g. node:vault-context


def load_targets(path=TARGETS):
    """The owner's targets, or None when no file is set. Invalid files raise ValueError."""
    path = Path(path).expanduser()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) - {"bench", "bench_arm", "work", "work_days", "min_samples", "packs"}:
        raise ValueError("Targets file keys: bench, bench_arm, work, work_days, min_samples, packs")
    for section in ("bench", "work", "packs"):
        if not isinstance(data.get(section, {}), dict):
            raise ValueError(f"{section} must be an object of metric targets")
    packs = data.get("packs", {})  # project-pack metrics; each pack's own tool knows their names
    if not isinstance(packs, dict) or not all(label(k) and isinstance(v, dict) for k, v in packs.items()):
        raise ValueError("packs maps a pack name to its metric targets")
    for section, known in [("bench", BENCH_METRICS), ("work", WORK_METRICS)] + [(f"packs.{k}", None) for k in packs]:
        specs = packs[section[6:]] if known is None else data.get(section, {})
        unknown = [] if known is None else [m for m in specs if m not in known and not (section == "work" and NODE_METRIC.match(m))]
        if not isinstance(specs, dict) or unknown:
            raise ValueError(f"Unknown {section} metric; known: {', '.join(known)}, node:<id>")
        for spec in specs.values():
            if not isinstance(spec, str) or not TARGET_SPEC.match(spec.strip()) \
                    or not math.isfinite(float(TARGET_SPEC.match(spec.strip()).group(2))):
                raise ValueError('A target is ">=N" or "<=N" with a finite N')
    days, floor = data.get("work_days", 7), data.get("min_samples", 3)
    for name, value, top in (("work_days", days, 365), ("min_samples", floor, 1000)):
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= top:
            raise ValueError(f"{name} must be 1..{top}")
    arm = data.get("bench_arm", "devstack")
    if not label(arm):
        raise ValueError("bench_arm must be an arm name such as devstack or candidate")
    return {"bench": data.get("bench", {}), "bench_arm": arm,
            "work": data.get("work", {}), "work_days": days, "min_samples": floor, "packs": packs}


def evaluate(metrics, specs, samples=None, min_samples=1):
    """One row per target: value, PASS/MISS/UNKNOWN and the exact gap left to close (0 when met).
    A metric with fewer than MIN_SAMPLES observations in SAMPLES is UNKNOWN, never met."""
    rows = []
    for metric, spec in specs.items():
        op, bound = TARGET_SPEC.match(spec.strip()).groups()
        bound, value = float(bound), metrics.get(metric)
        n = (samples or {}).get(metric)
        if value is None or n is not None and n < min_samples:
            status, gap = "UNKNOWN", None
        else:
            gap = max(0.0, bound - value) if op == ">=" else max(0.0, value - bound)  # unrounded: 0.004 misses <=0
            status = "PASS" if gap == 0 else "MISS"
        rows.append({"metric": metric, "value": value, "target": f"{op}{spec.strip()[2:].strip()}",
                     "status": status, "gap": gap, "n": n})
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


def work_metrics(rows, as_of, days, nodes=()):
    """Real-work KPIs over the last DAYS: designated tasks that ended in the window.
    NODES: proof node ids whose pass rate is wanted (node:<id>), over the tasks that recorded that node."""
    since = stamp(as_of) - timedelta(days=days)
    rows = [r for r in rows if r["workflow"] != "registry_observation" and r["status"] not in ("open", "cancelled")
            and needs_verification(r) and since <= stamp(r.get("ended_at") or r["updated_at"]) <= stamp(as_of)]
    summary = summarize(rows, as_of)
    minutes = summary["time_to_complete_seconds"]["median"]
    samples = {"verified_success_pct": summary["task_completion_rate"]["observed"],
               "autonomous_resolution_pct": summary["autonomous_resolution_rate"]["observed"],
               "unexpected_handoff_pct": summary["unexpected_handoff_rate"]["observed"],
               "median_minutes": summary["time_to_complete_seconds"]["count"],
               "review_rounds_mean": summary["review_rounds"]["count"]}
    # exact (the report rounds; targets must not) and complete: one eligible task without the label leaves the
    # rate unknown, so three labelled successes and one unlabelled task can never read as 100 %
    exact = lambda rate: 100 * rate["numerator"] / rate["observed"] if rate["observed"] and not rate["missing"] else None
    node_rates = {}
    for node in nodes:  # every recorded status counts: not_run on a task that needed the step is a miss
        seen = [n["status"] for r in rows for n in r.get("nodes", []) if n["id"] == node]
        samples[f"node:{node}"] = len(seen)
        node_rates[f"node:{node}"] = 100 * seen.count("pass") / len(seen) if seen else None
    return samples, {**node_rates, "tasks": len(rows),
            "verified_success_pct": exact(summary["task_completion_rate"]),
            "autonomous_resolution_pct": exact(summary["autonomous_resolution_rate"]),
            "unexpected_handoff_pct": exact(summary["unexpected_handoff_rate"]),
            "median_minutes": minutes / 60 if minutes is not None else None,
            "review_rounds_mean": summary["review_rounds"]["mean"] if not summary["review_rounds"]["missing"] else None,
            "verification_missing": summary["verification_missing"],
            "ci_missing": summary["nodes"].get("ci", {}).get("not_run", 0)}


def latest_bench(runs=BENCH_RUNS, arm="devstack"):
    """The newest scoreboard.json with ARM: its run folder name and that arm's summary."""
    runs = Path(runs)
    for folder in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True) if runs.is_dir() else []:
        board = folder / "scoreboard.json"
        if board.is_file():
            data = json.loads(board.read_text(encoding="utf-8"))
            if arm in data.get("summary", {}):  # an incomplete run proves nothing: its values stay unknown
                # judged only on exact values: an older scoreboard without them, or an incomplete run, stays unknown
                exact = data["summary"][arm].get("exact") if data.get("complete") else None
                return folder.name, exact, bool(data.get("complete")) and exact is not None
    return None, None, False


def scorecard(rows, as_of, targets, runs=BENCH_RUNS):
    run, bench, complete = latest_bench(runs, targets["bench_arm"]) if targets["bench"] else (None, None, False)
    nodes = [NODE_METRIC.match(m).group(1) for m in targets["work"] if NODE_METRIC.match(m)]
    samples, metrics = work_metrics(rows, as_of, targets["work_days"], nodes)
    work = evaluate(metrics, targets["work"], samples, targets["min_samples"])
    bench_rows = evaluate({m: (bench or {}).get(m) for m in targets["bench"]}, targets["bench"])
    every = work + bench_rows
    return {"work_days": targets["work_days"], "min_samples": targets["min_samples"], "work": work, "bench_run": run,
            "bench_complete": complete, "bench_arm": targets["bench_arm"], "bench": bench_rows,
            "met": sum(r["status"] == "PASS" for r in every), "total": len(every)}


def shown(value):
    return "–" if value is None else (round(value, 2) if isinstance(value, float) else value)


def scorecard_line(card):
    """One line for the session status: targets met and the misses with their values."""
    misses = [r for r in card["work"] + card["bench"] if r["status"] != "PASS"]
    text = "; ".join(f"{r['status']} {r['metric']} {shown(r['value'])} ({r['target']})" for r in misses[:3])
    more = f" +{len(misses) - 3}" if len(misses) > 3 else ""
    return f"🎯 targets {card['met']}/{card['total']} met" + (f" · {text}{more}" if misses else "")


def scorecard_text(card):
    def line(r):
        sample = f"  n={r['n']}" if r.get("n") is not None else ""
        gap = f"  gap {shown(r['gap'])}" if r["gap"] else ""
        return f"  {r['status']:<7} {r['metric']:<26} {shown(r['value']):>8}  target {r['target']}{gap}{sample}"
    lines = [scorecard_line(card), "", f"Work, last {card['work_days']} days (rates need n >= {card['min_samples']}):"]
    lines += [line(r) for r in card["work"]] or ["  (no work targets)"]
    if card["bench"]:
        run = card["bench_run"] or "none yet: run bench/bench.py"
        state = "" if card["bench_run"] is None or card["bench_complete"] else " (incomplete or scored before exact values: unknown; rerun or rescore)"
        lines += ["", f"Bench, arm {card['bench_arm']}, run {run}{state}:"] + [line(r) for r in card["bench"]]
    return "\n".join(lines)

def main():
    parser = MetadataParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path.home() / ".local/state/devstack/kpis.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("record", help="Read one allowlisted JSON snapshot from stdin")
    capture = commands.add_parser("collect", help="Refresh safe root metadata from the supported local registry CLI")
    capture.add_argument("--host", choices=HOSTS, required=True)
    audit = commands.add_parser("audit-hook", help="Private nonblocking lifecycle audit receipt; reads hook JSON on stdin")
    audit.add_argument("--host", choices=HOSTS, required=True)
    audit.add_argument("--runtime", choices=("codex", "claude"), required=True)
    audit.add_argument("--event", choices=("Stop", "SessionEnd") + TOOL_EVENTS, required=True)
    read = commands.add_parser("report", help="Print a read-only Retro JSON report")
    read.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    read.add_argument("--max-duration", type=float, help="Explicit duration-only upper cutoff in seconds")
    read.add_argument("--targets", type=Path, default=TARGETS, help="Owner-set targets; adds a scorecard (default %(default)s)")
    card = commands.add_parser("scorecard", help="Print the KPIs against the owner's targets (PASS/MISS and the gap)")
    card.add_argument("--targets", type=Path, default=TARGETS)
    card.add_argument("--runs", type=Path, default=BENCH_RUNS, help="Benchmark runs folder (latest scoreboard.json is used)")
    card.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    card.add_argument("--json", action="store_true")
    share = commands.add_parser("export", help="Print counts-only JSON for opt-in sharing (requires --aggregate)")
    share.add_argument("--aggregate", action="store_true", help="Counts per topic/workflow/status/host; no ids or fine timestamps")
    share.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    try:
        args = parser.parse_args()
    except ValueError:
        if "audit-hook" in sys.argv[1:]:
            print("DevStack audit receipt unavailable; invalid configuration.", file=sys.stderr)
            print("{}")
            return 0
        print('{"error":"Invalid command arguments"}', file=sys.stderr)
        return 2
    except SystemExit as error:
        if "audit-hook" in sys.argv[1:]:
            print("{}")
            return 0
        return error.code
    try:
        if args.command == "record":
            body = sys.stdin.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("Snapshot too large")
            result = {"inserted": record(args.db, json.loads(body))}
        elif args.command == "audit-hook":
            body = sys.stdin.buffer.read(HOOK_ENVELOPE_LIMIT + 1)
            if len(body) > HOOK_ENVELOPE_LIMIT:
                while sys.stdin.buffer.read(1 << 20):  # drain so the client never blocks; this receipt stays unmeasured
                    pass
                print("{}")
                return 0
            audit_pulse(args.db, json.loads(body), args.host, args.runtime, args.event)
            print("{}")
            return 0
        elif args.command == "export":
            if not args.aggregate:
                raise ValueError("Only --aggregate export is supported")
            result = aggregate(latest(args.db, args.as_of), args.as_of)
        elif args.command == "collect":
            result = collect(args.db, args.host)
        elif args.command == "scorecard":
            targets = load_targets(args.targets)
            if targets is None:
                print(f"No targets set. Copy examples/kpi-targets.example.json to {args.targets} and edit it.")
                return 0
            card = scorecard(latest(args.db, args.as_of), args.as_of, targets, args.runs)
            print(json.dumps(card, indent=2, allow_nan=False) if args.json else scorecard_text(card))
            return 0
        else:
            if args.max_duration is not None and not 0 < args.max_duration < float("inf"):
                raise ValueError("Duration limit must be finite and positive")
            result = report(latest(args.db, args.as_of), args.as_of, args.max_duration)
            result["audit_hook_coverage"] = audit_coverage(args.db)
            result["session_kpis"] = session_kpis(args.db)
            result["audit_hook_coverage_scope"] = "Current all-time receipts; not historical as-of reconstruction or outcome audit"
            try:
                targets = load_targets(args.targets)
                card = targets and scorecard(latest(args.db, args.as_of), args.as_of, targets)
                result["scorecard"] = card and {**card, "line": scorecard_line(card)}
            except (ValueError, TypeError, OSError, OverflowError):
                result["scorecard"] = {"error": "targets file invalid"}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, RecursionError, OSError, sqlite3.Error, subprocess.TimeoutExpired):
        if args.command == "audit-hook":
            print("DevStack audit receipt unavailable; workflow continues. Retro should inspect hook coverage.", file=sys.stderr)
            print("{}")
            return 0
        print('{"error":"Invalid metadata or unavailable KPI store; no private values echoed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
