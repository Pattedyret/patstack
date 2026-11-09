#!/usr/bin/env python3
"""Install the narrow KPI addition, preserving existing workflow/client settings.

By default the hooks point at the DevStack checkout that contains this file; --root selects
another reviewed setup tree, into which the monitor package is then copied.
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
import tempfile
from datetime import datetime, timezone


MARKER = "<!-- devstack-kpi:start -->"
END = "<!-- devstack-kpi:end -->"
# Blocks written before the rename are replaced in place rather than duplicated.
LEGACY_MARKERS = (("<!-- patstack-kpi:start -->", "<!-- patstack-kpi:end -->"),)
CHECKOUT = Path(__file__).resolve().parent.parent.parent
POINTER = """<!-- devstack-kpi:start -->
## Workflow KPI audit

Record private workflow metadata at meaningful milestones and outcomes using
`monitoring/devstack/README.md` in the DevStack checkout.
This covers development, research and testing without creating extra tickets.
Before Retro, read the relevant host reports; distinguish hook receipts, historical
registry observations, audited outcomes and missing measurements. Ticket numbers
carry no execution state; never restart retired registry services for monitoring.
Keep prompts, transcripts, credentials and device inventories out of telemetry.
<!-- devstack-kpi:end -->
"""


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


# Hook scripts the installer writes, relative to the checkout, with the first argument it passes.
HOOK_FORMS = (("monitoring/devstack/kpi_monitor.py", "audit-hook"), ("scripts/setup_doctor.py", "--host"))


def other_checkouts(data, root):
    """Checkout paths, other than ROOT, that DevStack hooks in DATA run (an old or moved checkout).

    Detection only: those hooks are left in place; scripts/detach.py --from OLD removes them.
    """
    found = []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    for groups in (hooks.values() if isinstance(hooks, dict) else ()):
        for group in groups if isinstance(groups, list) else ():
            for hook in (group.get("hooks") or []) if isinstance(group, dict) else ():
                command = hook.get("command") if isinstance(hook, dict) else None
                argv = canonical_argv(command) if isinstance(command, str) else []
                if len(argv) < 3 or not INTERPRETER.fullmatch(Path(argv[0]).name):
                    continue
                script = argv[1].replace("\\", "/")
                for suffix, first in HOOK_FORMS:
                    if script.endswith("/" + suffix) and argv[2] == first:
                        old = script[:-len(suffix) - 1]
                        if not same_checkout(old, root) and old not in found:
                            found.append(old)
    return found


def same_checkout(path, root):
    key = (lambda p: os.path.normcase(os.path.normpath(p))) if os.name == "nt" else os.path.normpath
    if key(path) == key(str(root)) or key(path) == key(str(Path(root).resolve())):
        return True
    return Path(path).exists() and Path(path).resolve() == Path(root).resolve()


def runs(command, name, arguments):
    """True only when a hook command runs script NAME with exactly ARGUMENTS (the form we write)."""
    script, rest = invoked_script(canonical_argv(command))
    return Path(script).name == name and rest == arguments


def is_kpi_hook(command, host, runtime):
    return runs(command, "kpi_monitor.py", ["audit-hook", "--host", host, "--runtime", runtime, "--event", "Stop"])


ALL_TOOLS = (None, "", "*", ".*")  # a narrower matcher would count only some tools


def is_tool_hook(command, host, runtime, event):
    return runs(command, "kpi_monitor.py", ["audit-hook", "--host", host, "--runtime", runtime, "--event", event])


def is_status_hook(command, host, runtime):
    return runs(command, "setup_doctor.py", ["--host", host, "--hook", runtime])


def with_pointer(text):
    for start, end in LEGACY_MARKERS:
        if start in text and MARKER not in text:
            text = text.replace(start, MARKER, 1).replace(end, END, 1)
    if MARKER in text:
        before, rest = text.split(MARKER, 1)
        if END not in rest:
            raise RuntimeError("Incomplete KPI instruction marker")
        return before + POINTER.rstrip() + rest.split(END, 1)[1]
    return text.rstrip() + "\n\n" + POINTER


def hook_command(executable, script, host, runtime, windows=False, arguments=None):
    arguments = [str(executable), str(script)] + (arguments or ["audit-hook", "--host", host,
                                                               "--runtime", runtime, "--event", "Stop"])
    if windows:
        arguments = [a.replace("\\", "/") for a in arguments]
        if any(not re.fullmatch(r"[A-Za-z0-9_:/.-]+", a) for a in arguments):
            raise RuntimeError("Unsupported Windows hook path; no hook installed")
        return " ".join(arguments)
    return shlex.join(arguments)


def settings_problem(data):
    """Why DATA is not a client settings object this installer can extend, or None."""
    if not isinstance(data, dict):
        return "top level is not a JSON object"
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return "'hooks' is not an object"
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            return f"hooks.{event} is not a list"
        for g, group in enumerate(groups):
            if not isinstance(group, dict):
                return f"hooks.{event}[{g}] is not an object"
            if group.get("matcher") is not None and not isinstance(group["matcher"], str):
                return f"hooks.{event}[{g}].matcher is not a string"
            if not isinstance(group.get("hooks", []), list):
                return f"hooks.{event}[{g}].hooks is not a list"
            for h, hook in enumerate(group.get("hooks", [])):
                if not isinstance(hook, dict):
                    return f"hooks.{event}[{g}].hooks[{h}] is not an object"
                if not isinstance(hook.get("command", ""), str):
                    return f"hooks.{event}[{g}].hooks[{h}].command is not a string"
    return None


def retro_target(root, stack):
    """The Retro file that carries the KPI pointer for an active DevStack setup tree."""
    if stack.get("name") != "devstack":
        return None
    return root / ("skills/retro/SKILL.md" if "retro" in stack.get("global_skills", []) else "skills/devstack/references/retro.md")


def preflight(root, home, skip_codex_hook):
    """Validate every file the install will read or extend, before the first write."""
    def load(path, what):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"{path} is not valid {what}; nothing was changed") from error

    for runtime, relative in (("codex", ".codex/hooks.json"), ("claude", ".claude/settings.json")):
        path = home / relative
        if path.exists() and not (runtime == "codex" and skip_codex_hook):
            problem = settings_problem(load(path, "JSON"))
            if problem:
                raise RuntimeError(f"{path}: {problem}; nothing was changed")
    targets = [root / "AGENTS.md"] if (root / "AGENTS.md").exists() else [(home / r).resolve() for r in (".codex/AGENTS.md", ".claude/CLAUDE.md")]
    manifest = root / "manifest.json"
    if manifest.exists():
        data = load(manifest, "JSON")
        stack = data.get("active_stack", {}) if isinstance(data, dict) else None
        if not isinstance(stack, dict) or not isinstance(stack.get("global_skills", []), list):
            raise RuntimeError(f"{manifest}: unexpected active_stack; nothing was changed")
        retro = retro_target(root, stack)
        if retro is not None:
            targets.append(retro)  # its pointer marker is checked with the instruction files below
    overlay = root / "vendor/mattpocock-skills/overlay.json"
    if overlay.exists() and not (manifest.exists() and load(manifest, "JSON").get("active_stack", {}).get("name") == "devstack"):
        data = load(overlay, "JSON")
        try:
            prefix = data["expose"]["retro"]["body_prefix"]
            if not isinstance(prefix, str):
                raise TypeError
        except (KeyError, TypeError) as error:
            raise RuntimeError(f"{overlay}: expose.retro.body_prefix missing; nothing was changed") from error
        with_pointer(prefix)
    for path in targets:
        if path.exists():
            try:
                with_pointer(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, RuntimeError) as error:
                raise RuntimeError(f"{path}: {error}; nothing was changed") from error


def install(source, home, host, skip_codex_hook=False, root=None):
    source, home = Path(source).resolve(), Path(home).resolve()
    root = Path(root).expanduser().resolve() if root else CHECKOUT
    dest = root / "monitoring/devstack"
    # Private rollback copies live outside any checkout, so they can never be committed.
    backup = home / ".local/state/devstack/install-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    changed, stale = [], []
    files = ("kpi_monitor.py", "test_kpi_monitor.py", "README.md", "install.py", "task_kpi.py", "test_task_kpi.py")
    # Validate every input before the first write, so a bad file never leaves a half-done install.
    missing = [name for name in files if not (source / name).is_file()]
    if missing:
        raise RuntimeError("Monitor package incomplete: " + ", ".join(missing))
    preflight(root, home, skip_codex_hook)

    def shown(path):
        """Report path relative to home when it lives there, else in full (--root may be anywhere)."""
        path = Path(path)
        return str(path.relative_to(home)) if path == home or home in path.parents else str(path)

    def write(path, content):
        previous = path.read_bytes() if path.exists() else None
        if previous == content:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if previous is not None:
            backup.mkdir(parents=True, exist_ok=True, mode=0o700)
            copy = backup / (hashlib.sha256(str(path).encode()).hexdigest()[:16] + "-" + path.name)
            copy.write_bytes(previous)
            if os.name != "nt":
                copy.chmod(0o600)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        try:
            current = path.read_bytes() if path.exists() else None
            if current != previous:
                raise RuntimeError("Concurrent configuration change; refusing overwrite")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        changed.append(shown(path))

    for name in files:
        write(dest / name, (source / name).read_bytes())

    def point(path):
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        write(path, with_pointer(text).encode())

    if (root / "AGENTS.md").exists():
        point(root / "AGENTS.md")
    else:
        # No shared AGENTS.md in the setup tree: update each client's own global instructions.
        for relative in (".codex/AGENTS.md", ".claude/CLAUDE.md"):
            point((home / relative).resolve())

    manifest = root / "manifest.json"
    active_stack = json.loads(manifest.read_text(encoding="utf-8")).get("active_stack", {}) if manifest.exists() else {}
    overlay = root / "vendor/mattpocock-skills/overlay.json"
    retro = root / "skills/retro"
    if retro_target(root, active_stack) is not None:
        point(retro_target(root, active_stack))
    elif overlay.exists():
        data = json.loads(overlay.read_text(encoding="utf-8"))
        prefix = data["expose"]["retro"]["body_prefix"]
        data["expose"]["retro"]["body_prefix"] = with_pointer(prefix).rstrip() + "\n\n"
        write(overlay, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode())
        module_path = root / "scripts/mp_skills.py"
        spec = importlib.util.spec_from_file_location("mp_skills", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Render only the changed skill, preserving every unrelated skill.
        for relative, content in module.render_skill("retro", data["expose"]["retro"]).items():
            write(retro / relative, content)

    for runtime, relative in (("codex", ".codex/hooks.json"), ("claude", ".claude/settings.json")):
        if runtime == "codex" and skip_codex_hook:
            continue
        path = home / relative
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for old in other_checkouts(data, root):
            if old not in stale:
                stale.append(old)
        executable = sys.executable if os.name == "nt" else (shutil.which("python3") or sys.executable)
        command = hook_command(executable, dest / "kpi_monitor.py", host, runtime, os.name == "nt")
        groups = data.setdefault("hooks", {}).setdefault("Stop", [])
        found = any(is_kpi_hook(hook.get("command", ""), host, runtime) for group in groups for hook in group.get("hooks", []))
        if not found:
            groups.append({"hooks": [{"type": "command", "command": command, "timeout": 5, "async": True}]})
        # Tool-call counts per session (Claude also has a failure event); receipts only, never tool data.
        for event in ("PostToolUse", "PostToolUseFailure") if runtime == "claude" else ("PostToolUse",):
            tools = data["hooks"].setdefault(event, [])
            # A recognised counter under a narrower matcher would double-count with the full one: drop just
            # that handler, keep every other hook, and drop a group only if it held nothing else.
            ours = (dest / "kpi_monitor.py").resolve()
            for group in tools:
                if group.get("matcher") not in ALL_TOOLS:  # remove only handlers that run this installed script
                    group["hooks"] = [hook for hook in group.get("hooks", [])
                                      if not (is_tool_hook(hook.get("command", ""), host, runtime, event)
                                              and Path(invoked_script(canonical_argv(hook.get("command", "")))[0]).resolve() == ours)]
            tools[:] = [group for group in tools if group.get("hooks")]
            if not any(group.get("matcher") in ALL_TOOLS and is_tool_hook(hook.get("command", ""), host, runtime, event)
                       for group in tools for hook in group.get("hooks", [])):
                counter = hook_command(executable, dest / "kpi_monitor.py", host, runtime, os.name == "nt",
                                       ["audit-hook", "--host", host, "--runtime", runtime, "--event", event])
                tools.append({"matcher": "*" if runtime == "claude" else ".*",
                              "hooks": [{"type": "command", "command": counter, "timeout": 5, "async": True}]})
        # Session-start status line from the read-only setup check, when the source ships it.
        doctor = root / "scripts/setup_doctor.py"
        starts = data["hooks"].setdefault("SessionStart", [])
        if doctor.exists() and not any(is_status_hook(hook.get("command", ""), host, runtime)
                                       for group in starts for hook in group.get("hooks", [])):
            status = hook_command(executable, doctor, host, runtime, os.name == "nt",
                                  ["--host", host, "--hook", runtime])
            starts.append({"hooks": [{"type": "command", "command": status, "timeout": 5}]})
        if not starts:
            del data["hooks"]["SessionStart"]
        write(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode())
    result = {"host": host, "changed": changed, "hook_activation": "configured; native trust/loading still requires verification"}
    if stale:
        result["other_checkouts"] = stale
        result["hint"] = [f"DevStack hooks still run {old}: from this checkout, run "
                          f"python3 scripts/detach.py --from {shlex.quote(old)} (dry run), then add --apply" for old in stale]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("mac", "devbox", "windows"), required=True)
    parser.add_argument("--skip-codex-hook", action="store_true", help="Preserve a separately owned/unavailable Codex hook configuration")
    parser.add_argument("--root", type=Path, help="Setup tree the hooks point at (default: this DevStack checkout)")
    args = parser.parse_args()
    outcome = install(Path(__file__).parent, Path.home(), args.host, args.skip_codex_hook, args.root)
    print(json.dumps(outcome, indent=2))
    for line in outcome.get("hint", []):
        print("hint: " + line, file=sys.stderr)
