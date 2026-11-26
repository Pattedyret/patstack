#!/usr/bin/env python3
"""Offline tests for start_here.py in a throwaway home folder: dry run, apply, idempotence, keeping
what the person already has, backups, and refusing what it must not touch."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_doctor  # noqa: E402
import start_here as s  # noqa: E402


class StartHereTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.rows = s.Rows()
        self.skills = sorted(p.name for p in (s.ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())

    def tearDown(self):
        self.tmp.cleanup()

    def monday_rows(self, cfg=None, token=None, check=None, raw=None):
        absent = False
        env = {"PATSTACK_MONDAY_TOKEN_FILE": str(self.home / "token")}
        if cfg is not None:
            (self.home / "cfg.json").write_text(json.dumps(cfg))
            env["PATSTACK_MONDAY_CONFIG"] = str(self.home / "cfg.json")
        elif raw is not None:
            (self.home / "cfg.json").write_text(raw)
            env["PATSTACK_MONDAY_CONFIG"] = str(self.home / "cfg.json")
        else:
            absent = True
        if token is not None:
            (self.home / "token").write_text(token)
        sys.path.insert(0, str(s.ROOT / "tools"))
        try:
            import monday_ticket
            nothing = mock.patch.object(monday_ticket, "load_config", side_effect=monday_ticket.NoConfig("none"))
            with mock.patch.dict(os.environ, env), mock.patch.object(monday_ticket, "check", side_effect=check):
                if absent:
                    with nothing:
                        s.monday(self.home, True, self.rows)
                else:
                    s.monday(self.home, True, self.rows)
        finally:
            sys.path.pop(0)
        return [(status, detail) for status, step, detail in self.rows.rows if step == "ticket board"]

    MONDAY = {"account": "team", "workspace": 7, "board": 10, "subitems_board": 20, "first_number": 30001,
              "columns": {"ticket": "num", "status": "status", "person": "person"}, "statuses": {}}

    def test_monday_is_skipped_without_a_team_board(self):
        (status, detail), = self.monday_rows()
        self.assertEqual(status, "SKIP")

    @unittest.skipIf(os.name == "nt", "native symlink fixture; run on Linux")
    def test_a_dangling_bundled_config_link_is_a_todo_never_a_skip(self):
        sys.path.insert(0, str(s.ROOT / "tools"))
        import monday_ticket
        sys.path.pop(0)
        pack = self.home / "root/project-packs/team"
        pack.mkdir(parents=True)
        (pack / "monday.json").symlink_to(self.home / "gone.json")
        real = monday_ticket.load_config
        with mock.patch.dict(os.environ, {"PATSTACK_MONDAY_TOKEN_FILE": str(self.home / "token")}), \
                mock.patch.object(Path, "home", return_value=self.home / "nohome"), \
                mock.patch.object(monday_ticket, "load_config", lambda **kw: real(self.home / "root", **kw)):
            os.environ.pop("PATSTACK_MONDAY_CONFIG", None)
            s.monday(self.home, True, self.rows)
        (status, detail), = [(st, d) for st, step, d in self.rows.rows if step == "ticket board"]
        self.assertEqual(status, "TODO")
        self.assertIn("broken", detail)

    def test_a_broken_monday_config_is_a_todo_never_a_skip(self):
        for raw in ("{", "[]", '{"account": "team"}'):
            with self.subTest(raw=raw):
                self.rows = s.Rows()
                (status, detail), = self.monday_rows(raw=raw)
                self.assertEqual(status, "TODO")
                self.assertIn("broken", detail)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX permissions as a normal user")
    def test_an_unreadable_config_folder_is_a_todo_and_the_other_rows_still_print(self):
        folder = self.home / ".config/patstack"
        folder.mkdir(parents=True)
        (self.home / "cfg.json").write_text(json.dumps(self.MONDAY))
        folder.chmod(0)
        try:
            with mock.patch.dict(os.environ, {"PATSTACK_MONDAY_CONFIG": str(self.home / "cfg.json")}):
                os.environ.pop("PATSTACK_MONDAY_TOKEN_FILE", None)
                s.monday(self.home, True, self.rows)                 # the token sits under the unreadable folder
        finally:
            folder.chmod(0o700)
        (status, detail), = [(st, d) for st, step, d in self.rows.rows if step == "ticket board"]
        self.assertEqual(status, "TODO")
        self.assertIn("the stored Monday token cannot be used", detail)
        self.assertIn("PermissionError", detail)
        seen = []
        with mock.patch.object(s, "monday", side_effect=PermissionError("denied")), redirect_stdout(io.StringIO()), \
                mock.patch.object(s.Rows, "print", lambda rows, out=None: seen.extend(rows.rows)):
            self.assertEqual(s.main(["--home", str(self.home), "--clients", "claude"]), 0)
        steps = {step: detail for _, step, detail in seen}
        self.assertIn("the team board step failed (PermissionError)", steps["ticket board"])
        self.assertIn("ticket-ref", steps)                           # the other rows are still there

    @unittest.skipIf(os.name == "nt", "native symlink fixture; run on Linux")
    def test_a_dangling_token_link_is_a_todo_not_a_missing_token(self):
        (self.home / "cfg.json").write_text(json.dumps(self.MONDAY))
        (self.home / "token").symlink_to(self.home / "gone")
        with mock.patch.dict(os.environ, {"PATSTACK_MONDAY_CONFIG": str(self.home / "cfg.json"),
                                          "PATSTACK_MONDAY_TOKEN_FILE": str(self.home / "token")}):
            s.monday(self.home, True, self.rows)
        (status, detail), = [(st, d) for st, step, d in self.rows.rows if step == "ticket board"]
        self.assertEqual(status, "TODO")
        self.assertIn("link to nothing", detail)

    def test_monday_without_a_token_says_exactly_what_the_agent_does(self):
        (status, detail), = self.monday_rows(cfg=self.MONDAY)
        self.assertEqual(status, "TODO")
        for expected in ("https://team.monday.com/apps/manage/tokens", "private secret input", "setup --store"):
            self.assertIn(expected, detail)
        self.assertFalse((self.home / "token").exists())          # start-here never takes or writes the token

    def test_monday_with_a_token_checks_the_board(self):
        (status, detail), = self.monday_rows(cfg=self.MONDAY, token="t.o.k", check=lambda api, cfg: "Monday OK: x")
        self.assertEqual((status, detail), ("OK", "Monday OK: x"))
        sys.path.insert(0, str(s.ROOT / "tools"))
        import monday_ticket
        sys.path.pop(0)
        self.rows = s.Rows()
        (status, detail), = self.monday_rows(cfg=self.MONDAY, token="t.o.k",
                                             check=monday_ticket.MondayError("Monday API answered HTTP 401"))
        self.assertEqual(status, "TODO")
        self.assertIn("HTTP 401", detail)
        self.assertNotIn("t.o.k", detail)

    def statuses(self, step_prefix):
        return [(status, step) for status, step, _ in self.rows.rows if step.startswith(step_prefix)]

    def files(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))

    def test_dry_run_writes_nothing(self):
        s.skills(self.home, False, self.rows, windows=False)
        s.instructions(self.home, False, self.rows)
        s.merge_guard(self.home, False, self.rows, {"claude", "codex"})
        s.ticket_numbers(self.home, False, self.rows)
        self.assertEqual(self.files(), [])
        self.assertTrue(all(status in ("TODO", "SKIP") for status, _, _ in self.rows.rows), self.rows.rows)

    @unittest.skipIf(os.name == "nt", "links are POSIX; Windows uses skill_mirrors.py")
    def test_apply_links_every_skill_and_is_idempotent(self):
        s.skills(self.home, True, self.rows, windows=False)
        for rel in (".claude/skills", ".agents/skills"):
            for name in self.skills:
                link = self.home / rel / name
                self.assertTrue(link.is_symlink())
                self.assertEqual(Path(os.path.realpath(link)), (s.ROOT / "skills" / name).resolve())
        self.assertIn("start-here", self.skills)
        self.rows = s.Rows()
        s.skills(self.home, True, self.rows, windows=False)
        self.assertEqual(self.statuses("skills"), [("OK", "skills claude"), ("OK", "skills codex")])

    @unittest.skipIf(os.name == "nt", "links are POSIX")
    def test_foreign_skill_entries_are_left_alone(self):
        (self.home / ".claude/skills").mkdir(parents=True)
        (self.home / ".claude/skills/review").mkdir()  # someone else's skill with the same name
        s.skills(self.home, True, self.rows, windows=False)
        self.assertFalse((self.home / ".claude/skills/review").is_symlink())
        detail = " ".join(d for _, step, d in self.rows.rows if step == "skills claude")
        self.assertIn("left alone, not this checkout: review", detail)

    def test_instructions_installed_where_absent_and_never_overwritten(self):
        mine = self.home / ".claude/CLAUDE.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("# My own rules\n")
        s.instructions(self.home, True, self.rows)
        self.assertEqual(mine.read_text(), "# My own rules\n")
        installed = (self.home / ".codex/AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(installed.startswith(setup_doctor.TEMPLATE_MARKER))
        self.assertIn(str(s.ROOT), installed)
        self.assertNotIn("<PATSTACK>", installed)
        self.assertEqual(self.statuses("instr"), [("TODO", "instr claude"), ("DONE", "instr codex")])

    def test_a_settings_file_with_a_byte_order_mark_is_read_and_rewritten_without_it(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_bytes(b"\xef\xbb\xbf" + json.dumps({"theme": "dark"}).encode())
        s.merge_guard(self.home, True, self.rows, {"claude"})
        self.assertIn(("DONE", "guard claude"), self.statuses("guard claude"))
        raw = settings.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(json.loads(raw)["theme"], "dark")

    def test_merge_guard_added_keeping_existing_hooks_with_backup(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        mine = {"theme": "dark", "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "mine.sh"}]}],
                                           "Stop": [{"hooks": [{"type": "command", "command": "bye.sh"}]}]}}
        settings.write_text(json.dumps(mine))
        s.merge_guard(self.home, True, self.rows, {"claude", "codex"})
        after = json.loads(settings.read_text())
        self.assertEqual(after["theme"], "dark")
        self.assertEqual(after["hooks"]["Stop"], mine["hooks"]["Stop"])
        self.assertEqual(after["hooks"]["PreToolUse"][0], mine["hooks"]["PreToolUse"][0])
        self.assertTrue(setup_doctor.guard_positions(after))
        backups = list(settings.parent.glob("settings.json.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), mine)
        codex = json.loads((self.home / ".codex/hooks.json").read_text())
        self.assertTrue(setup_doctor.guard_positions(codex))
        # Codex is not trusted yet: the person is told, every time, until Codex records trust.
        self.assertIn(("TODO", "guard codex"), self.statuses("guard codex"))
        self.rows = s.Rows()
        s.merge_guard(self.home, True, self.rows, {"claude", "codex"})
        self.assertEqual(len(list(settings.parent.glob("settings.json.*.bak"))), 1)  # nothing rewritten
        self.assertIn(("TODO", "guard codex"), self.statuses("guard codex"))
        hooks_file = self.home / ".codex/hooks.json"
        (self.home / ".codex/config.toml").write_text(  # an outdated hash does not count as trust
            f'[hooks.state.{json.dumps(str(hooks_file) + ":pre_tool_use:0:0")}]\ntrusted_hash = "sha256:00"\n')
        self.rows = s.Rows()
        s.merge_guard(self.home, True, self.rows, {"codex"})
        self.assertIn(("TODO", "guard codex"), self.statuses("guard codex"))
        group = json.loads(hooks_file.read_text())["hooks"]["PreToolUse"][0]
        current = setup_doctor.codex_hook_hash("pre_tool_use", group["matcher"], group["hooks"][0])
        (self.home / ".codex/config.toml").write_text(
            f'[hooks.state.{json.dumps(str(hooks_file) + ":pre_tool_use:0:0")}]\ntrusted_hash = "{current}"\n')
        self.rows = s.Rows()
        s.merge_guard(self.home, True, self.rows, {"claude", "codex"})
        self.assertEqual(self.statuses("guard codex"), [("OK", "guard codex"), ("OK", "guard codex")])

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_private_settings_and_their_backup_stay_private(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"env": {"PROVIDER_TOKEN": "synthetic"}}))
        settings.chmod(0o600)
        old = os.umask(0o022)
        try:
            s.merge_guard(self.home, True, self.rows, {"claude", "codex"})
        finally:
            os.umask(old)
        self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
        (backup,) = settings.parent.glob("settings.json.*.bak")
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.home / ".codex/hooks.json").stat().st_mode & 0o777, 0o600)  # new: owner-only
        s.instructions(self.home, True, self.rows)
        self.assertEqual((self.home / ".claude/CLAUDE.md").stat().st_mode & 0o777, 0o644)

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_never_writes_through_a_linked_folder(self):
        outside = self.home / "outside"
        outside.mkdir()
        os.symlink(outside, self.home / ".codex")
        os.symlink(outside, self.home / ".agents")
        s.merge_guard(self.home, True, self.rows, {"codex"})
        s.instructions(self.home, True, self.rows)
        s.skills(self.home, True, self.rows, windows=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertIn(("TODO", "guard codex"), self.statuses("guard codex"))
        self.assertIn(("TODO", "instr codex"), self.statuses("instr codex"))
        self.assertIn(("TODO", "skills codex"), self.statuses("skills codex"))
        self.assertTrue((self.home / ".claude/CLAUDE.md").is_file())  # unlinked folders still work

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_linked_skill_folder_that_already_resolves_is_ok(self):
        # A shared overlay: ~/.claude/skills and ~/.agents/skills both link to one folder of per-skill links.
        overlay = self.home / "overlay-skills"
        overlay.mkdir()
        for name in self.skills[:-1]:
            os.symlink(s.ROOT / "skills" / name, overlay / name)
        for rel in (".claude", ".agents"):
            (self.home / rel).mkdir()
            os.symlink(overlay, self.home / rel / "skills")
        s.skills(self.home, True, self.rows, windows=False)
        self.assertEqual(self.statuses("skills"), [("TODO", "skills claude"), ("TODO", "skills codex")])
        self.assertIn(self.skills[-1], " ".join(d for _, _, d in self.rows.rows))
        self.assertFalse((overlay / self.skills[-1]).exists())  # nothing written through the link
        os.symlink(s.ROOT / "skills" / self.skills[-1], overlay / self.skills[-1])
        self.rows = s.Rows()
        s.skills(self.home, True, self.rows, windows=False)
        self.assertEqual(self.statuses("skills"), [("OK", "skills claude"), ("OK", "skills codex")])

    def test_windows_guard_command_is_quoted_for_cmd_and_bash(self):
        from pathlib import PureWindowsPath, PurePosixPath
        cmd = s.guard_command(PureWindowsPath("C:/patstack"), windows=True)
        self.assertEqual(cmd, 'python "C:/patstack/tools/merge_guard.py"')
        self.assertEqual(s.guard_command(PureWindowsPath("D:/Work/dev stack"), windows=True),
                         'python "D:/Work/dev stack/tools/merge_guard.py"')
        for bad in ("C:/%TEMP%/patstack", "C:/Work/$(touch X)/patstack", "C:/Work/`id`/patstack", "C:/a$HOME/b"):
            with self.assertRaises(ValueError, msg=bad):
                s.guard_command(PureWindowsPath(bad), windows=True)
        self.assertEqual(s.guard_command(PurePosixPath("/opt/dev stack"), windows=False), "python3 '/opt/dev stack/tools/merge_guard.py'")

    def test_unreadable_settings_are_never_written(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{not json")
        s.merge_guard(self.home, True, self.rows, {"claude"})
        self.assertEqual(settings.read_text(), "{not json")
        self.assertEqual(self.statuses("guard"), [("TODO", "guard claude")])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_never_writes_through_a_symlink(self):
        target = self.home / "elsewhere.json"
        target.write_text("{}")
        (self.home / ".codex").mkdir()
        os.symlink(target, self.home / ".codex/hooks.json")
        s.merge_guard(self.home, True, self.rows, {"codex"})
        self.assertEqual(target.read_text(), "{}")
        self.assertEqual(self.statuses("guard codex")[0], ("TODO", "guard codex"))
        self.assertEqual(list(self.home.glob(".codex/*.bak")), [])

    def test_tickets_install_only_the_launcher(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            os.environ.pop("PATSTACK_TICKET_DB", None)
            s.ticket_numbers(self.home, True, self.rows)
        self.assertEqual(self.statuses("tickets"), [("SKIP", "tickets")])  # the agent sets up the counter
        self.assertEqual(self.statuses("ticket board"), [])  # the board has its own step (monday), checked live
        self.assertFalse((self.home / ".local/state/patstack/tickets.sqlite3").exists())
        self.assertEqual(self.statuses("ticket-ref"), [("DONE", "ticket-ref")], self.rows.rows)
        launcher = self.home / ".local/bin" / ("ticket-ref.cmd" if os.name == "nt" else "ticket-ref")
        self.assertIn(str(s.ROOT / "tools" / "ticket-ref" / "ticket_ref.py"), launcher.read_text())
        # A launcher for another (moved) checkout is repointed, the old one backed up by ticket_launcher.
        launcher.write_text("#!/bin/sh\nexec python3 /old/patstack/tools/ticket-ref/ticket_ref.py \"$@\"\n")
        self.rows = s.Rows()
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            s.ticket_numbers(self.home, False, self.rows)
            self.assertIn("another checkout", " ".join(d for _, step, d in self.rows.rows if step == "ticket-ref"))
            self.rows = s.Rows()
            s.ticket_numbers(self.home, True, self.rows)
        self.assertEqual(self.statuses("ticket-ref"), [("DONE", "ticket-ref")], self.rows.rows)
        self.assertIn(str(s.ROOT), launcher.read_text())

    def test_main_dry_run_prints_a_summary(self):
        out = io.StringIO()
        with mock.patch.object(s, "packs", lambda home, apply, rows: rows.add("SKIP", "project pack", "test")), \
                redirect_stdout(out):
            self.assertEqual(s.main(["--home", str(self.home)]), 0)
        self.assertIn("DRY-RUN:", out.getvalue())
        self.assertEqual(self.files(), [])


if __name__ == "__main__":
    unittest.main()
