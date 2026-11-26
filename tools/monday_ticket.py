#!/usr/bin/env python3
"""Ticket numbers and status on a Monday board. Agents run this; people never do.

  monday_ticket.py check                                   is the token set up and the board reachable?
  monday_ticket.py parents                                 list roadmap items available as ticket parents (JSON lines)
  monday_ticket.py setup                                   where to create a token (prints the page, opens nothing)
  monday_ticket.py setup --store FILE                      store a token from FILE (owner-only), then check
  monday_ticket.py new --parent ITEM_ID --title "Tittel"   a subitem under ITEM_ID with the next TKT number
  monday_ticket.py status TKT-n "IN PROGRESS" [--item ID]  set the subitem's status from a Patstack status
  monday_ticket.py find TKT-n                              every subitem with that number, one JSON line each
  monday_ticket.py link TKT-n URL [--item ID]              post a link (for example the PR) as an update
  monday_ticket.py renumber --item ID                      give one subitem a fresh number

A ticket is a subitem of the configured board. It has two names. Its identity is Monday's own
subitem ID, which Monday guarantees unique. Its label is the short number in the subitems'
ticket column (`TKT-n`), which people and agents use in titles, branches and PRs.

`new` creates the subitem, writes the highest number + 1 and reads it back; if another subitem
holds that number too, the lower subitem ID keeps it and this one takes the next. Monday has no
lock or atomic counter, so an agent that stalls between reading and writing can still, rarely,
leave two subitems with one number. That never mixes two tickets up: every command resolves a
number to a subitem ID on the board at the moment of the write: a number on one subitem is that
subitem; a number on several is refused with each candidate listed, until `--item ID` names one
of them (the agent keeps the ID that `new` printed). An `--item` that does not hold the number is
refused too. Monday has no conditional write, so a renumber landing between the lookup and the
write cannot be prevented; every write reads the board again afterwards and fails loudly, naming
the subitem it changed, when the number has moved. The newer of the two then takes a fresh number with `renumber`.

Config: PATSTACK_MONDAY_CONFIG, else ~/.config/patstack/monday.json, else the one bundled
project-packs/<name>/monday.json. Token: PATSTACK_MONDAY_TOKEN_FILE, else
~/.config/patstack/monday-token (mode 0600). The token is never printed.

Scope: the config names one workspace, one board and its subitems board. Before any other call,
every command checks on Monday that both boards exist and sit in that workspace, and refuses to
run otherwise. Writes only ever touch subitems of that board. The tool never creates boards,
items outside it, or columns, and touches no other workspace. Exit 0 ok, 1 failed or not set up, 2 usage, 3 when `find`
shows several subitems. Standard library only.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.monday.com/v2"
API_VERSION = "2025-04"
TICKET = re.compile(r"TKT-([0-9]{1,12})")
MAX_TRIES = 8
AMBIGUOUS = 3           # exit code of `find` when several subitems hold the number


class MondayError(Exception):
    """A failure that is safe to show: it never contains the token."""


class NoConfig(MondayError):
    """No team board is configured here at all, as opposed to a configuration that is broken."""


class NoToken(MondayError):
    """This machine has no Monday token yet, as opposed to a token file that cannot be read."""


def present(path):
    """Whether PATH exists in any form; a dangling link counts. Raises OSError when that cannot be told
    (for example a folder this user may not read), so "cannot tell" is never mistaken for "absent"."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    return True


def read_regular(path):
    """The text of PATH, which must be a regular file once links are followed. A FIFO or device would block
    the read for ever, and a folder is not a file: each is refused as broken instead."""
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise MondayError(f"{path} is not a regular file")
    return Path(path).read_text(encoding="utf-8")


def pack_configs(root):
    """Every project-packs/<name>/monday.json under ROOT, probed folder by folder (glob would hide a
    folder that cannot be read)."""
    try:
        folders = sorted((Path(root) / "project-packs").iterdir())
    except FileNotFoundError:
        return []
    return [folder / "monday.json" for folder in folders if present(folder / "monday.json")]


def config_path(root=ROOT, home=None, env=None):
    """Where the team board configuration is. HOME and ENV default to this user's; the setup tools pass
    theirs, so every tool agrees on what is absent and what is broken."""
    override = (os.environ if env is None else env).get("PATSTACK_MONDAY_CONFIG")
    if override:
        return Path(override)
    private = (Path.home() if home is None else Path(home)) / ".config/patstack/monday.json"
    try:
        if present(private):
            return private
        found = pack_configs(root)
    except OSError as error:  # a folder this user cannot inspect: broken, never "absent"
        where = getattr(error, "filename", None) or private
        raise MondayError(f"cannot look for the Monday config ({where}): {error.__class__.__name__}") from None
    if len(found) > 1:
        raise MondayError("more than one bundled monday.json; put the one you want in ~/.config/patstack/monday.json")
    if not found:
        raise NoConfig("no Monday config: no project-packs/<pack>/monday.json and no ~/.config/patstack/monday.json")
    return found[0]


def load_config(root=ROOT, home=None, env=None):
    """The team board configuration. NoConfig when none exists; any other MondayError means one exists
    (an override, a private file, a pack file) but is missing, unreadable or invalid."""
    path = config_path(root, home, env)
    try:
        data = json.loads(read_regular(path))
    except FileNotFoundError:
        raise MondayError(f"the Monday config {path} is named but missing") from None
    except (OSError, ValueError) as error:
        raise MondayError(f"unreadable Monday config {path}: {error.__class__.__name__}") from None
    if not isinstance(data, dict):
        raise MondayError(f"invalid Monday config {path}")
    columns = data.get("columns")
    if not (isinstance(data.get("account"), str) and re.fullmatch(r"[a-z0-9-]{1,63}", data["account"])
            and all(isinstance(data.get(k), int) and not isinstance(data.get(k), bool) and data[k] > 0
                    for k in ("workspace", "board", "subitems_board", "first_number"))
            and isinstance(columns, dict) and all(isinstance(columns.get(k), str) for k in ("ticket", "status", "person"))
            and isinstance(data.get("statuses"), dict)):
        raise MondayError(f"invalid Monday config {path}")
    return data


def token_path(home=None, env=None):
    override = (os.environ if env is None else env).get("PATSTACK_MONDAY_TOKEN_FILE")
    return Path(override) if override else (Path.home() if home is None else Path(home)) / ".config/patstack/monday-token"


def read_token(home=None, env=None):
    """The stored token. NoToken only when nothing exists at its path; a file or link that exists but
    cannot be used (unreadable, not UTF-8, empty, a link to nothing) is a plain MondayError."""
    path = token_path(home, env)
    try:
        token = read_regular(path).strip(" \r\n")
    except FileNotFoundError:
        try:
            there = present(path)
        except OSError as error:
            raise MondayError(f"unreadable Monday token file {path}: {error.__class__.__name__}") from None
        if there:
            raise MondayError(f"the Monday token file {path} is a link to nothing") from None
        raise NoToken(f"no Monday token at {path}; run `monday_ticket.py setup`") from None
    except (OSError, ValueError) as error:  # ValueError: not UTF-8
        raise MondayError(f"unreadable Monday token file {path}: {error.__class__.__name__}") from None
    if not token or any(not 33 <= ord(c) <= 126 for c in token):
        raise MondayError(f"the Monday token file {path} is empty or malformed")
    return token


def store_token(source):
    """Copy a token from SOURCE into the private token file (0600), never echoing it."""
    try:
        token = read_regular(source).strip(" \r\n")
    except (OSError, ValueError) as error:
        raise MondayError(f"cannot read the token to store ({source}): {error.__class__.__name__}") from None
    if not token or any(not 33 <= ord(c) <= 126 for c in token):
        raise MondayError("the token to store is empty or malformed")
    path = token_path()
    try:
        return _write_token(path, token)
    except OSError as error:
        raise MondayError(f"cannot store the token at {path}: {error.__class__.__name__}") from None


def _write_token(path, token):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise MondayError(f"{path} is a symlink; refusing to write through it")
    # A new owner-only file, then an atomic swap: the token never sits in a file others can read,
    # even when an older token file had looser permissions.
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(token + "\n")
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Authenticated calls never follow a redirect, so the token cannot reach another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


class Api:
    """One method per Monday call. Tests replace this with a fake."""

    def __init__(self, token, cfg, timeout=45, tries=3):
        self.token, self.cfg, self.timeout, self.tries = token, cfg, timeout, tries

    def _q(self, query, variables=None, retry=True):
        """One API call. RETRY repeats a timed-out or 5xx call (self.tries in all); only for calls that are
        safe to repeat (reads and setting a value). Creating a subitem or posting an update is never repeated."""
        request = urllib.request.Request(API, method="POST", data=json.dumps(
            {"query": query, "variables": variables or {}}).encode("utf-8"),
            headers={"Authorization": self.token, "Content-Type": "application/json", "API-Version": API_VERSION})
        tries = self.tries if retry else 1
        for attempt in range(tries):
            try:
                with OPENER.open(request, timeout=self.timeout) as response:
                    data = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if 300 <= error.code < 400:
                    raise MondayError(f"Monday API answered a redirect (HTTP {error.code}); refused") from None
                if not (error.code >= 500 and attempt < tries - 1):
                    raise MondayError(f"Monday API answered HTTP {error.code}") from None
            except (OSError, ValueError) as error:
                if not (isinstance(error, OSError) and attempt < tries - 1):
                    raise MondayError(f"Monday API unreachable: {error.__class__.__name__}") from None
            time.sleep(2 * (attempt + 1))
        if data.get("errors") or data.get("error_message"):
            messages = [e.get("message", "") for e in data.get("errors") or []] or [data.get("error_message", "")]
            raise MondayError("Monday API error: " + "; ".join(m[:200] for m in messages))
        return data["data"]

    def me(self):
        return self._q("{ me { id name } }")["me"]

    def boards(self):
        ids = [self.cfg["board"], self.cfg["subitems_board"]]
        return self._q("query($ids: [ID!]) { boards(ids: $ids) { id name workspace { id } columns { id } } }",
                       {"ids": ids})["boards"]

    def item_board(self, item_id):
        items = self._q("query($ids: [ID!]) { items(ids: $ids) { id board { id } } }", {"ids": [item_id]})["items"]
        return int(items[0]["board"]["id"]) if items else None

    def parents(self):
        """All roadmap items, including pages after the first 500; no subitems or writes."""
        found, cursor = [], None
        while True:
            if cursor is None:
                page = self._q("query($board: [ID!]) { boards(ids: $board) { items_page(limit: 500) {"
                               " cursor items { id name } } } }", {"board": [self.cfg["board"]]})["boards"][0]["items_page"]
            else:
                page = self._q("query($cursor: String!) { next_items_page(cursor: $cursor, limit: 500) {"
                               " cursor items { id name } } }", {"cursor": cursor})["next_items_page"]
            found.extend({"id": int(item["id"]), "name": item["name"]} for item in page["items"])
            cursor = page.get("cursor")
            if not cursor:
                return found

    def create_subitem(self, parent, title, values):
        query = ("mutation($parent: ID!, $name: String!, $values: JSON) { create_subitem(parent_item_id: $parent,"
                 " item_name: $name, column_values: $values, create_labels_if_missing: false) { id board { id } } }")
        made = self._q(query, {"parent": parent, "name": title, "values": json.dumps(values)}, retry=False)["create_subitem"]
        return int(made["id"]), int(made["board"]["id"])

    def numbers(self):
        """[(subitem id, number)] for every subitem with a number."""
        found, cursor, column = [], None, self.cfg["columns"]["ticket"]
        first = ("query($board: [ID!], $col: [String!]) { boards(ids: $board) { items_page(limit: 500) {"
                 " cursor items { id column_values(ids: $col) { text } } } } }")
        nxt = ("query($cursor: String!, $col: [String!]) { next_items_page(cursor: $cursor, limit: 500) {"
               " cursor items { id column_values(ids: $col) { text } } } }")
        while True:
            if cursor is None:
                page = self._q(first, {"board": [self.cfg["subitems_board"]], "col": [column]})["boards"][0]["items_page"]
            else:
                page = self._q(nxt, {"cursor": cursor, "col": [column]})["next_items_page"]
            for item in page["items"]:
                text = (item["column_values"][0]["text"] or "").strip() if item["column_values"] else ""
                if re.fullmatch(r"[0-9]+(\.0+)?", text):
                    found.append((int(item["id"]), int(float(text))))
            cursor = page.get("cursor")
            if not cursor:
                return found

    def set_number(self, item_id, number):
        self._q("mutation($board: ID!, $item: ID!, $col: String!, $value: String) { change_simple_column_value("
                "board_id: $board, item_id: $item, column_id: $col, value: $value) { id } }",
                {"board": self.cfg["subitems_board"], "item": item_id, "col": self.cfg["columns"]["ticket"],
                 "value": str(number)})

    def by_number(self, number):
        """[(id, name, parent name, status)] of subitems whose ticket column holds NUMBER."""
        query = ("query($board: ID!, $col: String!, $val: [String]!, $status: [String!]) {"
                 " items_page_by_column_values(board_id: $board, limit: 100, columns: [{column_id: $col, column_values: $val}])"
                 " { items { id name parent_item { name } column_values(ids: $status) { text } } } }")
        page = self._q(query, {"board": self.cfg["subitems_board"], "col": self.cfg["columns"]["ticket"],
                               "val": [str(number)], "status": [self.cfg["columns"]["status"]]})
        return [(int(i["id"]), i["name"], (i.get("parent_item") or {}).get("name"),
                 (i["column_values"][0]["text"] if i["column_values"] else None))
                for i in page["items_page_by_column_values"]["items"]]

    def set_status(self, item_id, label):
        self._q("mutation($board: ID!, $item: ID!, $col: String!, $value: JSON!) { change_column_value("
                "board_id: $board, item_id: $item, column_id: $col, value: $value) { id } }",
                {"board": self.cfg["subitems_board"], "item": item_id, "col": self.cfg["columns"]["status"],
                 "value": json.dumps({"label": label})})

    def add_update(self, item_id, body):
        self._q("mutation($item: ID!, $body: String!) { create_update(item_id: $item, body: $body) { id } }",
                {"item": item_id, "body": body}, retry=False)


def subitem_url(cfg, item_id):
    return f"https://{cfg['account']}.monday.com/boards/{cfg['subitems_board']}/pulses/{item_id}"


def in_scope(api, cfg):
    """{board id: board} for the two configured boards, after proving both sit in the configured
    workspace. Anything else is refused: this tool works on that board and nowhere else."""
    boards = {int(b["id"]): b for b in api.boards()}
    for key in ("board", "subitems_board"):
        board = boards.get(cfg[key])
        if board is None:
            raise MondayError(f"board {cfg[key]} is not visible to this token; refusing")
        workspace = int((board.get("workspace") or {}).get("id") or 0)
        if workspace != cfg["workspace"]:
            raise MondayError(f"board {cfg[key]} is in workspace {workspace or 'unknown'}, outside the configured "
                              f"scope (workspace {cfg['workspace']}); refusing")
    return boards


def check(api, cfg):
    me = api.me()
    boards = in_scope(api, cfg)
    columns = {c["id"] for c in boards[cfg["subitems_board"]]["columns"]}
    missing = [c for c in cfg["columns"].values() if c not in columns]
    if missing:
        raise MondayError("the subitems board lacks column(s) " + ", ".join(missing))
    return (f"Monday OK: token for {me['name']}; board {boards[cfg['board']]['name']} in workspace "
            f"{cfg['workspace']}; ticket column present")


def allocate(api, cfg, item_id, pause=1.0):
    """Give ITEM_ID the next free number; the lower subitem ID wins a tie. See the module text for
    what this cannot rule out and how a shared number is handled."""
    for _ in range(MAX_TRIES):
        taken = [n for i, n in api.numbers() if i != item_id]
        number = max([cfg["first_number"] - 1] + taken) + 1
        api.set_number(item_id, number)
        settled = True
        for _ in range(2):  # twice, a pause apart, to catch a lower subitem that wrote just after the first look
            time.sleep(pause)
            holders = [i for i, *_ in api.by_number(number)]
            # confirmed only while this subitem itself still holds the number (another agent may have
            # renumbered it meanwhile) and no older subitem holds it too
            if item_id not in holders or any(other < item_id for other in holders if other != item_id):
                settled = False
                break
        if settled:
            return number
    raise MondayError(f"could not settle a unique number for subitem {item_id} after {MAX_TRIES} tries")


def new(api, cfg, parent, title, pause=1.0):
    if api.item_board(parent) != cfg["board"]:
        raise MondayError(f"item {parent} is not on board {cfg['board']}; choose a roadmap item as parent")
    me = api.me()
    values = {cfg["columns"]["person"]: {"personsAndTeams": [{"id": int(me["id"]), "kind": "person"}]}}
    label = cfg["statuses"].get("IN PROGRESS")
    if label:
        values[cfg["columns"]["status"]] = {"label": label}
    item_id, board = api.create_subitem(parent, title, values)
    if board != cfg["subitems_board"]:
        raise MondayError(f"Monday created subitem {item_id} on board {board}, not the configured subitems board")
    number = allocate(api, cfg, item_id, pause)
    return number, item_id


def resolve(api, cfg, number, item=None):
    """The subitem a ticket number means, read from the board at the moment of the write.

    The number must be on exactly one subitem, or ITEM must be one of the subitems holding it right
    now. Anything else (no holder, several holders, or ITEM holding another number or none) is refused
    with what was found, so a write never lands on a subitem the number does not point to."""
    found = sorted(api.by_number(number))
    if item is not None:
        if item in [i for i, *_ in found]:
            return item
        holders = ", ".join(str(i) for i, *_ in found) or "none"
        raise MondayError(f"subitem {item} does not hold TKT-{number} (holders now: {holders}); "
                          "check the number, or `find` it again")
    if not found:
        raise MondayError(f"TKT-{number} is not on the Monday board")
    if len(found) > 1:
        listed = "; ".join(f"{i} \"{name}\" under \"{parent}\"" for i, name, parent, _ in found)
        raise MondayError(f"TKT-{number} is on {len(found)} subitems: {listed}. Pass --item ID for the one you "
                          "mean (yours is the ID `new` printed); the newer one (higher ID) should take a fresh "
                          "number with `renumber --item ID`")
    return found[0][0]


def write_checked(api, cfg, number, item, write):
    """Resolve NUMBER on the board, apply WRITE(subitem ID), then read the board again. Monday has no
    conditional write, so a renumber that lands between the lookup and the write (or during a retry)
    cannot be prevented; it is caught here and reported as a failure naming the subitem that was
    changed, never confirmed as success. Returns the subitem ID written."""
    target = resolve(api, cfg, number, item)
    write(target)
    holders = [i for i, *_ in api.by_number(number)]
    if target not in holders:
        now = ", ".join(str(i) for i in sorted(holders)) or "none"
        raise MondayError(f"TKT-{number} moved during the update: subitem {target} was changed but no longer "
                          f"holds TKT-{number} (holders now: {now}). Check subitem {target} on the board, then "
                          "repeat the update for the right ticket")
    return target


def parse_ticket(text):
    match = TICKET.fullmatch(text or "")
    if not match:
        raise MondayError(f"not a ticket reference: {text!r}")
    return int(match.group(1))


def sync_status(task, status, root=ROOT, timeout=8, deadline=15):
    """For task_status.py, after the status went out: mirror it to the ticket and return the line to show,
    or None when Monday is not set up here or the number or status has no board counterpart. One attempt
    per call, and the whole update has a hard DEADLINE in seconds; past it the status is reported as not
    updated (the call may still land) and task_status returns at once."""
    try:
        cfg = load_config(root)
    except NoConfig:
        return None
    except MondayError as error:  # a board is configured but its config is broken: say so
        return f"monday: {task} NOT updated ({error})"
    try:
        number = parse_ticket(task)
    except MondayError:
        return None
    label = cfg["statuses"].get(status)
    if number < cfg["first_number"] or not label:
        return None  # an older machine-issued number has no subitem; RETRO has no board status
    try:
        token = read_token()
    except NoToken:
        return None
    except MondayError as error:
        return f"monday: {task} NOT updated ({error})"
    outcome = {}

    def work():
        try:
            api = Api(token, cfg, timeout=timeout, tries=1)
            in_scope(api, cfg)
            write_checked(api, cfg, number, None, lambda target: api.set_status(target, label))
            outcome["line"] = f"monday: {task} -> {label}"
        except MondayError as error:
            outcome["line"] = f"monday: {task} NOT updated ({error})"
        except Exception as error:  # never let the mirror break the status command
            outcome["line"] = f"monday: {task} NOT updated ({error.__class__.__name__})"

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(deadline)
    return outcome.get("line") or f"monday: {task} NOT confirmed within {deadline}s; check it with `find`"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("parents")
    setup = sub.add_parser("setup")
    setup.add_argument("--store", metavar="FILE", help="store the token from FILE, then check")
    made = sub.add_parser("new")
    made.add_argument("--parent", required=True, type=int, help="roadmap item ID the ticket belongs under")
    made.add_argument("--title", required=True)
    for name in ("status", "find", "link"):
        p = sub.add_parser(name)
        p.add_argument("ticket")
        if name == "status":
            p.add_argument("status")
        if name == "link":
            p.add_argument("url")
        if name != "find":
            p.add_argument("--item", type=int, help="subitem ID, when several subitems hold the number")
    again = sub.add_parser("renumber")
    again.add_argument("--item", required=True, type=int, help="subitem ID that takes a fresh number")
    args = parser.parse_args(argv)
    try:
        cfg = load_config()
        if args.command == "setup":
            if not args.store:
                print(f"Create a personal API token at https://{cfg['account']}.monday.com/apps/manage/tokens "
                      "(profile picture > Developers > My access tokens), then store it with --store FILE.")
                return 0
            print(f"stored token at {store_token(args.store)}")
        api = Api(read_token(), cfg)
        if args.command not in ("check", "setup"):
            in_scope(api, cfg)  # every command proves the scope before it reads or writes
        if args.command in ("check", "setup"):
            print(check(api, cfg))
        elif args.command == "parents":
            for item in api.parents():
                print(json.dumps(item))
        elif args.command == "new":
            title = " ".join(args.title.split())[:255]
            if not title:
                raise MondayError("--title is empty")
            number, item_id = new(api, cfg, args.parent, title)
            print(f"TKT-{number} {item_id} {subitem_url(cfg, item_id)}")
        elif args.command == "renumber":
            if api.item_board(args.item) != cfg["subitems_board"]:
                raise MondayError(f"item {args.item} is not a subitem of board {cfg['board']}")
            number = allocate(api, cfg, args.item)
            print(f"TKT-{number} {args.item} {subitem_url(cfg, args.item)}")
        elif args.command == "find":
            number = parse_ticket(args.ticket)
            found = sorted(api.by_number(number))
            if not found:
                raise MondayError(f"{args.ticket} is not on the Monday board")
            for item_id, name, parent, status in found:
                print(json.dumps({"ticket": args.ticket, "id": item_id, "name": name, "parent": parent, "status": status,
                                  "url": subitem_url(cfg, item_id)}))
            if len(found) > 1:
                print(f"monday_ticket: {args.ticket} is on {len(found)} subitems; use --item ID, and renumber the "
                      "newer one", file=sys.stderr)
                return AMBIGUOUS
        elif args.command == "status":
            label = cfg["statuses"].get(args.status)
            if label is None:
                print(f"{args.status}: no Monday status for it; nothing changed")
                return 0
            write_checked(api, cfg, parse_ticket(args.ticket), args.item, lambda target: api.set_status(target, label))
            print(f"{args.ticket} -> {label}")
        elif args.command == "link":
            if not args.url.startswith(("http://", "https://")):
                raise MondayError("the link must be http(s)")
            write_checked(api, cfg, parse_ticket(args.ticket), args.item, lambda target: api.add_update(target, args.url))
            print(f"{args.ticket}: link posted")
    except MondayError as error:
        print(f"monday_ticket: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
