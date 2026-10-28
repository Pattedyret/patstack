#!/usr/bin/env python3
"""Install the narrow KPI addition, preserving existing workflow/client settings."""
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


MARKER = "<!-- patstack-kpi:start -->"
END = "<!-- patstack-kpi:end -->"
POINTER = """<!-- patstack-kpi:start -->
## Workflow KPI audit

Record private workflow metadata at meaningful milestones and outcomes using
`~/.harnesses-shared/agent-setup/monitoring/patstack/README.md`.
This covers development, research and testing without creating extra tickets.
Before Retro, read the relevant host reports; distinguish hook receipts, historical
registry observations, audited outcomes and missing measurements. Ticket numbers
carry no execution state; never restart retired registry services for monitoring.
Keep prompts, transcripts, credentials and device inventories out of telemetry.
<!-- patstack-kpi:end -->
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


def install(source, home, host, skip_codex_hook=False):
    source, home = Path(source).resolve(), Path(home).resolve()
    root = home / ".harnesses-shared/agent-setup"
    dest = root / "monitoring/patstack"
    backup = dest / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    changed = []

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
        changed.append(str(path.relative_to(home)))

    for name in ("kpi_monitor.py", "test_kpi_monitor.py", "README.md", "install.py", "task_kpi.py", "test_task_kpi.py"):
        write(dest / name, (source / name).read_bytes())

    def point(path):
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        write(path, with_pointer(text).encode())

    if (root / "AGENTS.md").exists():
        point(root / "AGENTS.md")
    else:
        # Windows has standalone global instructions rather than shared symlinks.
        for relative in (".codex/AGENTS.md", ".claude/CLAUDE.md"):
            point((home / relative).resolve())

    manifest = root / "manifest.json"
    active_stack = json.loads(manifest.read_text(encoding="utf-8")).get("active_stack", {}) if manifest.exists() else {}
    overlay = root / "vendor/mattpocock-skills/overlay.json"
    retro = root / "skills/retro"
    if active_stack.get("name") == "patstack":
        point(root / ("skills/retro/SKILL.md" if "retro" in active_stack.get("global_skills", []) else "skills/patstack/references/retro.md"))
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
    return {"host": host, "changed": changed, "hook_activation": "configured; native trust/loading still requires verification"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("mac", "devbox", "windows"), required=True)
    parser.add_argument("--skip-codex-hook", action="store_true", help="Preserve a separately owned/unavailable Codex hook configuration")
    args = parser.parse_args()
    print(json.dumps(install(Path(__file__).parent, Path.home(), args.host, args.skip_codex_hook), indent=2))
