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

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".md", ".py", ".json", ".svg", ".html", ".txt", ".yml", ".yaml", ""}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = re.compile(r"(\.sqlite3?|\.db|\.jsonl|\.env|devices\.local\.json|\.pem|\.key)$", re.I)

PATTERNS = {
    "home path": re.compile(r"/Users/[A-Za-z]|/home/[a-z][a-z0-9_-]+/|[A-Z]:\\\\Users\\\\"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[a-z]{2,}"),
    "IPv4 address": re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b"),
    "private key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "token": re.compile(r"\b(?:ghp|gho|ghs|github_pat|sk-ant|xox[abpr])[-_][A-Za-z0-9_]{12,}"),
    "ssh public key": re.compile(r"\bssh-(?:ed25519|rsa) AAAA"),
    "tailnet host": re.compile(r"\.ts\.net\b"),
    "registry id": re.compile(r"\b[ta]-[0-9a-f]{12}\b|\b(?:TKT|INT)-\d{3,}\b"),
    "session uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
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
        if path.is_file() and not SKIP_DIRS & set(path.relative_to(ROOT).parts):
            yield path


def rel(path):
    return path.relative_to(ROOT).as_posix()


def check_manifest():
    manifest = json.loads((ROOT / "SOURCE-MANIFEST.json").read_text())
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        if not path.is_file():
            fail(f"manifest: missing {entry['path']}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["published_sha256"]:
            fail(f"manifest: {entry['path']} was edited by hand; edit the source and refresh")


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


def check_privacy():
    local_terms = []
    if LOCAL_DENYLIST.is_file():
        local_terms = [t.strip().lower() for t in LOCAL_DENYLIST.read_text().splitlines()
                       if t.strip() and not t.startswith("#")]
    for path in files():
        name = rel(path)
        if FORBIDDEN_NAMES.search(path.name):
            fail(f"privacy: forbidden file type {name}")
            continue
        if path.suffix not in TEXT:
            continue
        text = path.read_text(encoding="utf-8")
        if name == "scripts/check.py":
            text = text.split("PATTERNS = {", 1)[0] + text.split("failures = []", 1)[1]
        for label, pattern in PATTERNS.items():
            if (name, label) in ALLOW:
                continue
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                fail(f"privacy: {label} at {name}:{line}")
        for number, line in enumerate(text.splitlines(), 1):
            for word in re.findall(r"[a-z0-9]+", line.lower()):
                if hashlib.sha256(word.encode()).hexdigest() in PRIVATE_WORD_HASHES:
                    fail(f"privacy: private name at {name}:{number}")
            lowered = line.lower()
            for term in local_terms:
                if term in lowered:
                    fail(f"privacy: local denylist term at {name}:{number}")


def check_formats():
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
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        head = skill.read_text().split("---")
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", head[1], re.M)) if len(head) > 2 else {}
        if meta.get("name") != skill.parent.name or not meta.get("description", "").startswith("Use when"):
            fail(f"skill: {rel(skill)} frontmatter needs name={skill.parent.name} and a 'Use when' description")


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


def main():
    for step in (check_manifest, check_links, check_privacy, check_formats, check_skills, check_kpi_example):
        step()
    ran = check_tests()
    if failures:
        print("\n".join(failures))
        print(f"\nFAILED: {len(failures)} problem(s)")
        return 1
    print(f"OK: manifest, links, privacy, formats, skills, KPI example; unit tests: {ran}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
