#!/usr/bin/env python3
"""Install the `ticket-ref` launcher for this checkout's tools/ticket-ref/ticket_ref.py.

  python3 scripts/ticket_launcher.py install           # dry run: show what would happen
  python3 scripts/ticket_launcher.py install --apply   # write ~/.local/bin/ticket-ref (Windows: ticket-ref.cmd)

An existing launcher, file or symlink, is first saved under a new unique name
(`ticket-ref.<time>.bak`, created exclusively, a symlink stays a symlink); if that fails nothing is
replaced. The new launcher is written to an exclusive temporary file (never through a symlink) and
moved into place with os.replace, which replaces a symlink itself rather than its target. If the
launcher folder or a folder above it below HOME is a symlink (for example ~/.local/bin -> a shared
folder), it refuses with exit code 3 unless --follow-client-links is given; the route is re-checked
right before the backup and the write. A second run with the same content changes nothing. It never initialises the ticket counter. Standard library only.
"""
import argparse
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path
import secrets
import shlex
import stat
import sys

SELF_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SELF_ROOT / "tools/ticket-ref/ticket_ref.py"
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
BINARY = getattr(os, "O_BINARY", 0)


def content(style, python, script):
    if style == "cmd":
        if '"' in str(script) or '"' in python:
            raise ValueError("a double quote cannot appear in a Windows launcher path")
        quoted = str(script).replace("%", "%%")  # cmd expands %NAME% even inside quotes
        return f'@echo off\r\n"{python}" "{quoted}" %*\r\n'.encode("utf-8")
    return f'#!/bin/sh\nexec {shlex.quote(python)} {shlex.quote(str(script))} "$@"\n'.encode("utf-8")


def unique_backup(target):
    """Save TARGET under a new name that did not exist before; a symlink is copied as a link."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    info = os.lstat(str(target))
    for n in range(1000):
        backup = target.with_name(f"{target.name}.{stamp}{'' if n == 0 else '-' + str(n)}.bak")
        try:
            if stat.S_ISLNK(info.st_mode):
                os.symlink(os.readlink(str(target)), str(backup))  # fails if the name exists, link or not
            else:
                fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | BINARY, 0o600)
                source = os.open(str(target), os.O_RDONLY | NOFOLLOW | BINARY)
                with os.fdopen(source, "rb") as src, os.fdopen(fd, "wb") as out:
                    out.write(src.read())
                os.chmod(str(backup), stat.S_IMODE(info.st_mode))
            return backup
        except FileExistsError:
            continue
    raise RuntimeError(f"no free backup name next to {target}")


def write_new(target, data):
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | BINARY, 0o755)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(str(temporary), 0o755)
        os.replace(str(temporary), str(target))
    finally:
        if os.path.lexists(str(temporary)):
            os.unlink(str(temporary))


class LinkRefused(RuntimeError):
    pass


def symlinked_component(home, folder):
    """The first symlink among FOLDER and its parents below HOME (only FOLDER itself when outside HOME)."""
    home, folder = Path(home), Path(folder)
    try:
        chain = [home.joinpath(*folder.relative_to(home).parts[:i + 1]) for i in range(len(folder.relative_to(home).parts))]
    except ValueError:
        chain = [folder]
    for current in chain:
        if os.path.islink(str(current)):
            return current
        if not os.path.lexists(str(current)):
            return None
    return None


def path_advice(bin_dir, style, path_env):
    norm = ntpath.normcase if style == "cmd" else os.path.normpath
    entries = [norm(p) for p in path_env.split(";" if style == "cmd" else os.pathsep) if p]
    if norm(str(bin_dir)) in entries:
        return None
    if style == "cmd":
        return (f"{bin_dir} is not on PATH. In PowerShell: [Environment]::SetEnvironmentVariable('Path', "
                f"'{bin_dir};' + [Environment]::GetEnvironmentVariable('Path', 'User'), 'User'), then open a new terminal.")
    return (f"{bin_dir} is not on PATH. Add  export PATH=\"{bin_dir}:$PATH\"  to ~/.zshrc (macOS) or ~/.bashrc (Linux), "
            "then open a new shell.")


def install(bin_dir, style, python, script=SCRIPT, apply=False, path_env=None, home=None, follow=False):
    bin_dir = Path(bin_dir)
    home = Path.home() if home is None else Path(home)
    link = symlinked_component(home, bin_dir)
    if link is not None and not follow:
        raise LinkRefused(f"{link} is a symlink to {os.readlink(str(link))}; nothing changed "
                          "(rerun with --follow-client-links to write in its resolved location)")
    if link is not None:
        bin_dir = Path(os.path.realpath(str(bin_dir)))
    expected = os.path.realpath(str(bin_dir))

    def guard():
        if os.path.realpath(str(bin_dir)) != expected or (link is None and symlinked_component(home, bin_dir)):
            raise RuntimeError(f"{bin_dir} moved or became a link since the check; nothing replaced")
    target = bin_dir / ("ticket-ref.cmd" if style == "cmd" else "ticket-ref")
    data = content(style, python, script)
    report = {"mode": "apply" if apply else "dry-run", "launcher": str(target), "runs": str(script),
              "via_link": str(link) if link is not None else None,
              "backup": None, "path_advice": path_advice(bin_dir, style, os.environ.get("PATH", "") if path_env is None else path_env)}
    info = os.lstat(str(target)) if os.path.lexists(str(target)) else None
    if info is not None and stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"{target} is a directory; nothing changed")
    if info is not None and stat.S_ISREG(info.st_mode):
        fd = os.open(str(target), os.O_RDONLY | NOFOLLOW | BINARY)
        with os.fdopen(fd, "rb") as handle:
            if handle.read() == data:
                report["result"] = "unchanged"
                return report
    report["result"] = ("replace" if info is not None else "create") + ("" if apply else " (dry run; rerun with --apply)")
    if not apply:
        return report
    bin_dir.mkdir(parents=True, exist_ok=True)
    expected = os.path.realpath(str(bin_dir))
    guard()
    if info is not None:
        report["backup"] = str(unique_backup(target))  # raises before any replacement
    guard()
    write_new(target, data)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("install", help="Install or update the launcher (dry run without --apply)")
    cmd.add_argument("--apply", action="store_true", help="Write the launcher (default: dry run)")
    cmd.add_argument("--bin", type=Path, default=Path.home() / ".local/bin", help="Launcher folder (default: ~/.local/bin)")
    cmd.add_argument("--style", choices=("sh", "cmd"), default="cmd" if os.name == "nt" else "sh",
                     help="sh launcher or Windows .cmd (default: this OS)")
    cmd.add_argument("--follow-client-links", action="store_true",
                     help="Write into the resolved folder when ~/.local/bin (or a folder above it) is a symlink")
    cmd.add_argument("--python", default="python" if os.name == "nt" else "python3",
                     help="Interpreter the launcher runs (default: python3; Windows: python)")
    args = parser.parse_args(argv)
    if not SCRIPT.is_file():
        parser.error(f"{SCRIPT} is missing")
    try:
        report = install(args.bin, args.style, args.python, apply=args.apply, follow=args.follow_client_links)
    except LinkRefused as error:
        print(json.dumps({"error": str(error), "changed": False}, indent=2))
        return 3
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"error": str(error), "changed": False}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
