#!/usr/bin/env python3
"""Read-only Patstack setup check for one host.

Checks the source, client skill links, global instructions (and whether the shipped
template is installed), the bundled project pack, its shared product vault checkout (found,
right remote, revision, freshness; never fetched here) and benchmark folders, ticket-ref, the
merge guard hook, and hooks that point to missing files or retired Patstack tools. Changes no
configuration. Only clients in use are checked (binary on PATH or the client's own state; --clients
overrides); an unused client's rows are INFO, never FAIL. FAIL means broken setup; WARN means working but incomplete; INFO is unverifiable here. A green
result proves configuration, not that a client loaded a hook in the current session.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

SELF_ROOT = Path(__file__).resolve().parent.parent  # source setup or published checkout
CLIENTS = ("claude", "codex")
# Each client's own files (written by the client itself, never by Patstack's installer), so an install
# that wrote hooks for both clients does not make an unused client look set up.
CLIENT_STATE = {"claude": (".claude.json", ".claude/.credentials.json", ".claude/projects"),
                "codex": (".codex/config.toml", ".codex/auth.json", ".codex/sessions")}
# Retired Patstack hooks: the old task registry, the KPI recorder and the session status line.
RETIRED_HOOK = re.compile(r"agent-work-[a-z-]+\.py|kpi_monitor\.py|setup_doctor\.py\b.*--hook")
MERGE_GUARD = re.compile(r"merge_guard\.py")
SCRIPT = re.compile(r"\.(py|sh|cmd|ps1)\Z")
# The bundled pack's read-only vault tool owns the vault rules; the doctor only shows its rows.
PACK_VAULT_TOOL = "project-packs/*/tools/vault_context.py"
# First line of examples/global-instructions/AGENTS.md; kept when the template is merged by hand.
TEMPLATE_MARKER = "<!-- patstack-global-instructions -->"


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, check, detail):
        self.rows.append({"status": status, "check": check, "detail": detail})

    @property
    def failed(self):
        return any(row["status"] == "FAIL" for row in self.rows)


def hook_commands(settings):
    """Yield (event, group index, hook index, command) for command hooks."""
    for event, groups in (settings.get("hooks") or {}).items():
        for g, group in enumerate(groups or []):
            for h, hook in enumerate(group.get("hooks") or []):
                if hook.get("type", "command") == "command" and hook.get("command"):
                    yield event, g, h, hook["command"]


def split(command):
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return []


def missing_paths(command):
    parts = split(command)
    candidates = parts[:1] + [p for p in parts[1:] if SCRIPT.search(p)]
    return [p for p in candidates if Path(p).is_absolute() and not Path(p).is_file()]


def load_json(path, report, check):
    if path.exists() and not path.is_file():  # a FIFO or device would block the read
        report.add("FAIL", check, f"{path} is not a regular file")
        return None
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):  # Windows PowerShell 5 and Notepad can write one
            report.add("WARN", check, f"{path} starts with a byte-order mark; save it as UTF-8 without BOM")
        return json.loads(raw.decode("utf-8-sig"))
    except FileNotFoundError:
        report.add("FAIL", check, f"{path} is missing")
    except (OSError, ValueError) as exc:
        report.add("FAIL", check, f"{path} is unreadable: {exc.__class__.__name__}")
    return None


def detect_clients(home, which=shutil.which):
    """Clients in use on this host: the client's binary on PATH or its own state in HOME."""
    found = [name for name in CLIENTS
             if which(name) or any((Path(home) / marker).exists() for marker in CLIENT_STATE[name])]
    return found


def not_set_up(report, check, client):
    report.add("INFO", check, f"{client} not set up on this host; not checked (use --clients to check it anyway)")


def check_source(root, home, host, report, clients=CLIENTS):
    if not (root / "skills/patstack/SKILL.md").is_file():
        report.add("FAIL", "source", f"{root}/skills/patstack/SKILL.md is missing")
        return
    report.add("OK", "source", str(root))
    names = sorted(p.parent.name for p in (root / "skills").glob("*/SKILL.md"))
    mirrors = None
    if host == "windows":
        try:  # the mirror tool beside this script owns the mirror format
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import skill_mirrors as mirrors
        except ImportError:
            mirrors = None
        finally:
            sys.path.pop(0)
    for link, client in ((home / ".claude/skills", "claude"), (home / ".agents/skills", "codex")):
        name = f"skills {link.parent.name}"
        if client not in clients:
            not_set_up(report, name, client)
            continue
        if host == "windows" and not link.is_symlink():
            missing = [n for n in names if not (link / n / "SKILL.md").is_file()]
            if missing:
                report.add("FAIL", name, f"{len(missing)} of {len(names)} skill mirrors missing: {', '.join(missing[:4])}")
            elif mirrors is None:
                report.add("WARN", name, f"{len(names)} mirrors present; freshness not checked (scripts/skill_mirrors.py missing)")
            else:
                outdated = mirrors.stale((root / "skills").resolve(), link)
                broken = mirrors.broken_links(link, (root / "skills").resolve())
                unsupported = mirrors.unsupported_links((root / "skills").resolve())
                if unsupported:
                    report.add("WARN", name, f"{len(unsupported)} source link(s) use syntax the mirror tool cannot rewrite, "
                                             f"e.g. {unsupported[0][0]}:{unsupported[0][1]}")
                elif outdated:
                    report.add("WARN", name, f"{len(outdated)} mirror file(s) out of date; run scripts/skill_mirrors.py --apply")
                elif broken:
                    report.add("WARN", name, f"{len(broken)} mirror link(s) point to nothing, e.g. {broken[0][0]} -> {broken[0][1]}")
                else:
                    report.add("OK", name, f"all {len(names)} skill mirrors match the source")
            continue
        # one link for the whole skills/ directory, or one link per skill folder
        wrong = [n for n in names if (link / n).resolve() != (root / "skills" / n).resolve()]
        if wrong:
            report.add("FAIL", name, f"{len(wrong)} of {len(names)} skills do not resolve to {root / 'skills'}: {', '.join(wrong[:4])}")
        else:
            report.add("OK", name, f"all {len(names)} skills -> {root / 'skills'}")
    for path, client in ((home / ".claude/CLAUDE.md", "claude"), (home / ".codex/AGENTS.md", "codex")):
        name = f"instructions {path.parent.name}"
        if client not in clients:
            not_set_up(report, name, client)
            continue
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
        if text is None or "patstack" not in text.lower():
            report.add("FAIL", name, f"{path} missing or does not select Patstack")
        else:
            report.add("OK", name, "selects Patstack")
        if text is not None and "patstack" in text.lower():
            if TEMPLATE_MARKER in text:
                report.add("OK", f"template {path.parent.name}", "Patstack global instructions template installed")
            else:
                report.add("INFO", f"template {path.parent.name}",
                           "hand-written instructions; compare with examples/global-instructions/AGENTS.md")
    packs = sorted(root.glob("project-packs/*/INDEX.md"))
    report.add("OK" if packs else "INFO", "project pack",
               ", ".join(str(pack) for pack in packs) if packs else "no bundled project pack; configure private packs as needed")
    bench = root / "bench/bench.py"
    report.add("OK" if bench.is_file() else "INFO", "bench",
               str(bench) if bench.is_file() else f"{bench} not in this tree; optional")
    tool = home / ".local/bin" / ("ticket-ref.cmd" if host == "windows" else "ticket-ref")
    report.add("OK" if tool.is_file() else "WARN", "ticket-ref", str(tool) if tool.is_file() else f"{tool} missing; see tools/ticket-ref/README.md")


def check_pack_vault(root, home, env, report):
    """Pack vault: OK/WARN when it is configured or found, INFO when unused; never FAIL."""
    for tool in sorted(root.glob(PACK_VAULT_TOOL)):
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True  # no __pycache__ in the checkout from a read-only check
            spec = importlib.util.spec_from_file_location("patstack_pack_vault", tool)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            rows = module.doctor_rows(home, os.environ if env is None else env)
        except Exception as exc:  # a broken pack tool must not break the setup check
            report.add("WARN", "pack vault", f"vault check failed: {exc.__class__.__name__}")
            return
        finally:
            sys.dont_write_bytecode = previous
        for status, check, detail in rows:
            report.add(status if status in ("OK", "WARN", "INFO") else "WARN", check, detail)


def check_hooks(runtime, settings, report):
    """Hooks that point to missing files or to retired Patstack tools."""
    for event, g, h, command in hook_commands(settings):
        for path in missing_paths(command):
            report.add("FAIL", f"{runtime} hook", f"{event} command points to missing {path}")
        retired = RETIRED_HOOK.search(command)
        if retired:
            report.add("WARN", f"{runtime} hook", f"retired Patstack hook still wired in {event}: {retired.group()}; remove it")


def check_claude(home, report):
    settings = load_json(home / ".claude/settings.json", report, "claude settings")
    if settings is None:
        return
    if settings.get("disableAllHooks") is True:
        report.add("FAIL", "claude hooks", "disableAllHooks is true; the merge guard cannot run")
        return
    check_hooks("claude", settings, report)
    groups = (settings.get("hooks") or {}).get("PreToolUse") or []
    found = [(groups[g].get("matcher"), command) for event, g, _, command in hook_commands(settings)
             if event == "PreToolUse" and MERGE_GUARD.search(command)]
    if any(covers_bash(matcher) and runs_guard(command) for matcher, command in found):
        report.add("OK", "claude merge guard", "PreToolUse merge guard runs for Bash")
    elif found:
        report.add("WARN", "claude merge guard", "merge guard hook found, but its matcher misses Bash or its interpreter "
                                                  "or guard file is missing; see docs/setup.md")
    else:
        report.add("WARN", "claude merge guard", "merge guard not wired; add tools/merge_guard.py as a PreToolUse Bash hook (docs/setup.md)")


def covers_bash(matcher):
    """Claude Code runs a hook for every tool when the matcher is empty or *, else when it matches the tool name."""
    if matcher in (None, "", "*"):
        return True
    try:
        return re.fullmatch(matcher, "Bash") is not None
    except (re.error, TypeError):
        return False


INTERPRETER = re.compile(r"(python(\d+(\.\d+)*)?|py)(\.exe)?", re.IGNORECASE)
SAFE_FLAGS = {"-B", "-E", "-I", "-O", "-OO", "-s", "-S", "-u"}  # flags that still run the script operand


def runs_guard(command):
    """Only the documented form: PYTHON [safe flags] /abs/merge_guard.py, with both files present.

    Anything else (-c, -m, another program, shell syntax) is unrecognised, so the check WARNs rather
    than calling a guard OK that never runs."""
    # Windows splits without POSIX rules, so "C:\\path with quotes" keeps its quotes; drop them.
    parts = [part[1:-1] if len(part) > 1 and part[0] == part[-1] == '"' else part for part in split(command)]
    if not parts or not INTERPRETER.fullmatch(Path(parts[0]).name):
        return False
    head = Path(parts[0])
    if not ((head.is_file() and os.access(head, os.X_OK)) if head.is_absolute() else shutil.which(parts[0])):
        return False
    i = 1
    while i < len(parts) and parts[i] in SAFE_FLAGS:
        i += 1
    rest = parts[i:]
    if not (len(rest) == 1 and Path(rest[0]).name == "merge_guard.py" and Path(rest[0]).is_absolute() and Path(rest[0]).is_file()):
        return False
    # The interpreter must really start: on Windows `python3` is often only the Store placeholder,
    # which exits 9009, so the hook would never block anything.
    try:
        # probe with the hook's own flags, so -E/-I start Python exactly as the hook will
        return subprocess.run([*parts[:i], "-c", "pass"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_preferences(home, report, env=None):
    """The person's own preferences from the start-here interview: present and well formed. Model ids are
    not checked against the catalogs here (the interview did that); this check stays offline and fast."""
    env = os.environ if env is None else env
    path = Path(env.get("PATSTACK_PREFERENCES") or home / ".config/patstack/preferences.json")
    try:
        present = os.lstat(path) is not None  # lstat: a dangling link exists, and reads as unreadable below
    except (FileNotFoundError, NotADirectoryError):
        present = False
    except OSError as error:  # for example a config folder this user cannot read
        report.add("WARN", "preferences", f"cannot look for {path} ({error.__class__.__name__}); fix the folder's permissions")
        return
    if not present:
        report.add("INFO", "preferences", "not set: run /start-here (it asks how you work and ranks your models)")
        return
    try:
        regular = path.is_file()  # a FIFO or device would block the read below
    except OSError:
        regular = False
    if not regular:
        report.add("WARN", "preferences", f"{path} is not a readable regular file; rerun /start-here")
        return
    try:
        prefs = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        report.add("WARN", "preferences", f"{path} is unreadable ({error.__class__.__name__}); rerun /start-here")
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import preferences
        found = preferences.problems(prefs, [])
    finally:
        sys.path.pop(0)
    if found:
        report.add("WARN", "preferences", f"{path}: {found[0]}; rerun /start-here")
        return
    pair = " + ".join(prefs["models"]["reviewPair"])
    report.add("OK", "preferences", f"set {prefs.get('updated', '?')}: language {prefs['language']}, "
                                    f"review pair {pair}, lead {prefs['models']['ranking']['lead'][0]}")


def check_codex(home, report):
    hooks_file = home / ".codex/hooks.json"
    if not hooks_file.exists():
        report.add("WARN", "codex merge guard", f"{hooks_file} absent; add the merge guard with "
                                                "scripts/start_here.py --apply (docs/setup.md step 6)")
        return
    settings = load_json(hooks_file, report, "codex hooks")
    if settings is None:
        return
    check_hooks("codex", settings, report)
    wired = guard_positions(settings)
    if not wired:
        report.add("WARN", "codex merge guard", f"not wired in {hooks_file}; scripts/start_here.py --apply adds it")
        return
    state = codex_guard_state(home, hooks_file, settings, wired)
    if state == "trusted":
        report.add("OK", "codex merge guard", "PreToolUse merge guard runs for Bash; Codex trusts this exact hook")
    else:
        report.add("WARN", "codex merge guard", CODEX_STATE_ADVICE[state])


def guard_positions(settings):
    """(group, hook) indexes of PreToolUse hooks that run the merge guard for Bash."""
    groups = (settings.get("hooks") or {}).get("PreToolUse") or []
    return [(g, h) for event, g, h, command in hook_commands(settings)
            if event == "PreToolUse" and MERGE_GUARD.search(command)
            and covers_bash(groups[g].get("matcher")) and runs_guard(command)]


TRUST_START = "Start `codex` in a terminal and choose 'Trust all and continue' (or review it under /hooks)"
CODEX_STATE_ADVICE = {
    "untrusted": "wired but not trusted: Codex skips an untrusted hook without a word. " + TRUST_START,
    "changed": "trusted before, but the hook changed since: Codex skips it until it is trusted again. " + TRUST_START,
    "disabled": "wired but turned off in Codex (enabled = false): turn it on under /hooks",
    "unreadable": "trust unknown: ~/.codex/config.toml is not readable TOML here, or this Python is older than 3.11 "
                  "(no TOML reader). " + TRUST_START + ", then check it under /hooks",
}
DEFAULT_CONTEXT_LIMIT = 2500  # Codex's default additionalContext limit, left out of the trust hash


def codex_hook_hash(event, matcher, hook):
    """Codex 0.167's trust hash for one command hook (hooks/src/engine/discovery.rs hook_hash and
    config/src/fingerprint.rs version_for_toml): sha256 over the sorted, compact JSON of the normalized
    identity {event_name, matcher, hooks: [handler]}, where the handler has its timeout defaulted to 600
    and absent optional fields left out. Checked against hashes Codex itself recorded."""
    timeout = hook.get("timeout")
    timeout = 600 if timeout is None else timeout  # Codex: timeout_sec.unwrap_or(600).max(1)
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        return None  # Codex rejects such a hook; it can never be trusted as written
    handler = {"type": "command", "command": hook.get("command", ""),
               "timeout": max(1, timeout), "async": bool(hook.get("async", False))}
    if hook.get("statusMessage") is not None:
        handler["statusMessage"] = hook["statusMessage"]
    limit = hook.get("additionalContextLimit")
    if limit is not None and limit != DEFAULT_CONTEXT_LIMIT:
        handler["additionalContextLimit"] = limit
    identity = {"event_name": event, "hooks": [handler]}
    if matcher is not None:
        identity["matcher"] = matcher
    data = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def codex_hook_states(text):
    """{state key: {"trusted_hash", "enabled"}} from config.toml text; None when it cannot be read as TOML.
    Needs tomllib (Python 3.11+); on older Pythons there is no safe way to read every valid TOML form, so the
    answer is "unknown" (WARN), never a guess."""
    try:
        import tomllib
    except ImportError:
        return None
    try:
        table = (tomllib.loads(text).get("hooks") or {}).get("state") or {}
    except tomllib.TOMLDecodeError:
        return None
    return {k: {"trusted_hash": v.get("trusted_hash"), "enabled": v.get("enabled")}
            for k, v in table.items() if isinstance(v, dict)}


def codex_guard_state(home, hooks_file, settings, wired):
    """trusted | changed | untrusted | disabled | unreadable, by Codex's own rule: the stored trusted_hash must
    equal the current hash of that exact hook, and a hook with enabled = false never runs. The best wired
    position wins."""
    try:
        states = codex_hook_states((home / ".codex/config.toml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        states = {}
    except OSError:
        states = None
    if states is None:
        return "unreadable"
    groups = (settings.get("hooks") or {}).get("PreToolUse") or []
    found = []
    for g, h in wired:
        state = states.get(f"{hooks_file}:pre_tool_use:{g}:{h}") or {}
        hook = groups[g]["hooks"][h]
        if state.get("enabled") is False:
            found.append("disabled")
        elif not isinstance(state.get("trusted_hash"), str):
            found.append("untrusted")
        elif state["trusted_hash"] == codex_hook_hash("pre_tool_use", groups[g].get("matcher"), hook):
            found.append("trusted")
        else:
            found.append("changed")
    return min(found, key=["trusted", "changed", "disabled", "untrusted"].index)


def monday_tool():
    """tools/monday_ticket.py from the tree this doctor belongs to, or None when that tree ships none."""
    tool = SELF_ROOT / "tools/monday_ticket.py"
    if not tool.is_file():
        return None
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True  # a read-only check leaves no __pycache__ behind
        spec = importlib.util.spec_from_file_location("patstack_monday_ticket", tool)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


def check_monday(root, home, env, report):
    """Offline: is a team board configured, is its config usable, and is the token in place and private?
    tools/monday_ticket.py decides what is absent and what is broken, so the doctor, start-here and the ticket
    tool always agree. The token is read to prove it is usable and is never shown. Live check:
    `monday_ticket.py check`."""
    monday = monday_tool()
    if monday is None:
        return
    env = os.environ if env is None else env
    try:
        monday.load_config(root, home=home, env=env)
    except monday.NoConfig:
        return  # no team board in this setup: no row
    except monday.MondayError as error:
        report.add("WARN", "ticket board", f"the team board configuration is broken: {error}")
        return
    token = monday.token_path(home, env)
    try:
        monday.read_token(home=home, env=env)
        open_to_others = os.name != "nt" and bool(token.stat().st_mode & 0o077)
    except monday.NoToken:
        report.add("WARN", "ticket board", f"no token at {token}; run start-here, or the agent sets it up the first "
                                           "time it needs a ticket")
        return
    except (OSError, monday.MondayError) as error:
        detail = error if isinstance(error, monday.MondayError) else error.__class__.__name__
        report.add("WARN", "ticket board", f"the stored Monday token cannot be used: {detail}")
        return
    if open_to_others:
        report.add("WARN", "ticket board", f"{token} is readable by others; chmod 600 it")
        return
    report.add("OK", "ticket board", f"config and token in place ({token}); live check: python3 tools/monday_ticket.py check")


def run(root, home, host, env=None, clients=None, which=shutil.which):
    """CLIENTS: the clients to check; None detects them (falling back to both when none is found)."""
    report = Report()
    if clients is None:
        clients = detect_clients(home, which)
        if not clients:
            clients = list(CLIENTS)
            report.add("INFO", "clients", "no Claude Code or Codex binary or state found; checking both")
        else:
            report.add("INFO", "clients", f"checking {' and '.join(clients)} (detected; --clients overrides)")
    check_source(root, home, host, report, clients)
    check_pack_vault(root, home, env, report)
    check_monday(root, home, env, report)
    check_preferences(home, report, env)
    for name, check in (("claude", check_claude), ("codex", check_codex)):
        if name not in clients:
            not_set_up(report, f"{name} hooks", name)
        else:
            check(home, report)
    return report


def build_parser():
    parser = argparse.ArgumentParser(description="Read-only Patstack setup check for one host.")  # -OO strips __doc__
    parser.add_argument("--host", choices=("mac", "devbox", "windows"), required=True)
    parser.add_argument("--home", type=Path, default=Path.home(), help="Home directory to inspect (tests)")
    parser.add_argument("--root", type=Path, help="Setup source or Patstack checkout (default: the tree containing this script)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--clients", choices=("auto", "claude", "codex", "both"), default="auto",
                        help="Clients to check (default: auto, the clients whose binary or own state is found)")
    return parser


def chosen(option):
    """None for auto-detection, else the explicit client list."""
    return {"auto": None, "both": list(CLIENTS), "claude": ["claude"], "codex": ["codex"]}[option]


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root or SELF_ROOT
    report = run(root, args.home, args.host, clients=chosen(args.clients))
    if args.json:
        print(json.dumps(report.rows, indent=2))
    else:
        for row in report.rows:
            print(f"{row['status']:<4}  {row['check']:<20}  {row['detail']}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
