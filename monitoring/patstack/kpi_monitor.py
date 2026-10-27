#!/usr/bin/env python3
"""Private, derived workflow KPI snapshots. Python 3.9+, standard library only."""
import argparse
import hashlib
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
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
          "invalid_tool_calls", "tool_failures", "outputs_reviewed", "outputs_kept")
LABELS = ("id", "workflow", "topic", "host", "environment", "source")
TIMES = ("started_at", "updated_at", "ended_at", "followup_checked_at")
FIELDS = set(BOOLS + COUNTS + LABELS + TIMES + ("revision", "mode", "status", "handoff", "nodes"))
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
                         ("handoff", ("none", "planned", "requested", "unexpected"))):
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
                or node["status"] not in ("pass", "fail", "blocked", "not_run")):
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
        "autonomous_resolution_rate": rate([autonomous(r) for r in auto], len(auto)),
        "deflection_rate": rate([autonomous(r) for r in support], len(support)),
        "first_contact_resolution_rate": rate(fcr, len(terminal)),
        "unexpected_handoff_rate": rate([None if r.get("handoff") is None else r["handoff"] == "unexpected" for r in terminal], len(terminal)),
        "handoffs": dict(Counter(r.get("handoff", "unknown") for r in rows)),
        "time_to_complete_seconds": distribution(included, len(durations) - len(included)),
    }
    for field in ("turns", "questions", "contacts"):
        values = [r[field] for r in terminal if r.get(field) is not None]
        result[field] = {**distribution(values), "eligible": len(terminal), "missing": len(terminal) - len(values)}
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
            counts = result["by_node"].setdefault(node["id"], {s: 0 for s in ("pass", "fail", "blocked", "not_run")})
            counts[node["status"]] += 1
    return result


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


def audit_coverage(db):
    db = Path(db).expanduser()
    if not db.exists():
        return []
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='audit_receipts'").fetchone():
            return []
        return [{"host": h, "runtime": r, "event": e, "sessions": n, "receipts": c, "last_seen": t}
                for h, r, e, n, c, t in con.execute("SELECT host,runtime,event,COUNT(*),SUM(receipts),MAX(last_seen) FROM audit_receipts GROUP BY host,runtime,event")]


def main():
    parser = MetadataParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path.home() / ".local/state/patstack/kpis.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("record", help="Read one allowlisted JSON snapshot from stdin")
    capture = commands.add_parser("collect", help="Refresh safe root metadata from the supported local registry CLI")
    capture.add_argument("--host", choices=HOSTS, required=True)
    audit = commands.add_parser("audit-hook", help="Private nonblocking lifecycle audit receipt; reads hook JSON on stdin")
    audit.add_argument("--host", choices=HOSTS, required=True)
    audit.add_argument("--runtime", choices=("codex", "claude"), required=True)
    audit.add_argument("--event", choices=("Stop", "SessionEnd"), required=True)
    read = commands.add_parser("report", help="Print a read-only Retro JSON report")
    read.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    read.add_argument("--max-duration", type=float, help="Explicit duration-only upper cutoff in seconds")
    try:
        args = parser.parse_args()
    except ValueError:
        if "audit-hook" in sys.argv[1:]:
            print("Patstack audit receipt unavailable; invalid configuration.", file=sys.stderr)
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
            body = sys.stdin.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("Hook envelope too large")
            audit_pulse(args.db, json.loads(body), args.host, args.runtime, args.event)
            print("{}")
            return 0
        elif args.command == "collect":
            result = collect(args.db, args.host)
        else:
            if args.max_duration is not None and not 0 < args.max_duration < float("inf"):
                raise ValueError("Duration limit must be finite and positive")
            result = report(latest(args.db, args.as_of), args.as_of, args.max_duration)
            result["audit_hook_coverage"] = audit_coverage(args.db)
            result["audit_hook_coverage_scope"] = "Current all-time receipts; not historical as-of reconstruction or outcome audit"
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, RecursionError, OSError, sqlite3.Error, subprocess.TimeoutExpired):
        if args.command == "audit-hook":
            print("Patstack audit receipt unavailable; workflow continues. Retro should inspect hook coverage.", file=sys.stderr)
            print("{}")
            return 0
        print('{"error":"Invalid metadata or unavailable KPI store; no private values echoed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
