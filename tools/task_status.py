#!/usr/bin/env python3
"""Set a DevStack task's status: print its thread title and ping the owner when it matters.

  python3 tools/task_status.py TKT-… "DEPLOYED ON STAGE" --title "New invoice flow" --url URL
  python3 tools/task_status.py TKT-… "IN PROGRESS" --title "New invoice flow" --ping --note "Stage check failed, do not test yet"
  python3 tools/task_status.py TKT-… "REVIEW" --title "New invoice flow" --pr owner/repo#12
  python3 tools/task_status.py sweep --older-than-hours 24

The printed line is the thread title; the lead sets it in its own native thread. A status
names where the work is, and only the task's lead sets it. WAITING ON YOU, DEPLOYED ON STAGE,
DEPLOYED ON PROD and DONE ping; the others stay quiet unless --ping asks. A quiet status still
reaches a client that shows the whole board: it goes to the `<topic>-board` topic, which the stock
apps do not subscribe to. DONE is refused until the KPI store shows verified success, so "done"
never reaches the owner without proof.
`sweep` sends one summary of tasks still open past the age limit, for a daily timer, because a
task that died cannot report itself.

Pings go to the owner's private ntfy server, named in ~/.config/devstack/notify.json
(DEVSTACK_NOTIFY overrides; examples/notify.example.json shows the shape). With no such file
the title still prints and nothing is sent, so a copy without a server works unchanged. A
configured server that fails exits 1 with the reason; the status itself stays valid and the
task continues. Titles and notes are metadata: no secrets. Python 3.9+, standard library only.

Each status message is readable as it stands and also carries typed fields, so a client never has
to parse the display title: the message is the task title, then the note on a second line, and the
tags are `ds:1`, `task:`, `status:` (the status in lower case with hyphens), `at:` (sender time in
milliseconds, because ntfy keeps whole seconds) and, when known, `project:`, `host:`, `thread:` and
`pr:`. Project comes from the KPI store, host from `host` in notify.json or else the KPI store,
and thread from --thread or T3CODE_THREAD_ID. Unknown fields are left out, never guessed.
"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "monitoring/devstack"))
import task_kpi  # noqa: E402

# status -> (colour, ntfy priority when it pings, or None when it stays quiet)
STATUSES = {
    "WAITING ON YOU": ("🔴", 4),
    "IN PROGRESS": ("🟡", None),
    "DEPLOYED ON STAGE": ("🔵", 3),
    "DEPLOYED ON PROD": ("🔵", 3),
    "REVIEW": ("🟣", None),
    "RETRO": ("⚪", None),
    "DONE": ("🟢", 2),
}
FORCED_PRIORITY = 3
BOARD_PRIORITY = 1
BOARD_SUFFIX = "-board"
TICKET = re.compile(r"TKT-[0-9]{1,12}")
THREAD = re.compile(r"[A-Za-z0-9:%_.-]{1,200}")
PULL_REQUEST = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]{1,8}")
HOST = re.compile(r"[A-Za-z0-9_-]{1,32}")
PROJECT = re.compile(r"[A-Za-z0-9_.-]{1,64}")
DEPLOYED = ("DEPLOYED ON STAGE", "DEPLOYED ON PROD")
MAX_TITLE, MAX_NOTE = 120, 300
SWEEP_LIST = 8


def config_path():
    return Path(os.environ.get("DEVSTACK_NOTIFY") or Path.home() / ".config/devstack/notify.json")


def load_config():
    """The server to ping, or None when this copy has none. A broken file raises ValueError."""
    path = config_path()
    if not path.is_file():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"unreadable {path}: {error}") from None
    url, topic = (config.get("url"), config.get("topic")) if isinstance(config, dict) else (None, None)
    if not (isinstance(url, str) and url.startswith(("http://", "https://"))
            and isinstance(topic, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,58}", topic)):
        raise ValueError(f"{path} needs an http(s) url and a simple topic")
    host = config.get("host")
    if host is not None and not (isinstance(host, str) and HOST.fullmatch(host)):
        raise ValueError(f"{path} has an invalid host")
    return {"url": url.rstrip("/"), "topic": topic, "host": host}


def one_line(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def send(config, title, message, priority, click=None, tags=None, topic=None):
    body = {"topic": topic or config["topic"], "title": title, "message": message, "priority": priority}
    if click:
        body["click"] = click
    if tags:
        body["tags"] = tags
    request = urllib.request.Request(config["url"], data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=8):
        pass


def deliver(title, message, priority, click=None, tags=None, quiet=False, known_host=None):
    """Send one message. 0 when sent or not configured; 1 with the reason on stderr otherwise."""
    try:
        config = load_config()
        if config is None:
            if not quiet:
                print("notifications not configured; nothing sent", file=sys.stderr)
            return 0
        host = config["host"] or known_host
        if tags and host:
            tags = [*tags, f"host:{host}"]
        send(config, title, message, priority, click, tags,
             config["topic"] + BOARD_SUFFIX if quiet else None)
    except (ValueError, OSError, http.client.HTTPException) as error:  # URLError and timeouts are OSError
        print(f"ping FAILED, status still set: {error}", file=sys.stderr)
        return 1
    return 0


def has_proof(task_id, db):
    return known_task(task_id, db).get("verified_success") is True


def known_task(task_id, db):
    """What the KPI store knows about this task, or {}: a bad store must never cost a ping."""
    try:
        snapshot = task_kpi.latest_snapshot(db, task_id)
    except (sqlite3.Error, ValueError, TypeError, OSError):
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def clean(value, pattern):
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def typed_fields(args, task, thread):
    fields = {"project": clean(task.get("topic"), PROJECT), "thread": thread, "pr": args.pr}
    tags = ["ds:1", f"task:{args.task}", f"status:{args.status.lower().replace(' ', '-')}",
            f"at:{int(time.time() * 1000)}"]
    return tags + [f"{name}:{value}" for name, value in fields.items() if value]


def set_status(args):
    if not TICKET.fullmatch(args.task):
        return usage(f"not a task reference: {args.task}")
    if args.status not in STATUSES:
        return usage(f"unknown status {args.status!r}; use one of: {', '.join(STATUSES)}")
    if args.url and not args.url.startswith(("http://", "https://")):
        return usage("--url must be http(s)")
    if args.thread and not THREAD.fullmatch(args.thread):
        return usage("--thread is not a thread id")
    if args.pr and not PULL_REQUEST.fullmatch(args.pr):
        return usage("--pr must look like owner/repo#12")
    if args.status == "DONE" and not has_proof(args.task, args.db):
        return usage(f"{args.task} has no recorded proof. Record it with task_kpi.py finish "
                     "--verified yes, or set WAITING ON YOU and say what is missing.")
    colour, priority = STATUSES[args.status]
    title = one_line(args.title, MAX_TITLE)
    print(f"{colour} [{args.task} · {args.status}] {title}")
    if args.status in DEPLOYED and not (args.url or args.how):
        return usage(f"nothing sent: {args.status} needs --url, or --how when there is no web page to test.")
    quiet = priority is None and not args.ping
    note = " ".join(part for part in (args.how, args.note) if part)
    message = f"{title}\n{one_line(note, MAX_NOTE)}" if note else title
    task = known_task(args.task, args.db)
    inherited = os.environ.get("T3CODE_THREAD_ID", "")
    thread = args.thread or (inherited if THREAD.fullmatch(inherited) else None)
    return deliver(f"{colour} {args.status} · {args.task}", message,
                   BOARD_PRIORITY if quiet else priority or FORCED_PRIORITY, args.url,
                   typed_fields(args, task, thread), quiet, clean(task.get("host"), HOST))


def open_tasks(db, older_than_hours, now=None):
    """[(ticket, topic, age in hours)] oldest first: tasks whose latest snapshot is still open."""
    if not Path(db).is_file():
        return []
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)) as con:
        try:
            rows = con.execute("SELECT id, body FROM snapshots ORDER BY id, revision").fetchall()
        except sqlite3.OperationalError:  # store exists but has no snapshots yet
            return []
    latest = {task: json.loads(body) for task, body in rows if TICKET.fullmatch(task)}
    now = now or datetime.now(timezone.utc)
    found = []
    for task, snapshot in latest.items():
        started = datetime.fromisoformat(snapshot["started_at"].replace("Z", "+00:00"))
        if snapshot.get("status") == "open" and now - started >= timedelta(hours=older_than_hours):
            found.append((started, task, snapshot.get("topic", "?")))
    return [(task, topic, int((now - started).total_seconds() // 3600))
            for started, task, topic in sorted(found)]


def sweep(args):
    found = open_tasks(args.db, args.older_than_hours)
    if not found:
        return 0
    lines = [f"{task} {topic} {age}h" for task, topic, age in found[:SWEEP_LIST]]
    if len(found) > SWEEP_LIST:
        lines.append(f"and {len(found) - SWEEP_LIST} more")
    print("\n".join(lines))
    return deliver(f"⚫ {len(found)} open past {args.older_than_hours}h, may be stalled",
                   "\n".join(lines), FORCED_PRIORITY)


def usage(message):
    print(f"task_status: {message}", file=sys.stderr)
    return 2


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # a Windows console defaults to cp1252, which has no status colours
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--db", default=task_kpi.DEFAULT_DB, help=argparse.SUPPRESS)
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["sweep"]:
        sub = argparse.ArgumentParser(prog="task_status.py sweep", parents=[parser], add_help=False)
        sub.add_argument("--older-than-hours", type=int, default=24)
        return sweep(sub.parse_args(argv[1:]))
    parser.add_argument("task", help="TKT-… reference")
    parser.add_argument("status", help=", ".join(STATUSES))
    parser.add_argument("--title", required=True, help="Short task title, without the reference")
    parser.add_argument("--url", help="Link the ping opens. A deployed status needs this or --how")
    parser.add_argument("--how", help="How to test a deployment with no web page, for example a TestFlight build")
    parser.add_argument("--note", help="One line for the owner")
    parser.add_argument("--ping", action="store_true", help="Ping even for a status that stays quiet")
    parser.add_argument("--thread", help="T3 thread id, when T3CODE_THREAD_ID does not name the right one")
    parser.add_argument("--pr", help="The task's pull request, as owner/repo#12")
    return set_status(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
