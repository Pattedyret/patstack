#!/usr/bin/env python3
"""Set up Patstack for this user on this machine, idempotently. Dry run unless --apply.

  python3 scripts/start_here.py                    # show what would happen
  python3 scripts/start_here.py --apply            # do it

Steps, each reported as one row (OK = already in place, DONE = changed now, TODO = needs the person,
SKIP = not applicable here):
  1. skills         link every skills/<name> into ~/.claude/skills and ~/.agents/skills
                    (Windows: scripts/skill_mirrors.py --apply, which copies instead of linking)
  2. instructions   install examples/global-instructions/AGENTS.md as ~/.claude/CLAUDE.md and
                    ~/.codex/AGENTS.md where absent; an existing file without the Patstack marker is
                    left alone and reported, because merging it is a human decision
  3. merge guard    add tools/merge_guard.py as a PreToolUse Bash hook to ~/.claude/settings.json and
                    ~/.codex/hooks.json, keeping every existing hook; the old file is backed up first.
                    Codex runs a new hook only after the person trusts it once in an interactive codex.
  4. ticket-ref     install the ticket-ref launcher; the counter itself is set up by the agent the first
                    time it needs a new number (it asks for this machine's slot)
  5. project pack   for each bundled pack: its own tools/start_here.py (for example cloning its product
                    vault and checking its test logins)

Nothing is ever overwritten without a backup, nothing is written through a symlink, existing hooks and
instructions are kept, and no credential is read or printed. No ticket, project or production change.
"""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import setup_doctor  # noqa: E402  (reuses its hook readers, so both tools agree on what "wired" means)
from ticket_launcher import symlinked_component  # noqa: E402  (same link policy as the launcher)

TEMPLATE = ROOT / "examples/global-instructions/AGENTS.md"
INSTRUCTIONS = (("claude", ".claude/CLAUDE.md"), ("codex", ".codex/AGENTS.md"))
SKILL_DIRS = (("claude", ".claude/skills"), ("codex", ".agents/skills"))
HOOK_FILES = (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json"))


class Rows:
    def __init__(self):
        self.rows = []

    def add(self, status, step, detail):
        self.rows.append((status, step, detail))

    def print(self, out=sys.stdout):
        for status, step, detail in self.rows:
            print(f"{status:5} {step:15} {detail}", file=out)


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


class Linked(Exception):
    """A destination or one of its folders below HOME is a symlink: nothing is written through it."""


def check_links(home, path):
    """Refuses PATH when it or a folder above it below HOME is a symlink. Outside HOME (an override such as
    PATSTACK_PREFERENCES), every folder above it counts, except the operating system's own top-level links
    (macOS /tmp and /var point into /private)."""
    link = symlinked_component(home, path)
    if link is None:
        try:
            Path(path).relative_to(home)
        except ValueError:
            full = Path(os.path.abspath(str(path)))
            chain = [full, *full.parents]
            link = next((p for p in chain if os.path.islink(str(p)) and p.parent != Path(p.anchor)), None)
    if link is not None:
        raise Linked(f"{link} is a symlink; nothing is written through it, so change {path} by hand")


def create_private(path, mode):
    """Exclusive create with MODE set before any byte is written (the umask cannot widen it)."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, mode)
    return fd


def unique_name(path, suffix):
    """path.<time>.<suffix>, or path.<time>-N.<suffix> when that exists: never an earlier one's name."""
    base = f"{path.name}.{stamp()}"
    for n in range(1000):
        target = path.with_name(f"{base}{'-' + str(n) if n else ''}.{suffix}")
        if not os.path.lexists(str(target)):
            return target
    raise OSError(f"no free {suffix} name next to {path}")


def backup(path, suffix="bak"):
    """Copy path to path.<time>.<suffix>, owner-only (it may hold the same secrets); return the copy's path.
    The name is created exclusively, so a copy never replaces an earlier one."""
    while True:
        target = unique_name(path, suffix)
        try:
            fd = create_private(target, 0o600)
            break
        except FileExistsError:  # taken between the check and the create: try the next name
            continue
    with os.fdopen(fd, "wb") as out:
        out.write(path.read_bytes())
    return target


def write_atomic(home, path, text, new_mode, force_mode=False):
    """Replace PATH atomically. An existing file keeps its own mode, unless FORCE_MODE; a new one gets NEW_MODE."""
    check_links(home, path)
    mode = (path.stat().st_mode & 0o777) if path.exists() and not force_mode else new_mode
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with os.fdopen(create_private(tmp, mode), "w", encoding="utf-8", newline="\n") as out:
        out.write(text)
    os.replace(tmp, path)


def skills(home, apply, rows, windows):
    names = sorted(p.name for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())
    if windows:
        if not apply:
            rows.add("TODO", "skills", f"{len(names)} skill mirrors: run with --apply (skill_mirrors.py --apply)")
            return
        result = subprocess.run([sys.executable, str(ROOT / "scripts/skill_mirrors.py"), "--apply", "--home", str(home)],
                                capture_output=True, text=True)
        rows.add("DONE" if result.returncode == 0 else "TODO", "skills",
                 f"skill_mirrors.py --apply exit {result.returncode}")
        return
    for client, rel in SKILL_DIRS:
        folder = home / rel
        link = symlinked_component(home, folder)
        if link is not None:  # never write through it; only report what already resolves
            here = [n for n in names if (folder / n).is_dir()
                    and Path(os.path.realpath(folder / n)) == (ROOT / "skills" / n).resolve()]
            missing = [n for n in names if not (folder / n).exists()]
            elsewhere = [n for n in names if n not in here and n not in missing]
            if missing:
                rows.add("TODO", f"skills {client}", f"{link} is a symlink above the skill folder; link these by hand "
                                                     f"in its target: {', '.join(missing)}")
            if elsewhere:
                rows.add("TODO", f"skills {client}", f"through {link}, these resolve to another checkout, left alone: "
                                                     f"{', '.join(elsewhere)}")
            if not missing and not elsewhere:
                rows.add("OK", f"skills {client}", f"all {len(names)} resolve to this checkout (through {link})")
            continue
        made, ok, other = [], [], []
        for name in names:
            dest, source = folder / name, ROOT / "skills" / name
            if dest.is_symlink() or dest.exists():
                same = dest.is_symlink() and Path(os.path.realpath(dest)) == source.resolve()
                (ok if same else other).append(name)
                continue
            if apply:
                folder.mkdir(parents=True, exist_ok=True)
                dest.symlink_to(source, target_is_directory=True)
            made.append(name)
        if made:
            rows.add("DONE" if apply else "TODO", f"skills {client}",
                     f"{'linked' if apply else 'would link'} {len(made)} in {folder}: {', '.join(made)}")
        if other:
            rows.add("TODO", f"skills {client}", f"left alone, not this checkout: {', '.join(other)} "
                                                 f"(inspect; an old 'patstack' link is the pre-rename name)")
        if ok and not made and not other:
            rows.add("OK", f"skills {client}", f"all {len(ok)} linked to this checkout")


def instructions(home, apply, rows):
    text = TEMPLATE.read_text(encoding="utf-8").replace("<PATSTACK>", str(ROOT))
    for client, rel in INSTRUCTIONS:
        path = home / rel
        if path.exists() or path.is_symlink():
            try:
                has_marker = setup_doctor.TEMPLATE_MARKER in path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                has_marker = False
            if has_marker:
                rows.add("OK", f"instr {client}", f"{path} has the Patstack instructions")
            else:
                rows.add("TODO", f"instr {client}", f"{path} exists without Patstack: merge {TEMPLATE.relative_to(ROOT)} "
                                                    "into it by hand (keep your rules and the template's first line)")
            continue
        if apply:
            try:
                write_atomic(home, path, text, 0o644)
            except Linked as error:
                rows.add("TODO", f"instr {client}", str(error))
                continue
        rows.add("DONE" if apply else "TODO", f"instr {client}", f"{'installed' if apply else 'would install'} {path}")


def guard_command(root=None, windows=None):
    """The hook command. Windows: Codex runs hooks through cmd.exe /C and Claude Code through a POSIX
    shell, so the path is always double-quoted with forward slashes. Characters either shell still
    expands inside double quotes are refused: % (cmd.exe), $ and ` (bash), and the quote itself."""
    windows = os.name == "nt" if windows is None else windows
    script = (root or ROOT) / "tools" / "merge_guard.py"
    if windows:
        text = script.as_posix()
        if any(c in text for c in '%$`"'):
            raise ValueError(f"checkout path {text} has % $ ` or a quote; move the checkout to a plain path")
        return f'python "{text}"'
    return f"python3 {shlex.quote(str(script))}"


def merge_guard(home, apply, rows, clients):
    for client, rel in HOOK_FILES:
        if client not in clients:
            continue
        path = home / rel
        try:
            # utf-8-sig: Windows PowerShell 5 and Notepad can write a byte-order mark; a rewrite drops it
            settings = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        except (OSError, ValueError):
            rows.add("TODO", f"guard {client}", f"{path} is not readable JSON; fix it, then rerun")
            continue
        if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
            rows.add("TODO", f"guard {client}", f"{path} has an unexpected shape; add the hook by hand (docs/setup.md step 6)")
            continue
        if setup_doctor.guard_positions(settings):
            rows.add("OK", f"guard {client}", f"merge guard wired in {path}")
        elif apply:
            try:
                check_links(home, path)
                command = guard_command()
            except (Linked, ValueError) as error:
                rows.add("TODO", f"guard {client}", f"{error} (docs/setup.md step 6)")
                continue
            saved = backup(path) if path.exists() else None
            settings.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
                {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]})
            write_atomic(home, path, json.dumps(settings, indent=2) + "\n", 0o600)
            note = f" (backup {saved.name})" if saved else ""
            rows.add("DONE", f"guard {client}", f"added the merge guard to {path}{note}")
        else:
            rows.add("TODO", f"guard {client}", f"would add the merge guard to {path}")
        if client == "codex" and apply or client == "codex" and path.exists():
            current = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
            wired = setup_doctor.guard_positions(current)
            if wired and setup_doctor.codex_guard_state(home, path, current, wired) == "trusted":
                rows.add("OK", "guard codex", "Codex has recorded trust for the merge guard")
            else:
                rows.add("TODO", "guard codex", "start `codex` once in a terminal and choose 'Trust all and continue' "
                                                "(or /hooks): Codex skips an untrusted hook without a word")


def ticket_numbers(home, apply, rows):
    """Only the launcher. The counter is the agent's job the first time it needs a new number: it asks
    for this machine's slot and derives --after from history (skills/patstack/references/coordination.md)."""
    db = Path(os.environ.get("PATSTACK_TICKET_DB") or home / ".local/state/patstack/tickets.sqlite3")
    rows.add("OK" if db.exists() else "SKIP", "tickets",
             f"counter initialized ({db})" if db.exists() else
             "no counter yet; the agent sets it up the first time it needs a new number and asks you for "
             "this machine's slot (handed out by the Patstack maintainer)")
    launcher = home / ".local/bin" / ("ticket-ref.cmd" if os.name == "nt" else "ticket-ref")
    tool = str(ROOT / "tools" / "ticket-ref" / "ticket_ref.py")
    try:
        current = launcher.exists() and tool in launcher.read_text(encoding="utf-8", errors="replace")
    except OSError:
        current = False
    if current:
        rows.add("OK", "ticket-ref", f"launcher {launcher}")
    elif not apply:
        rows.add("TODO", "ticket-ref", f"would {'repoint' if launcher.exists() else 'install'} the launcher {launcher}"
                                       + (" (it runs another checkout)" if launcher.exists() else ""))
    else:
        result = subprocess.run([sys.executable, str(ROOT / "scripts/ticket_launcher.py"), "install", "--apply",
                                 "--bin", str(launcher.parent)],
                                capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
        error = (result.stderr.strip().splitlines() or [""])[-1]
        rows.add("DONE" if result.returncode == 0 else "TODO", "ticket-ref",
                 f"installed the launcher {launcher}" if result.returncode == 0
                 else f"launcher install failed (exit {result.returncode}): {error}")


def monday(home, apply, rows):
    """The `ticket board` row: team board access (Monday) when a pack ships monday.json. OK only after the board
    answered with the person's token; TODO says what is missing. The token is personal and secret, so this step
    never takes or writes it: the agent does that through the host's private secret input (the skill's step 3).
    What counts as absent or broken is decided by tools/monday_ticket.py alone."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import monday_ticket
    finally:
        sys.path.pop(0)
    try:
        cfg = monday_ticket.load_config(home=home)
    except monday_ticket.NoConfig:
        rows.add("SKIP", "ticket board", "no team board configured (no project-packs/<pack>/monday.json)")
        return
    except monday_ticket.MondayError as error:  # configured but broken: never skip that quietly
        rows.add("TODO", "ticket board", f"the team board configuration is broken ({error}); fix or remove it, then rerun")
        return
    page = f"https://{cfg['account']}.monday.com/apps/manage/tokens"
    store = "take the token through the private secret input, then run `python3 tools/monday_ticket.py setup --store <file>`"
    try:
        token = monday_ticket.read_token(home=home)
    except monday_ticket.NoToken:
        rows.add("TODO", "ticket board", f"no Monday token yet: open {page} in the person's browser, {store}")
        return
    except monday_ticket.MondayError as error:
        rows.add("TODO", "ticket board", f"the stored Monday token cannot be used ({error}); fix that, or create a new "
                                         f"one at {page} and {store}")
        return
    try:
        rows.add("OK", "ticket board", monday_ticket.check(monday_ticket.Api(token, cfg, timeout=15, tries=1), cfg))
    except monday_ticket.MondayError as error:
        rows.add("TODO", "ticket board", f"token stored but the board check failed ({error}); if the token is wrong or "
                                         f"expired, create a new one at {page} and store it again")


def packs(home, apply, rows):
    """Each bundled pack may ship tools/start_here.py with run(home, apply, add) for its own setup."""
    found = sorted((ROOT / "project-packs").glob("*/tools/start_here.py"))
    if not found:
        rows.add("SKIP", "project pack", "no bundled pack setup")
    for tool in found:
        name = tool.parent.parent.name
        spec = importlib.util.spec_from_file_location(f"patstack_pack_start_{name}", tool)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            module.run(home, apply, lambda status, step, detail: rows.add(status, f"{name} {step}", detail))
        except Exception as error:  # a broken pack hook must not stop the rest of the setup
            rows.add("TODO", f"{name}", f"pack setup failed: {type(error).__name__}: {error}")


def clients_in_use(home, option):
    if option != "auto":
        return {"both": {"claude", "codex"}}.get(option, {option})
    return set(setup_doctor.detect_clients(home) or ("claude", "codex"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    parser.add_argument("--clients", choices=("auto", "claude", "codex", "both"), default="both",
                        help="clients to wire the merge guard for (default both: harmless for an unused client)")
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    home = args.home.expanduser()
    rows = Rows()
    windows = os.name == "nt"
    skills(home, args.apply, rows, windows)
    instructions(home, args.apply, rows)
    merge_guard(home, args.apply, rows, clients_in_use(home, args.clients))
    ticket_numbers(home, args.apply, rows)
    try:
        monday(home, args.apply, rows)
    except Exception as error:  # this step must never cost the person the other rows
        rows.add("TODO", "ticket board", f"the team board step failed ({error.__class__.__name__}); run "
                                   "`python3 tools/monday_ticket.py check` to see why")
    packs(home, args.apply, rows)
    rows.print()
    todo = sum(1 for status, _, _ in rows.rows if status == "TODO")
    print(f"{'APPLIED' if args.apply else 'DRY-RUN'}: {todo} item(s) need you. "
          f"Then run: python3 scripts/setup_doctor.py --host {'windows' if windows else 'mac' if sys.platform == 'darwin' else 'devbox'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
