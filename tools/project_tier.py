#!/usr/bin/env python3
"""Report a project's tier, which decides how the DevStack mode is chosen.

  python3 tools/project_tier.py [--path DIR] [--json]

The tier says who a failure reaches:

  CRITICAL      customer-facing products for consulting work or other customers
  FRIENDS       real people, but internal use for the owner and friends
  INTERNAL      only the owner
  UNCLASSIFIED  anything not positively classified; treated exactly as CRITICAL

CRITICAL and UNCLASSIFIED projects evaluate Full Send or Full Stop at intake. FRIENDS and
INTERNAL projects are always Full Send. The map is the owner's private file, by default
~/.config/devstack/project-tiers.json, overridden by DEVSTACK_PROJECT_TIERS
(examples/project-tiers.example.json shows the shape):

  owners  GitHub owner -> CRITICAL. Only CRITICAL: an owner default never lowers a tier.
  repos   OWNER/NAME for GitHub, or HOST[:PORT]/PATH for another forge -> any tier.
  local   path relative to the home directory, for a project with no remotes -> any tier.

The tier comes from the checkout, never from a name passed in. A project is FRIENDS or
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

TIERS = ("CRITICAL", "FRIENDS", "INTERNAL")
UNCLASSIFIED = "UNCLASSIFIED"
ALWAYS_FULL_SEND = ("FRIENDS", "INTERNAL")
STRICTNESS = {"INTERNAL": 0, "FRIENDS": 1, UNCLASSIFIED: 2, "CRITICAL": 3}
GITHUB_HOSTS = ("github.com", "www.github.com", "ssh.github.com")
SCP_LIKE = re.compile(r"^(?:[^@/:\s]+@)?([\w-]+(?:\.[\w-]+)+):(?!/)(.+)$")


def map_path():
    override = os.environ.get("DEVSTACK_PROJECT_TIERS")
    return Path(override) if override else Path.home() / ".config/devstack/project-tiers.json"


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
    unknown = set(data) - {"owners", "repos", "local"}
    if unknown:
        return f"unknown sections {sorted(unknown)}"
    allowed = {"owners": ("CRITICAL",), "repos": TIERS, "local": TIERS}
    for name, values in allowed.items():
        problem = section_problem(name, data.get(name, {}), values)
        if problem:
            return problem
    return None


def load_map(path):
    """The map, or an empty one with a warning: a bad file must not lower a tier."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
    parser = argparse.ArgumentParser(description="Report a project's DevStack tier.")
    parser.add_argument("--path", default=".", help="project directory (default: current)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # a path must not stop the tier from printing
            stream.reconfigure(errors="backslashreplace")

    try:
        data, warning = load_map(map_path())
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
