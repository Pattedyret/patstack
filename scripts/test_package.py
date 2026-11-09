"""Adversarial checks for publication coverage, privacy and source parity."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check
import refresh_from_source as refresh

# Generic stand-ins for the hashed private guards; the real terms are asserted
# only in the private export tests, so the public package never spells them.
FIXTURE_GUARDS = {
    "PERSONAL_NAME_HASHES": {refresh.sha(b"quillon")},
    "PERSONAL_NAME_LENGTHS": (7,),
    "PRIVATE_PATH_HASHES": {refresh.sha(b"~/fixture-src/"), refresh.sha(b".fixture-setup")},
}

ROOT_DIR = check.ROOT


class PublicationControls(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "source"
        self.package = self.root / "package"
        self.relative = "skills/sample/SKILL.md"
        for root in (self.source, self.package):
            target = root / self.relative
            target.parent.mkdir(parents=True)
            target.write_text("Reviewed public workflow\n")
        patcher = patch.multiple(refresh, FILES=(self.relative,), MIRRORED=("skills/sample",),
                                 SANITIZE={}, SKILLS=("sample",), PACKAGE=self.package)
        patcher.start()  # not TestCase.enterContext: that needs Python 3.11, the Mac has 3.9
        self.addCleanup(patcher.stop)

    def test_verbatim_and_published_parity(self):
        entries, outputs = refresh.build(self.source)
        self.assertEqual(entries[0]["source_sha256"], entries[0]["published_sha256"])
        self.assertEqual(refresh.parity(entries, entries, outputs), [])
        (self.package / self.relative).write_text("Changed publication\n")
        self.assertEqual(refresh.parity(entries, entries, outputs), [self.relative])

    def test_changed_source_is_detected(self):
        recorded, _ = refresh.build(self.source)
        (self.source / self.relative).write_text("New source\n")
        entries, outputs = refresh.build(self.source)
        self.assertIn(self.relative, refresh.parity(recorded, entries, outputs))

    def test_missing_extra_duplicate_manifest_entries(self):
        entries, outputs = refresh.build(self.source)
        self.assertTrue(refresh.parity([], entries, outputs))
        extra = dict(entries[0], path="skills/sample/extra.md")
        self.assertIn(extra["path"], refresh.parity(entries + [extra], entries, outputs))
        self.assertIn("<duplicate manifest paths>", refresh.parity(entries * 2, entries, outputs))

    def test_new_resource_is_not_silently_omitted(self):
        (self.source / "skills/sample/new.md").write_text("New resource")
        self.assertEqual(refresh.unmapped(self.source), ["skills/sample/new.md"])

    def test_backup_is_not_silently_omitted(self):
        backup = self.source / "skills/sample/backups/old.md"
        backup.parent.mkdir()
        backup.write_text("Old resource")
        self.assertEqual(refresh.unmapped(self.source), ["skills/sample/backups/old.md"])

    def test_only_exact_monitor_runtime_backup_tree_is_excluded(self):
        backup = self.source / "monitoring/devstack/backups/fixture/old.md"
        backup.parent.mkdir(parents=True)
        backup.write_text("Private runtime state")
        with patch.object(refresh, "MIRRORED", ("skills/sample", "monitoring/devstack")):
            self.assertEqual(refresh.unmapped(self.source), [])
        self.assertTrue(check.privacy_issues("monitoring/devstack/backups/fixture/old.md",
                                             backup.read_bytes()))

    def test_missing_skill_directory_is_rejected(self):
        with patch.object(refresh, "MIRRORED", ("skills/absent",)):
            with self.assertRaisesRegex(SystemExit, "Missing or linked"):
                refresh.unmapped(self.source)

    def test_linked_source_is_rejected(self):
        link = self.source / "skills/sample/link.md"
        link.symlink_to(self.source / self.relative)
        with self.assertRaisesRegex(SystemExit, "Linked source"):
            refresh.unmapped(self.source)

    def test_sanitization_requires_exact_anchors(self):
        original = b"Private paragraph\n"
        rules = {refresh.sha(b"Private paragraph"): "Generic paragraph"}
        with patch.object(refresh, "SANITIZE", {self.relative: rules}):
            published, changed = refresh.sanitize(self.relative, original)
            self.assertTrue(changed)
            self.assertEqual(published, b"Generic paragraph\n")
            with self.assertRaisesRegex(SystemExit, "anchor"):
                refresh.sanitize(self.relative, b"Changed paragraph\n")
            with self.assertRaisesRegex(SystemExit, "duplicate"):
                refresh.sanitize(self.relative, original * 2)

    def test_extra_published_resource_fails_source_parity(self):
        entries, outputs = refresh.build(self.source)
        (self.package / "skills/sample/extra.md").write_text("Unexpected")
        self.assertIn("skills/sample/extra.md", refresh.parity(entries, entries, outputs))

    def test_extra_numbering_resource_fails_source_and_package_coverage(self):
        relative = "tools/ticket-ref/README.md"
        for root in (self.source, self.package):
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_text("Numbering contract")
        listed = (self.relative, relative)
        with patch.multiple(refresh, FILES=listed,
                            MIRRORED=("skills/sample", "tools/ticket-ref")):
            entries, outputs = refresh.build(self.source)
            (self.source / "tools/ticket-ref/extra.py").write_text("unexpected")
            self.assertEqual(refresh.unmapped(self.source), ["tools/ticket-ref/extra.py"])
            (self.package / "tools/ticket-ref/extra.py").write_text("unexpected")
            self.assertIn("tools/ticket-ref/extra.py", refresh.parity(entries, entries, outputs))

    def test_privacy_patterns_with_redacted_diagnostics(self):
        values = ["/Users/" + "fixture/private", "C:" + "\\Users\\fixture",
                  "fixture@" + "example.net", "100." + "110.120.130",
                  "ghp_" + "a" * 24, "node." + "ts.net",
                  "t-" + "0" * 12, "12345678-" + "1234-1234-1234-123456789abc",
                  "1B4E28BA-" + "2FA1-11D2-883F-0016D3CCA427",
                  "session_12345678-" + "1234-1234-1234-123456789ABC",
                  "x12345678-" + "1234-1234-1234-123456789ABCsuffix"]
        for value in values:
            with self.subTest(category=value[:3]):
                issues = check.privacy_issues("fixture.md", value.encode())
                self.assertTrue(issues)
                self.assertNotIn(value, "\n".join(issues))

    def test_home_paths_any_case_but_not_api_routes(self):
        for value in ("/users/" + "x/", "/USERS/" + "x/", "cd /Users/" + "x", "path=/Users/" + "x", "file://" + "/Users/" + "x",
                      "`/Users/" + "x`", "'/users/" + "x/repo'", "/home/" + "fixture/", "C:" + "\\users\\x"):
            with self.subTest(value=value):
                self.assertTrue(check.privacy_issues("docs/fixture.md", value.encode()))
        for value in ("GET /api/users/me", "https://api.example.invalid/v1/Users/list", "/teams/7/users/42",
                      "`/users/me` returns 403", 'proxyTarget("/users/me", BASE)'):
            with self.subTest(value=value):
                self.assertEqual(check.privacy_issues("docs/fixture.md", value.encode()), [])

    def test_private_setup_paths_and_reserved_fixture_emails(self):
        with patch.multiple(check, **FIXTURE_GUARDS):
            for value in ("~/.fixture-setup/agent-setup", "~/fixture-src/private-repo", "cd ~/.FIXTURE-SETUP"):
                with self.subTest(value=value):
                    self.assertTrue(check.privacy_issues("docs/fixture.md", value.encode()))
            for value in ("~/src/example-app/", "~/.config/devstack/", "fixture-src", "some.fixture-setupx"):
                with self.subTest(value=value):
                    self.assertEqual(check.privacy_issues("docs/fixture.md", value.encode()), [])
        for value in ("bench@" + "example.invalid", "kunde@" + "shop.invalid."):
            self.assertEqual(check.privacy_issues("bench/fixture.py", value.encode()), [])
        for value in ("a@" + "b.invalid.com", "someone@" + "example.no."):
            self.assertTrue(check.privacy_issues("bench/fixture.py", value.encode()))

    def test_only_exact_reviewed_animation_bytes_are_publishable(self):
        name = "docs/assets/devstack-workflow.gif"
        data = (check.ROOT / name).read_bytes()
        self.assertEqual(check.privacy_issues(name, data), [])
        self.assertTrue(check.privacy_issues(name, data + b"changed"))
        self.assertTrue(check.privacy_issues("docs/assets/unreviewed.gif", data))
        changed = b"BADHDR" + data[6:]
        expected = dict(check.BINARY_ASSETS[name], sha256=refresh.sha(changed))
        with patch.object(check, "BINARY_ASSETS", {name: expected}):
            self.assertTrue(check.privacy_issues(name, changed))

    def test_private_names_and_local_denylist(self):
        with patch.object(check, "PRIVATE_WORD_HASHES", {refresh.sha(b"privatefixture")}):
            self.assertTrue(check.privacy_issues("fixture.md", b"privatefixture"))
        denylist = self.root / "denylist.txt"
        denylist.write_text("private-phrase")
        with patch.object(check, "LOCAL_DENYLIST", denylist):
            self.assertTrue(check.privacy_issues("fixture.md", b"private-phrase"))

    def test_forbidden_unknown_and_unreadable_resources(self):
        for name, content in [("state.db", b""), ("backups/old.md", b""),
                              ("unknown.bin", b""), ("invalid.md", bytes([255]))]:
            self.assertTrue(check.privacy_issues(name, content))

    def test_refresh_privacy_failure_writes_nothing(self):
        (self.package / self.relative).write_text("fixture@" + "example.net")
        before = (self.package / self.relative).read_bytes()
        with patch("sys.argv", ["refresh"]):
            with self.assertRaisesRegex(SystemExit, "before writing"):
                refresh.main()
        self.assertEqual((self.package / self.relative).read_bytes(), before)
        self.assertFalse((self.package / "SOURCE-MANIFEST.json").exists())

    def test_upstream_privacy_finding_is_reported_redacted_and_writes_nothing(self):
        value = "fixture@" + "example.net"
        (self.source / self.relative).write_text(value)
        before = (self.package / self.relative).read_bytes()
        out = io.StringIO()
        with patch("sys.argv", ["refresh", "--source", str(self.source), "--check"]), contextlib.redirect_stdout(out):
            self.assertEqual(refresh.main(), 1)
        report = json.loads(out.getvalue())
        self.assertTrue(report["privacy_findings"])
        self.assertNotIn(value, out.getvalue())
        self.assertEqual((self.package / self.relative).read_bytes(), before)
        self.assertFalse((self.package / "SOURCE-MANIFEST.json").exists())

    def test_pre_rename_upstream_layout_brand_and_owner_are_mapped(self):
        local = "skills/devstack/SKILL.md"
        (self.package / local).parent.mkdir(parents=True)
        (self.package / local).write_text("# DevStack\nThe owner decides; ask the owner. See monitoring/devstack.\n")
        (self.source / "skills/patstack").mkdir(parents=True)
        owner = "Quillon"
        upstream = f"# Patstack\n{owner} decides; ask {owner}. See monitoring/patstack.\n"
        (self.source / "skills/patstack/SKILL.md").write_text(upstream)
        with patch.multiple(refresh, FILES=(local,), MIRRORED=("skills/devstack",), SKILLS=("devstack",),
                            OWNER_NAME_HASHES={refresh.sha(b"quillon")}):
            self.assertTrue(refresh.legacy_layout(self.source))
            out = io.StringIO()
            with patch("sys.argv", ["refresh", "--source", str(self.source), "--check"]), contextlib.redirect_stdout(out):
                self.assertEqual(refresh.main(), 0, out.getvalue())
            report = json.loads(out.getvalue())
            self.assertEqual((report["upstream_layout"], report["identical"]), ("pre-rename", 1))
            (self.source / "skills/patstack/SKILL.md").write_text(upstream + "Upstream change\n")
            (self.source / "skills/patstack/new.md").write_text("New upstream file\n")
            with patch("sys.argv", ["refresh", "--source", str(self.source), "--check"]), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(refresh.main(), 1)
            report = json.loads(out.getvalue())
            self.assertEqual(report["differs"], [local])
            self.assertEqual(report["unmapped_upstream_files"], ["skills/devstack/new.md"])

    def test_check_mode_checks_actual_published_bytes(self):
        entries, _ = refresh.build(self.source)
        (self.package / "SOURCE-MANIFEST.json").write_text(json.dumps({"files": entries}))
        (self.package / self.relative).write_text("Tampered public output")
        with patch("sys.argv", ["refresh", "--source", str(self.source), "--check"]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(refresh.main(), 1)

    def test_package_extra_file_and_missing_skill_fail(self):
        entries, _ = refresh.build(self.source)
        manifest = {"files": entries, "skills": ["sample"], "workflow_version": refresh.WORKFLOW_VERSION}
        (self.package / "SOURCE-MANIFEST.json").write_text(json.dumps(manifest))
        (self.package / "skills/sample/extra.md").write_text("Unexpected resource")
        with patch.multiple(check, ROOT=self.package, FILES=(self.relative,),
                            SKILLS=("sample", "missing"), failures=[]):
            check.check_manifest()
            check.check_skills()
            self.assertTrue(any("coverage differs" in message for message in check.failures))
            self.assertTrue(any("missing actual entrypoint" in message for message in check.failures))

    def test_shipped_private_guards_stay_in_place(self):
        # Hashes only: the guarded names and paths are asserted in plain form by the private export tests.
        self.assertLessEqual({'97683eaa94b4560d33e3daa6ff734885474fc5a508b5026784b22a7a0e439afc', '44edd410d3cc163201f7bbc09cc6210e52543f1fb413338ac65533293eff16d9', '23ddda4810068cc44360dffd31b6c5a9ad13fb9e6a69c9354a5d1b07f1b9843f'}, check.PERSONAL_NAME_HASHES)
        self.assertLessEqual({'7ad5f749dbf71e52e6ee8da9a48239e3c9a40dc3ae544737e335caf1986d9143', '73550989116704f5ce33d5d1f05ef9a2d6b003e09769edbe8f9ccc0ad54236c9'}, check.PRIVATE_PATH_HASHES)
        self.assertIn('3318a69ad31e3f18ec2ccea4041e8d59fe52ea6b1147a9c3f000d35174d53f8b', check.PRIVATE_WORD_HASHES)

    def test_personal_names_only_allowed_in_exact_credit_lines(self):
        guards = patch.multiple(check, **FIXTURE_GUARDS)
        guards.start()
        self.addCleanup(guards.stop)
        for name in ("Quillon", "github.com/Quillonaccount", "@quillon99"):
            for path in ("skills/sample/SKILL.md", "README.md", "NOTICE.md", "scripts/check.py"):
                with self.subTest(path=path, name=name):
                    self.assertTrue(check.privacy_issues(path, name.upper().encode()))
        self.assertEqual(check.privacy_issues("README.md", b"Quill on a quilt"), [])
        credit = "Original author credit: Quillon"
        with patch.object(check, "CREDIT_LINES", {"NOTICE.md": {refresh.sha(credit.encode())}}):
            self.assertEqual(check.privacy_issues("NOTICE.md", credit.encode()), [])
            self.assertTrue(check.privacy_issues("README.md", credit.encode()))
            self.assertTrue(check.privacy_issues("NOTICE.md", (credit + " extra instruction").encode()))

    def test_bundled_pack_is_the_only_published_pack_and_keeps_the_full_scan(self):
        words = b"privatefixture"
        policy = {"project-packs/sample/": {"word_hashes": [refresh.sha(words)],
                                           "brand_pattern": r"(?!)", "allow_lines": {}}}
        patcher = patch.object(check, "pack_policies", return_value=policy)
        patcher.start()
        self.addCleanup(patcher.stop)
        private = patch.object(check, "PRIVATE_WORD_HASHES", check.PRIVATE_WORD_HASHES | {refresh.sha(words), refresh.sha(b"otherclientfx")})
        private.start()
        self.addCleanup(private.stop)
        self.assertEqual(check.privacy_issues("project-packs/sample/skills/x/SKILL.md", words), [])
        self.assertEqual(check.privacy_issues("project-packs/sample/skills/x/proxy.ts", words), [])
        self.assertTrue(check.privacy_issues("README.md", words))
        self.assertTrue(check.privacy_issues("scripts/proxy.ts", b"code"))
        self.assertTrue(check.privacy_issues("project-packs/other/INDEX.md", b"Router"))
        self.assertTrue(check.privacy_issues("project-packs/sample/skills/x/.DS_Store", b""))
        guards = patch.multiple(check, **FIXTURE_GUARDS)
        guards.start()
        self.addCleanup(guards.stop)
        for value in ("Quillon", "someone@" + "example.no", "/Users/" + "fixture/repo",
                      "~/.fixture-setup/x", "ghp_" + "a" * 24, "otherclientfx project"):
            with self.subTest(value=value[:4]):
                self.assertTrue(check.privacy_issues("project-packs/sample/INDEX.md", value.encode()))
        self.assertTrue(check.privacy_issues("docs/fixture.md", ("100." + "64.1.1").encode()))
        for value in ("GET /api/users/me", 'app.listen(PORT, "0.0.0.0")', "TEST-NET " + "192.0.2.1", "see examples/project-pack/README.md"):
            self.assertEqual(check.privacy_issues("docs/fixture.md", value.encode()), [])

    def test_tracked_cache_files_are_scanned_and_rejected(self):
        import subprocess
        repo = self.package
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        cache = repo / "scripts/__pycache__/leak.cpython-39.pyc"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"fixture@" + b"example.net")
        subprocess.run(["git", "-C", str(repo), "add", "-f", "scripts/__pycache__/leak.cpython-39.pyc"], check=True)
        with patch.multiple(check, ROOT=repo, failures=[]):
            self.assertIn(cache, list(check.files()))
            check.check_tracked_caches()
            check.check_privacy()
            self.assertTrue(any("tracked cache file scripts/__pycache__/leak" in m for m in check.failures))
            self.assertTrue(any("leak.cpython-39.pyc" in m and "tracked" not in m for m in check.failures))

    def test_exemptions_cover_exact_lines_only(self):
        stub = next(line for line in (check.ROOT / "bench/bench.py").read_text().splitlines() if "print('TKT-" in line)
        self.assertEqual(check.privacy_issues("bench/bench.py", stub.encode()), [])
        self.assertTrue(check.privacy_issues("bench/bench.py", b"see TKT-" + b"90001 here"))
        self.assertTrue(check.privacy_issues("bench/other.py", stub.encode()))
        self.assertTrue(check.privacy_issues("bench/bench.py", (stub + "\n/home/" + "fixture/x").encode()))

    def test_optional_unlicensed_skill_provenance_follows_the_exact_catalog(self):
        with patch.multiple(check, ROOT=self.package, SKILLS=("reverse-engineer-anything",), failures=[]):
            check.check_provenance()
            self.assertTrue(any("all nine" in finding for finding in check.failures))
        with patch.multiple(check, ROOT=self.package, SKILLS=("sample",), failures=[]):
            check.check_provenance()
            self.assertFalse(any("all nine" in finding for finding in check.failures))

    def test_missing_node_fails_or_is_incomplete_never_ok(self):
        # An isolated security-test fixture exercises both outcomes even in a core-only tree.
        pack = self.package / "project-packs/sample"
        pack.mkdir(parents=True)
        (pack / "proxy.test.mjs").write_text("// security fixture")
        with patch.multiple(check, ROOT=self.package), patch.object(check, "pack_policies", return_value={"project-packs/sample/": {}}), patch.object(check.shutil, "which", return_value=None):
            with patch.multiple(check, failures=[], incomplete=[]):
                check.ALLOW_MISSING_NODE = False
                check.check_pack_tests()
                self.assertTrue(any("node is not installed" in m and "--allow-missing-node" in m for m in check.failures))
            with patch.multiple(check, failures=[], incomplete=[]):
                check.ALLOW_MISSING_NODE = True
                try:
                    check.check_pack_tests()
                    self.assertEqual(check.failures, [])
                    self.assertTrue(check.incomplete)
                finally:
                    check.ALLOW_MISSING_NODE = False

    def test_team_brand_exception_keeps_private_name_scan(self):
        brand = b"privatefixture"
        policy = {"project-packs/sample/": {"brand_pattern": r"privatefixture(?= team\b)"}}
        with patch.object(check, "pack_policies", return_value=policy), patch.object(check, "PRIVATE_WORD_HASHES", {refresh.sha(brand)}):
            self.assertEqual(check.privacy_issues("README.md", brand + b" team copy"), [])
            self.assertTrue(check.privacy_issues("README.md", brand + b" private account"))
            self.assertTrue(check.privacy_issues("README.md", brand + b" team copy; " + brand))

    def test_default_refresh_uses_local_repo_and_never_overwrites_resources(self):
        # Local team text need not match upstream sanitization anchors.
        with patch.object(refresh, "SANITIZE", {self.relative: {"stale": "replacement"}}):
            with patch.dict("os.environ", {"DEVSTACK_SOURCE": str(self.source)}):
                with patch("sys.argv", ["refresh"]), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(refresh.main(), 0)
        manifest_path = self.package / "SOURCE-MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["source_label"], ".")
        entry = manifest["files"][0]
        self.assertEqual(entry["source_sha256"], refresh.sha((self.package / self.relative).read_bytes()))
        self.assertEqual(entry["source_sha256"], entry["published_sha256"])
        self.assertFalse(entry["sanitized"])
        before = manifest_path.read_bytes()
        with patch("sys.argv", ["refresh", "--check"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refresh.main(), 0)
        self.assertEqual(manifest_path.read_bytes(), before)
        (self.package / self.relative).write_text("Team edit\n")
        with patch("sys.argv", ["refresh", "--check"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refresh.main(), 1)
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_upstream_write_is_rejected_without_changing_team_files(self):
        (self.source / self.relative).write_text("Upstream replacement\n")
        before = (self.package / self.relative).read_bytes()
        with patch("sys.argv", ["refresh", "--source", str(self.source)]):
            with self.assertRaisesRegex(SystemExit, "comparison-only"):
                refresh.main()
        self.assertEqual((self.package / self.relative).read_bytes(), before)
        self.assertFalse((self.package / "SOURCE-MANIFEST.json").exists())

    def test_linked_manifest_is_rejected_without_writing_target(self):
        outside = self.root / "protected-manifest.json"
        outside.write_text("Protected data\n")
        (self.package / "SOURCE-MANIFEST.json").symlink_to(outside)
        with patch("sys.argv", ["refresh"]):
            with self.assertRaisesRegex(SystemExit, "Linked manifest"):
                refresh.main()
        self.assertEqual(outside.read_text(), "Protected data\n")

    def test_broken_links_and_anchors_fail(self):
        doc = self.package / "README.md"
        doc.write_text("[Missing](absent.md)\n[Bad anchor](#absent)\n")
        with patch.multiple(check, ROOT=self.package, failures=[]):
            check.check_links()
            self.assertEqual(len(check.failures), 2)




class CiTemplateControls(unittest.TestCase):
    TEMPLATE = (ROOT_DIR / "examples/ci/node.yml").read_text(encoding="utf-8")

    def test_templates_parse_and_pass(self):
        for name in ("node.yml", "python.yml"):
            data = check.parse_yaml((ROOT_DIR / "examples/ci" / name).read_text(encoding="utf-8"))
            self.assertEqual(check.ci_template_issues(data), [], name)
            self.assertEqual(data["permissions"], {"contents": "read"})
            self.assertIn("npm ci" if name == "node.yml" else "uv sync --frozen", json.dumps(data))

    def test_malformed_yaml_is_rejected(self):
        for text in ("a: 1\n\tb: 2\n", "a: 1\na: 2\n", "a:\n  - x\n   y: 1\n", "a: b: c\n",
                     "a: [1, [2]]\n", "a: {b: 1}\n", "  a: 1\n", "a: 'open\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check.parse_yaml(text)

    def test_wide_permissions_and_unpinned_actions_are_rejected(self):
        for old, new, needle in (("  contents: read", "  contents: write", "permissions"),
                                 ("actions/setup-node@v5", "actions/setup-node@main", "not pinned"),
                                 ("actions/setup-node@v5", "someone/action@1a2b3c", "not pinned"),
                                 ("      - uses: actions/checkout@v5\n        with:\n          persist-credentials: false\n", "", "checkout")):
            with self.subTest(new=new):
                self.assertIn(old, self.TEMPLATE)
                issues = check.ci_template_issues(check.parse_yaml(self.TEMPLATE.replace(old, new, 1)))
                self.assertTrue(any(needle in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
