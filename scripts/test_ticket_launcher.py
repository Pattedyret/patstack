"""ticket_launcher.py tests in temporary folders; never touch the live ~/.local/bin."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("ticket_launcher", Path(__file__).with_name("ticket_launcher.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


@unittest.skipIf(os.name == "nt", "uses POSIX symlinks and an sh launcher")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.target = self.bin / "ticket-ref"

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, apply=True, **kwargs):
        return t.install(self.bin, "sh", sys.executable, apply=apply, path_env=str(self.bin), **kwargs)

    def test_existing_bak_symlink_is_never_followed(self):
        # Probe: ticket-ref.bak already links to an outside file; the old `cp -P L L.bak` wrote through it.
        outside = self.base / "outside.txt"
        outside.write_text("precious\n", encoding="utf-8")
        self.target.write_text("#!/bin/sh\necho old\n", encoding="utf-8")
        os.symlink(str(outside), str(self.bin / "ticket-ref.bak"))
        report = self.install()
        self.assertEqual("precious\n", outside.read_text(encoding="utf-8"))
        self.assertEqual(str(outside), os.readlink(str(self.bin / "ticket-ref.bak")))
        backup = Path(report["backup"])
        self.assertNotEqual(self.bin / "ticket-ref.bak", backup)
        self.assertEqual("#!/bin/sh\necho old\n", backup.read_text(encoding="utf-8"))
        self.assertEqual(t.content("sh", sys.executable, t.SCRIPT), self.target.read_bytes())

    def test_target_symlink_is_replaced_not_followed(self):
        outside = self.base / "shared-launcher"
        outside.write_text("#!/bin/sh\necho shared\n", encoding="utf-8")
        os.symlink(str(outside), str(self.target))
        report = self.install()
        self.assertEqual("#!/bin/sh\necho shared\n", outside.read_text(encoding="utf-8"))
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(str(outside), os.readlink(report["backup"]))

    def test_second_run_is_unchanged_and_makes_no_backup(self):
        self.assertEqual("create", self.install()["result"])
        report = self.install()
        self.assertEqual(("unchanged", None), (report["result"], report["backup"]))
        self.assertEqual(["ticket-ref"], sorted(p.name for p in self.bin.iterdir()))

    def test_dry_run_writes_nothing(self):
        self.target.write_text("old\n", encoding="utf-8")
        report = self.install(apply=False)
        self.assertTrue(report["result"].startswith("replace (dry run"))
        self.assertEqual(["ticket-ref"], sorted(p.name for p in self.bin.iterdir()))
        self.assertEqual("old\n", self.target.read_text(encoding="utf-8"))

    def test_failed_backup_aborts_the_replacement(self):
        self.target.write_text("old\n", encoding="utf-8")
        with mock.patch.object(t, "unique_backup", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual("old\n", self.target.read_text(encoding="utf-8"))
        self.assertEqual(["ticket-ref"], sorted(p.name for p in self.bin.iterdir()))

    def test_backup_names_are_unique(self):
        self.target.write_text("one\n", encoding="utf-8")
        with mock.patch.object(t, "datetime") as clock:
            clock.now.return_value = t.datetime(2026, 1, 1, tzinfo=t.timezone.utc)
            first = self.install()["backup"]
            self.target.write_text("two\n", encoding="utf-8")
            second = self.install()["backup"]
        self.assertNotEqual(first, second)
        self.assertEqual(("one\n", "two\n"), (Path(first).read_text(encoding="utf-8"), Path(second).read_text(encoding="utf-8")))

    def test_launcher_runs_ticket_ref_from_a_quoted_path(self):
        odd = self.base / "dev stack's [1]" / "ticket_ref.py"
        odd.parent.mkdir()
        odd.write_text("import sys\nprint('args', sys.argv[1:])\n", encoding="utf-8")
        t.install(self.bin, "sh", sys.executable, script=odd, apply=True, path_env="")
        out = subprocess.run([str(self.target), "new", "a b"], capture_output=True, text=True, check=True).stdout
        self.assertEqual("args ['new', 'a b']\n", out)
        self.assertTrue(os.access(str(self.target), os.X_OK))

    def test_symlinked_local_bin_is_refused_unless_followed(self):
        home = self.base / "home"
        shared = self.base / "shared-bin"
        shared.mkdir()
        (shared / "ticket-ref").write_text("shared\n", encoding="utf-8")
        (home / ".local").mkdir(parents=True)
        os.symlink(str(shared), str(home / ".local/bin"))
        with self.assertRaises(t.LinkRefused):
            t.install(home / ".local/bin", "sh", sys.executable, apply=True, path_env="", home=home)
        self.assertEqual(["ticket-ref"], [p.name for p in shared.iterdir()])
        self.assertEqual("shared\n", (shared / "ticket-ref").read_text(encoding="utf-8"))
        report = t.install(home / ".local/bin", "sh", sys.executable, apply=True, path_env="", home=home, follow=True)
        self.assertEqual("shared\n", Path(report["backup"]).read_text(encoding="utf-8"))
        self.assertEqual(shared, Path(report["backup"]).parent)
        self.assertEqual(t.content("sh", sys.executable, t.SCRIPT), (shared / "ticket-ref").read_bytes())

    def test_symlinked_folder_above_local_bin_is_refused(self):
        home = self.base / "home"
        home.mkdir()
        shared = self.base / "shared-local"
        (shared / "bin").mkdir(parents=True)
        os.symlink(str(shared), str(home / ".local"))
        with self.assertRaises(t.LinkRefused):
            t.install(home / ".local/bin", "sh", sys.executable, apply=True, path_env="", home=home)
        self.assertEqual([], list((shared / "bin").iterdir()))


class FormatTests(unittest.TestCase):
    def test_windows_cmd_quotes_the_path_and_escapes_percent(self):
        data = t.content("cmd", "python", "D:\\my dev\\100%\\tools\\ticket-ref\\ticket_ref.py").decode()
        self.assertEqual('@echo off\r\n"python" "D:\\my dev\\100%%\\tools\\ticket-ref\\ticket_ref.py" %*\r\n', data)
        with self.assertRaises(ValueError):
            t.content("cmd", "python", 'D:\\a"b\\ticket_ref.py')

    def test_path_advice_only_when_missing(self):
        self.assertIsNone(t.path_advice(Path("/opt/x/bin"), "sh", "/usr/bin:/opt/x/bin"))
        self.assertIn("export PATH=", t.path_advice(Path("/opt/x/bin"), "sh", "/usr/bin"))
        self.assertIsNone(t.path_advice("D:\\Home\\.local\\bin", "cmd", "C:\\Windows;d:\\home\\.local\\bin"))
        self.assertIn("SetEnvironmentVariable", t.path_advice("D:\\Home\\.local\\bin", "cmd", "C:\\Windows"))


if __name__ == "__main__":
    unittest.main()
