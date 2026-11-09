#!/usr/bin/env python3
"""Keep explicit skill mirrors (native Windows clients) identical to the skill source.

Windows clients read copies of each skill folder instead of links. A mirror is the
source file with CRLF line endings, and every Markdown link that leaves the skill
folder rewritten to the absolute forward-slash source path, because the client
resolves links from the mirror's own location. Code blocks and inline code are left
as written. Other files are copied byte for byte.

  python scripts/skill_mirrors.py --check      # list stale or missing mirror files and broken links
  python scripts/skill_mirrors.py --apply      # refresh them, backing up what it replaces

Standard library only. It writes nothing outside the mirror folders and its backup,
and never writes through a link into the source.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys

SELF_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIRS = (".claude/skills", ".agents/skills")
# The supported link grammar is closed: anything else in a source file is reported by
# unsupported_links(), so an unhandled form becomes a warning instead of a silent broken mirror.
TITLE = r"""(?:\s+(?:"[^"\n]*"|'[^'\n]*'|\([^()\n]*\)))?"""
# Inline link: ](destination) or ](<destination>), with an optional "title", 'title' or (title).
INLINE = re.compile(r"\]\(\s*(<[^>\n]+>|[^)\s]+)(" + TITLE + r")\s*\)")
# Reference definition at the start of a line: [label]: destination with an optional title.
REFERENCE = re.compile(r"^(\s{0,3}\[[^\]\n]+\]:\s*)(<[^>\n]+>|\S+)(" + TITLE + r"\s*)$")
REFERENCE_LIKE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
EXTERNAL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|#|/)")  # scheme (incl. C:), anchor or absolute


def skills(source):
    return sorted(p for p in source.iterdir() if (p / "SKILL.md").is_file())


def _destination(raw):
    return raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw


def _outside_code(line, rewrite):
    """Apply rewrite to the parts of a line that are not inline code spans."""
    parts = re.split(r"(`+[^`\n]*`+)", line)
    return "".join(part if part.startswith("`") else rewrite(part) for part in parts)


def _markdown_lines(text):
    """Yield (line, in_code) for each line, tracking fenced code blocks."""
    fence = None
    for line in text.split("\n"):
        marker = FENCE.match(line)
        if fence is None and marker:
            fence = marker.group(1)
            yield line, True
        elif fence is not None:
            if marker and marker.group(1) == fence:
                fence = None
            yield line, True
        else:
            yield line, False


def transform(path, source):
    """Mirror bytes for one source file."""
    if path.suffix != ".md":
        return path.read_bytes()
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    skill_dir = (source / path.relative_to(source).parts[0]).resolve()

    def target(raw):
        dest = _destination(raw)
        target_path, hash_, anchor = dest.partition("#")
        if not target_path or EXTERNAL.match(dest):
            return raw
        resolved = (path.parent / target_path).resolve()
        if resolved == skill_dir or str(resolved).startswith(str(skill_dir) + os.sep):
            return raw  # stays inside the skill folder
        new = resolved.as_posix() + (hash_ + anchor)
        return f"<{new}>" if re.search(r"[\s()<>]", new) else new

    def inline(part):
        return INLINE.sub(lambda m: "](" + target(m.group(1)) + m.group(2) + ")", part)

    out = []
    for line, in_code in _markdown_lines(text):
        if in_code:
            out.append(line)
            continue
        ref = REFERENCE.match(line)
        if ref:
            out.append(ref.group(1) + target(ref.group(2)) + ref.group(3))
        else:
            out.append(_outside_code(line, inline))
    return "\n".join(out).replace("\n", "\r\n").encode("utf-8")


def _linked(mirror_root, skill_name, source):
    """True when the client entry is a link (or resolves into the source), so it is not a mirror."""
    entry = mirror_root / skill_name
    return entry.is_symlink() or (entry.exists() and str(entry.resolve()).startswith(str(source.resolve()) + os.sep))


def stale(source, mirror_root):
    """[(relative path, 'missing'|'stale')] for one client's mirror folder; linked skills are skipped."""
    found = []
    for skill in skills(source):
        if _linked(mirror_root, skill.name, source):
            continue
        for path in sorted(skill.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(source)
            target = mirror_root / relative
            if not target.is_file():
                found.append((relative.as_posix(), "missing"))
            elif target.read_bytes() != transform(path, source):
                found.append((relative.as_posix(), "stale"))
    return found


# Safety net for link contexts in any container (blockquote, list, HTML): a destination that
# climbs out of its folder is the only kind that can break in a mirror. Prose is not a link.
PARENT = r"(?:\./)*(?:\.\./)+"
# A delimited destination is captured whole (spaces allowed); a bare one ends at whitespace.
ESCAPE = re.compile(
    r"(?:\]\(\s*|\]:\s*)(?:<(" + PARENT + r"[^>\n]*)>|(" + PARENT + r"""[^\s)\]>'"`|]*))"""
    r"""|\b(?:href|src)\s*=\s*(?:"(""" + PARENT + r"""[^"\n]*)"|'(""" + PARENT + r"""[^'\n]*)'|(""" + PARENT + r"""[^\s>'"`]*))""",
    re.IGNORECASE)


def escaping_tokens(text):
    """[(line number, token)] for parent-relative link destinations outside code (anchors removed)."""
    found = []
    for number, (line, in_code) in enumerate(_markdown_lines(text), 1):
        if in_code:
            continue
        for part in re.split(r"`+[^`\n]*`+", line):
            for match in ESCAPE.finditer(part):
                token = next(group for group in match.groups() if group is not None).partition("#")[0]
                if token:
                    found.append((number, token))
    return found


def unsupported_links(source):
    """[(source file, line number)] for links the transform cannot rewrite safely (outside code).

    Two layers: link syntax outside the supported grammar, and any '../' path that still
    leaves its skill folder after transform(), whatever syntax carries it.
    """
    found = set()
    for skill in skills(source):
        skill_dir = skill.resolve()
        for path in sorted(skill.rglob("*.md")):
            relative = path.relative_to(source).as_posix()
            text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
            for number, (line, in_code) in enumerate(_markdown_lines(text), 1):
                if in_code:
                    continue
                if REFERENCE_LIKE.match(line):
                    if not REFERENCE.match(line):
                        found.add((relative, number))
                    continue
                for part in re.split(r"`+[^`\n]*`+", line):
                    if part.count("](") != len(INLINE.findall(part)):
                        found.add((relative, number))
                        break
            mirrored = transform(path, source).decode("utf-8").replace("\r\n", "\n")
            for number, token in escaping_tokens(mirrored):
                resolved = (path.parent / token).resolve()
                if resolved != skill_dir and not str(resolved).startswith(str(skill_dir) + os.sep):
                    found.add((relative, number))  # still climbs out of the skill after rewriting
    return sorted(found)


def broken_links(mirror_root, source):
    """[(mirror file, destination)] for local links in mirrors that point to nothing.

    Independent of transform(): it reads the mirror as a client would.
    """
    broken = []
    for skill in skills(source):
        if _linked(mirror_root, skill.name, source):
            continue
        for path in sorted((mirror_root / skill.name).rglob("*.md")):
            text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
            for line, in_code in _markdown_lines(text):
                if in_code:
                    continue
                ref = REFERENCE.match(line)
                found = [ref.group(2)] if ref else []
                for part in re.split(r"`+[^`\n]*`+", line):
                    found += [m.group(1) for m in INLINE.finditer(part)]
                for raw in found:
                    dest = _destination(raw).partition("#")[0]
                    if not dest or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://|^mailto:", dest):
                        continue  # bare anchor or URL
                    drive_or_root = dest.startswith("/") or re.match(r"^[A-Za-z]:/", dest)
                    candidate = Path(dest) if drive_or_root else path.parent / dest
                    if not candidate.exists():
                        broken.append((path.relative_to(mirror_root).as_posix(), dest))
            for _, token in escaping_tokens(text):  # any syntax: every '../' path must exist from the mirror
                entry = (path.relative_to(mirror_root).as_posix(), token)
                if not (path.parent / token).exists() and entry not in broken:
                    broken.append(entry)
    return broken


def apply(source, home, backup):
    refreshed = []
    for client in CLIENT_DIRS:
        mirror_root = home / client
        if mirror_root.is_symlink():
            continue  # a linked skills directory is not a mirror
        allowed = mirror_root.resolve()
        for relative, _ in stale(source, mirror_root):
            target = mirror_root / relative
            # Every write must land inside this mirror folder: no link may redirect it elsewhere.
            if target.is_symlink() or not str(target.resolve()).startswith(str(allowed) + os.sep):
                raise SystemExit(f"Refusing to write outside the mirror folder through {target}")
            if target.is_file():
                (backup / client / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup / client / relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(transform(source / relative, source))
            refreshed.append(f"{client}/{relative}")
    return refreshed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--root", type=Path, default=SELF_ROOT, help="Setup source or DevStack checkout")
    parser.add_argument("--home", type=Path, default=Path.home())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    source = (args.root / "skills").resolve()
    if args.check:
        result = {}
        for client in CLIENT_DIRS:
            if (args.home / client).is_symlink():
                continue
            result[client] = ([f"{status}: {path}" for path, status in stale(source, args.home / client)]
                              + [f"broken link: {path} -> {dest}" for path, dest in broken_links(args.home / client, source)])
        result["unsupported link syntax in source"] = [f"{path}:{line}" for path, line in unsupported_links(source)]
        print(json.dumps(result, indent=2))
        return 1 if any(result.values()) else 0
    backup = args.home / ".local/state/devstack" / ("backup-skill-mirrors-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    refreshed = apply(source, args.home, backup)
    print(json.dumps({"refreshed": refreshed, "backup": str(backup) if refreshed else None}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
