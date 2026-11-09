#!/usr/bin/env python3
"""Regenerate the team repository's resource manifest without copying files.

  python3 scripts/refresh_from_source.py          # record local resource hashes
  python3 scripts/refresh_from_source.py --check  # verify local manifest, no writes

Optional upstream-only comparison (never imports or overwrites team edits):
  python3 scripts/refresh_from_source.py --source PATH --check

The comparison maps the upstream (pre-rename) layout and brand onto DevStack, applies the
exact sanitization anchors for private source trees, and reports per file which resources
differ, which upstream files are unmapped and any privacy findings (redacted). It always
exits 1 while anything differs. Standard library only. Nothing outside this package is written.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PACKAGE = Path(__file__).resolve().parent.parent

WORKFLOW_VERSION = "1.4.0"
PACKAGE_RESOURCE_ROOTS = ("skills", "monitoring/devstack", "tools/ticket-ref")
# Single published source files outside those roots (the setup check lives beside the package tooling).
PACKAGE_RESOURCE_FILES = ("scripts/setup_doctor.py", "scripts/test_setup_doctor.py",
                          "scripts/skill_mirrors.py", "scripts/test_skill_mirrors.py",
                          "scripts/codex_hook_trust.py", "scripts/test_codex_hook_trust.py",
                          "scripts/detach.py", "scripts/test_detach.py",
                          "scripts/ticket_launcher.py", "scripts/test_ticket_launcher.py")

SKILLS = (
    "devstack", "ponytail", "to-spec", "to-tickets", "implement", "review",
    "council", "verify", "full-send", "full-stop", "file-pr", "babysit-pr",
    "takeover", "modernize", "retro", "grilling", "workflow-eval",
    "create-test-recipes", "reverse-engineer-anything",
)

# Directories mirrored from the source. Every regular file inside them must be
# listed in FILES or EXCLUDED, so a new source file cannot be skipped silently.
MIRRORED = tuple("skills/" + name for name in SKILLS) + ("monitoring/devstack", "tools/ticket-ref")
# Only generated interpreter caches may be omitted. Archives, backups and
# unknown resources must cause a coverage error, rather than disappearing.
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
# The monitor installer stores private rollback state here. This exact runtime
# tree is never source material; a backup anywhere inside a skill still fails.
PRIVATE_RUNTIME_TREES = ("monitoring/devstack/backups",)

FILES = (
    *("skills/" + name + "/SKILL.md" for name in SKILLS
      if name not in {"devstack", "create-test-recipes"}),
    "skills/devstack/SKILL.md",
    "skills/devstack/references/access.md",
    "skills/devstack/references/build-review.md",
    "skills/devstack/references/change-sets.md",
    "skills/devstack/references/coordination.md",
    "skills/devstack/references/decisions.md",
    "skills/devstack/references/planning.md",
    "skills/devstack/references/project-context.md",
    "skills/devstack/references/quality.md",
    "skills/devstack/references/retro.md",
    "skills/devstack/references/sources.md",
    "skills/devstack/references/task-state.md",
    "skills/devstack/references/testing-delivery.md",
    "skills/ponytail/LICENSE.txt",
    "skills/ponytail/PROVENANCE.json",
    "skills/implement/references/critical-path.md",
    "skills/grilling/references/approval-scenarios.md",
    "skills/workflow-eval/references/scenarios.md",
    "skills/reverse-engineer-anything/LICENSE",
    "skills/reverse-engineer-anything/PROVENANCE.json",
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
    "monitoring/devstack/README.md",
    "monitoring/devstack/kpi_monitor.py",
    "monitoring/devstack/test_kpi_monitor.py",
    "monitoring/devstack/install.py",
    "monitoring/devstack/task_kpi.py",
    "monitoring/devstack/test_task_kpi.py",
    "scripts/setup_doctor.py",
    "scripts/test_setup_doctor.py",
    "scripts/skill_mirrors.py",
    "scripts/test_skill_mirrors.py",
    "scripts/codex_hook_trust.py",
    "scripts/test_codex_hook_trust.py",
    "scripts/detach.py",
    "scripts/test_detach.py",
    "scripts/ticket_launcher.py",
    "scripts/test_ticket_launcher.py",
    "tools/ticket-ref/README.md",
    "tools/ticket-ref/SLOTS.md",
    "tools/ticket-ref/slots.json",
    "tools/ticket-ref/ticket_ref.py",
    "tools/ticket-ref/test_ticket_ref.py",
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
    "skills/devstack/references/project-context.md": {
        "a2b23eb4bca9416884e363c0c16176a24991487310d57d973319c970385ececb": GENERIC_PROJECT_PACKS,
        "18803b4b7a3919086e6786f4f29a71541d95757e4e596c66d1ee3d0ac3e0a92a": GENERIC_SYNC,
        "a08073af2f4181ac9a560e81c2c1bf14101f62b90323db862bbb5f5307eda148": GENERIC_BROWSER,
    },
}


# Upstream sync map. The upstream tree keeps the names this team copy had before the
# rename; the comparison reads it through this map and never writes it.
UPSTREAM_PATHS = (("skills/patstack/", "skills/devstack/"),
                  ("monitoring/patstack/", "monitoring/devstack/"))
UPSTREAM_WORDS = ((b"PatStack", b"DevStack"), (b"Patstack", b"DevStack"),
                  (b"PATSTACK", b"DEVSTACK"), (b"patstack", b"devstack"))
# SHA-256 of the upstream owner's lowercase first name, compared as "the owner" (this
# repository's wording), so owner-neutral team edits do not show up as differences.
OWNER_NAME_HASHES = {"23ddda4810068cc44360dffd31b6c5a9ad13fb9e6a69c9354a5d1b07f1b9843f"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def legacy_layout(source):
    """True for an upstream tree that still uses the pre-rename paths."""
    old, new = UPSTREAM_PATHS[0]
    return (source / old / "SKILL.md").is_file() and not (source / new / "SKILL.md").is_file()


def source_path(relative, legacy):
    """Location in the source tree of this repository's RELATIVE resource."""
    if legacy:
        for old, new in UPSTREAM_PATHS:
            if (relative + "/").startswith(new):
                return (old + relative[len(new):]).rstrip("/")
    return relative


def owner_neutral(text):
    def replace(match):
        if sha(match.group().lower().encode()) not in OWNER_NAME_HASHES:
            return match.group()
        before = text[:match.start()].split("\n")[-1]
        start = not before.strip(" -*>#|`") or before.rstrip().endswith((".", "!", "?", ":"))
        return "The owner" if start else "the owner"
    return re.sub(r"\b[A-Za-z]+\b", replace, text)


def rebrand(data):
    """Map upstream brand words and owner name onto this repository's wording."""
    for old, new in UPSTREAM_WORDS:
        data = data.replace(old, new)
    try:
        return owner_neutral(data.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return data


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
    legacy = legacy_layout(source)
    for top in MIRRORED:
        root = source / source_path(top, legacy)
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


def build(source, *, upstream=True, findings=None):
    """Hash every resource; with FINDINGS (a dict), record upstream problems instead of stopping."""
    entries = []
    outputs = {}
    legacy = legacy_layout(source) if upstream else False
    for relative in FILES:
        path = source / source_path(relative, legacy)
        if not path.is_file() or path.is_symlink():
            if findings is None:
                raise SystemExit(f"Missing or linked required source file: {relative}")
            findings.setdefault("missing_upstream", []).append(relative)
            continue
        original = path.read_bytes()
        if not upstream:
            published, changed = original, False
        elif findings is None:
            published, changed = sanitize(relative, original)
        else:
            try:
                published, changed = sanitize(relative, original)
            except SystemExit as problem:
                lines = original.decode("utf-8", "replace").split("\n")
                if not all(line in lines for line in SANITIZE.get(relative, {}).values()):
                    findings.setdefault("sanitization", []).append(str(problem))
                published, changed = original, False  # a published upstream copy is already sanitized
        if upstream:
            rebranded = rebrand(published)
            published, changed = rebranded, changed or rebranded != published
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
              for top in PACKAGE_RESOURCE_ROOTS
              for path in (package / top).rglob("*")
              if (path.is_file() or path.is_symlink())
              and not EXCLUDED_PARTS & set(path.relative_to(package).parts)}
    actual |= {name for name in PACKAGE_RESOURCE_FILES if (package / name).exists()}
    drift.extend(actual ^ set(expected))
    if len(previous) != len(recorded):
        drift.append("<duplicate manifest paths>")
    for relative, entry in expected.items():
        target = package / relative
        if (previous.get(relative) != entry or target.is_symlink()
                or not target.is_file() or target.read_bytes() != outputs[relative]):
            drift.append(relative)
    return sorted(set(drift))


def compare_upstream(source):
    """Read-only report of how an upstream tree differs from this repository after mapping."""
    from check import privacy_issues
    findings = {}
    extra = unmapped(source)
    _, outputs = build(source, upstream=True, findings=findings)
    problems = [issue for relative, data in outputs.items() for issue in privacy_issues(relative, data)]
    differs = [relative for relative, data in outputs.items()
               if (PACKAGE / relative).is_symlink() or not (PACKAGE / relative).is_file()
               or (PACKAGE / relative).read_bytes() != data]
    result = {
        "upstream_layout": "pre-rename" if legacy_layout(source) else "current",
        "files_checked": len(FILES),
        "identical": len(outputs) - len(differs),
        "differs": differs,
        "missing_upstream": findings.get("missing_upstream", []),
        "unmapped_upstream_files": extra,
        "sanitization_anchors_unmatched": findings.get("sanitization", []),
        "privacy_findings": problems,
    }
    result["up_to_date"] = not any(result[key] for key in (
        "differs", "missing_upstream", "unmapped_upstream_files",
        "sanitization_anchors_unmatched", "privacy_findings"))
    print(json.dumps(result, indent=2))
    return 0 if result["up_to_date"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", help="Optional upstream tree; requires --check and never writes")
    parser.add_argument("--check", action="store_true", help="Compare local or explicit upstream source with the manifest; write nothing")
    args = parser.parse_args()
    source = Path(args.source).expanduser().resolve() if args.source else PACKAGE.resolve()
    upstream = source != PACKAGE.resolve()
    if upstream and not args.check:
        raise SystemExit("Upstream sources are comparison-only: use --source PATH --check. "
                         "Review and apply selected upstream changes manually.")
    if not (source / source_path("skills/" + SKILLS[0], upstream and legacy_layout(source)) / "SKILL.md").is_file():
        raise SystemExit(f"No DevStack source at {source}")
    if upstream:
        return compare_upstream(source)
    extra = unmapped(source)
    if extra:
        raise SystemExit("Unmapped source files (add to FILES or exclude deliberately):\n  " + "\n  ".join(extra))
    entries, outputs = build(source, upstream=upstream)
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
    if manifest_path.is_symlink():
        raise SystemExit("Linked manifest destination is not allowed")
    if args.check:
        recorded = json.loads(manifest_path.read_text())["files"] if manifest_path.exists() else []
        drift = parity(recorded, entries, outputs)
        print(json.dumps({"parity_drift": drift, "up_to_date": not drift,
                          "files_checked": len(entries), "skills_checked": len(SKILLS)}, indent=2))
        return 1 if drift else 0
    manifest = {
        "description": "Approved resources maintained in this repository; hashes are local repository bytes.",
        "source_label": ".",
        "workflow_version": WORKFLOW_VERSION,
        "skills": list(SKILLS),
        "excluded_private_runtime_trees": list(PRIVATE_RUNTIME_TREES),
        "refresh_command": "python3 scripts/refresh_from_source.py",
        "files": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"manifest_files": len(entries), "resources_written": 0}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
