#!/usr/bin/env python3
"""Validate this package before commit or publication.

  python3 scripts/check.py                       # exit 0 OK, 1 failed
  python3 scripts/check.py --allow-missing-node  # without node: exit 3 INCOMPLETE, never OK

Checks: local resources still match SOURCE-MANIFEST.json, relative Markdown
links and anchors resolve, the privacy scan is clean (including the published
project pack and the benchmark), JSON/SVG/YAML parse (CI templates stay least-privilege and pinned), the animated HTML is
self-contained with reduced-motion and pause support, skill frontmatter is
valid, the global-instructions template and project pack are present, the
example KPI snapshot round-trips through the real recorder, and the KPI,
numbering, tool, package and benchmark unit tests pass. Standard library only; exits 1 on any
failure. Network access is never used.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import xml.etree.ElementTree as ET

from refresh_from_source import FILES, SKILLS, PACKAGE_RESOURCE_ROOTS, PACKAGE_RESOURCE_FILES, WORKFLOW_VERSION

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".md", ".py", ".json", ".svg", ".html", ".txt", ".yml", ".yaml", ""}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = re.compile(r"(\.sqlite3?|\.db|\.jsonl|\.env|devices\.local\.json|\.pem|\.key)$", re.I)
FORBIDDEN_PARTS = {"backups", "archives", "transcripts", "project-skills", ".ssh", ".config"}
# Only packs with an explicit reviewed publication policy are admitted. Unknown
# project-packs paths remain private. Pack-owned exceptions never bypass the scan.
PACK_TEXT = {".ts", ".tsx", ".js", ".mjs", ".sh"}


def pack_policies(root=None):
    root = ROOT if root is None else root
    return {path.parent.relative_to(root).as_posix() + "/": json.loads(path.read_text())
            for path in sorted((root / "project-packs").glob("*/publication.json"))
            if path.is_file() and not path.is_symlink()}


# One reviewed, generated preview; all other binary paths remain rejected.
BINARY_ASSETS = {
    "docs/assets/devstack-workflow.gif": {
        "sha256": "6681f220103b14bd8a9b9f6b945f5506af39005814b76565da181e6b87829f18",
        "signature": b"GIF89a",
        "size": 143274,
        "width": 960,
        "height": 550,
    },
}

# Personal instruction names are rejected everywhere except exact author-credit
# lines in the notice. They are guarded by SHA-256 of a lowercase word prefix of
# the listed lengths, so account names in URLs are caught without being spelled here.
PERSONAL_NAME_HASHES = {
    "23ddda4810068cc44360dffd31b6c5a9ad13fb9e6a69c9354a5d1b07f1b9843f",
    "97683eaa94b4560d33e3daa6ff734885474fc5a508b5026784b22a7a0e439afc",
    "44edd410d3cc163201f7bbc09cc6210e52543f1fb413338ac65533293eff16d9",
}
PERSONAL_NAME_LENGTHS = (6, 7, 8)
# SHA-256 of private setup locations, matched as one lowercase "~/<dir>/" or ".<dir>" segment.
PRIVATE_PATH_HASHES = {
    "73550989116704f5ce33d5d1f05ef9a2d6b003e09769edbe8f9ccc0ad54236c9",
    "7ad5f749dbf71e52e6ee8da9a48239e3c9a40dc3ae544737e335caf1986d9143",
}
PRIVATE_PATH_SHAPES = (re.compile(r"~/[^/\s'\"`]+/"), re.compile(r"\.[a-z0-9-]+"))
CREDIT_LINES = {
    "NOTICE.md": {
        "d68821fb9aaa338454a9b78a33f96d8676b2f10c57afb0d09179b53f7e40d0a7",
    },
}

PATTERNS = {
    # A home folder where a path can start: /Users/<name> (macOS case) or /users/<name>/ in any case
    # with a further path segment, so API routes such as /users/me and /api/users/me pass.
    "home path": re.compile(r"(?<![^\s'\"`(=:~,;|<>\[/])(?:(?-i:/Users/)[a-z]|/users/[a-z][^/\s'\"`]*/)"
                            r"|/home/[a-z][a-z0-9_-]+/|[a-z]:[\\/]+users[\\/]+", re.I),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[a-z]{2,}\b(?<!\.invalid)"),
    "IPv4 address": re.compile(r"\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b|192\.0\.2\.|198\.51\.100\.|203\.0\.113\.)(?:\d{1,3}\.){3}\d{1,3}\b"),
    "private key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "token": re.compile(r"\b(?:ghp|gho|ghs|github_pat|sk-ant|xox[abpr])[-_][A-Za-z0-9_]{12,}"),
    "ssh public key": re.compile(r"\bssh-(?:ed25519|rsa) AAAA"),
    "tailnet host": re.compile(r"\.ts\.net\b"),
    "registry id": re.compile(r"\b[ta]-[0-9a-f]{12}\b|\b(?:TKT|INT)-\d{3,}\b"),
    "session uuid": re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),
}
# Exact reviewed lines that may contain one finding category: {path: {sha256(line): category}}.
# Any other line, or this line in another file, is still rejected.
ALLOW_LINES = {
    "bench/bench.py": {  # the sandbox stub's fixed reference number
        "60a47f24d736bb1c00f79b5c3a9e01b1bcf524dc8c4e8b5554f01eab5c7c1a2f": "registry id",
    },
}
# SHA-256 of lowercase private words (customer, product, account and host
# names). Hashes keep the guarded names out of the published checker.
PRIVATE_WORD_HASHES = {
    "3318a69ad31e3f18ec2ccea4041e8d59fe52ea6b1147a9c3f000d35174d53f8b",
    "0b4e6e1a8f6c0fbe044f9ba4f8667cb22d9bf86fab71b1d227ed99e3fc634914",
    "2f9cb7cda5222087ae8774bc7a30bd0ac7de094e8aa354059072eece2217bbf8",
    "d2ec7ac9b679a4f6a78840b882b846b93b8f6dc6a7359b6272e63e89e56eb3bf",
    "08ed8bf0b5ecd497ecdc72ce192a073faabd63a48979afc8f3ec781153a85ef2",
    "9c6e990c0eab420414f9e0774aca0322570fa48cd7a8c82afe116d19b9f8818c",
    "d000a131ba8f46691edd322bb11d0d9746cb99dac0d51f67cdb6645589a36c49",
    "61a881df2f426222462b7da88aaa5496f7db09ac19aaa48fa3fd9d90acb0b9d8",
    "97683eaa94b4560d33e3daa6ff734885474fc5a508b5026784b22a7a0e439afc",
    "56c78b19f2a15ced19e59404720a59ff41a8dd1bcc7bec07fd06c3085e75cb61",
    "0fcabb5c695a26ac10921bb958c3b5daf59085d80b4f7a895d667f5f9e7d547a",
    "b98246ad0d30014a7e7cf23f1f2b7ad3ec06937c148ba3bf5b3451c869fc7431",
    "d30ca7a7a32bf5772dc5eb2a2e7bd35737eff795ad74f2479b359716b59abdfa",
    "19ce2330fe21ed704dadecdeb7815c2beca3e4b4d0ef92baec3ef22eccd49f08",
}
# Optional extra plain-text terms, one per line, kept outside the package.
LOCAL_DENYLIST = Path(os.environ.get("DEVSTACK_PRIVACY_DENYLIST",
                                     Path.home() / ".config/devstack/privacy-denylist.txt"))

failures = []


def fail(message):
    failures.append(message)


def tracked():
    """Paths git tracks in ROOT (empty outside a git checkout)."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [ROOT / name for name in out.decode("utf-8", "surrogateescape").split("\0") if name]


def files():
    """Every file on disk outside generated caches, plus every tracked file wherever it lives."""
    seen = set()
    for path in sorted(ROOT.rglob("*")):
        if (path.is_file() or path.is_symlink()) and not SKIP_DIRS & set(path.relative_to(ROOT).parts):
            seen.add(path)
            yield path
    for path in tracked():
        if path not in seen and (path.is_file() or path.is_symlink()):
            yield path


def check_tracked_caches():
    for path in tracked():
        if {"__pycache__", ".pytest_cache"} & set(path.relative_to(ROOT).parts) or path.suffix in (".pyc", ".pyo"):
            fail(f"privacy: tracked cache file {rel(path)}")


def rel(path):
    return path.relative_to(ROOT).as_posix()


def check_manifest():
    manifest = json.loads((ROOT / "SOURCE-MANIFEST.json").read_text())
    paths = [entry["path"] for entry in manifest["files"]]
    if len(paths) != len(set(paths)) or set(paths) != set(FILES):
        fail("manifest: paths must match the exact approved source file list")
    if manifest.get("skills") != list(SKILLS) or manifest.get("workflow_version") != WORKFLOW_VERSION:
        fail(f"manifest: expected modular {WORKFLOW_VERSION} and all {len(SKILLS)} skills")
    actual = {rel(path) for top in PACKAGE_RESOURCE_ROOTS
              for path in (ROOT / top).rglob("*")
              if (path.is_file() or path.is_symlink())
              and not SKIP_DIRS & set(path.relative_to(ROOT).parts)}
    actual |= {name for name in PACKAGE_RESOURCE_FILES if (ROOT / name).exists()}
    if actual != set(FILES):
        fail("manifest: package coverage differs: " + ", ".join(sorted(actual ^ set(FILES))))
    for entry in manifest["files"]:
        if entry["path"] not in FILES:
            continue
        path = ROOT / entry["path"]
        if path.is_symlink() or not path.is_file():
            fail(f"manifest: missing {entry['path']}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["published_sha256"]:
            fail(f"manifest: {entry['path']} differs from its recorded published bytes")
        for key in ("source_sha256", "published_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get(key, ""))):
                fail(f"manifest: invalid {key} for {entry['path']}")
        if not isinstance(entry.get("sanitized"), bool):
            fail(f"manifest: missing sanitization status for {entry['path']}")
        if entry.get("sanitized"):
            fail(f"manifest: team resource must use local unsanitized bytes for {entry['path']}")
        if entry.get("source_sha256") != entry.get("published_sha256"):
            fail(f"manifest: unexplained source/publication difference for {entry['path']}")


def slug(heading):
    text = re.sub(r"[`*_~]|<[^>]+>", "", heading.strip().lower())
    text = re.sub(r"\]\([^)]*\)", "", text).replace("[", "")
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path):
    found, seen = set(), {}
    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        match = re.match(r"#{1,6}\s+(.*)", line)
        if match:
            base = slug(match.group(1))
            count = seen.get(base, 0)
            seen[base] = count + 1
            found.add(base if count == 0 else f"{base}-{count}")
    return found


def check_links():
    link = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)")
    for path in files():
        if path.suffix != ".md":
            continue
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for match in link.finditer(text):
            target = match.group(1) or match.group(2)
            if re.match(r"[a-z]+:", target):
                continue
            file_part, _, anchor = target.partition("#")
            destination = (path.parent / file_part).resolve() if file_part else path
            if not destination.exists():
                fail(f"link: {rel(path)} -> {target} (missing)")
            elif ROOT not in destination.parents and destination != ROOT:
                fail(f"link: {rel(path)} -> {target} (leaves the package)")
            elif anchor and destination.suffix == ".md" and anchor not in anchors(destination):
                fail(f"link: {rel(path)} -> {target} (missing anchor)")


def personal_name(line):
    """True when a word in the line starts with a guarded personal name."""
    return any(hashlib.sha256(word[:size].encode()).hexdigest() in PERSONAL_NAME_HASHES
               for word in re.findall(r"[a-z0-9]+", line.lower())
               for size in PERSONAL_NAME_LENGTHS if len(word) >= size)


def privacy_issues(name, data, policies=None):
    """Return redacted findings for one path; shared by refresh preflight."""
    problems = []
    path = Path(name)
    if name in BINARY_ASSETS:
        expected = BINARY_ASSETS[name]
        if (hashlib.sha256(data).hexdigest() != expected["sha256"]
                or not data.startswith(expected["signature"])
                or len(data) != expected["size"]
                or int.from_bytes(data[6:8], "little") != expected["width"]
                or int.from_bytes(data[8:10], "little") != expected["height"]):
            return [f"privacy: changed or invalid reviewed binary asset {name}"]
        return []
    policies = pack_policies() if policies is None else policies
    policy = next((p for prefix, p in policies.items() if name.startswith(prefix)), None)
    in_pack = policy is not None
    if (FORBIDDEN_NAMES.search(path.name) or FORBIDDEN_PARTS & set(path.parts)
            or ("project-packs" in path.parts and not in_pack)
            or (path.name.startswith(".") and path.name not in {".gitignore"})):
        return [f"privacy: forbidden path {name}"]
    if path.suffix not in TEXT and not (in_pack and path.suffix in PACK_TEXT):
        return [f"privacy: unreviewed file type {name}"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"privacy: unreadable text {name}"]
    for number, line in enumerate(text.splitlines(), 1):
        if (personal_name(line)
                and hashlib.sha256(line.encode()).hexdigest() not in CREDIT_LINES.get(name, set())):
            problems.append(f"privacy: personal instruction name at {name}:{number}")
    local_terms = []
    if LOCAL_DENYLIST.is_file():
        local_terms = [t.strip().lower() for t in LOCAL_DENYLIST.read_text().splitlines()
                       if t.strip() and not t.startswith("#")]
    if name == "scripts/check.py" and "PATTERNS = {" in text and "failures = []" in text:
        text = text.split("PATTERNS = {", 1)[0] + text.split("failures = []", 1)[1]
    lines = text.split("\n")
    allowed = dict(ALLOW_LINES.get(name, {}))
    if policy:
        allowed.update(policy.get("allow_lines", {}).get(name, {}))
    for label, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            if allowed.get(hashlib.sha256(lines[line - 1].encode()).hexdigest()) == label:
                continue
            problems.append(f"privacy: {label} at {name}:{line}")
    for number, line in enumerate(lines, 1):
        lower = line.lower()
        if (any(hashlib.sha256(m.group().encode()).hexdigest() in PRIVATE_PATH_HASHES
                for shape in PRIVATE_PATH_SHAPES for m in shape.finditer(lower))
                and allowed.get(hashlib.sha256(line.encode()).hexdigest()) != "private setup path"):
            problems.append(f"privacy: private setup path at {name}:{number}")
    for number, line in enumerate(text.splitlines(), 1):
        credit = hashlib.sha256(line.encode()).hexdigest() in CREDIT_LINES.get(name, set())
        for match in re.finditer(r"[a-z0-9]+", line.lower()):
            word = match.group()
            digest = hashlib.sha256(word.encode()).hexdigest()
            if (digest in PRIVATE_WORD_HASHES and not credit
                    and not any(re.compile(p["brand_pattern"], re.I).match(line, match.start())
                                for p in policies.values())
                    and not (in_pack and digest in policy.get("word_hashes", []))):
                problems.append(f"privacy: private name at {name}:{number}")
        for term in local_terms:
            if term in line.lower():
                problems.append(f"privacy: local denylist term at {name}:{number}")
    return problems


def check_privacy():
    for path in files():
        if path.is_symlink():
            fail(f"privacy: linked package resource {rel(path)}")
            continue
        failures.extend(privacy_issues(rel(path), path.read_bytes()))


# A strict YAML subset (block mappings and sequences, flow lists, quoted and block scalars):
# enough for the CI templates, with no third-party parser. Anything outside it is an error.
YAML_KEY = re.compile(r"""(?P<key>[A-Za-z0-9_.$/-]+|"[^"]*"|'[^']*'):(?:[ ]+(?P<value>.*))?$""")
ACTION_PIN = re.compile(r"[\w.-]+/[\w.-]+(?:/[\w./-]+)?@v\d+")


def _yaml_comment(line):
    quote = None
    for index, char in enumerate(line):
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"" and (index == 0 or line[index - 1] in " [,:-"):
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index]
    return line


def _yaml_lines(text):
    raw, out, blocks, index = text.split("\n"), [], {}, 0
    while index < len(raw):
        line, number = raw[index], index + 1
        index += 1
        lead = line[:len(line) - len(line.lstrip())]
        if "\t" in lead:
            raise ValueError(f"line {number}: tab indentation")
        content = _yaml_comment(line).rstrip()
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip())
        content = content.strip()
        block = re.search(r"(?:^|: |^- )([|>][-+]?)$", content)
        if block:
            body = []
            while index < len(raw) and (not raw[index].strip() or len(raw[index]) - len(raw[index].lstrip()) > indent):
                body.append(raw[index])
                index += 1
            token = f"\0block{len(blocks)}"
            blocks[token] = textwrap.dedent("\n".join(body)).strip("\n") + "\n"
            content = content[:block.start(1)] + token
        out.append([indent, content, number])
    return out, blocks


def _yaml_scalar(value, number, blocks):
    if value in blocks:
        return blocks[value]
    if value.startswith("[") or value.startswith("{"):
        if not value.endswith("]") or value.startswith("{") or "[" in value[1:-1]:
            raise ValueError(f"line {number}: only flat flow lists are supported")
        return [_yaml_scalar(item.strip(), number, blocks) for item in value[1:-1].split(",") if item.strip()]
    if value[0] in "\"'":
        if len(value) < 2 or value[-1] != value[0]:
            raise ValueError(f"line {number}: unterminated quoted scalar")
        return json.loads(value) if value[0] == '"' else value[1:-1].replace("''", "'")
    if value[0] in "*&!%@`|>" or ": " in value or value.endswith(":"):
        raise ValueError(f"line {number}: ambiguous plain scalar; quote it")
    return value


def _yaml_block(lines, pos, indent, blocks):
    if lines[pos][1] == "-" or lines[pos][1].startswith("- "):
        return _yaml_sequence(lines, pos, indent, blocks)
    return _yaml_mapping(lines, pos, indent, blocks)


def _yaml_mapping(lines, pos, indent, blocks):
    result = {}
    while pos < len(lines) and lines[pos][0] >= indent:
        level, content, number = lines[pos]
        match = YAML_KEY.match(content)
        if level > indent or not match:
            raise ValueError(f"line {number}: expected 'key: value' at indent {indent}")
        key = match.group("key").strip("'\"")
        if key in result:
            raise ValueError(f"line {number}: duplicate key {key!r}")
        value, pos = match.group("value"), pos + 1
        if value:
            result[key] = _yaml_scalar(value, number, blocks)
        elif pos < len(lines) and (lines[pos][0] > indent or (lines[pos][0] == indent and lines[pos][1].startswith("- "))):
            result[key], pos = _yaml_block(lines, pos, lines[pos][0], blocks)
        else:
            result[key] = None
    return result, pos


def _yaml_sequence(lines, pos, indent, blocks):
    items = []
    while pos < len(lines) and lines[pos][0] == indent and (lines[pos][1] == "-" or lines[pos][1].startswith("- ")):
        level, content, number = lines[pos]
        rest = content[1:].strip()
        if not rest:
            pos += 1
            if pos >= len(lines) or lines[pos][0] <= indent:
                raise ValueError(f"line {number}: empty sequence item")
            item, pos = _yaml_block(lines, pos, lines[pos][0], blocks)
        elif YAML_KEY.match(rest):
            lines[pos] = [indent + len(content) - len(rest), rest, number]
            item, pos = _yaml_mapping(lines, pos, lines[pos][0], blocks)
        else:
            item, pos = _yaml_scalar(rest, number, blocks), pos + 1
        items.append(item)
    if pos < len(lines) and lines[pos][0] > indent:
        raise ValueError(f"line {lines[pos][2]}: unexpected indentation")
    return items, pos


def parse_yaml(text):
    lines, blocks = _yaml_lines(text)
    if not lines:
        return None
    if lines[0][0]:
        raise ValueError(f"line {lines[0][2]}: document must start at column 0")
    value, pos = _yaml_block(lines, 0, 0, blocks)
    if pos != len(lines):
        raise ValueError(f"line {lines[pos][2]}: unexpected content")
    return value


def ci_template_issues(data):
    """Least-privilege, pinned-action shape of a CI template (examples/ci/)."""
    problems = []
    if not isinstance(data, dict) or not {"name", "on", "permissions", "jobs"} <= set(data):
        return ["needs name, on, permissions and jobs"]
    if data["permissions"] != {"contents": "read"}:
        problems.append("top-level permissions must be exactly contents: read")
    jobs = data["jobs"] if isinstance(data["jobs"], dict) else {}
    if not jobs:
        problems.append("no jobs")
    for name, job in jobs.items():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list) or not steps:
            problems.append(f"job {name} has no steps")
            continue
        if "permissions" in job and job["permissions"] != {"contents": "read"}:
            problems.append(f"job {name} widens permissions")
        uses = [step.get("uses") for step in steps if isinstance(step, dict) and step.get("uses")]
        if not uses or not str(uses[0]).startswith("actions/checkout@"):
            problems.append(f"job {name} must start with actions/checkout")
        problems += [f"job {name}: action {u!r} is not pinned to a major version (@vN)"
                     for u in uses if not ACTION_PIN.fullmatch(str(u))]
    return problems


def check_formats():
    for name in BINARY_ASSETS:
        if not (ROOT / name).is_file():
            fail(f"asset: missing reviewed binary {name}")
    for path in files():
        if path.suffix == ".json":
            try:
                json.loads(path.read_text())
            except ValueError as error:
                fail(f"json: {rel(path)}: {error}")
        elif path.suffix in (".yml", ".yaml"):
            try:
                data = parse_yaml(path.read_text(encoding="utf-8"))
            except ValueError as error:
                fail(f"yaml: {rel(path)}: {error}")
                continue
            if rel(path).startswith("examples/ci/"):
                for problem in ci_template_issues(data):
                    fail(f"ci template: {rel(path)}: {problem}")
        elif path.suffix == ".svg":
            try:
                root = ET.parse(path).getroot()
                if not root.tag.endswith("svg") or root.find("{http://www.w3.org/2000/svg}title") is None:
                    fail(f"svg: {rel(path)} needs an <svg> root with an accessible <title>")
            except ET.ParseError as error:
                fail(f"svg: {rel(path)}: {error}")
            if re.search(r"<script|href=\"https?:", path.read_text()):
                fail(f"svg: {rel(path)} must be static and self-contained")
        elif path.suffix == ".html":
            html = path.read_text()
            if re.search(r"<(?:script|link|img|iframe)[^>]+(?:src|href)=[\"']?https?:", html, re.I):
                fail(f"html: {rel(path)} loads a remote resource")
            for needle in ("prefers-reduced-motion", "aria-pressed", "<meta name=\"viewport\""):
                if needle not in html:
                    fail(f"html: {rel(path)} lacks {needle}")


def check_skills():
    actual = {path.name for path in (ROOT / "skills").iterdir() if path.is_dir()}
    if actual != set(SKILLS):
        fail(f"skills: expected exactly {len(SKILLS)} callable folders: " + ", ".join(sorted(actual ^ set(SKILLS))))
    for name in SKILLS:
        if not (ROOT / "skills" / name / "SKILL.md").is_file():
            fail(f"skill: missing actual entrypoint {name}/SKILL.md")
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        head = skill.read_text().split("---")
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", head[1], re.M)) if len(head) > 2 else {}
        if meta.get("name") != skill.parent.name or not meta.get("description", "").strip():
            fail(f"skill: {rel(skill)} frontmatter needs name={skill.parent.name} and a description")
        body = "---".join(head[2:]) if len(head) > 2 else ""
        if len(body.split()) < 120 or len(re.findall(r"^##? ", body, re.M)) < 2:
            fail(f"skill: {rel(skill)} must contain an actionable workflow, not a thin reference wrapper")


def check_provenance():
    for name, license_name, provenance_name in (
            ("create-test-recipes", "LICENSE", "PROVENANCE.md"),
            ("ponytail", "LICENSE.txt", "PROVENANCE.json"),
            ("reverse-engineer-anything", "LICENSE", "PROVENANCE.json")):
        if name not in SKILLS:
            continue
        directory = ROOT / "skills" / name
        for required in (license_name, provenance_name):
            if not (directory / required).is_file():
                fail(f"provenance: {name} missing {required}")
        license_file = directory / license_name
        if license_file.is_file():
            text = license_file.read_text()
            if "MIT License" not in text or "Copyright" not in text:
                fail(f"provenance: {name} missing retained MIT notice")
            provenance_file = directory / ("source.json" if name == "create-test-recipes"
                                            else provenance_name)
            if provenance_file.is_file():
                provenance = json.loads(provenance_file.read_text())
                expected = (next(entry["sha256"] for entry in provenance["files"]
                                 if entry["path"] == "pstack/LICENSE")
                            if name == "create-test-recipes"
                            else provenance["upstream_files"]["LICENSE"])
                if hashlib.sha256(license_file.read_bytes()).hexdigest() != expected:
                    fail(f"provenance: {name} license differs from recorded upstream notice")
    if "reverse-engineer-anything" in SKILLS:
        rea = ROOT / "skills/reverse-engineer-anything"
        if len([path for path in rea.rglob("*") if path.is_file()]) != 9:
            fail("provenance: expected all nine REA files; review any additions deliberately")


def check_kpi_example():
    monitor = ROOT / "monitoring/devstack/kpi_monitor.py"
    snapshot = (ROOT / "examples/kpi-snapshot.example.json").read_text()
    with tempfile.TemporaryDirectory() as scratch:
        db = str(Path(scratch) / "kpis.sqlite3")
        recorded = subprocess.run([sys.executable, str(monitor), "--db", db, "record"],
                                  input=snapshot, capture_output=True, text=True)
        report = subprocess.run([sys.executable, str(monitor), "--db", db, "report",
                                 "--as-of", "2026-10-26T12:00:00+00:00"], capture_output=True, text=True)
        card = subprocess.run([sys.executable, str(monitor), "--db", db, "scorecard", "--as-of", "2026-10-26T12:00:00+00:00",
                               "--targets", str(ROOT / "examples/kpi-targets.example.json"), "--runs", scratch],
                              capture_output=True, text=True)
    if recorded.returncode or report.returncode:
        fail(f"kpi example: record={recorded.returncode} report={report.returncode} {recorded.stderr}{report.stderr}")
    if card.returncode or "🎯 targets" not in card.stdout:
        fail(f"kpi targets example: scorecard={card.returncode} {card.stderr}")


def check_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_kpi_monitor", "test_task_kpi"],
                            cwd=ROOT / "monitoring/devstack", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    summary = (result.stderr.strip().splitlines() or ["no output"])[-3:]
    if result.returncode:
        fail("tests: " + " | ".join(summary))
    return " ".join(line for line in summary if line.startswith("Ran"))


def check_ticket_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_ticket_ref"],
                            cwd=ROOT / "tools/ticket-ref", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode:
        fail("ticket numbering tests: " + result.stderr.strip())
    return " ".join(line for line in result.stderr.splitlines() if line.startswith("Ran"))


def check_tool_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", *sorted(p.stem for p in (ROOT / "tools").glob("test_*.py"))],
                            cwd=ROOT / "tools", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode:
        fail("tool tests: " + " | ".join(result.stderr.strip().splitlines()[-3:]))
    return " ".join(line for line in result.stderr.splitlines() if line.startswith("Ran"))


def check_script_tests():
    """Tests for the setup tools: the setup check, skill mirrors, Codex hook trust, detach and the ticket launcher."""
    modules = ["test_setup_doctor", "test_skill_mirrors", "test_codex_hook_trust", "test_detach", "test_ticket_launcher"]
    if any((ROOT / "scripts" / name).is_file() for name in ("export_public.py", "test_export_public.py")):
        modules.append("test_export_public")  # private-source tests also verify the public tree end to end
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", *modules],
                            cwd=ROOT / "scripts", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode:
        fail("setup helper tests: " + " | ".join(result.stderr.strip().splitlines()[-3:]))
    return " ".join(line for line in result.stderr.splitlines() if line.startswith("Ran"))


def check_bench_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_bench"],
                            cwd=ROOT / "bench", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode:
        fail("benchmark tests: " + " | ".join(result.stderr.strip().splitlines()[-3:]))
    return " ".join(line for line in result.stderr.splitlines() if line.startswith("Ran"))


ALLOW_MISSING_NODE = False
incomplete = []


def check_pack_tests():
    """Run the pack's own offline tests. The JS tests guard the auth proxy and need node."""
    ran = []
    for test in sorted(test for pack in pack_policies() for test in (ROOT / pack).rglob("*.test.mjs")):
        node = shutil.which("node")
        if not node:
            message = f"node is not installed, so the pack's security tests ({rel(test)}) cannot run"
            if ALLOW_MISSING_NODE:
                incomplete.append(message)
                continue
            fail(f"pack test: {message}; install Node.js, or pass --allow-missing-node to accept an INCOMPLETE result")
            continue
        result = subprocess.run([node, "--test", test.name], cwd=test.parent, capture_output=True, text=True)
        if result.returncode:
            fail(f"pack test: {rel(test)}: " + " | ".join(result.stdout.strip().splitlines()[-4:]))
        ran.append(test.name)
    for test in sorted(test for pack in pack_policies() for test in (ROOT / pack).rglob("test_*.py")):
        result = subprocess.run([sys.executable, "-m", "unittest", "-q", test.stem], cwd=test.parent,
                                capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if result.returncode:
            fail(f"pack test: {rel(test)}: " + " | ".join(result.stderr.strip().splitlines()[-3:]))
        ran.append(test.name)
    return f"{len(ran)} files"


def check_template():
    template = ROOT / "examples/global-instructions/AGENTS.md"
    text = template.read_text(encoding="utf-8") if template.is_file() else ""
    if not text.startswith("<!-- devstack-global-instructions -->\n"):
        fail("template: examples/global-instructions/AGENTS.md must start with its install marker")
    for needle in ("<DEVSTACK>/skills/devstack/SKILL.md", "<DEVSTACK>/monitoring/devstack/task_kpi.py",
                   "<DEVSTACK>/examples/project-pack/README.md"):
        if needle not in text:
            fail(f"template: missing {needle}")
        elif not (ROOT / needle.replace("<DEVSTACK>/", "")).is_file():
            fail(f"template: {needle} does not exist in this checkout")


def check_package_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_package"],
                            cwd=ROOT / "scripts", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode:
        fail("package negative controls: " + result.stderr.strip())
    return " ".join(line for line in result.stderr.splitlines() if line.startswith("Ran"))


def main(argv=None):
    global ALLOW_MISSING_NODE
    argv = sys.argv[1:] if argv is None else argv
    unknown = [a for a in argv if a != "--allow-missing-node"]
    if unknown:
        print("usage: check.py [--allow-missing-node]")
        return 2
    ALLOW_MISSING_NODE = "--allow-missing-node" in argv
    for step in (check_manifest, check_links, check_privacy, check_tracked_caches, check_formats, check_skills,
                 check_provenance, check_template, check_kpi_example):
        step()
    ran = check_tests()
    ticket_ran = check_ticket_tests()
    tool_ran = check_tool_tests()
    package_ran = check_package_tests()
    helper_ran = check_script_tests()
    bench_ran = check_bench_tests()
    pack_ran = check_pack_tests()
    if failures:
        print("\n".join(failures))
        print(f"\nFAILED: {len(failures)} problem(s)")
        return 1
    if incomplete:
        print("INCOMPLETE: " + "; ".join(incomplete) + ". Every other check passed; this is not a green result.")
        return 3
    print(f"OK: exact manifest, links, privacy, formats, {len(SKILLS)} skills, template, KPI example; KPI tests: {ran}; "
          f"numbering tests: {ticket_ran}; tool tests: {tool_ran}; package controls: {package_ran}; setup helper tests: {helper_ran}; bench tests: {bench_ran}; pack tests: {pack_ran}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
