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
Before Retro, refresh supported discovery and read the host report; distinguish
hook receipts, registry discovery, audited outcomes and missing measurements.
Keep prompts, transcripts, credentials and device inventories out of telemetry.
<!-- patstack-kpi:end -->
"""


def with_pointer(text):
    if MARKER in text:
        before, rest = text.split(MARKER, 1)
        if END not in rest:
            raise RuntimeError("Incomplete KPI instruction marker")
        return before + POINTER.rstrip() + rest.split(END, 1)[1]
    return text.rstrip() + "\n\n" + POINTER


def hook_command(executable, script, host, runtime, windows=False):
    arguments = [str(executable), str(script), "audit-hook", "--host", host,
                 "--runtime", runtime, "--event", "Stop"]
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

    for name in ("kpi_monitor.py", "test_kpi_monitor.py", "README.md", "install.py"):
        write(dest / name, (source / name).read_bytes())

    def point(path):
        text = path.read_text() if path.exists() else ""
        write(path, with_pointer(text).encode())

    if (root / "AGENTS.md").exists():
        point(root / "AGENTS.md")
    else:
        # Windows has standalone global instructions rather than shared symlinks.
        for relative in (".codex/AGENTS.md", ".claude/CLAUDE.md"):
            point((home / relative).resolve())

    manifest = root / "manifest.json"
    active_stack = json.loads(manifest.read_text()).get("active_stack", {}) if manifest.exists() else {}
    overlay = root / "vendor/mattpocock-skills/overlay.json"
    retro = root / "skills/retro"
    if active_stack.get("name") == "patstack":
        point(root / "skills/patstack/references/retro.md")
    elif overlay.exists():
        data = json.loads(overlay.read_text())
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
        data = json.loads(path.read_text()) if path.exists() else {}
        executable = sys.executable if os.name == "nt" else (shutil.which("python3") or sys.executable)
        command = hook_command(executable, dest / "kpi_monitor.py", host, runtime, os.name == "nt")
        groups = data.setdefault("hooks", {}).setdefault("Stop", [])
        found = any("kpi_monitor.py" in hook.get("command", "") and "audit-hook" in hook.get("command", "")
                    for group in groups for hook in group.get("hooks", []))
        if not found:
            groups.append({"hooks": [{"type": "command", "command": command, "timeout": 5, "async": True}]})
        write(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode())
    return {"host": host, "changed": changed, "hook_activation": "configured; native trust/loading still requires verification"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("mac", "devbox", "windows"), required=True)
    parser.add_argument("--skip-codex-hook", action="store_true", help="Preserve a separately owned/unavailable Codex hook configuration")
    args = parser.parse_args()
    print(json.dumps(install(Path(__file__).parent, Path.home(), args.host, args.skip_codex_hook), indent=2))
