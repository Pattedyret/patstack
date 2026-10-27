#!/usr/bin/env python3
"""Validate this package before commit or publication.

  python3 scripts/check.py

Checks: refreshed files still match SOURCE-MANIFEST.json, relative Markdown
links and anchors resolve, the privacy scan is clean, JSON/SVG parse, the
animated HTML is self-contained with reduced-motion and pause support, skill
frontmatter is valid, the example KPI snapshot round-trips through the real
recorder, and the KPI unit tests pass. Standard library only; exits 1 on any
failure. Network access is never used.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from refresh_from_source import FILES, SKILLS, PACKAGE_RESOURCE_ROOTS, WORKFLOW_VERSION

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".md", ".py", ".json", ".svg", ".html", ".txt", ".yml", ".yaml", ""}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = re.compile(r"(\.sqlite3?|\.db|\.jsonl|\.env|devices\.local\.json|\.pem|\.key)$", re.I)
FORBIDDEN_PARTS = {"backups", "archives", "transcripts", "project-skills", ".ssh", ".config"}

# One reviewed, generated preview; all other binary paths remain rejected.
BINARY_ASSETS = {
    "docs/assets/patstack-workflow.gif": {
        "sha256": "6681f220103b14bd8a9b9f6b945f5506af39005814b76565da181e6b87829f18",
        "signature": b"GIF89a",
        "size": 143274,
        "width": 960,
        "height": 550,
    },
}

PATTERNS = {
    "home path": re.compile(r"/Users/[A-Za-z]|/home/[a-z][a-z0-9_-]+/|[A-Z]:[\\/]+Users[\\/]+", re.I),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[a-z]{2,}"),
    "IPv4 address": re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b"),
    "private key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "token": re.compile(r"\b(?:ghp|gho|ghs|github_pat|sk-ant|xox[abpr])[-_][A-Za-z0-9_]{12,}"),
    "ssh public key": re.compile(r"\bssh-(?:ed25519|rsa) AAAA"),
    "tailnet host": re.compile(r"\.ts\.net\b"),
    "registry id": re.compile(r"\b[ta]-[0-9a-f]{12}\b|\b(?:TKT|INT)-\d{3,}\b"),
    "session uuid": re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),
}
# Fictional fixtures that intentionally look like a private value.
ALLOW = {
    ("monitoring/patstack/test_kpi_monitor.py", "home path"),
}
# SHA-256 of lowercase private words (customer, product, account and host
# names). Hashes keep the guarded names out of the published checker.
PRIVATE_WORD_HASHES = {
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
LOCAL_DENYLIST = Path(os.environ.get("PATSTACK_PRIVACY_DENYLIST",
                                     Path.home() / ".config/patstack/privacy-denylist.txt"))

failures = []


def fail(message):
    failures.append(message)


def files():
    for path in sorted(ROOT.rglob("*")):
        if (path.is_file() or path.is_symlink()) and not SKIP_DIRS & set(path.relative_to(ROOT).parts):
            yield path


def rel(path):
    return path.relative_to(ROOT).as_posix()


def check_manifest():
    manifest = json.loads((ROOT / "SOURCE-MANIFEST.json").read_text())
    paths = [entry["path"] for entry in manifest["files"]]
    if len(paths) != len(set(paths)) or set(paths) != set(FILES):
        fail("manifest: paths must match the exact approved source file list")
    if manifest.get("skills") != list(SKILLS) or manifest.get("workflow_version") != WORKFLOW_VERSION:
        fail(f"manifest: expected modular {WORKFLOW_VERSION} and all 19 skills")
    actual = {rel(path) for top in PACKAGE_RESOURCE_ROOTS
              for path in (ROOT / top).rglob("*")
              if (path.is_file() or path.is_symlink())
              and not SKIP_DIRS & set(path.relative_to(ROOT).parts)}
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
        if not entry.get("sanitized") and entry.get("source_sha256") != entry.get("published_sha256"):
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


def privacy_issues(name, data):
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
    if FORBIDDEN_NAMES.search(path.name) or FORBIDDEN_PARTS & set(path.parts):
        return [f"privacy: forbidden path {name}"]
    if path.suffix not in TEXT:
        return [f"privacy: unreviewed file type {name}"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"privacy: unreadable text {name}"]
    local_terms = []
    if LOCAL_DENYLIST.is_file():
        local_terms = [t.strip().lower() for t in LOCAL_DENYLIST.read_text().splitlines()
                       if t.strip() and not t.startswith("#")]
    if name == "scripts/check.py":
        text = text.split("PATTERNS = {", 1)[0] + text.split("failures = []", 1)[1]
    for label, pattern in PATTERNS.items():
        if (name, label) in ALLOW:
            continue
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"privacy: {label} at {name}:{line}")
    for number, line in enumerate(text.splitlines(), 1):
        for word in re.findall(r"[a-z0-9]+", line.lower()):
            if hashlib.sha256(word.encode()).hexdigest() in PRIVATE_WORD_HASHES:
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
        fail("skills: expected exactly 19 callable folders: " + ", ".join(sorted(actual ^ set(SKILLS))))
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
            ("ponytail", "LICENSE.txt", "PROVENANCE.json")):
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
    rea = ROOT / "skills/reverse-engineer-anything"
    if len([path for path in rea.rglob("*") if path.is_file()]) != 7:
        fail("provenance: expected all seven existing REA files; review any additions deliberately")


def check_kpi_example():
    monitor = ROOT / "monitoring/patstack/kpi_monitor.py"
    snapshot = (ROOT / "examples/kpi-snapshot.example.json").read_text()
    with tempfile.TemporaryDirectory() as scratch:
        db = str(Path(scratch) / "kpis.sqlite3")
        recorded = subprocess.run([sys.executable, str(monitor), "--db", db, "record"],
                                  input=snapshot, capture_output=True, text=True)
        report = subprocess.run([sys.executable, str(monitor), "--db", db, "report",
                                 "--as-of", "2026-10-26T12:00:00+00:00"], capture_output=True, text=True)
    if recorded.returncode or report.returncode:
        fail(f"kpi example: record={recorded.returncode} report={report.returncode} {recorded.stderr}{report.stderr}")


def check_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_kpi_monitor"],
                            cwd=ROOT / "monitoring/patstack", capture_output=True, text=True,
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


def check_package_tests():
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_package"],
                            cwd=ROOT / "scripts", capture_output=True, text=True,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode:
        fail("package negative controls: " + result.stderr.strip())
    return " ".join(line for line in result.stderr.splitlines() if line.startswith("Ran"))


def main():
    for step in (check_manifest, check_links, check_privacy, check_formats, check_skills,
                 check_provenance, check_kpi_example):
        step()
    ran = check_tests()
    ticket_ran = check_ticket_tests()
    package_ran = check_package_tests()
    if failures:
        print("\n".join(failures))
        print(f"\nFAILED: {len(failures)} problem(s)")
        return 1
    print(f"OK: exact manifest, links, privacy, formats, {len(SKILLS)} skills, KPI example; KPI tests: {ran}; numbering tests: {ticket_ran}; package controls: {package_ran}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
