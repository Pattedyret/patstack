#!/usr/bin/env python3
"""One-line KPI snapshots for a Patstack task: start at intake, finish at the endpoint.

`start` records revision 1 (open). `finish` reads the latest snapshot, keeps its identity
(start time, workflow, host, environment), bumps the revision and records the outcome.
`show` prints the latest snapshot. All validation is kpi_monitor's own; the store stays private.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kpi_monitor  # noqa: E402

DEFAULT_DB = Path.home() / ".local/state/patstack/kpis.sqlite3"
IDENTITY = ("id", "workflow", "topic", "mode", "started_at", "host", "environment", "source")


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def latest_snapshot(db, task_id):
    if not Path(db).is_file():
        return None
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)) as con:
        try:
            row = con.execute("SELECT body FROM snapshots WHERE id=? ORDER BY revision DESC LIMIT 1",
                              (task_id,)).fetchone()
        except sqlite3.OperationalError:  # store exists but has no snapshots yet
            return None
    return json.loads(row[0]) if row else None


def start(args):
    previous = latest_snapshot(args.db, args.id)
    if previous:  # resuming the same task keeps its first start, never a second revision 1
        return {"recorded": False, "note": "already started", "revision": previous["revision"]}
    stamp = now()
    row = {"id": args.id, "revision": 1, "workflow": args.workflow, "topic": args.topic, "mode": args.mode,
           "status": "open", "started_at": stamp, "updated_at": stamp, "host": args.host,
           "environment": args.environment, "source": args.source}
    kpi_monitor.record(args.db, row)
    return {"recorded": True, "revision": 1}


def finish(args):
    previous = latest_snapshot(args.db, args.id)
    opening = None
    if not previous:  # finish without start: a real start time is required, never invented
        if not (args.workflow and args.topic and args.mode and args.host and args.started_at):
            raise ValueError("No start snapshot for this task: pass --started-at (when the request began), --workflow, --topic, --mode and --host")
        opening = {"id": args.id, "revision": 1, "workflow": args.workflow, "topic": args.topic, "mode": args.mode,
                   "status": "open", "started_at": args.started_at, "updated_at": args.started_at, "host": args.host,
                   "environment": args.environment, "source": args.source}
        previous = kpi_monitor.validate(dict(opening))
    stamp = now()
    # Keep earlier observations and an existing terminal time; only what this call states changes.
    row = {key: value for key, value in previous.items() if key not in ("revision", "updated_at")}
    row.update(status=args.status, ended_at=previous.get("ended_at") or stamp)
    if args.verified != "unknown":  # unknown leaves any earlier label alone, never false
        row["verified_success"] = args.verified == "yes"
    if args.human_interventions is not None:
        row["human_interventions"] = args.human_interventions
    if args.handoff:
        row["handoff"] = args.handoff
    nodes = {node["id"]: node["status"] for node in previous.get("nodes", [])}
    for item in args.node or []:  # later statements update a node; earlier nodes stay
        name, _, status = item.partition("=")
        nodes[name] = status
    if nodes:
        row["nodes"] = [{"id": name, "status": status} for name, status in nodes.items()]
    unchanged = {k: v for k, v in previous.items() if k not in ("revision", "updated_at")}
    if row == unchanged:  # a retry of the same outcome records nothing new
        return {"recorded": False, "revision": previous["revision"], "status": row["status"],
                "verified_success": row.get("verified_success")}
    row.update(revision=previous["revision"] + 1, updated_at=stamp)
    kpi_monitor.validate(dict(row))  # both snapshots are valid before anything is written
    if opening:
        kpi_monitor.record(args.db, opening)
    kpi_monitor.record(args.db, row)
    return {"recorded": True, "revision": row["revision"], "status": args.status,
            "verified_success": row.get("verified_success")}


def once(args):
    """Unticketed discussion/research/testing: one closed snapshot when the request concludes."""
    if latest_snapshot(args.db, args.id):
        raise ValueError("ID already recorded; use a new request ID")
    end = now()
    begin = args.started_at or end
    row = {"id": args.id, "revision": 1, "workflow": args.workflow, "topic": args.topic, "mode": "other",
           "status": args.status, "started_at": begin, "updated_at": end, "ended_at": end, "host": args.host,
           "environment": args.environment, "source": args.source, "handoff": "none"}
    if args.verified != "unknown":
        row["verified_success"] = args.verified == "yes"
    kpi_monitor.record(args.db, row)
    return {"recorded": True, "id": args.id, "status": args.status, "verified_success": row.get("verified_success")}


def show(args):
    return latest_snapshot(args.db, args.id) or {"missing": args.id}


def main(argv=None):
    parser = kpi_monitor.MetadataParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start", help="Record the task's open snapshot")
    begin.add_argument("--id", required=True, help="Ticket reference such as TKT-<number>")
    begin.add_argument("--workflow", required=True, help="Slug such as feature, bugfix, incident, research")
    begin.add_argument("--topic", required=True, help="Project or area slug")
    begin.add_argument("--mode", required=True, choices=("full_send", "full_stop", "other"))
    begin.add_argument("--host", required=True, choices=kpi_monitor.HOSTS)
    begin.add_argument("--environment", default="local", choices=kpi_monitor.ENVIRONMENTS)
    begin.add_argument("--source", default="patstack")
    end = commands.add_parser("finish", help="Record the task's outcome at its endpoint")
    end.add_argument("--id", required=True)
    end.add_argument("--status", required=True, choices=[s for s in kpi_monitor.STATUSES if s != "open"])
    end.add_argument("--verified", required=True, choices=("yes", "no", "unknown"),
                     help="yes only when the required proof exists")
    end.add_argument("--human-interventions", type=int)
    end.add_argument("--handoff", choices=("none", "planned", "requested", "unexpected"))
    end.add_argument("--node", action="append", help="Proof node as id=pass|fail|blocked|not_run; repeatable")
    end.add_argument("--workflow", help="Only needed when there was no start")
    end.add_argument("--topic", help="Only needed when there was no start")
    end.add_argument("--mode", choices=("full_send", "full_stop", "other"), help="Only needed when there was no start")
    end.add_argument("--host", choices=kpi_monitor.HOSTS, help="Only needed when there was no start")
    end.add_argument("--environment", default="local", choices=kpi_monitor.ENVIRONMENTS)
    end.add_argument("--source", default="patstack")
    end.add_argument("--started-at", help="ISO time the request began; required when there was no start")
    single = commands.add_parser("once", help="Record an unticketed request (discussion, research, testing) when it concludes")
    single.add_argument("--id", required=True, help="Opaque request slug, e.g. req-20261028-kpi-question")
    single.add_argument("--workflow", required=True, help="discussion, research, testing, ...")
    single.add_argument("--topic", required=True)
    single.add_argument("--host", required=True, choices=kpi_monitor.HOSTS)
    single.add_argument("--environment", default="local", choices=kpi_monitor.ENVIRONMENTS)
    single.add_argument("--source", default="patstack")
    single.add_argument("--status", default="completed", choices=[s for s in kpi_monitor.STATUSES if s != "open"])
    single.add_argument("--verified", default="unknown", choices=("yes", "no", "unknown"))
    single.add_argument("--started-at", help="ISO time the request began; defaults to now")
    look = commands.add_parser("show", help="Print the latest snapshot")
    look.add_argument("--id", required=True)
    try:
        args = parser.parse_args(argv)
    except ValueError:  # the monitor's parser never echoes argument values
        print(json.dumps({"error": "Invalid command arguments"}), file=sys.stderr)
        return 2
    try:
        if not kpi_monitor.label(args.id):
            raise ValueError("Invalid metadata label")
        result = {"start": start, "finish": finish, "once": once, "show": show}[args.command](args)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
