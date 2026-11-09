#!/usr/bin/env python3
"""Read-only DevStack setup check for one host.

Checks the source, client skill links, global instructions (and whether the shipped
template is installed), the bundled project pack, its shared product vault checkout (found,
right remote, revision, freshness; never fetched here) and benchmark folders, ticket-ref, Claude
and Codex hooks (including Codex trust) and KPI hook receipts/outcome coverage. Changes no
configuration; reading the private KPI store may let SQLite create its usual -wal/-shm
sidecar files. Only clients in use are checked (binary on PATH or the client's own state; --clients
overrides); an unused client's rows are INFO, never FAIL. FAIL means broken setup; WARN means working but incomplete; INFO is unverifiable here. A green
result proves configuration and recorded receipts, not that a client loaded a hook in
the current session.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import threading

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

SELF_ROOT = Path(__file__).resolve().parent.parent  # source setup or published checkout
CLIENTS = ("claude", "codex")
# Each client's own files (written by the client itself, never by DevStack's installer), so an install
# that wrote hooks for both clients does not make an unused client look set up.
CLIENT_STATE = {"claude": (".claude.json", ".claude/.credentials.json", ".claude/projects"),
                "codex": (".codex/config.toml", ".codex/auth.json", ".codex/sessions")}
RETIRED_HOOK = re.compile(r"agent-work-[a-z-]+\.py")
SCRIPT = re.compile(r"\.(py|sh|cmd|ps1)\Z")
# The bundled pack's read-only vault tool owns the vault rules; the doctor only shows its rows.
PACK_VAULT_TOOL = "project-packs/*/tools/vault_context.py"
# First line of examples/global-instructions/AGENTS.md; kept when the template is merged by hand.
TEMPLATE_MARKER = "<!-- devstack-global-instructions -->"


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


def canonical_argv(command):
    """argv only when COMMAND is exactly the installer's shlex.join of it (no newlines, ;, odd quoting)."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    return parts if shlex.join(parts) == command else []


INTERPRETER = re.compile(r"(python(\d+(\.\d+)*)?|py)(\.exe)?", re.IGNORECASE)
FLAGS = {"-B", "-E", "-I", "-O", "-OO", "-s", "-S", "-u"}
LAUNCHER_VERSION = re.compile(r"-\d+(\.\d+)?(-\d+)?")


def invoked_script(parts):
    """The script a hook argv runs, using a closed grammar: PYTHON [-3.N] [flags] /abs/SCRIPT.py ARGS.

    PYTHON must resolve to an executable (absolute path or on PATH) and SCRIPT must be an existing
    absolute file. Callers pass argv from canonical_argv(), so shell syntax never reaches here.
    Anything else (env, VAR=1, -c, -m, -X, relative or missing paths) is unrecognised and returns
    ("", []): that errs towards a WARN or a duplicate hook, never towards calling a dead command OK.
    Callers then compare ARGS exactly with the form the installer writes.
    """
    if not parts or not INTERPRETER.fullmatch(Path(parts[0]).name):
        return "", []
    if not (os.access(parts[0], os.X_OK) and Path(parts[0]).is_file() if Path(parts[0]).is_absolute() else shutil.which(parts[0])):
        return "", []
    launcher = Path(parts[0]).name.lower() in ("py", "py.exe")
    i = 1
    while i < len(parts) and parts[i].startswith("-"):
        if parts[i] in FLAGS or (launcher and LAUNCHER_VERSION.fullmatch(parts[i])):
            i += 1
        else:  # includes -X/-W, whose values can stop Python before the script runs
            return "", []
    if i < len(parts) and Path(parts[i]).is_absolute() and Path(parts[i]).is_file():
        return parts[i], parts[i + 1:]
    return "", []
    if i < len(parts) and parts[i].endswith(".py"):
        return parts[i], parts[i + 1:]
    return "", []


def kpi_runtime(command, host):
    """Return the runtime of a KPI Stop audit hook in the installer's exact form, else None."""
    script, rest = invoked_script(canonical_argv(command))
    for runtime in ("claude", "codex"):
        if Path(script).name == "kpi_monitor.py" and rest == ["audit-hook", "--host", host, "--runtime", runtime, "--event", "Stop"]:
            return runtime
    return None


ALL_TOOLS = (None, "", "*", ".*")  # a narrower matcher would count only some tools


def tool_runtime(command, host, event):
    """Return the runtime of a KPI tool-count hook for EVENT in the installer's exact form, else None."""
    script, rest = invoked_script(canonical_argv(command))
    for runtime in ("claude", "codex"):
        if Path(script).name == "kpi_monitor.py" and rest == ["audit-hook", "--host", host, "--runtime", runtime, "--event", event]:
            return runtime
    return None


def status_runtime(command, host):
    """Return the runtime of a session status hook in the installer's exact form, else None."""
    script, rest = invoked_script(canonical_argv(command))
    for runtime in ("claude", "codex"):
        if Path(script).name == "setup_doctor.py" and rest == ["--host", host, "--hook", runtime]:
            return runtime
    return None


def load_json(path, report, check):
    if path.exists() and not path.is_file():  # a FIFO or device would block the read
        report.add("FAIL", check, f"{path} is not a regular file")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    if not (root / "skills/devstack/SKILL.md").is_file():
        report.add("FAIL", "source", f"{root}/skills/devstack/SKILL.md is missing")
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
        if text is None or "devstack" not in text.lower():
            report.add("FAIL", name, f"{path} missing or does not select DevStack")
        elif "monitoring/devstack" not in text:
            report.add("WARN", name, "no KPI pointer; run monitoring/devstack/install.py")
        else:
            report.add("OK", name, "selects DevStack and points to KPI contract")
        if text is not None and "devstack" in text.lower():
            if TEMPLATE_MARKER in text:
                report.add("OK", f"template {path.parent.name}", "DevStack global instructions template installed")
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
            spec = importlib.util.spec_from_file_location("devstack_pack_vault", tool)
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


def check_hooks(runtime, settings, host, report):
    """Shared hook checks; return DevStack hook positions [(label, event, g, h)] and all commands."""
    positions, wired = [], []
    for event, g, h, command in hook_commands(settings):
        for path in missing_paths(command):
            report.add("FAIL", f"{runtime} hook", f"{event} command points to missing {path}")
        if event == "Stop" and kpi_runtime(command, host) == runtime:
            positions.append(("KPI", event, g, h))
        if event == "SessionStart" and status_runtime(command, host) == runtime:
            positions.append(("status", event, g, h))
        matcher = ((settings.get("hooks") or {}).get(event) or [{}])[g].get("matcher")
        if event in ("PostToolUse", "PostToolUseFailure") and matcher in ALL_TOOLS and tool_runtime(command, host, event) == runtime:
            positions.append((event, event, g, h))
        wired.append(command)
        if RETIRED_HOOK.search(command):
            report.add("WARN", f"{runtime} hook", f"retired registry hook still wired in {event}: {RETIRED_HOOK.search(command).group()}")
    labels = {label for label, *_ in positions}
    for event in ("PostToolUse", "PostToolUseFailure"):
        counters = sum(1 for e, g, h, command in hook_commands(settings) if e == event and tool_runtime(command, host, e) == runtime)
        if counters > 1:  # also counts handlers under narrow matchers: each fires for its tools
            report.add("WARN", f"{runtime} tool hook", f"{counters} {event} counters would double-count; rerun monitoring/devstack/install.py")
    if "KPI" in labels:
        report.add("OK", f"{runtime} KPI hook", "Stop audit hook configured")
    else:
        report.add("FAIL", f"{runtime} KPI hook", "Stop audit hook missing or not in the installer's form; run monitoring/devstack/install.py")
    for event in ("PostToolUse", "PostToolUseFailure") if runtime == "claude" else ("PostToolUse",):
        if event in labels:
            report.add("OK", f"{runtime} tool hook", f"{event} counter configured")
        else:
            report.add("WARN", f"{runtime} tool hook", f"{event} counter missing; run monitoring/devstack/install.py")
    if "status" in labels:
        report.add("OK", f"{runtime} status hook", "SessionStart status hook configured")
    else:
        report.add("WARN", f"{runtime} status hook", "SessionStart status hook missing or not in the installer's form; run monitoring/devstack/install.py")
    return positions, wired


def check_claude(home, host, report):
    settings = load_json(home / ".claude/settings.json", report, "claude settings")
    if settings is None:
        return False
    if settings.get("disableAllHooks") is True:
        report.add("FAIL", "claude hooks", "disableAllHooks is true; no hook runs")
        return False
    positions, _ = check_hooks("claude", settings, host, report)
    # DevStack ships no shell safety hooks; owner-specific ones are the user's own and are not judged here.
    report.add("INFO", "claude safety hook", "optional owner-specific safety hooks are not part of DevStack; not checked")
    return any(label == "KPI" for label, *_ in positions)


def check_codex(home, host, report):
    if not (home / ".codex").is_dir():
        report.add("WARN", "codex", f"{home / '.codex'} missing; Codex checks skipped")
        return False
    hooks_file = home / ".codex/hooks.json"
    settings = load_json(hooks_file, report, "codex hooks")
    if settings is None:
        return False
    positions, _ = check_hooks("codex", settings, host, report)
    if not positions:
        return False
    active = any(label == "KPI" for label, *_ in positions)
    config = home / ".codex/config.toml"
    if not config.is_file():
        report.add("WARN", "codex trust", "config.toml unavailable; trust not checked")
        return active
    try:
        state = trust_state(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.add("WARN", "codex trust", f"config.toml unreadable: {exc.__class__.__name__}")
        return active
    for label, event, g, h in positions:
        key = f"{hooks_file}:{re.sub(r'(?<!^)(?=[A-Z])', '_', event).lower()}:{g}:{h}"
        if (state.get(key) or {}).get("trusted_hash"):
            # Codex's hash cannot be recomputed here and a stale entry can remain at a reused position.
            report.add("INFO", "codex trust", f"{label} hook has a trust entry (unverifiable here); approve it if /hooks lists it as new")
        else:
            report.add("WARN", "codex trust", f"{label} hook not trusted; open Codex and approve it in /hooks")
    return active


def trust_state(text):
    """Codex's hooks.state tables; without tomllib (Python < 3.11, e.g. macOS's python3) only the form Codex writes."""
    if tomllib is not None:
        return tomllib.loads(text).get("hooks", {}).get("state", {})
    state, table = {}, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            m = re.fullmatch(r'\[hooks\.state\.("(?:[^"\\]|\\.)*")\]', line)
            table = state.setdefault(json.loads(m.group(1)), {}) if m else None
        elif table is not None and re.match(r'trusted_hash\s*=\s*"[^"]+"', line):
            table["trusted_hash"] = True
    return state


def check_kpi(root, host, runtimes, db, report, timeout):
    command = [sys.executable, str(root / "monitoring/devstack/kpi_monitor.py")]
    command += (["--db", str(db)] if db else []) + ["report"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report.add("WARN", "kpi report", f"report unavailable: {exc.__class__.__name__}")
        return
    receipts = {row.get("runtime"): row.get("receipts", 0) for row in data.get("audit_hook_coverage", [])
                if row.get("host") == host and row.get("event") == "Stop"}
    for runtime in runtimes:
        count = receipts.get(runtime, 0)
        if count:
            report.add("OK", f"{runtime} receipts", f"{count} Stop receipts recorded on {host}")
        else:
            report.add("WARN", f"{runtime} receipts", "hook configured but never fired; restart the client or check hook trust")
    counts = data.get("overall", {}).get("counts", {})
    overall = data.get("overall", {})
    # Only designated tasks need a verification label; unticketed `once` requests are not counted.
    missing = overall.get("verification_missing", overall.get("task_completion_rate", {}).get("missing", 0))
    if not counts.get("total"):
        report.add("WARN", "kpi outcomes", "no workflow snapshots recorded yet")
    elif missing:
        report.add("WARN", "kpi outcomes", f"{missing} completed workflow(s) lack verified_success; record it with task_kpi.py finish")
    else:
        report.add("OK", "kpi outcomes", f"{counts['total']} workflow snapshots; completed ones carry verified_success")
    card = data.get("scorecard")
    if not card:
        report.add("INFO", "kpi targets", "none set; copy examples/kpi-targets.example.json to ~/.config/devstack/kpi-targets.json")
    elif "error" in card:
        report.add("WARN", "kpi targets", "targets file invalid; kpi_monitor.py scorecard names the problem")
    else:
        report.add("OK" if card["met"] == card["total"] else "WARN", "kpi targets", card["line"])


def run(root, home, host, db=None, timeout=30, env=None, clients=None, which=shutil.which):
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
    active = []
    for name, check in (("claude", check_claude), ("codex", check_codex)):
        if name not in clients:
            not_set_up(report, f"{name} hooks", name)
        elif check(home, host, report):
            active.append(name)
    runtimes = active
    if (root / "monitoring/devstack/kpi_monitor.py").is_file():
        check_kpi(root, host, runtimes, db, report, timeout)
    else:
        report.add("FAIL", "kpi monitor", "monitoring/devstack/kpi_monitor.py is missing")
    return report


def summary(report):
    """One short status line for the session-start hook."""
    # KPI targets belong in a finished development task's report (task_kpi.py finish), not in every session
    issues = [row for row in report.rows if row["status"] in ("WARN", "FAIL") and row["check"] != "kpi targets"]
    receipts = [row["detail"].split(" Stop")[0] + " " + row["check"].split()[0]
                for row in report.rows if row["check"].endswith("receipts") and row["status"] == "OK"]
    head = ("⚠ DevStack setup broken" if report.failed else "📈 DevStack monitoring on")
    head += f" ({', '.join(receipts)} receipts)" if receipts else ""
    if not issues:
        return head + " · all checks OK"
    names = ", ".join(f"{row['status']} {row['check']}" for row in issues[:4])
    more = f" +{len(issues) - 4}" if len(issues) > 4 else ""
    return f"{head} · {names}{more} · details: setup_doctor.py --host HOST"


def hook_output(runtime, line):
    context = (f"DevStack session status: {line}. Do not repeat it in replies unless it starts with ⚠ (setup broken) "
               "or the user asks about the setup; do not act on it unless the user asks.")
    output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    if runtime == "claude":
        output["systemMessage"] = line  # shown directly by Claude Code; Codex keeps the proven context-only shape
    return json.dumps(output)  # ASCII escapes: safe in any console encoding


def hook_main(argv):
    """Session-start mode: always one JSON line, exit 0, within the client's 5 s budget."""
    runtime = "codex" if "codex" in argv else "claude"
    line = "⚠ DevStack setup check could not run; try setup_doctor.py manually"
    try:
        with contextlib.redirect_stdout(io.StringIO()):  # --help or usage must not precede the JSON
            args = build_parser().parse_args(argv)
        runtime = args.hook
        root = args.root or SELF_ROOT
        result = {}

        def work():
            try:
                clients = chosen(args.clients)
                if clients is None:  # the client running this hook is set up by definition
                    clients = [c for c in CLIENTS if c in detect_clients(args.home) or c == runtime]
                result["line"] = summary(run(root, args.home, args.host, args.db, timeout=3,
                                             clients=clients)).replace("HOST", args.host)
            except BaseException:
                result["line"] = line  # crashed, not slow

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join(4)
        line = result.get("line", "⚠ DevStack setup check timed out; try setup_doctor.py manually")
    except BaseException:  # includes argparse's SystemExit; telemetry must never trap a session
        pass
    try:
        sys.stdout.write(hook_output(runtime, line) + "\n")
        sys.stdout.flush()
    except BaseException:
        pass
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Read-only DevStack setup check for one host.")  # -OO strips __doc__
    parser.add_argument("--host", choices=("mac", "devbox", "windows"), required=True)
    parser.add_argument("--home", type=Path, default=Path.home(), help="Home directory to inspect (tests)")
    parser.add_argument("--root", type=Path, help="Setup source or DevStack checkout (default: the tree containing this script)")
    parser.add_argument("--db", type=Path, help="Private KPI store (default from kpi_monitor.py)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--hook", choices=("claude", "codex"), help="SessionStart output; never fails the session")
    parser.add_argument("--clients", choices=("auto", "claude", "codex", "both"), default="auto",
                        help="Clients to check (default: auto, the clients whose binary or own state is found)")
    return parser


def chosen(option):
    """None for auto-detection, else the explicit client list."""
    return {"auto": None, "both": list(CLIENTS), "claude": ["claude"], "codex": ["codex"]}[option]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if any(a == "--hook" or a.startswith("--hook=") for a in argv):
        return hook_main(argv)
    args = build_parser().parse_args(argv)
    root = args.root or SELF_ROOT
    report = run(root, args.home, args.host, args.db, clients=chosen(args.clients))
    if args.json:
        print(json.dumps(report.rows, indent=2))
    else:
        for row in report.rows:
            print(f"{row['status']:<4}  {row['check']:<20}  {row['detail']}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
