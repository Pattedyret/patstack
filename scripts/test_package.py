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
        # start()/addCleanup(stop) instead of enterContext(), which needs 3.11+.
        patcher = patch.multiple(refresh, FILES=(self.relative,),
                                 MIRRORED=("skills/sample",), SANITIZE={},
                                 SKILLS=("sample",), PACKAGE=self.package)
        patcher.start()
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
        backup = self.source / "monitoring/patstack/backups/fixture/old.md"
        backup.parent.mkdir(parents=True)
        backup.write_text("Private runtime state")
        with patch.object(refresh, "MIRRORED", ("skills/sample", "monitoring/patstack")):
            self.assertEqual(refresh.unmapped(self.source), [])
        self.assertTrue(check.privacy_issues("monitoring/patstack/backups/fixture/old.md",
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

    def test_only_exact_reviewed_animation_bytes_are_publishable(self):
        name = "docs/assets/patstack-workflow.gif"
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
        (self.source / self.relative).write_text("fixture@" + "example.net")
        before = (self.package / self.relative).read_bytes()
        with patch("sys.argv", ["refresh", "--source", str(self.source)]):
            with self.assertRaisesRegex(SystemExit, "before writing"):
                refresh.main()
        self.assertEqual((self.package / self.relative).read_bytes(), before)
        self.assertFalse((self.package / "SOURCE-MANIFEST.json").exists())

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

    def test_broken_links_and_anchors_fail(self):
        doc = self.package / "README.md"
        doc.write_text("[Missing](absent.md)\n[Bad anchor](#absent)\n")
        with patch.multiple(check, ROOT=self.package, failures=[]):
            check.check_links()
            self.assertEqual(len(check.failures), 2)


if __name__ == "__main__":
    unittest.main()
