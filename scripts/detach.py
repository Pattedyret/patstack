#!/usr/bin/env python3
"""Detach a DevStack checkout from this user's Claude Code and Codex configuration.

  python3 scripts/detach.py                         # dry run: what an uninstall of this checkout would change
  python3 scripts/detach.py --apply                 # uninstall: skill links, unchanged mirror files, DevStack hooks
  python3 scripts/detach.py --from OLD_PATH         # dry run after moving the checkout here from OLD_PATH
  python3 scripts/detach.py --from OLD_PATH --apply # drop OLD_PATH's links and hooks, repoint instructions here
  ... --follow-client-links                         # also inside a symlinked ~/.claude, ~/.codex or ~/.agents

What it touches, and nothing else:
- links in ~/.claude/skills and ~/.agents/skills whose target lies inside CHECKOUT/skills/;
- on uninstall only, mirror files (native Windows copies) whose bytes equal what skill_mirrors.py
  writes for this checkout; edited or added files, symlinks and anything below a symlink stay;
- hooks in ~/.claude/settings.json and ~/.codex/hooks.json whose command is exactly one of the forms
  monitoring/devstack/install.py writes for CHECKOUT (interpreter, kpi_monitor.py or setup_doctor.py,
  exact arguments); any other hook, also one that mentions the checkout, stays;
- after a move, the old path in ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md when they are regular
  files. A symlinked instruction file is reported and never written through.

Every path is checked component by component from HOME down. If a folder on the way is a symlink
(for example ~/.claude -> a shared folder), nothing under it is touched: it is listed under `kept` and
`left_in_place`, and the exit code is 3. --follow-client-links opts in to working on the resolved
location instead, with the same exact-match, byte-identical and backup rules. The route to each path is
re-validated right before every write or delete. Exit codes: 0 done, 1 stopped on an error, 3 pieces
left behind a symlinked client folder.

Paths are compared literally after normalisation (no globbing), so a sibling such as devstack1 next to
devstack[1] never matches. Every change is backed up first under
~/.local/state/devstack/detach-backups/<time>/ (a new folder per run, never overwritten); a failed
backup stops the run before that change. Files are rewritten through a temporary file and os.replace,
keeping unknown JSON keys. A second run finds nothing to do. Standard library only, Python 3.9+.
"""
import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import json
import ntpath
import os
import posixpath
import re
import shlex
import stat
import sys
import tempfile
from pathlib import Path

SELF_ROOT = Path(__file__).resolve().parent.parent
CLIENT_SKILL_DIRS = (".claude/skills", ".agents/skills")
HOOK_FILES = (".claude/settings.json", ".codex/hooks.json")
INSTRUCTION_FILES = (".claude/CLAUDE.md", ".codex/AGENTS.md")
HOSTS = ("mac", "devbox", "windows")
RUNTIMES = ("claude", "codex")
EVENTS = ("Stop", "PostToolUse", "PostToolUseFailure", "SessionEnd")
INTERPRETER = re.compile(r"(python(\d+(\.\d+)*)?|py)(\.exe)?", re.IGNORECASE)
WINDOWS = os.name == "nt"


def norm(path, windows=WINDOWS):
    """Literal, normalised comparison key for a path (no filesystem access, no globbing)."""
    if windows:
        return ntpath.normcase(ntpath.normpath(str(path).replace("/", "\\")))
    return posixpath.normpath(str(path))


def parts(path, windows=WINDOWS):
    return [p for p in norm(path, windows).split("\\" if windows else "/") if p]


def within(path, root, windows=WINDOWS, equal=False):
    """True when PATH lies below ROOT (or is ROOT with equal=True), compared component by component."""
    p, r = parts(path, windows), parts(root, windows)
    return p[:len(r)] == r and (len(p) > len(r) or (equal and len(p) == len(r)))


def roots(path):
    """The given and the resolved spelling of a checkout path, so either form matches."""
    found = [os.path.abspath(str(path))]
    resolved = os.path.realpath(str(path))
    if resolved not in found:
        found.append(resolved)
    return found


def hook_kind(command, checkout_roots, windows=WINDOWS):
    """'kpi' or 'status' when COMMAND is exactly an installer hook for one of CHECKOUT_ROOTS, else None."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if shlex.join(argv) != command or len(argv) < 2:
        return None  # the installer writes shlex.join(argv); anything else was written by someone else
    name = ntpath.basename(argv[0]) if windows else posixpath.basename(argv[0])
    if not INTERPRETER.fullmatch(name):
        return None
    script, rest = argv[1], argv[2:]
    for root in checkout_roots:
        base = root.replace("\\", "/") if windows else root
        if norm(script, windows) == norm(base + "/monitoring/devstack/kpi_monitor.py", windows):
            if (len(rest) == 7 and rest[0] == "audit-hook" and rest[1] == "--host" and rest[2] in HOSTS
                    and rest[3] == "--runtime" and rest[4] in RUNTIMES and rest[5] == "--event" and rest[6] in EVENTS):
                return "kpi"
        if norm(script, windows) == norm(base + "/scripts/setup_doctor.py", windows):
            if len(rest) == 4 and rest[0] == "--host" and rest[2] == "--hook" and rest[1] in HOSTS and rest[3] in RUNTIMES:
                return "status"
    return None


def strip_hooks(data, checkout_roots, windows=WINDOWS):
    """A copy of DATA without DevStack hooks for the checkout, and how many were removed."""
    data = copy.deepcopy(data)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return data, 0
    removed = 0
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                kept.append(group)
                continue
            left = [h for h in entries if not (isinstance(h, dict) and isinstance(h.get("command"), str)
                                                and hook_kind(h["command"], checkout_roots, windows))]
            removed += len(entries) - len(left)
            if left or not entries:  # drop a group only when this run emptied it
                group["hooks"] = left
                kept.append(group)
        if kept or not groups:
            hooks[event] = kept
        else:
            del hooks[event]
    return data, removed


def named(old_forms):
    """Regex matching an old checkout path as a whole path (followed by a separator, quote, space or end)."""
    alternatives = "|".join(re.escape(form) for form in sorted(set(old_forms), key=len, reverse=True))
    return re.compile("(?:" + alternatives + r")(?=[/\\`'\")\s]|$)")


def lstat(path):
    try:
        return os.lstat(str(path))
    except FileNotFoundError:
        return None


def safe_mirror_file(mirror_root, relative):
    """MIRROR_ROOT/RELATIVE when every component is a real directory and the last a regular file inside it."""
    current = Path(mirror_root)
    info = lstat(current)
    if info is None or not stat.S_ISDIR(info.st_mode):
        return None  # also rejects a symlinked mirror root
    for i, part in enumerate(relative.parts):
        current = current / part
        info = lstat(current)
        last = i == len(relative.parts) - 1
        if info is None or stat.S_ISLNK(info.st_mode):
            return None
        if (last and not stat.S_ISREG(info.st_mode)) or (not last and not stat.S_ISDIR(info.st_mode)):
            return None
    if not within(os.path.realpath(str(current)), os.path.realpath(str(mirror_root))):
        return None
    return current


class Backup:
    def __init__(self, home):
        self.base = Path(home) / ".local/state/devstack/detach-backups"
        self.home = Path(home)
        self.folder = None

    def _ensure(self):
        if self.folder is None:
            self.base.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            for n in range(1000):
                candidate = self.base / (stamp if n == 0 else f"{stamp}-{n}")
                try:
                    candidate.mkdir(mode=0o700)  # exclusive: an existing backup is never reused
                except FileExistsError:
                    continue
                self.folder = candidate
                break
            else:
                raise RuntimeError("no free backup folder name")
        return self.folder

    def save(self, path):
        """Copy PATH (a link stays a link) into the backup; raise before any change if that fails."""
        path = Path(path)
        folder = self._ensure()
        try:
            relative = Path(os.path.relpath(str(path), str(self.home)))
            if relative.parts and relative.parts[0] == "..":
                raise ValueError
        except ValueError:
            drive = re.sub(r"[^A-Za-z0-9]", "", path.drive)  # a resolved shared folder keeps its own layout
            relative = Path("outside", *([drive] if drive else []), *path.parts[1:])
        dest = folder / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        info = os.lstat(str(path))
        if stat.S_ISLNK(info.st_mode):
            os.symlink(os.readlink(str(path)), str(dest))
        else:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            source = os.open(str(path), flags)
            with os.fdopen(source, "rb") as handle:
                content = handle.read()
            with open(str(dest), "xb") as out:
                out.write(content)
            os.chmod(str(dest), 0o600)
        return dest


def replace_file(path, content):
    """Write CONTENT to PATH through a temporary file and os.replace; never through a symlink."""
    path = Path(path)
    if path.is_symlink():
        raise RuntimeError(f"{path} is a symlink; not written through")
    mode = stat.S_IMODE(os.lstat(str(path)).st_mode)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, str(path))
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def load_mirrors():
    spec = importlib.util.spec_from_file_location("skill_mirrors", Path(__file__).with_name("skill_mirrors.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def symlinked_ancestor(home, path):
    """The first component strictly between HOME and PATH that is a symlink, else None."""
    home, path = Path(home), Path(path)
    try:
        relative = path.relative_to(home)
    except ValueError:
        return None
    current = home
    for part in relative.parts[:-1]:
        current = current / part
        info = lstat(current)
        if info is None:
            return None
        if stat.S_ISLNK(info.st_mode):
            return current
    return None


def plan_skills(folder, checkout_roots, new, source, windows, transform, actions, kept):
    info = lstat(folder)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        target = os.path.join(str(folder.parent), os.readlink(str(folder)))
        if any(within(target, r + "/skills", windows, equal=True) for r in checkout_roots):
            actions.append({"action": "remove link", "path": str(folder)})
        else:
            kept.append({"path": str(folder), "reason": "skills folder is a symlink elsewhere; not descended"})
        return
    if not stat.S_ISDIR(info.st_mode):
        return
    for entry in sorted(folder.iterdir()):
        entry_info = lstat(entry)
        if entry_info is None:
            continue
        if stat.S_ISLNK(entry_info.st_mode):
            target = os.path.join(str(folder), os.readlink(str(entry)))
            resolved = os.path.realpath(str(entry))
            if any(within(t, r + "/skills", windows) for r in checkout_roots for t in (target, resolved)):
                actions.append({"action": "remove link", "path": str(entry)})
            continue
        if new is not None or source is None or not stat.S_ISDIR(entry_info.st_mode):
            continue
        skill = Path(source) / entry.name
        if not (skill / "SKILL.md").is_file():
            continue
        for src in sorted(skill.rglob("*")):
            if not src.is_file() or "__pycache__" in src.parts:
                continue
            relative = src.relative_to(skill)
            mirror = safe_mirror_file(entry, relative)
            if mirror is None:
                if os.path.lexists(str(entry / relative)):
                    kept.append({"path": str(entry / relative), "reason": "symlink on the way or not a regular file"})
                continue
            if mirror.read_bytes() == transform(src, Path(source)):
                actions.append({"action": "delete mirror file", "path": str(mirror), "mirror_root": str(entry)})
            else:
                kept.append({"path": str(mirror), "reason": "differs from the mirror tool's output"})


def plan_hooks(path, checkout_roots, windows, actions, kept):
    info = lstat(path)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        kept.append({"path": str(path), "reason": "symlink; not written through"})
        return
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        kept.append({"path": str(path), "reason": "not valid JSON; not changed"})
        return
    stripped, removed = strip_hooks(data, checkout_roots, windows)
    if removed:
        actions.append({"action": "remove hooks", "path": str(path), "count": removed, "before": raw,
                        "content": (json.dumps(stripped, indent=2, ensure_ascii=False) + "\n").encode("utf-8")})


def plan_instructions(path, pattern, new, actions, kept, manual):
    info = lstat(path)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        kept.append({"path": str(path), "reason": f"symlink to {os.readlink(str(path))}; not written through, "
                                                   "edit the target yourself if it names the old path"})
        return
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="surrogateescape")
    if not pattern.search(text):
        return
    if new is None:
        manual.append({"path": str(path), "todo": "still names this checkout; delete the DevStack sections or restore your .bak"})
    else:
        replacement = str(new)
        content = pattern.sub(lambda m: replacement, text).encode("utf-8", errors="surrogateescape")
        actions.append({"action": "repoint instructions", "path": str(path), "to": replacement,
                        "before": raw, "content": content})


def plan(home, checkout, new=None, source=None, windows=WINDOWS, transform=None, follow=False):
    """Actions (dicts) for the run, plus kept/manual/left-in-place notes. No filesystem change.

    A client folder reached through a symlink below HOME (for example ~/.claude -> a shared folder) is
    not touched unless FOLLOW; then the resolved location is used, with the same exact-match rules.
    """
    home = Path(home)
    checkout_roots = roots(checkout)
    actions, kept, manual, left = [], [], [], []
    old_forms = []
    for r in checkout_roots:
        old_forms += [r, r.replace("\\", "/")]
    if str(checkout) not in old_forms:
        old_forms.append(str(checkout))
    pattern = named(old_forms)
    targets = ([(r, "skills") for r in CLIENT_SKILL_DIRS] + [(r, "hooks") for r in HOOK_FILES]
               + [(r, "instructions") for r in INSTRUCTION_FILES])
    for relative, kind in targets:
        path = home / relative
        link = symlinked_ancestor(home, path)
        if link is not None:
            path = Path(os.path.realpath(str(path.parent))) / path.name
        if kind == "skills":
            info = lstat(path)
            owned = info is not None and stat.S_ISLNK(info.st_mode) and any(
                within(os.path.join(str(path.parent), os.readlink(str(path))), r + "/skills", windows, equal=True)
                for r in checkout_roots)
            if info is not None and stat.S_ISLNK(info.st_mode) and not owned:
                # A skills folder linked elsewhere (a shared folder) is a client link like ~/.claude itself.
                link = link if link is not None else path
                path = Path(os.path.realpath(str(path)))
        own_actions, own_kept, own_manual = [], [], []
        if kind == "skills":
            plan_skills(path, checkout_roots, new, source, windows, transform, own_actions, own_kept)
        elif kind == "hooks":
            plan_hooks(path, checkout_roots, windows, own_actions, own_kept)
        else:
            plan_instructions(path, pattern, new, own_actions, own_kept, own_manual)
        if link is not None and not follow:
            if own_actions or own_manual:
                reason = (f"{link} is a symlink to {os.readlink(str(link))}; nothing under it was touched "
                          "(rerun with --follow-client-links to include it)")
                kept.append({"path": str(home / relative), "reason": reason})
                left.append({"path": str(home / relative), "link": str(link), "pieces": len(own_actions) + len(own_manual)})
            continue
        for action in own_actions:
            action["parent_real"] = os.path.realpath(str(Path(action["path"]).parent))
            action["guard_home"] = None if link is not None else str(home)
            if link is not None:
                action["via_link"] = str(link)
        actions += own_actions
        kept += own_kept
        manual += own_manual
    return dedupe(actions, windows), kept, manual, left


def destination(path, windows=WINDOWS):
    """Where an action really lands: the resolved folder plus the entry's own name (a link is not followed)."""
    path = Path(path)
    return norm(os.path.join(os.path.realpath(str(path.parent)), path.name), windows)


def dedupe(actions, windows=WINDOWS):
    """Drop actions that reach an already planned destination (aliased client folders share one folder)."""
    seen, unique = set(), []
    for action in actions:
        key = destination(action["path"], windows)
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def guard(action):
    """Re-validate the route to an action's path right before it changes anything."""
    path = Path(action["path"])
    if os.path.realpath(str(path.parent)) != action["parent_real"]:
        raise RuntimeError(f"the folder holding {path} moved or became a link since the plan; stopped")
    if action["guard_home"] is not None and symlinked_ancestor(action["guard_home"], path) is not None:
        raise RuntimeError(f"a folder above {path} became a symlink since the plan; stopped")


def execute(actions, backup):
    done, mirror_roots = [], []
    for action in actions:
        path = Path(action["path"])
        kind = action["action"]
        guard(action)
        if kind == "remove link":
            if not path.is_symlink():
                raise RuntimeError(f"{path} changed since the plan; stopped")
            backup.save(path)
            guard(action)
            path.unlink()
        elif kind == "delete mirror file":
            root = Path(action["mirror_root"])
            if safe_mirror_file(root, path.relative_to(root)) is None:
                raise RuntimeError(f"{path} changed since the plan; stopped")
            backup.save(path)
            guard(action)
            path.unlink()
            if str(root) not in mirror_roots:
                mirror_roots.append(str(root))
        else:
            if path.is_symlink() or path.read_bytes() != action["before"]:
                raise RuntimeError(f"{path} changed since the plan; stopped")
            backup.save(path)
            guard(action)
            replace_file(path, action["content"])
        done.append(action)
    for root in mirror_roots:  # remove folders this run emptied; never follow or remove a symlink
        for dirpath, _, _ in os.walk(root, topdown=False, followlinks=False):
            if not os.path.islink(dirpath) and not os.listdir(dirpath):
                os.rmdir(dirpath)
    return done


def public(action):
    return {k: v for k, v in action.items() if k not in ("before", "content", "mirror_root", "parent_real", "guard_home")}


def run(home, checkout, new=None, source=None, apply=False, windows=WINDOWS, transform=None, follow=False):
    if transform is None and new is None and source is not None:
        transform = load_mirrors().transform
    actions, kept, manual, left = plan(home, checkout, new, source, windows, transform, follow)
    report = {"mode": "apply" if apply else "dry-run", "checkout": str(checkout),
              "repoint_to": str(new) if new is not None else None,
              "changes": [public(a) for a in actions], "kept": kept, "manual": manual,
              "left_in_place": left, "backup": None}
    if apply and actions:
        backup = Backup(home)
        try:
            execute(actions, backup)
        except (OSError, RuntimeError) as error:
            report["error"] = f"stopped: {error}; changes made before this point are backed up"
        report["backup"] = str(backup.folder) if backup.folder else None
    if not actions and not left:
        report["note"] = "nothing to change"
    elif not actions:
        report["note"] = "DevStack pieces remain behind symlinked client folders; see left_in_place"
    elif not apply:
        report["note"] = "dry run: nothing changed; rerun with --apply"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="old", type=Path,
                        help="Old location of this checkout after a move; repoint instructions to this checkout")
    parser.add_argument("--apply", action="store_true", help="Make the changes (default: dry run)")
    parser.add_argument("--follow-client-links", action="store_true",
                        help="Also work inside client folders reached through a symlink below HOME (for example "
                             "~/.claude -> a shared folder), on their resolved location, with the same rules")
    parser.add_argument("--home", type=Path, default=Path.home(), help="Home directory (tests)")
    args = parser.parse_args(argv)
    if args.old is not None:
        if within(os.path.abspath(str(args.old)), str(SELF_ROOT), equal=True):
            parser.error("--from must be the checkout's old location, not this checkout")
        report = run(args.home, args.old, new=SELF_ROOT, apply=args.apply, follow=args.follow_client_links)
    else:
        report = run(args.home, SELF_ROOT, source=SELF_ROOT / "skills", apply=args.apply,
                     follow=args.follow_client_links)
    print(json.dumps(report, indent=2))
    return exit_code(report)


def exit_code(report):
    """0 done (or nothing to do), 1 stopped on an error, 3 DevStack pieces left behind symlinked client folders."""
    if "error" in report:
        return 1
    return 3 if report["left_in_place"] else 0


if __name__ == "__main__":
    sys.exit(main())
