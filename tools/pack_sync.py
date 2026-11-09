#!/usr/bin/env python3
"""Keep the project pack's copies of shared skills in step with their upstream skill repository.

  python3 tools/pack_sync.py status [--fetch] [--json]
  python3 tools/pack_sync.py diff SKILL [--files F ...] [--json]
  python3 tools/pack_sync.py pull SKILL [--files F ...] [--json]
  python3 tools/pack_sync.py resolve SKILL [--files F ...] [--json]
  python3 tools/pack_sync.py adopt SKILL [--as NAME] [--keep-pack] [--json]

Global options (--upstream, --config, --json, --fetch) go before or after the command. The
mapping and sync state live in the selected pack's pack-sync.json. The upstream checkout
comes from `--upstream PATH`, else $PACK_SYNC_UPSTREAM, else the config's `checkout_hint`.
Upstream bytes and modes are read from its fetched ref (default `origin/main`) with git, never
from its working tree, and nothing is ever written there; `--fetch` runs only `git fetch origin`.

Every file is compared three ways by content and git mode: the recorded base (upstream at the
last sync), the upstream ref and the pack. `pull` fast-forwards only files the pack has not
changed since the base. Any conflict or privacy finding in the selection writes nothing. Writes
are one transaction: every target and the state file are snapshotted, written through fresh
temporary files, checked again by the package privacy guard (`scripts/check.py`) and restored
together on any failure. Destinations must stay inside the pack's skills folder, outside the
upstream checkout, with no symlink anywhere in their path.

Exit codes: 0 in sync, 1 drift, conflicts or refused files, 2 usage or errors.
Python 3.9+, standard library only.
"""
import argparse
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG = "project-packs/*/pack-sync.json"
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
MODES = {"100644": 0o644, "100755": 0o755}
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
NEUTRALIZE = ("Neutralize the reported lines in the pack copy (placeholders such as <workspace> for home "
              "or private paths; no owner names, emails, hosts, tokens or registry IDs), never in upstream.")
DRIFT_ACTIONS = ("pull", "record", "conflict", "restructure", "unsupported")
BLOCKING = ("conflict", "restructure", "unsupported")
LOOKUP = "lookup order: --upstream PATH, then $PACK_SYNC_UPSTREAM, then checkout_hint in pack-sync.json"


class PackSyncError(RuntimeError):
    pass


class Refused(PackSyncError):
    """A published file failed the privacy guard after it was written; everything was restored."""

    def __init__(self, refused):
        super().__init__("privacy guard failed after writing; all changes were restored")
        self.refused = refused


def sha(data):
    """SHA-256 of DATA, or None for an absent file."""
    return None if data is None else hashlib.sha256(data).hexdigest()


def guard_issues(relative, data, root=None):
    """Privacy findings (redacted) for DATA published at RELATIVE in this package."""
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from check import pack_policies, privacy_issues
    return privacy_issues(relative, data, policies=pack_policies(ROOT if root is None else root))


def check_name(value, what):
    """VALUE as a single safe folder name."""
    if not isinstance(value, str) or not NAME.fullmatch(value) or value in (".", ".."):
        raise PackSyncError(f"invalid {what} {value!r}: use one folder name of letters, digits, '.', '_' or '-'")
    return value


def check_relative(value, what, single=False):
    """VALUE as a relative POSIX path without empty, '.', '..' or control-character segments."""
    if (not isinstance(value, str) or not value or value.startswith("/") or "\\" in value
            or re.search(r"[\x00-\x1f\x7f]", value) or re.match(r"[A-Za-z]:", value)):
        raise PackSyncError(f"invalid {what} {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") or part != part.strip() for part in parts) or (single and len(parts) > 1):
        raise PackSyncError(f"invalid {what} {value!r}")
    return value


def mode_of(st):
    return "100755" if st.st_mode & stat.S_IXUSR else "100644"


def ident(data, mode):
    return None if data is None else (mode, sha(data))


def file_mode(git_mode):
    umask = os.umask(0)
    os.umask(umask)
    return MODES[git_mode] & ~umask


class Upstream:
    """Read-only view of one ref in the upstream checkout."""

    def __init__(self, path, ref, fetch=False, source="--upstream"):
        self.path = Path(path).expanduser()
        if not (self.path / ".git").exists():
            # The path itself is not printed: it can be a private home path.
            raise PackSyncError(f"upstream checkout from {source} not found; {LOOKUP}")
        self.real = Path(os.path.realpath(self.path))
        if fetch:
            self.git("fetch", "--quiet", "origin")
        self.ref = ref
        self.rev = self.git("rev-parse", "--verify", "--quiet", ref + "^{commit}").decode().strip()

    def git(self, *args):
        try:
            out = subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise PackSyncError(f"git {args[0]} timed out in the upstream checkout") from None
        if out.returncode:
            # stderr can carry authenticated remote URLs; report only the command and exit code.
            raise PackSyncError(f"git {args[0]} failed in the upstream checkout (exit {out.returncode})")
        return out.stdout

    def skills(self, root):
        out = self.git("ls-tree", "-z", self.rev, root.rstrip("/") + "/")
        names = []
        for item in out.decode("utf-8", "surrogateescape").split("\0"):
            if item:
                meta, name = item.split("\t", 1)
                if meta.split()[1] == "tree":
                    names.append(name.rsplit("/", 1)[-1])
        return sorted(names)

    def files(self, directory):
        """{relative path: (blob id, git mode) or None for an unsupported entry} below DIRECTORY."""
        out = self.git("ls-tree", "-r", "-z", self.rev, directory.rstrip("/") + "/")
        result = {}
        for item in out.decode("utf-8", "surrogateescape").split("\0"):
            if not item:
                continue
            meta, name = item.split("\t", 1)
            mode, kind, blob = meta.split()
            relative = name[len(directory.rstrip("/")) + 1:]
            if SKIP_PARTS & set(relative.split("/")):
                continue
            check_relative(relative, "upstream file name")
            result[relative] = (blob, mode) if kind == "blob" and mode in MODES else None
        return result

    def read(self, blob):
        return self.git("cat-file", "blob", blob)


class Pack:
    def __init__(self, root, config_path=None):
        self.root = Path(os.path.realpath(root))
        self.forbidden = []
        if config_path is None:
            configs = sorted(self.root.glob(CONFIG))
            if len(configs) != 1:
                raise PackSyncError("select exactly one pack with --config; no unique pack-sync.json")
            config_path = configs[0]
        config_path = Path(config_path)
        config_path = Path(os.path.abspath(config_path))
        supplied_root = Path(os.path.abspath(root))
        try:
            config_path = self.root / config_path.relative_to(supplied_root)
        except ValueError:
            pass
        try:
            self.config_name = config_path.relative_to(self.root).as_posix()
        except ValueError:
            raise PackSyncError("the config file must be inside the package") from None
        check_relative(self.config_name, "config path")
        self.config_path = self.root / self.config_name
        self.chain(self.config_path)
        try:
            self.config = json.loads(read_file(self.config_path)[0])
        except (OSError, ValueError) as error:
            raise PackSyncError(f"cannot read {self.config_path.name}: {error}") from None
        try:
            self.pack_root = check_relative(self.config["pack_root"], "pack_root")
            self.upstream_root = check_relative(self.config["upstream"]["skills_root"], "skills_root")
            for name, entry in self.config["skills"].items():
                check_name(name, "pack skill name")
                if not isinstance(entry, dict):
                    raise KeyError(f"skills.{name}")
                check_name(entry.get("upstream"), "upstream skill name")
                for relative in entry.get("files", {}):
                    check_relative(relative, f"file name in {name}")
        except (KeyError, AttributeError, TypeError) as error:
            raise PackSyncError(f"{self.config_path.name}: missing or invalid {error}") from None
        self.skills_dir = self.root / self.pack_root
        self.chain(self.skills_dir)

    def forbid(self, path):
        """Refuse any destination at or below PATH (the upstream checkout)."""
        self.forbidden.append(Path(os.path.realpath(path)))
        for target in (self.skills_dir, self.config_path):
            self.outside_forbidden(target)

    def outside_forbidden(self, target):
        real = Path(os.path.realpath(target))
        for path in self.forbidden:
            if real == path or path in real.parents:
                raise PackSyncError("refusing a destination inside the upstream checkout")

    def chain(self, target):
        """Refuse TARGET when it leaves the package or any existing part of its path is a symlink."""
        target = Path(target)
        try:
            parts = target.relative_to(self.root).parts
        except ValueError:
            raise PackSyncError(f"refusing a destination outside the package: {target}") from None
        current = self.root
        for index, part in enumerate(parts):
            current = current / part
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                break
            if stat.S_ISLNK(st.st_mode):
                raise PackSyncError(f"refusing a symlink in the destination path: {current.relative_to(self.root)}")
            if index < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
                raise PackSyncError(f"not a folder in the destination path: {current.relative_to(self.root)}")
        self.outside_forbidden(target)
        return target

    def skill(self, name):
        try:
            return self.config["skills"][name]
        except KeyError:
            raise PackSyncError(f"unknown skill {name!r}; see `status` for mapped skills") from None

    def skill_dir(self, name):
        return self.chain(self.skills_dir / check_name(name, "pack skill name"))

    def target(self, name, relative):
        """Validated destination of RELATIVE in pack skill NAME."""
        path = self.skill_dir(name) / check_relative(relative, "file name")
        if self.skills_dir / name not in path.parents:
            raise PackSyncError(f"refusing a destination outside the skill folder: {relative}")
        return self.chain(path)

    def published(self, name, relative):
        return f"{self.pack_root}/{name}/{relative}"

    def files(self, name):
        """{relative: (bytes, git mode) or None for an unsupported entry} of pack skill NAME."""
        base = self.skill_dir(name)
        if not os.path.lexists(base):
            return {}
        if not base.is_dir():
            raise PackSyncError(f"{self.pack_root}/{name} is not a folder")
        result = {}
        for directory, dirs, names in os.walk(base, followlinks=False):
            here = Path(directory)
            for entry in list(dirs):
                if entry in SKIP_PARTS:
                    dirs.remove(entry)
                elif os.path.islink(here / entry):
                    result[(here / entry).relative_to(base).as_posix()] = None
                    dirs.remove(entry)
            for entry in names:
                path = here / entry
                if path.suffix in (".pyc", ".pyo"):
                    continue
                relative = path.relative_to(base).as_posix()
                st = os.lstat(path)
                result[relative] = (read_file(path)[0], mode_of(st)) if stat.S_ISREG(st.st_mode) else None
        return dict(sorted(result.items()))

    def state_bytes(self, config):
        return (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_file(path):
    """(bytes, st) of the regular file PATH, never following a final symlink."""
    fd = os.open(str(path), os.O_RDONLY | NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PackSyncError(f"not a regular file: {path.name}")
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                return b"".join(chunks), st
            chunks.append(chunk)
    finally:
        os.close(fd)


def atomic_write(target, data, mode):
    """Replace TARGET with DATA (permission bits MODE) through a fresh, exclusive temporary file."""
    fd, temp = tempfile.mkstemp(dir=str(target.parent), prefix=".pack-sync-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
        os.replace(temp, target)
    except BaseException:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise


class Transaction:
    """Write files and the state file together; restore every one of them on any failure."""

    def __init__(self, pack):
        self.pack = pack
        self.ops = []  # (target, published name, reported name, bytes or None to delete, git mode)

    def add(self, name, relative, data, mode):
        self.ops.append((self.pack.target(name, relative), self.pack.published(name, relative), relative, data, mode))

    def preflight(self, state):
        refused = [{"file": label, "findings": issues} for _, published, label, data, _ in self.ops
                   if data is not None for issues in [guard_issues(published, data, self.pack.root)] if issues]
        issues = guard_issues(self.pack.config_name, state, self.pack.root)
        if issues:
            refused.append({"file": self.pack.config_name, "findings": issues})
        return refused

    def commit(self, state):
        targets = [(target, published, label, data, file_mode(mode) if data is not None else None)
                   for target, published, label, data, mode in self.ops]
        snapshot, created = [], []
        for target, *_ in targets + [(self.pack.config_path,)]:
            self.pack.chain(target)
            if os.path.lexists(target):
                data, st = read_file(target)
                snapshot.append((target, data, stat.S_IMODE(st.st_mode)))
            else:
                snapshot.append((target, None, None))
        try:
            for target, _, _, data, mode in targets:
                if data is None:
                    if os.path.lexists(target):
                        os.unlink(target)
                    continue
                self.mkdirs(target.parent, created)
                atomic_write(self.pack.chain(target), data, mode)
            refused = [{"file": label, "findings": issues} for target, published, label, data, _ in targets
                       if data is not None for issues in [guard_issues(published, read_file(target)[0], self.pack.root)] if issues]
            if refused:
                raise Refused(refused)
            atomic_write(self.pack.chain(self.pack.config_path), state,
                         snapshot[-1][2] if snapshot[-1][2] is not None else file_mode("100644"))
            issues = guard_issues(self.pack.config_name, read_file(self.pack.config_path)[0], self.pack.root)
            if issues:
                raise Refused([{"file": self.pack.config_name, "findings": issues}])
        except BaseException as error:
            problems = self.restore(snapshot, created)
            if problems:
                raise PackSyncError(f"{error}; restore incomplete: {'; '.join(problems)}") from None
            if isinstance(error, (Refused, PackSyncError)):
                raise
            if isinstance(error, OSError):
                raise PackSyncError(f"write failed ({error.strerror or error}); all changes were restored") from None
            raise
        return self.prune([target for target, _, _, data, _ in targets if data is None])

    def mkdirs(self, directory, created):
        missing = []
        while not os.path.lexists(directory):
            missing.append(directory)
            directory = directory.parent
        for path in reversed(missing):
            self.pack.chain(path)
            os.mkdir(path)
            created.append(path)

    def restore(self, snapshot, created):
        problems = []
        for target, data, mode in reversed(snapshot):
            try:
                if data is None:
                    if os.path.lexists(target):
                        os.unlink(target)
                else:
                    self.mkdirs(target.parent, [])
                    atomic_write(self.pack.chain(target), data, mode)
            except (OSError, PackSyncError) as error:
                problems.append(f"{target.name}: {error}")
        for path in reversed(created):
            try:
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            except OSError:
                pass
        return problems

    def prune(self, deleted):
        """Best-effort removal of folders emptied by deletions; returns the folders left in place."""
        left = []
        for target in deleted:
            parent = target.parent
            while parent != self.pack.skills_dir and self.pack.skills_dir in parent.parents:
                try:
                    if not parent.is_dir() or any(parent.iterdir()):
                        break
                    parent.rmdir()
                except OSError:
                    left.append(parent.relative_to(self.pack.root).as_posix())
                    break
                parent = parent.parent
        return left


def classify(base, upstream, pack):
    """State, change and action for one file from three identities (None = absent)."""
    if upstream == pack:
        if base == upstream:
            return ("identical" if pack else "deleted"), "none", "in-sync"
        # Converged on both sides: the base must advance, or a later upstream revert is misread.
        return ("identical" if pack else "deleted"), "converged", "record"
    state = "pack-only" if upstream is None else "upstream-only" if pack is None else "differs"
    up_changed, pack_changed = upstream != base, pack != base
    if up_changed and pack_changed:
        return state, "both", "conflict"
    if up_changed:
        return state, "upstream", "pull"
    return state, "local", "keep"


def base_of(record):
    if not record.get("base_sha256"):
        return None
    return record.get("base_mode") or "100644", record["base_sha256"]


def skill_report(pack, upstream, name, upstream_skills):
    entry = pack.skill(name)
    present = entry["upstream"] in upstream_skills
    up_files = upstream.files(f"{pack.upstream_root}/{entry['upstream']}") if present else {}
    pack_files = pack.files(name)
    records = entry.get("files", {})
    files = []
    for relative in sorted(set(up_files) | set(pack_files) | set(records)):
        record = records.get(relative, {})
        item = {"file": relative, "policy": record.get("policy", "track")}
        if record.get("note"):
            item["note"] = record["note"]
        if (relative in up_files and up_files[relative] is None) or (relative in pack_files and pack_files[relative] is None):
            item.update(state="unsupported", change="unknown", action="unsupported")
            files.append(item)
            continue
        up_blob, up_mode = up_files.get(relative) or (None, None)
        up_data = upstream.read(up_blob) if up_blob else None
        pack_data, pack_mode = pack_files.get(relative) or (None, None)
        base, up_id, pack_id = base_of(record), ident(up_data, up_mode), ident(pack_data, pack_mode)
        if base is None and up_id is None and pack_id is None:
            continue  # recorded deletion on every side
        item["state"], item["change"], item["action"] = classify(base, up_id, pack_id)
        if item["policy"] == "ignore" and item["action"] != "in-sync":
            item["action"] = "ignored"
        if up_id and pack_id and up_id[1] == pack_id[1] and up_id[0] != pack_id[0]:
            item["modes"] = {"upstream": up_mode, "pack": pack_mode}
        item["_data"] = {"upstream": (up_data, up_mode), "pack": (pack_data, pack_mode)}
        files.append(item)
    mark_restructure(files, up_files, pack_files)
    counts = {}
    for item in files:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    return {"name": name, "upstream": entry["upstream"], "pack": name,
            "upstream_present": present, "pack_present": bool(pack_files), "counts": counts, "files": files}


def mark_restructure(files, up_files, pack_files):
    """Mark paths that are a file on one side and a folder on the other, when upstream changed them."""
    def folders(paths):
        return {"/".join(p.split("/")[:i]) for p in paths for i in range(1, p.count("/") + 1)}
    up = {p for p, entry in up_files.items() if entry is not None}  # symlinks stay "unsupported"
    pack = {p for p, entry in pack_files.items() if entry is not None}
    clashes = (up & folders(pack)) | (pack & folders(up))
    for clash in clashes:
        group = [i for i in files if i["file"] == clash or i["file"].startswith(clash + "/")]
        if any(i["action"] in ("pull", "conflict") for i in group):
            for item in group:
                if item["action"] != "unsupported":
                    item.update(state="restructure", change="type", action="restructure")


def public(report):
    """REPORT without the internal byte and bookkeeping fields."""
    if isinstance(report, dict):
        return {k: public(v) for k, v in report.items() if not k.startswith("_")}
    if isinstance(report, list):
        return [public(v) for v in report]
    return report


def skill_drift(skill):
    drift = []
    if not skill["upstream_present"]:
        drift.append(f"{skill['name']}: upstream skill {skill['upstream']} no longer exists; decide by hand")
    for item in skill["files"]:
        if item["action"] in DRIFT_ACTIONS:
            drift.append(f"{skill['name']}/{item['file']}: {item['action']} ({item['state']}, {item['change']} change)")
    return drift


def status(pack, upstream):
    upstream_skills = upstream.skills(pack.upstream_root)
    skills = [skill_report(pack, upstream, name, upstream_skills) for name in pack.config["skills"]]
    mapped_up = {entry["upstream"] for entry in pack.config["skills"].values()}
    mapped_pack = set(pack.config["skills"])
    known = pack.config.get("known_candidates", {})
    candidates = [{"name": name, "known": name in known, "note": known.get(name, "")}
                  for name in upstream_skills if name not in mapped_up]
    pack_only = sorted(p.name for p in pack.skills_dir.iterdir() if p.is_dir() and not p.is_symlink()
                       and p.name not in mapped_pack and p.name not in upstream_skills) \
        if pack.skills_dir.is_dir() else []
    drift = [line for skill in skills for line in skill_drift(skill)]
    drift += [f"new upstream skill {c['name']}: adopt it or list it under known_candidates"
              for c in candidates if not c["known"]]
    return {"upstream": {"ref": upstream.ref, "rev": upstream.rev}, "in_sync": not drift, "drift": drift,
            "skills": skills, "candidates": candidates, "pack_only_skills": pack_only}


def select(skill, files):
    if not files:
        return skill["files"]
    known = {item["file"]: item for item in skill["files"]}
    missing = [name for name in files if name not in known]
    if missing:
        raise PackSyncError(f"{skill['name']}: no such file(s): {', '.join(missing)}")
    return [known[name] for name in files]


def record(config, name, relative, rev, data, mode):
    files = config["skills"][name].setdefault("files", {})
    entry = files.setdefault(relative, {})
    entry["base_rev"], entry["base_sha256"] = rev, sha(data)
    entry["base_mode"] = mode if data is not None else None
    config["skills"][name]["files"] = dict(sorted(files.items()))


def pull(pack, upstream, name, files):
    skill = skill_report(pack, upstream, name, upstream.skills(pack.upstream_root))
    if not skill["upstream_present"]:
        raise PackSyncError(f"{name}: upstream skill {skill['upstream']} no longer exists; nothing pulled")
    result = {"skill": name, "upstream": {"ref": upstream.ref, "rev": upstream.rev},
              "pulled": [], "recorded": [], "conflicts": [], "refused": [], "kept": [], "unchanged": []}
    chosen = select(skill, files)
    result["conflicts"] = [{"file": i["file"], "state": i["state"], "change": i["change"]}
                           for i in chosen if i["action"] in BLOCKING]
    if result["conflicts"]:
        result["blocked"] = [i["file"] for i in chosen if i["action"] in ("pull", "record")]
        result["next"] = ("Nothing was written. Merge each conflict by hand (see `diff`) and run `resolve`, "
                          "or pull only the clean files with --files.")
        if any(i["action"] == "restructure" for i in chosen):
            result["next"] += (" A file and a folder of the same name swap places (restructure): move or delete "
                               "the pack copy by hand, then `pull`, then `resolve` (docs/pack-sync.md).")
        return result
    config = copy.deepcopy(pack.config)
    tx = Transaction(pack)
    for item in chosen:
        (up_data, up_mode), (pack_data, _) = item["_data"]["upstream"], item["_data"]["pack"]
        if item["action"] == "pull":
            tx.add(name, item["file"], up_data, up_mode)
            record(config, name, item["file"], upstream.rev, up_data, up_mode)
            result["pulled"].append({"file": item["file"], "operation": "deleted" if up_data is None else
                                     "created" if pack_data is None else "updated"})
        elif item["action"] == "record":
            record(config, name, item["file"], upstream.rev, up_data, up_mode)
            result["recorded"].append(item["file"])
        elif item["action"] in ("keep", "ignored"):
            result["kept"].append(item["file"])
        else:
            result["unchanged"].append(item["file"])
    return commit(pack, tx, config, result, NEUTRALIZE + " Then run `resolve` for those files.")


def commit(pack, tx, config, result, advice, done=("pulled", "recorded")):
    """Run TX with the new CONFIG; on refusal report it and clear the DONE lists."""
    if config == pack.config and not tx.ops:
        return result
    state = pack.state_bytes(config)
    refused = tx.preflight(state)
    if not refused:
        try:
            left = tx.commit(state)
            pack.config = config
            if left:
                result["warnings"] = [f"committed; empty folder not removed: {path}" for path in left]
            return result
        except Refused as error:
            refused = [dict(item, reverted=True) for item in error.refused]
    for key in done:
        if key in result:
            result[key] = []
    result["refused"] = refused
    result["next"] = "Nothing was written. " + advice
    return result


def resolve(pack, upstream, name, files):
    skill = skill_report(pack, upstream, name, upstream.skills(pack.upstream_root))
    chosen = select(skill, files) if files else [i for i in skill["files"] if i["action"] in ("conflict", "pull", "record")]
    result = {"skill": name, "upstream": {"ref": upstream.ref, "rev": upstream.rev}, "resolved": [], "refused": []}
    unsupported = [i["file"] for i in chosen if i["action"] == "unsupported"]
    if unsupported:
        result["refused"] = [{"file": f, "findings": ["unsupported entry (symlink or submodule)"]} for f in unsupported]
        return result
    config = copy.deepcopy(pack.config)
    for item in chosen:
        (up_data, up_mode), (pack_data, _) = item["_data"]["upstream"], item["_data"]["pack"]
        if pack_data is not None:
            issues = guard_issues(pack.published(name, item["file"]), pack_data, pack.root)
            if issues:
                result["refused"].append({"file": item["file"], "findings": issues})
        record(config, name, item["file"], upstream.rev, up_data, up_mode)
        result["resolved"].append(item["file"])
    if result["refused"]:
        result["resolved"] = []
        result["next"] = "Nothing was recorded. " + NEUTRALIZE
        return result
    return commit(pack, Transaction(pack), config, result, NEUTRALIZE, done=("resolved",))


def adopt(pack, upstream, name, pack_name, keep):
    check_name(name, "upstream skill name")
    pack_name = check_name(name if pack_name is None else pack_name, "pack skill name")
    if name not in upstream.skills(pack.upstream_root):
        raise PackSyncError(f"no upstream skill {name!r} at {upstream.ref}")
    if any(entry["upstream"] == name for entry in pack.config["skills"].values()):
        raise PackSyncError(f"{name} is already tracked; use pull")
    if pack_name in pack.config["skills"]:
        raise PackSyncError(f"pack name {pack_name!r} is already mapped")
    target = pack.skill_dir(pack_name)
    if os.path.lexists(target) and not keep:
        raise PackSyncError(f"{pack.pack_root}/{pack_name} already exists; use --keep-pack to track it as is")
    if keep and not target.is_dir():
        raise PackSyncError(f"--keep-pack needs an existing {pack.pack_root}/{pack_name}")
    up_files = upstream.files(f"{pack.upstream_root}/{name}")
    if any(entry is None for entry in up_files.values()):
        raise PackSyncError(f"{name}: upstream contains a symlink or submodule; adopt it by hand")
    up_data = {relative: (upstream.read(blob), mode) for relative, (blob, mode) in up_files.items()}
    result = {"skill": name, "pack": pack_name, "upstream": {"ref": upstream.ref, "rev": upstream.rev},
              "adopted": False, "copied": [], "refused": []}
    advice = (NEUTRALIZE + f" To adopt, copy the skill into {pack.pack_root}/{pack_name}/ by hand, "
              "neutralize it, then run `adopt` again with --keep-pack.")
    config = copy.deepcopy(pack.config)
    config["skills"][pack_name] = {"upstream": name, "files": {}}
    for relative, (data, mode) in sorted(up_data.items()):
        record(config, pack_name, relative, upstream.rev, data, mode)
    config.get("known_candidates", {}).pop(name, None)
    tx = Transaction(pack)
    if keep:
        local = pack.files(pack_name)
        if any(entry is None for entry in local.values()):
            raise PackSyncError(f"{pack_name}: the pack copy contains a symlink or special file")
        result["refused"] = [{"file": f, "findings": issues} for f, (data, _) in local.items()
                             for issues in [guard_issues(pack.published(pack_name, f), data, pack.root)] if issues]
        if result["refused"]:
            result["next"] = "Nothing was written. " + NEUTRALIZE
            return result
    else:
        for relative, (data, mode) in sorted(up_data.items()):
            tx.add(pack_name, relative, data, mode)
        result["copied"] = sorted(up_data)
    result["adopted"] = True
    result = commit(pack, tx, config, result, advice, done=("copied",))
    if result["refused"]:
        result["adopted"] = False
    else:
        result["next"] = "Route to the adopted skill from the pack INDEX.md, then run python3 scripts/check.py."
    return result


def diff(pack, upstream, name, files):
    skill = skill_report(pack, upstream, name, upstream.skills(pack.upstream_root))
    out = []
    for item in select(skill, files):
        if item["action"] in ("in-sync", "unsupported") or item["state"] == "deleted":
            continue
        (up_data, up_mode), (pack_data, pack_mode) = item["_data"]["upstream"], item["_data"]["pack"]
        text = "".join(difflib.unified_diff(
            [] if up_data is None else up_data.decode("utf-8", "replace").splitlines(True),
            [] if pack_data is None else pack_data.decode("utf-8", "replace").splitlines(True),
            f"upstream/{skill['upstream']}/{item['file']}@{upstream.rev[:12]}",
            f"pack/{skill['pack']}/{item['file']}"))
        if up_mode and pack_mode and up_mode != pack_mode:
            text = f"old mode {up_mode}\nnew mode {pack_mode}\n" + text
        out.append({"file": item["file"], "state": item["state"], "change": item["change"],
                    "action": item["action"], "diff": text})
    return {"skill": name, "upstream": {"ref": upstream.ref, "rev": upstream.rev}, "files": out}


def render_status(report):
    lines = [f"upstream {report['upstream']['ref']} @ {report['upstream']['rev'][:12]}: "
             f"{'in sync' if report['in_sync'] else 'DRIFT'}"]
    for skill in report["skills"]:
        counts = ", ".join(f"{n} {a}" for a, n in sorted(skill["counts"].items()))
        lines.append(f"  {skill['name']}: {counts or 'no files'}"
                     + ("" if skill["upstream_present"] else " [upstream skill missing]"))
        for item in skill["files"]:
            if item["action"] != "in-sync":
                lines.append(f"    {item['action']:<11} {item['file']} ({item['state']}, {item['change']})")
    known = [c["name"] for c in report["candidates"] if c["known"]]
    new = [c["name"] for c in report["candidates"] if not c["known"]]
    if new:
        lines.append("  new upstream candidates: " + ", ".join(new))
    if known:
        lines.append("  known upstream candidates (not adopted): " + ", ".join(known))
    if report["pack_only_skills"]:
        lines.append("  pack-only skills: " + ", ".join(report["pack_only_skills"]))
    lines += [f"  DRIFT: {line}" for line in report["drift"]]
    return "\n".join(lines)


def render_result(result):
    lines = [f"{result['skill']} @ {result['upstream']['rev'][:12]}"]
    for key in ("pulled", "recorded", "copied", "resolved", "kept", "conflicts", "blocked", "refused"):
        for item in result.get(key, []):
            if isinstance(item, str):
                lines.append(f"  {key}: {item}")
            elif "findings" in item:
                lines.append(f"  REFUSED {item['file']}{' (written, then restored)' if item.get('reverted') else ''}:")
                lines += [f"    {finding}" for finding in item["findings"]]
            else:
                detail = item.get("operation") or f"{item.get('state')}, {item.get('change')} change"
                lines.append(f"  {key}: {item['file']} ({detail})")
    if "adopted" in result:
        lines.append(f"  adopted: {'yes' if result['adopted'] else 'no'}")
    lines += [f"  warning: {warning}" for warning in result.get("warnings", [])]
    if result.get("next"):
        lines.append(f"  next: {result['next']}")
    return "\n".join(lines)


def global_options(suppress):
    """The options every command accepts, before or after the command name."""
    common = argparse.ArgumentParser(add_help=False)
    default = {"default": argparse.SUPPRESS} if suppress else {}
    common.add_argument("--upstream", help="Upstream checkout (default: $PACK_SYNC_UPSTREAM, else the config hint)",
                        **default)
    common.add_argument("--config", help=f"Mapping and state file inside the package (default: {CONFIG})", **default)
    common.add_argument("--root", help=argparse.SUPPRESS, **default)  # package root, for tests
    common.add_argument("--json", action="store_true", help="Print JSON for agents", **default)
    common.add_argument("--fetch", action="store_true", help="Run `git fetch origin` in the upstream checkout first",
                        **default)
    return common


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[global_options(False)])
    sub = parser.add_subparsers(dest="command", required=True)
    late = [global_options(True)]
    sub.add_parser("status", parents=late, help="Compare every mapped skill and list candidates")
    for command in ("diff", "pull", "resolve"):
        each = sub.add_parser(command, parents=late)
        each.add_argument("skill")
        each.add_argument("--files", nargs="+", help="Skill-relative files (default: all)")
    each = sub.add_parser("adopt", parents=late, help="Start tracking an upstream skill")
    each.add_argument("skill")
    each.add_argument("--as", dest="pack_name", help="Pack folder name (default: the upstream name)")
    each.add_argument("--keep-pack", action="store_true", help="Track an existing, neutralized pack copy as is")
    args = parser.parse_args(argv)
    try:
        pack = Pack(Path(args.root) if args.root else ROOT, args.config)
        sources = (("--upstream", args.upstream), ("$PACK_SYNC_UPSTREAM", os.environ.get("PACK_SYNC_UPSTREAM")),
                   ("checkout_hint", pack.config["upstream"].get("checkout_hint")))
        source, location = next(((label, value) for label, value in sources if value), (None, None))
        if not location:
            raise PackSyncError(f"no upstream checkout configured; {LOOKUP}")
        upstream = Upstream(location, pack.config["upstream"].get("ref", "origin/main"), fetch=args.fetch,
                            source=source)
        pack.forbid(upstream.real)
        if args.command == "status":
            report = status(pack, upstream)
            code = 0 if report["in_sync"] else 1
            text = render_status(report)
        elif args.command == "diff":
            report = diff(pack, upstream, args.skill, args.files)
            code = 1 if report["files"] else 0
            text = "\n".join(item["diff"] or f"{item['file']}: {item['state']}\n" for item in report["files"]) \
                or f"{args.skill}: no differences"
        elif args.command == "pull":
            report = pull(pack, upstream, args.skill, args.files)
            code = 1 if report["conflicts"] or report["refused"] else 0
            text = render_result(report)
        elif args.command == "resolve":
            report = resolve(pack, upstream, args.skill, args.files)
            code = 1 if report["refused"] else 0
            text = render_result(report)
        else:
            report = adopt(pack, upstream, args.skill, args.pack_name, args.keep_pack)
            code = 0 if report["adopted"] else 1
            text = render_result(report)
    except PackSyncError as error:
        print(f"pack_sync: {error}", file=sys.stderr)
        return 2
    print(json.dumps(public(report), indent=2) if args.json else text)
    return code


if __name__ == "__main__":
    sys.exit(main())
