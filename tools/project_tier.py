#!/usr/bin/env python3
"""Report a project's tier, which decides how the Patstack mode is chosen.

  python3 tools/project_tier.py [--path DIR] [--json]

The tier says who a failure reaches:

  CRITICAL      customer-facing products for consulting work or other customers
  INTERNAL      any internal tool for your own team, including shared team tooling
  UNCLASSIFIED  anything not positively classified; treated exactly as CRITICAL

CRITICAL and UNCLASSIFIED projects evaluate Full Send or Full Stop at intake.
INTERNAL projects are always Full Send. The map is PATSTACK_PROJECT_TIERS when set, else your
private ~/.config/patstack/project-tiers.json when it exists, else the one tier map a bundled
project pack ships (project-packs/<name>/project-tiers.json; more than one fails closed).
examples/project-tiers.example.json shows the shape:

  owners  GitHub owner -> CRITICAL. Only CRITICAL: an owner default never lowers a tier.
  repos   OWNER/NAME for GitHub, or HOST[:PORT]/PATH for another forge -> any tier.
  local   path relative to the home directory, for a project with no remotes -> any tier.
  local_ci  optional list of GitHub owners or OWNER/NAME that run no GitHub Actions at all.
            Every repository's CI runs in the agent (tools/local_ci.py runs scripts/ci-local.sh);
            for these, tools/merge_gate.py also leaves GitHub checks unread, and workflow files
            that remain are removed. It changes no tier.

The tier comes from the checkout, never from a name passed in. A project is
INTERNAL only if every effective fetch and push URL of every remote is positively
classified by its exact `repos` entry. Each URL gets its entry or `owners` default, else
UNCLASSIFIED, and the project takes the strictest result, so a customer remote cannot hide
behind a personal fork. A failed lookup, an unsupported remote, a missing path, an invalid
map or any unexpected error gives UNCLASSIFIED: a mistake can never lower a project's tier.
Every run prints a tier. Exit 0, or 2 on a usage error. Python 3.9+, standard library only.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

TIERS = ("CRITICAL", "INTERNAL")
UNCLASSIFIED = "UNCLASSIFIED"
ALWAYS_FULL_SEND = ("INTERNAL",)
STRICTNESS = {"INTERNAL": 0, UNCLASSIFIED: 1, "CRITICAL": 2}
GITHUB_HOSTS = ("github.com", "www.github.com", "ssh.github.com")
GITHUB_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:/[A-Za-z0-9._-]+)?")  # use fullmatch
SCP_LIKE = re.compile(r"^(?:[^@/:\s]+@)?([\w-]+(?:\.[\w-]+)+):(?!/)(.+)$")


ROOT = Path(__file__).resolve().parent.parent


def map_path():
    """The override, else the private map (which may not exist)."""
    override = os.environ.get("PATSTACK_PROJECT_TIERS")
    return Path(override) if override else Path.home() / ".config/patstack/project-tiers.json"


def pack_map(root):
    """(path or None, problem): the one tier map the bundled project packs ship.

    Only a plain project-packs/<name>/project-tiers.json counts, hidden folders included. A
    symlinked pack folder or map, an unreadable entry, or more than one map is a problem, so the
    caller fails closed: packs never combine, and nothing about them can lower a tier."""
    packs = Path(root) / "project-packs"
    try:
        folders = sorted(packs.iterdir())
    except FileNotFoundError:
        return None, None
    except OSError as error:
        return None, f"unreadable project packs {packs}: {error}"
    found = []
    for folder in folders:
        candidate = folder / "project-tiers.json"
        try:
            if folder.is_symlink():
                return None, f"pack folder {folder} is a symlink; tier maps must be plain files"
            if not folder.is_dir():
                continue
            os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError as error:
            return None, f"unreadable pack tier map {candidate}: {error}"
        if candidate.is_symlink() or not candidate.is_file():
            return None, f"pack tier map {candidate} is not a plain file"
        found.append(candidate)
    if len(found) > 1:
        return None, "more than one bundled pack tier map; put the tiers you want in a private map"
    return (found[0] if found else None), None


def load_tiers(root=ROOT):
    """The override or private map when there is one, else the single bundled pack map."""
    path = map_path()
    # a private map that exists in any form, even a broken link, is the user's choice: never fall back
    if os.environ.get("PATSTACK_PROJECT_TIERS") or path.exists() or path.is_symlink():
        return load_map(path)
    pack, problem = pack_map(root)
    if problem:
        return {}, problem
    return load_map(pack or path)


def normalized(key):
    """GitHub names ignore case; on another forge only the host does."""
    head, separator, rest = key.partition("/")
    return f"{head.lower()}{separator}{rest}" if re.search(r"[.:]", head) else key.lower()


def section_problem(name, section, allowed):
    if not isinstance(section, dict):
        return f"{name} is not an object"
    keys = [normalized(key) if isinstance(key, str) else key for key in section]
    if len(set(keys)) != len(keys):
        return f"{name} has entries that differ only in case"
    wrong = [key for key, value in section.items() if value not in allowed]
    return f"{name} has invalid values for {sorted(wrong)}" if wrong else None


def validate(data):
    """The reason this map cannot be trusted, or None."""
    if not isinstance(data, dict):
        return "the map is not an object"
    unknown = set(data) - {"owners", "repos", "local", "local_ci"}
    if unknown:
        return f"unknown sections {sorted(unknown)}"
    local = data.get("local_ci", [])
    if not isinstance(local, list) or not all(isinstance(x, str) and GITHUB_NAME.fullmatch(x) for x in local):
        return "local_ci is not a list of GitHub owners or OWNER/NAME"
    allowed = {"owners": ("CRITICAL",), "repos": TIERS, "local": TIERS}
    for name, values in allowed.items():
        problem = section_problem(name, data.get(name, {}), values)
        if problem:
            return problem
    return None


def unique_keys(pairs):
    """A JSON object, refusing a key given twice: the later one would silently win."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key appears twice in one object")
    return dict(pairs)


def load_map(path):
    """The map, or an empty one with a warning: a bad file must not lower a tier."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    except FileNotFoundError:
        return {}, f"no tier map at {path}"
    except (OSError, ValueError) as error:
        return {}, f"unreadable tier map {path}: {error}"
    problem = validate(data)
    return ({}, f"invalid tier map {path}: {problem}") if problem else (data, None)


def identity(url):
    """`owner/name` for GitHub, `host[:port]/path` elsewhere, or None if unsupported."""
    url = url.strip()
    port = None
    if "://" in url:
        try:
            parts = urlsplit(url)
            host, path, port = parts.hostname, parts.path, parts.port
        except ValueError:
            return None
        if parts.scheme not in ("https", "http", "ssh", "git"):
            return None
    else:
        match = SCP_LIKE.match(url)
        if not match:
            return None
        host, path = match.groups()
    segments = [segment for segment in path.split("/") if segment]
    if not host or "." not in host or not segments:
        return None
    segments[-1] = re.sub(r"\.git$", "", segments[-1])
    host = host.lower()
    if host in GITHUB_HOSTS and len(segments) == 2:
        return "/".join(segments).lower()
    return "/".join([f"{host}:{port}" if port else host, *segments])


def git(path, *args):
    """A completed process, or None when Git could not run."""
    try:
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None


def legacy_remote_files(path):
    """Files in the old remote locations, which `git remote` omits, or None if unreadable."""
    found = []
    for kind in ("remotes", "branches"):
        where = git(path, "rev-parse", "--path-format=absolute", "--git-path", kind)
        if where is None or where.returncode != 0:
            return None
        folder = Path(where.stdout.strip())
        found += list(folder.iterdir()) if folder.is_dir() else []
    return found


def discover(path):
    """(top level, {remote: [urls]}), or (None, reason) when the checkout cannot be read."""
    if not Path(path).is_dir():
        return None, f"{path} is not a directory"
    top = git(path, "rev-parse", "--show-toplevel")
    if top is None:
        return None, "git could not run"
    if top.returncode != 0:
        if "not a git repository" in top.stderr.lower():
            return Path(path).resolve(), {}
        return None, "git could not read the checkout"
    legacy = legacy_remote_files(path)
    if legacy is None or legacy:
        return None, "git keeps remotes here that it does not list (.git/remotes or .git/branches)"
    names = git(path, "remote")
    if names is None or names.returncode != 0:
        return None, "git could not read the remotes"
    remotes = {}
    for name in names.stdout.splitlines():
        for direction in ((), ("--push",)):
            urls = git(path, "remote", "get-url", *direction, "--all", name)
            if urls is None or urls.returncode != 0:
                return None, "git could not read a remote's address"
            remotes.setdefault(name, []).extend(urls.stdout.splitlines())
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common is None or common.returncode != 0:
        return None, "git could not read the repository"
    # A worktree is the same project as its main checkout, which is what `local` names.
    common_dir = Path(common.stdout.strip())
    return (common_dir.parent if common_dir.name == ".git" else Path(top.stdout.strip())).resolve(), remotes


def remote_tier(data, name):
    """The tier the map gives one identity, or None if it has none."""
    repos = {normalized(key): value for key, value in data.get("repos", {}).items()}
    if name in repos:
        return repos[name]
    owner, separator, _ = name.partition("/")
    if separator and "." not in owner and name.count("/") == 1:
        return {key.lower(): value for key, value in data.get("owners", {}).items()}.get(owner)
    return None


def local_ci(data, repo):
    """True when the map lists this GitHub OWNER/NAME, or its owner, under local_ci."""
    name = (repo or "").lower()
    owner = name.partition("/")[0]
    return any(entry.lower() in (name, owner) for entry in data.get("local_ci", []))


def local_tier(data, top):
    """The tier of a project with no remotes, by its path below the home directory."""
    try:
        relative = top.relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return None
    return data.get("local", {}).get(relative)


def classify(data, top, remotes):
    """(tier, project, source). `top` is None when discovery failed; `remotes` is the reason."""
    if top is None:
        return UNCLASSIFIED, "unknown project", remotes
    if not remotes:
        tier = local_tier(data, top)
        return (tier, top.name, "local") if tier else (UNCLASSIFIED, top.name, "no remotes, not in the map")
    found = [identity(url) for urls in remotes.values() for url in urls]
    known = [identity(url) for url in remotes.get("origin", [])] + sorted(filter(None, found))
    project = next(filter(None, known), top.name)
    tiers = [(remote_tier(data, name) if name else None) or UNCLASSIFIED for name in found]
    source = "strictest of every remote address" if tiers else "git reported no address"
    return max(tiers, key=STRICTNESS.get, default=UNCLASSIFIED), project, source


def main(argv=None):
    parser = argparse.ArgumentParser(description="Report a project's Patstack tier.")
    parser.add_argument("--path", default=".", help="project directory (default: current)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # a path must not stop the tier from printing
            stream.reconfigure(errors="backslashreplace")

    try:
        data, warning = load_tiers()
        top, remotes = discover(args.path)
        tier, project, source = classify(data, top, remotes)
    except Exception as error:  # intake needs an answer, and the safe answer is always available
        tier, project, source, warning = UNCLASSIFIED, "unknown project", "unexpected error", repr(error)
    mode = ("Full Send always" if tier in ALWAYS_FULL_SEND
            else "evaluate Full Send or Full Stop at intake")
    if args.json:
        print(json.dumps({"tier": tier, "mode": mode, "project": project, "source": source,
                          "warning": warning}))
    else:
        print(f"Tier: {tier} ({project}; {source})")
        print(f"Mode: {mode}")
        if tier == UNCLASSIFIED:
            print("Treated as CRITICAL. Report the project so the owner can classify it.")
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
