#!/usr/bin/env python3
"""Set a Patstack task's status: ping the owner when it matters and update the board and ticket.

  python3 tools/task_status.py TKT-… "DEPLOYED ON STAGE" --title "New invoice flow" --url URL
  python3 tools/task_status.py TKT-… "IN PROGRESS" --title "New invoice flow" --ping --note "Stage check failed, do not test yet"
  python3 tools/task_status.py TKT-… "REVIEW" --title "New invoice flow" --pr owner/repo#12

The printed line is a one-line summary; the thread title keeps only `[TKT-…] Short title`, and
the lead's native task list shows the steps. A status names the phase the work is in, and only the task's lead sets it. WAITING ON YOU, DEPLOYED ON STAGE,
DEPLOYED ON PROD and DONE ping; the others stay quiet unless --ping asks. PARKED puts a task aside
on purpose and needs --note saying why and what resumes it. A quiet status still
reaches a client that shows the whole board: it goes to the `<topic>-board` topic, which the stock
apps do not subscribe to. Set DONE only after the endpoint's proof is reported.

Pings go to the owner's private ntfy server, named in ~/.config/patstack/notify.json
(PATSTACK_NOTIFY overrides; examples/notify.example.json shows the shape). With no such file
the title still prints and nothing is sent, so a copy without a server works unchanged. A
configured server that fails exits 1 with the reason; the status itself stays valid and the
task continues. Titles and notes are metadata: no secrets. Python 3.9+, standard library only.

Each status message is readable as it stands and also carries typed fields, so a client never has
to parse the display title: the message is the task title, then the note on a second line, and the
tags are `ds:1`, `task:`, `status:` (the status in lower case with hyphens), `at:` (sender time in
milliseconds, because ntfy keeps whole seconds) and, when known, `project:`, `host:`, `thread:` and
`pr:`. Project comes from --project, host from `host` in notify.json, and thread from --thread or
T3CODE_THREAD_ID. Unknown fields are left out, never guessed.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request

# status -> (colour, ntfy priority when it pings, or None when it stays quiet)
STATUSES = {
    "WAITING ON YOU": ("🔴", 4),
    "IN PROGRESS": ("🟡", None),
    "DEPLOYED ON STAGE": ("🔵", 3),
    "DEPLOYED ON PROD": ("🔵", 3),
    "REVIEW": ("🟣", None),
    "RETRO": ("⚪", None),
    "DONE": ("🟢", 2),
    "PARKED": ("⏸", None),
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


def config_path():
    return Path(os.environ.get("PATSTACK_NOTIFY") or Path.home() / ".config/patstack/notify.json")


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


def deliver(title, message, priority, click=None, tags=None, quiet=False):
    """Send one message. 0 when sent or not configured; 1 with the reason on stderr otherwise."""
    try:
        config = load_config()
        if config is None:
            if not quiet:
                print("notifications not configured; nothing sent", file=sys.stderr)
            return 0
        host = config["host"]
        if tags and host:
            tags = [*tags, f"host:{host}"]
        send(config, title, message, priority, click, tags,
             config["topic"] + BOARD_SUFFIX if quiet else None)
    except (ValueError, OSError, http.client.HTTPException) as error:  # URLError and timeouts are OSError
        print(f"ping FAILED, status still set: {error}", file=sys.stderr)
        return 1
    return 0


def typed_fields(args, thread):
    fields = {"project": args.project, "thread": thread, "pr": args.pr}
    tags = ["ds:1", f"task:{args.task}", f"status:{args.status.lower().replace(' ', '-')}",
            f"at:{int(time.time() * 1000)}"]
    return tags + [f"{name}:{value}" for name, value in fields.items() if value]


def mirror_to_monday(task, status):
    """After the status is accepted and sent: set it on the Monday ticket, in order and with a short time
    limit (seconds, not minutes), and return the line to show. A failure is reported, never raised."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import monday_ticket
        return monday_ticket.sync_status(task, status)
    except Exception as error:  # the board is a convenience; the status has already gone out
        return f"monday: {task} NOT updated ({error.__class__.__name__})"
    finally:
        sys.path.pop(0)


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
    if args.project and not PROJECT.fullmatch(args.project):
        return usage("--project must be a repo or project slug")
    colour, priority = STATUSES[args.status]
    title = one_line(args.title, MAX_TITLE)
    print(f"{colour} [{args.task} · {args.status}] {title}")
    if args.status == "PARKED" and not (args.note or "").strip():
        return usage("nothing sent: PARKED needs --note saying why it is parked and what resumes it.")
    if args.status in DEPLOYED and not (args.url or args.how):
        return usage(f"nothing sent: {args.status} needs --url, or --how when there is no web page to test.")
    quiet = priority is None and not args.ping
    note = " ".join(part for part in (args.how, args.note) if part)
    message = f"{title}\n{one_line(note, MAX_NOTE)}" if note else title
    inherited = os.environ.get("T3CODE_THREAD_ID", "")
    thread = args.thread or (inherited if THREAD.fullmatch(inherited) else None)
    code = deliver(f"{colour} {args.status} · {args.task}", message,
                   BOARD_PRIORITY if quiet else priority or FORCED_PRIORITY, args.url,
                   typed_fields(args, thread), quiet)
    line = mirror_to_monday(args.task, args.status)
    if line:
        print(line, file=sys.stderr)
    return code


def usage(message):
    print(f"task_status: {message}", file=sys.stderr)
    return 2


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # a Windows console defaults to cp1252, which has no status colours
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("task", help="TKT-… reference")
    parser.add_argument("status", help=", ".join(STATUSES))
    parser.add_argument("--title", required=True, help="Short task title, without the reference")
    parser.add_argument("--url", help="Link the ping opens. A deployed status needs this or --how")
    parser.add_argument("--how", help="How to test a deployment with no web page, for example a TestFlight build")
    parser.add_argument("--note", help="One line for the owner")
    parser.add_argument("--ping", action="store_true", help="Ping even for a status that stays quiet")
    parser.add_argument("--thread", help="T3 thread id, when T3CODE_THREAD_ID does not name the right one")
    parser.add_argument("--pr", help="The task's pull request, as owner/repo#12")
    parser.add_argument("--project", help="Repo or project slug, for example auth-api")
    return set_status(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
