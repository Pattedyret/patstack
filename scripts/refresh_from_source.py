#!/usr/bin/env python3
"""Refresh the published Patstack files from the private source tree.

The private source keeps the same relative layout as this package
(skills/, monitoring/). Files are copied verbatim except for the
hash-anchored sanitization rules below. Every run rewrites
SOURCE-MANIFEST.json with source and published SHA-256 values.

  python3 scripts/refresh_from_source.py --source ~/.harnesses-shared/agent-setup
  python3 scripts/refresh_from_source.py --source PATH --check   # report drift only

Standard library only. Nothing outside this package is written.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = "~/.harnesses-shared/agent-setup"

SKILLS = (
    "patstack", "ponytail", "to-spec", "to-tickets", "implement", "review",
    "council", "verify", "full-send", "full-stop", "file-pr", "babysit-pr",
    "takeover", "modernize", "retro", "grilling", "workflow-eval",
    "create-test-recipes", "reverse-engineer-anything",
)

# Directories mirrored from the source. Every regular file inside them must be
# listed in FILES or EXCLUDED, so a new source file cannot be skipped silently.
MIRRORED = tuple("skills/" + name for name in SKILLS) + ("monitoring/patstack",)
# Only generated interpreter caches may be omitted. Archives, backups and
# unknown resources must cause a coverage error, rather than disappearing.
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
# The monitor installer stores private rollback state here. This exact runtime
# tree is never source material; a backup anywhere inside a skill still fails.
PRIVATE_RUNTIME_TREES = ("monitoring/patstack/backups",)

FILES = (
    *("skills/" + name + "/SKILL.md" for name in SKILLS
      if name not in {"patstack", "create-test-recipes"}),
    "skills/patstack/SKILL.md",
    "skills/patstack/references/access.md",
    "skills/patstack/references/build-review.md",
    "skills/patstack/references/coordination.md",
    "skills/patstack/references/decisions.md",
    "skills/patstack/references/planning.md",
    "skills/patstack/references/project-context.md",
    "skills/patstack/references/quality.md",
    "skills/patstack/references/retro.md",
    "skills/patstack/references/sources.md",
    "skills/patstack/references/task-state.md",
    "skills/patstack/references/testing-delivery.md",
    "skills/ponytail/LICENSE.txt",
    "skills/ponytail/PROVENANCE.json",
    "skills/implement/references/critical-path.md",
    "skills/workflow-eval/references/scenarios.md",
    "skills/reverse-engineer-anything/references/android-applications.md",
    "skills/reverse-engineer-anything/references/connection-and-recovery.md",
    "skills/reverse-engineer-anything/references/evidence-workflows.md",
    "skills/reverse-engineer-anything/references/javascript-applications.md",
    "skills/reverse-engineer-anything/references/native-and-artifacts.md",
    "skills/reverse-engineer-anything/references/runtime-observation.md",
    "skills/create-test-recipes/SKILL.md",
    "skills/create-test-recipes/LICENSE",
    "skills/create-test-recipes/PROVENANCE.md",
    "skills/create-test-recipes/source.json",
    "skills/create-test-recipes/references/quality-checks.md",
    "monitoring/patstack/README.md",
    "monitoring/patstack/kpi_monitor.py",
    "monitoring/patstack/test_kpi_monitor.py",
    "monitoring/patstack/install.py",
)

GENERIC_PROJECT_PACKS = (
    "Project packs are resolved from the shared setup source, never from this "
    "package: read the matching `project-skills/<project>/INDEX.md` and only the "
    "procedures it routes to for the actual change (for example new-surface "
    "intake, auth setup, deployment or synchronization). Use the canonical project "
    "workflow. These are conditional procedures, not mandatory scaffolding for "
    "every bug fix. Real project packs stay private and local; see "
    "`examples/project-pack/` in the published package for the shape."
)
GENERIC_SYNC = (
    "Some project packs define post-merge synchronization to another branch or "
    "hosted builder, with drift checks and project-specific exclusions. Preserve "
    "those constraints. If the established path includes a PR hook, verify its "
    "actual result for the delivered revision; if that step has not run, the "
    "affected Full Send delivery is not complete. The procedure alone does not "
    "prove that a live hook ran for this revision."
)
GENERIC_BROWSER = (
    "Use isolated task-owned browser sessions, profiles, fixtures and artifact "
    "directories. Do not reuse or close another session's browser. Keep the "
    "browser version/runtime and a verified launch recipe in the private "
    "capability profile. A synthetic browser smoke test establishes "
    "infrastructure readiness; it does not establish that a project feature or "
    "production behavior passes. Native Computer Use capability is recorded "
    "separately from Playwright automation."
)

# path -> {sha256 of the exact private source line: published replacement line}
SANITIZE = {
    "skills/patstack/references/project-context.md": {
        "a2b23eb4bca9416884e363c0c16176a24991487310d57d973319c970385ececb": GENERIC_PROJECT_PACKS,
        "18803b4b7a3919086e6786f4f29a71541d95757e4e596c66d1ee3d0ac3e0a92a": GENERIC_SYNC,
        "a08073af2f4181ac9a560e81c2c1bf14101f62b90323db862bbb5f5307eda148": GENERIC_BROWSER,
    },
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sanitize(relative, data):
    rules = SANITIZE.get(relative)
    if not rules:
        return data, False
    lines = data.decode("utf-8").split("\n")
    pending = dict(rules)
    matched = set()
    for index, line in enumerate(lines):
        digest = sha(line.encode("utf-8"))
        if digest in matched:
            raise SystemExit(f"{relative}: duplicate sanitization anchor")
        if digest in pending:
            lines[index] = pending.pop(digest)
            matched.add(digest)
    if pending:
        raise SystemExit(
            f"{relative}: {len(pending)} sanitization anchor(s) no longer match the source. "
            "Review the changed private paragraph, then update SANITIZE in this script.")
    return "\n".join(lines).encode("utf-8"), True


def unmapped(source):
    listed = set(FILES)
    extra = []
    for top in MIRRORED:
        root = source / top
        if root.is_symlink() or not root.is_dir():
            raise SystemExit(f"Missing or linked source directory: {top}")
        for path in sorted(root.rglob("*")):
            relative = top + "/" + path.relative_to(root).as_posix()
            if any(relative == private or relative.startswith(private + "/")
                   for private in PRIVATE_RUNTIME_TREES):
                continue
            if EXCLUDED_PARTS & set(path.relative_to(root).parts):
                continue
            if path.is_symlink():
                raise SystemExit(f"Linked source resource is not publishable: {relative}")
            if not path.is_file():
                continue
            if relative not in listed:
                extra.append(relative)
    return extra


def build(source):
    entries = []
    outputs = {}
    for relative in FILES:
        path = source / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"Missing or linked required source file: {relative}")
        original = path.read_bytes()
        published, changed = sanitize(relative, original)
        outputs[relative] = published
        entries.append({"path": relative, "source_sha256": sha(original),
                        "published_sha256": sha(published), "sanitized": changed})
    return entries, outputs


def parity(recorded, entries, outputs, package=None):
    """Compare exact coverage, both hashes, sanitization and actual outputs."""
    package = PACKAGE if package is None else package
    expected = {entry["path"]: entry for entry in entries}
    previous = {entry["path"]: entry for entry in recorded}
    drift = sorted(set(expected) ^ set(previous))
    actual = {path.relative_to(package).as_posix()
              for top in ("skills", "monitoring/patstack")
              for path in (package / top).rglob("*")
              if (path.is_file() or path.is_symlink())
              and not EXCLUDED_PARTS & set(path.relative_to(package).parts)}
    drift.extend(actual ^ set(expected))
    if len(previous) != len(recorded):
        drift.append("<duplicate manifest paths>")
    for relative, entry in expected.items():
        target = package / relative
        if (previous.get(relative) != entry or target.is_symlink()
                or not target.is_file() or target.read_bytes() != outputs[relative]):
            drift.append(relative)
    return sorted(set(drift))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=os.environ.get("PATSTACK_SOURCE", DEFAULT_SOURCE))
    parser.add_argument("--check", action="store_true", help="Compare source with the manifest; write nothing")
    args = parser.parse_args()
    source = Path(os.path.expanduser(args.source)).resolve()
    if not (source / "skills" / SKILLS[0] / "SKILL.md").is_file():
        raise SystemExit(f"No Patstack source at {args.source}")
    extra = unmapped(source)
    if extra:
        raise SystemExit("Unmapped source files (add to FILES or exclude deliberately):\n  " + "\n  ".join(extra))
    entries, outputs = build(source)
    # Validate all transformed bytes before the first publication write.
    from check import privacy_issues
    problems = [issue for relative, data in outputs.items()
                for issue in privacy_issues(relative, data)]
    if problems:
        raise SystemExit("Publication rejected before writing:\n" + "\n".join(problems))
    for relative in outputs:
        target = PACKAGE / relative
        if any(path.is_symlink() for path in (target, *target.parents)
               if path == PACKAGE or PACKAGE in path.parents):
            raise SystemExit(f"Linked publication destination: {relative}")
    manifest_path = PACKAGE / "SOURCE-MANIFEST.json"
    if args.check:
        recorded = json.loads(manifest_path.read_text())["files"] if manifest_path.exists() else []
        drift = parity(recorded, entries, outputs)
        print(json.dumps({"parity_drift": drift, "up_to_date": not drift,
                          "files_checked": len(entries), "skills_checked": len(SKILLS)}, indent=2))
        return 1 if drift else 0
    for relative, data in outputs.items():
        target = PACKAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    label = args.source if args.source.startswith("~") else "<custom --source>"
    manifest = {
        "description": "Published Patstack files and the private source revision they were refreshed from.",
        "source_label": label,
        "workflow_version": "1.1.0",
        "skills": list(SKILLS),
        "excluded_private_runtime_trees": list(PRIVATE_RUNTIME_TREES),
        "refresh_command": "python3 scripts/refresh_from_source.py --source " + label,
        "files": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"refreshed": len(entries), "sanitized": [e["path"] for e in entries if e["sanitized"]]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
