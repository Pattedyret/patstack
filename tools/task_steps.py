#!/usr/bin/env python3
"""Send a Patstack task's steps: the lead's plan as a checklist, so the owner sees how far along it is.

  python3 tools/task_steps.py TKT-… <<'EOF'
  [x] Map both repos | search and profile endpoints are clear
  [x] Backend counts and endpoint | 406 tests pass
  [>] Independent review | reviewer running
  [ ] Repair findings
  [ ] Mark the PRs ready
  EOF

One line per step, in order: `[x]` done, `[>]` in progress, `[ ]` to come. After ` | ` comes one
optional line on how it went or where it stands. Send the whole list every time: once the plan is
set, and again whenever a step finishes or the plan changes. The newest list replaces the earlier
ones. Use 1 to 12 steps that name the work in the owner's words; --file reads the list from a file
instead of standard input.

A client that shows the whole board draws the list as the task's progress. It goes to the quiet
`<topic>-board` topic of the owner's private ntfy server (see task_status.py for the config) and
never pings. With no server configured the summary still prints and nothing is sent. A configured
server that fails exits 1 with the reason, and the task continues. Steps are metadata: no secrets.
Python 3.9+, standard library only.

The message is a summary line followed by the steps as written, and the tags are `ds:1`, `task:`,
`status:steps`, `at:` (sender time in milliseconds) and, when known, `project:`, `host:` and
`thread:`, the same fields task_status.py sends.
"""
import argparse
import http.client
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import task_status as ts  # noqa: E402  (the same server, limits and fields)

MAX_STEPS, MAX_TITLE, MAX_DETAIL = 12, 80, 160
MAX_MESSAGE_BYTES = 3800  # ntfy turns a message over 4096 bytes into an attachment
STEP = re.compile(r"\[([xX> ])\] (.+)")
DETAIL_MARK = " | "


def read_steps(text):
    """The list as (mark, title, detail) rows. Raises ValueError naming the first line that is not a step."""
    steps = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        match = STEP.fullmatch(line)
        if not match:
            raise ValueError(f"line {number} is not a step: start it with [x], [>] or [ ] and a space")
        title, _, detail = match.group(2).partition(DETAIL_MARK)
        title = ts.one_line(title, MAX_TITLE)
        if not title:
            raise ValueError(f"line {number} has no step name")
        steps.append((match.group(1).lower(), title, ts.one_line(detail, MAX_DETAIL)))
    if not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"send 1 to {MAX_STEPS} steps, not {len(steps)}; merge small steps into one")
    return steps


def summary(steps):
    done = sum(mark == "x" for mark, _, _ in steps)
    now = next((title for mark, title, _ in steps if mark == ">"), None)
    return f"{done} of {len(steps)} steps done" + (f", now: {now}" if now else "")


def message(steps):
    """The summary and the steps, shortened only as far as one message needs: details first, then
    titles. Raises ValueError if it still does not fit, so nothing oversized is ever sent."""
    for detail_limit, title_limit in ((MAX_DETAIL, MAX_TITLE), (100, MAX_TITLE), (60, MAX_TITLE), (30, MAX_TITLE),
                                      (0, MAX_TITLE), (0, 60), (0, 40), (0, 24)):
        cut = [(mark, ts.one_line(title, title_limit), ts.one_line(detail, detail_limit) if detail_limit else "")
               for mark, title, detail in steps]
        lines = [f"[{mark}] {title}" + (f"{DETAIL_MARK}{detail}" if detail else "") for mark, title, detail in cut]
        text = "\n".join([summary(cut), *lines])
        if len(text.encode("utf-8")) <= MAX_MESSAGE_BYTES:
            return text
    raise ValueError("the steps do not fit in one message; shorten them")


def publish(task, text, tags):
    """0 when sent or not configured; 1 with the reason on stderr otherwise."""
    try:
        config = ts.load_config()
        if config is None:
            return 0
        if config["host"]:
            tags = [*tags, f"host:{config['host']}"]
        ts.send(config, f"steps · {task}", text, ts.BOARD_PRIORITY, tags=tags,
                topic=config["topic"] + ts.BOARD_SUFFIX)
    except (ValueError, OSError, http.client.HTTPException) as error:  # URLError and timeouts are OSError
        print(f"steps NOT sent: {error}", file=sys.stderr)
        return 1
    return 0


def usage(text):
    print(f"task_steps: {text}", file=sys.stderr)
    return 2


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # a Windows console defaults to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("task", help="TKT-… reference")
    parser.add_argument("--file", help="Read the steps from this file instead of standard input")
    parser.add_argument("--thread", help="T3 thread id, when T3CODE_THREAD_ID does not name the right one")
    parser.add_argument("--project", help="Repo or project slug, for example auth-api")
    args = parser.parse_args(argv)
    if not ts.TICKET.fullmatch(args.task):
        return usage(f"not a task reference: {args.task}")
    if args.thread and not ts.THREAD.fullmatch(args.thread):
        return usage("--thread is not a thread id")
    if args.project and not ts.PROJECT.fullmatch(args.project):
        return usage("--project must be a repo or project slug")
    try:
        raw = Path(args.file).read_bytes() if args.file else sys.stdin.buffer.read()
        steps = read_steps(raw.decode("utf-8", errors="replace"))
    except (OSError, ValueError) as error:
        return usage(f"nothing sent: {error}")
    try:
        text = message(steps)
    except ValueError as error:
        return usage(f"nothing sent: {error}")
    print(f"{args.task}: {summary(steps)}")
    inherited = os.environ.get("T3CODE_THREAD_ID", "")
    thread = args.thread or (inherited if ts.THREAD.fullmatch(inherited) else None)
    fields = {"project": args.project, "thread": thread}
    tags = ["ds:1", f"task:{args.task}", "status:steps", f"at:{int(time.time() * 1000)}"]
    return publish(args.task, text, tags + [f"{name}:{value}" for name, value in fields.items() if value])


if __name__ == "__main__":
    sys.exit(main())
