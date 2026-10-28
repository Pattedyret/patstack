"""skill_mirrors tests in a temporary tree; never touch live client folders."""
import importlib.util
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("skill_mirrors", Path(__file__).with_name("skill_mirrors.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.source = self.base / "src/skills"
        (self.source / "alpha/references").mkdir(parents=True)
        (self.source / "beta").mkdir()
        (self.source / "alpha/SKILL.md").write_text(
            "See [beta](../beta/SKILL.md#use), [ref](references/notes.md), [web](https://example.com/x) and [top](#top).\n"
            "Second line\n", encoding="utf-8")
        (self.source / "alpha/references/notes.md").write_text("Back to [alpha](../SKILL.md)\n", encoding="utf-8")
        (self.source / "alpha/data.json").write_bytes(b'{"k": 1}\n')
        (self.source / "beta/SKILL.md").write_text("Beta\n", encoding="utf-8")
        self.home = self.base / "home"
        for client in m.CLIENT_DIRS:
            (self.home / client).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_transform_rewrites_only_links_that_leave_the_skill(self):
        out = m.transform(self.source / "alpha/SKILL.md", self.source).decode("utf-8")
        beta = (self.source / "beta/SKILL.md").as_posix()
        self.assertIn(f"[beta]({beta}#use)", out)
        self.assertIn("[ref](references/notes.md)", out)
        self.assertIn("[web](https://example.com/x)", out)
        self.assertIn("[top](#top)", out)
        self.assertNotIn("\n", out.replace("\r\n", ""))  # every line ends in CRLF
        nested = m.transform(self.source / "alpha/references/notes.md", self.source).decode("utf-8")
        self.assertIn("[alpha](../SKILL.md)", nested)  # still inside alpha
        self.assertEqual(m.transform(self.source / "alpha/data.json", self.source), b'{"k": 1}\n')

    def test_link_forms_and_code_are_handled(self):
        spaced = self.source / "beta dir"
        spaced.mkdir()
        (spaced / "SKILL.md").write_text("Spaced\n", encoding="utf-8")
        page = self.source / "alpha/forms.md"
        page.write_text("\n".join([
            "[angle](<../beta dir/SKILL.md>) and [titled](../beta/SKILL.md \"Beta\")",
            "[ref]: ../beta/SKILL.md \"Ref title\"",
            "Inline code `[x](../beta/SKILL.md)` stays.",
            "```",
            "[fenced](../beta/SKILL.md)",
            "```",
            "[plain](../beta/SKILL.md)", ""]), encoding="utf-8")
        out = m.transform(page, self.source).decode("utf-8").split("\r\n")
        beta, spaced_path = (self.source / "beta/SKILL.md").as_posix(), (spaced / "SKILL.md").as_posix()
        self.assertEqual(out[0], f'[angle](<{spaced_path}>) and [titled]({beta} "Beta")')
        self.assertEqual(out[1], f'[ref]: {beta} "Ref title"')
        self.assertEqual(out[2], "Inline code `[x](../beta/SKILL.md)` stays.")
        self.assertEqual(out[4], "[fenced](../beta/SKILL.md)")
        self.assertEqual(out[6], f"[plain]({beta})")
        m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual(m.broken_links(self.home / ".claude/skills", self.source), [])  # every mirrored link resolves

    def test_all_commonmark_title_forms_are_rewritten(self):
        page = self.source / "alpha/titles.md"
        page.write_text("[a](../beta/SKILL.md 'Single') [b](../beta/SKILL.md (Paren))\n"
                        "[r]: ../beta/SKILL.md 'Ref'\n", encoding="utf-8")
        beta = (self.source / "beta/SKILL.md").as_posix()
        out = m.transform(page, self.source).decode("utf-8").split("\r\n")
        self.assertEqual(out[0], f"[a]({beta} 'Single') [b]({beta} (Paren))")
        self.assertEqual(out[1], f"[r]: {beta} 'Ref'")
        self.assertEqual(m.unsupported_links(self.source), [])
        m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual(m.broken_links(self.home / ".claude/skills", self.source), [])

    def test_unsupported_link_syntax_is_reported(self):
        (self.source / "beta/SKILL.md").write_text("[x](../alpha/SKILL.md 'unterminated\n[r]: ../alpha/SKILL.md tail words\n",
                                                   encoding="utf-8")
        self.assertEqual(m.unsupported_links(self.source), [("beta/SKILL.md", 1), ("beta/SKILL.md", 2)])
        self.assertEqual(m.main(["--root", str(self.base / "src"), "--home", str(self.home), "--apply"]), 0)
        self.assertEqual(m.main(["--root", str(self.base / "src"), "--home", str(self.home), "--check"]), 1)

    def test_any_syntax_that_leaves_the_skill_is_caught(self):
        # Syntax the grammar does not rewrite: blockquoted reference definition, list item and HTML href.
        docs = self.base / "src/docs"
        docs.mkdir()
        (docs / "guide.md").write_text("Guide\n", encoding="utf-8")
        (self.source / "beta/SKILL.md").write_text(
            "> [Guide][guide]\n>\n> [guide]: ../../docs/guide.md\n"
            "- [item]: ../../docs/guide.md\n"
            '<a href="../../docs/guide.md">guide</a>\n', encoding="utf-8")
        flagged = [line for path, line in m.unsupported_links(self.source) if path == "beta/SKILL.md"]
        self.assertEqual(flagged, [3, 4, 5])
        m.apply(self.source, self.home, self.base / "backup")
        broken = [dest for path, dest in m.broken_links(self.home / ".claude/skills", self.source) if path == "beta/SKILL.md"]
        self.assertEqual(broken, ["../../docs/guide.md"])  # one entry per file and destination
        self.assertEqual(m.main(["--root", str(self.base / "src"), "--home", str(self.home), "--check"]), 1)

    def test_dot_slash_parent_paths_in_link_contexts_are_caught(self):
        docs = self.base / "src/docs"
        docs.mkdir()
        (docs / "guide.md").write_text("Guide\n", encoding="utf-8")
        (self.source / "beta/SKILL.md").write_text("> [guide]: ./../../docs/guide.md\n", encoding="utf-8")
        self.assertEqual([e for e in m.unsupported_links(self.source) if e[0] == "beta/SKILL.md"], [("beta/SKILL.md", 1)])
        m.apply(self.source, self.home, self.base / "backup")
        self.assertIn(("beta/SKILL.md", "./../../docs/guide.md"), m.broken_links(self.home / ".claude/skills", self.source))

    def test_delimited_destinations_with_spaces_are_checked_whole(self):
        docs = self.source / "alpha/docs"
        docs.mkdir()
        (docs / "Usage Guide.md").write_text("Guide\n", encoding="utf-8")
        (self.source / "alpha/references/notes.md").write_text(
            '[guide](<../docs/Usage Guide.md>) and <a href="../docs/Usage Guide.md">guide</a>\n', encoding="utf-8")
        self.assertEqual(m.unsupported_links(self.source), [])  # stays inside alpha
        m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual(m.broken_links(self.home / ".claude/skills", self.source), [])
        (docs / "Usage Guide.md").unlink()
        m.apply(self.source, self.home, self.base / "backup")
        (self.home / ".claude/skills/alpha/docs/Usage Guide.md").unlink()  # now really missing in the mirror
        self.assertIn(("alpha/references/notes.md", "../docs/Usage Guide.md"),
                      m.broken_links(self.home / ".claude/skills", self.source))

    def test_prose_and_code_mentions_of_parent_paths_are_not_flagged(self):
        (self.source / "beta/SKILL.md").write_text(
            "Use `../../monitoring/x.md` in code.\n```\nsee ../../docs/guide.md\n```\n"
            "The repository documentation lives in ../../docs/guide.md.\n"
            "Links stay valid: [alpha](../alpha/SKILL.md)\n", encoding="utf-8")
        self.assertEqual([e for e in m.unsupported_links(self.source) if e[0] == "beta/SKILL.md"], [])
        m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual(m.broken_links(self.home / ".claude/skills", self.source), [])

    def test_writes_never_follow_links_out_of_the_mirror(self):
        outside = self.base / "outside.txt"
        outside.write_text("keep\n", encoding="utf-8")
        (self.home / ".claude/skills/alpha").mkdir()
        os.symlink(outside, self.home / ".claude/skills/alpha/SKILL.md")
        with self.assertRaises(SystemExit):
            m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep\n")
        os.unlink(self.home / ".claude/skills/alpha/SKILL.md")
        shutil.rmtree(self.home / ".claude/skills/alpha/references", ignore_errors=True)  # file order differs per OS
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, self.home / ".claude/skills/alpha/references")
        with self.assertRaises(SystemExit):
            m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_broken_mirror_link_is_reported(self):
        m.apply(self.source, self.home, self.base / "backup")
        mirror = self.home / ".claude/skills/alpha/SKILL.md"
        mirror.write_bytes(mirror.read_bytes() + b"[gone](../nowhere/SKILL.md)\r\n")
        self.assertEqual(m.broken_links(self.home / ".claude/skills", self.source), [("alpha/SKILL.md", "../nowhere/SKILL.md")])

    def test_per_skill_links_are_never_written_through(self):
        os.symlink(self.source / "alpha", self.home / ".claude/skills/alpha")  # linked, not mirrored
        before = (self.source / "alpha/SKILL.md").read_bytes()
        refreshed = m.apply(self.source, self.home, self.base / "backup")
        self.assertEqual((self.source / "alpha/SKILL.md").read_bytes(), before)
        self.assertFalse(any(path.startswith(".claude/skills/alpha/") for path in refreshed))
        self.assertTrue(any(path.startswith(".agents/skills/alpha/") for path in refreshed))

    def test_check_and_apply_refresh_only_what_differs(self):
        claude = self.home / ".claude/skills"
        self.assertEqual(len(m.stale(self.source, claude)), 4)  # all missing
        backup = self.base / "backup"
        first = m.apply(self.source, self.home, backup)
        self.assertEqual(len(first), 8)  # 4 files x 2 clients
        self.assertEqual(m.stale(self.source, claude), [])
        self.assertEqual(m.apply(self.source, self.home, backup), [])  # idempotent
        (self.source / "beta/SKILL.md").write_text("Beta v2\n", encoding="utf-8")
        self.assertEqual(m.stale(self.source, claude), [("beta/SKILL.md", "stale")])
        m.apply(self.source, self.home, backup)
        self.assertEqual((backup / ".claude/skills/beta/SKILL.md").read_bytes(), b"Beta\r\n")  # previous mirror kept

    def test_linked_client_folder_is_not_a_mirror(self):
        os.rmdir(self.home / ".agents/skills")
        os.symlink(self.source, self.home / ".agents/skills")
        refreshed = m.apply(self.source, self.home, self.base / "backup")
        self.assertTrue(all(path.startswith(".claude/") for path in refreshed))
        self.assertFalse((self.source / ".agents").exists())

    def test_cli_check_reports_and_exits_nonzero_when_stale(self):
        root = self.base / "src"
        self.assertEqual(m.main(["--root", str(root), "--home", str(self.home), "--check"]), 1)
        self.assertEqual(m.main(["--root", str(root), "--home", str(self.home), "--apply"]), 0)
        self.assertEqual(m.main(["--root", str(root), "--home", str(self.home), "--check"]), 0)


if __name__ == "__main__":
    unittest.main()
