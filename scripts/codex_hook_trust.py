#!/usr/bin/env python3
"""Approve DevStack's own Codex hooks the same way Codex's /hooks screen does.

It asks Codex's app-server for the hook inventory (hooks/list), keeps only hooks in the
user's ~/.codex/hooks.json whose command is exactly the form DevStack's installer writes for
this setup's own scripts, shows each one in full, and on confirmation writes Codex's own
current hash through config/batchWrite. Anything else is never trusted.

  python3 scripts/codex_hook_trust.py            # list, ask, approve
  python3 scripts/codex_hook_trust.py --dry-run  # list only
  python3 scripts/codex_hook_trust.py --yes      # approve without the question
"""
import argparse
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_doctor  # noqa: E402  (exact-form recognisers shared with the setup check)

ROOT = setup_doctor.SELF_ROOT
HOSTS = ("mac", "devbox", "windows")
NEEDS_REVIEW = ("untrusted", "modified")
TOOL_EVENTS = ("Stop", "PostToolUse")


def trusted_interpreters():
    """This machine's own Python installations: the one running this script and python3/python on PATH or in standard places."""
    found = {Path(sys.executable).resolve()}
    for name in ("python3", "python"):
        if shutil.which(name):
            found.add(Path(shutil.which(name)).resolve())
    for fixed in ("/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"):
        if Path(fixed).is_file():
            found.add(Path(fixed).resolve())
    return found


def is_devstack_hook(command, interpreters=None):
    """True only for the installer's exact command form: a real local Python running THIS setup's scripts."""
    parts = setup_doctor.canonical_argv(command)
    script, rest = setup_doctor.invoked_script(parts)
    if not script or Path(parts[0]).resolve() not in (interpreters or trusted_interpreters()):
        return False
    target = Path(script).resolve()
    if target == (ROOT / "scripts/setup_doctor.py").resolve():
        return any(rest == ["--host", host, "--hook", "codex"] for host in HOSTS)
    if target == (ROOT / "monitoring/devstack/kpi_monitor.py").resolve():
        return any(rest == ["audit-hook", "--host", host, "--runtime", "codex", "--event", event]
                   for host in HOSTS for event in TOOL_EVENTS)
    return False


def shown(text):
    """Command as printable text: control characters and non-ASCII are made visible."""
    return text.encode("unicode_escape").decode("ascii")


class AppServer:
    def __init__(self, codex=None, timeout=60):
        codex = codex or shutil.which("codex.cmd") or shutil.which("codex")
        if not codex:
            raise SystemExit("Codex CLI not found on PATH")
        self.timeout = timeout
        self.proc = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()  # bounded waits on every platform
        self.next_id = 0
        self.call("initialize", {"clientInfo": {"name": "devstack-hook-trust", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "initialized"})

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, message, deadline=None):
        """Write one message; a server that stops reading cannot block past the deadline."""
        def write():
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        writer.join(max(0.0, (deadline or time.monotonic() + self.timeout) - time.monotonic()))
        if writer.is_alive():
            raise SystemExit(f"codex app-server stopped reading; gave up after {self.timeout} s")

    def call(self, method, params):
        self.next_id += 1
        deadline = time.monotonic() + self.timeout
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}, deadline)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SystemExit(f"{method}: no answer from codex app-server within {self.timeout} s")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise SystemExit(f"{method}: codex app-server exited")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") == self.next_id:
                if "error" in message:
                    raise SystemExit(f"{method} failed: {message['error'].get('message', 'error')}")
                return message["result"]

    def close(self):
        self.proc.kill()  # also ends a writer thread blocked on a full pipe


def command_of(hook):
    return str(hook.get("command") or (hook.get("handler") or {}).get("command") or "")


def devstack_hooks(server, home):
    user_file = (home / ".codex" / "hooks.json").as_posix()
    inventory = server.call("hooks/list", {"cwds": [str(home)]})["data"][0]["hooks"]
    interpreters = trusted_interpreters()
    found = []
    for hook in inventory:
        command = command_of(hook)
        own = hook.get("source") == "user" and hook.get("key", "").replace("\\", "/").startswith(user_file + ":")
        if own and is_devstack_hook(command, interpreters):
            found.append({"key": hook["key"], "event": hook.get("eventName"), "status": hook.get("trustStatus"),
                          "hash": hook.get("currentHash"), "command": command})
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="List DevStack hooks and their trust status only")
    parser.add_argument("--yes", action="store_true", help="Approve without asking")
    parser.add_argument("--codex", help=argparse.SUPPRESS)          # tests: a stand-in app-server
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=60, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    server = AppServer(args.codex, args.timeout)
    try:
        hooks = devstack_hooks(server, args.home)
        pending = [h for h in hooks if h["status"] in NEEDS_REVIEW and h["hash"]]
        if not hooks:
            print("No DevStack hooks found in ~/.codex/hooks.json; run monitoring/devstack/install.py first.")
            return 1
        for h in hooks:
            print(f"[{h['status']}] {h['event']}  key: {shown(h['key'])}\n    command: {shown(h['command'])}")
        if not pending:
            print("All DevStack hooks are already approved.")
            return 0
        if args.dry_run:
            print(f"{len(pending)} DevStack hook(s) need approval (dry run, nothing written).")
            return 0
        if not args.yes:
            answer = input(f"Approve these {len(pending)} DevStack hook(s) in Codex? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "j", "ja"):
                print("Nothing approved.")
                return 1
        value = {h["key"]: {"trusted_hash": h["hash"]} for h in pending}
        server.call("config/batchWrite", {"edits": [{"keyPath": "hooks.state", "value": value, "mergeStrategy": "upsert"}],
                                          "filePath": None, "expectedVersion": None, "reloadUserConfig": True})
        after = {h["key"]: h["status"] for h in devstack_hooks(server, args.home)}
        still = [k for k in value if after.get(k) != "trusted"]
        if still:
            print(f"Codex still reports {len(still)} hook(s) as not trusted: {', '.join(map(shown, still))}")
            return 1
        print(f"Approved {len(value)} DevStack hook(s); Codex now reports them as trusted. Start a new Codex session to load them.")
        return 0
    finally:
        server.close()


if __name__ == "__main__":
    sys.exit(main())
