#!/usr/bin/env python3
"""Offline tests for preferences.py: model discovery from fixture catalogs, the proposal, validation, saving
and notify.json. No client, network or model is called."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preferences as p  # noqa: E402
import setup_doctor  # noqa: E402

CLAUDE_CATALOG = {"version": 2, "catalog": {"surface": "cc", "config": {"id": "cc", "models": [
    {"id": "claude-opus-5-5", "name": "Opus 5.5", "section": "main",
     "runtime": {"family": "opus", "effort_levels": ["low", "medium", "high", "xhigh", "max"]}},
    {"id": "claude-fable-5-2", "name": "Fable 5.2", "section": "main", "runtime": {"family": "fable"}},
    {"id": "claude-opus-4-8", "name": "Opus 4.8", "section": "overflow", "runtime": {"family": "opus"}},
]}}}
CODEX_CATALOG = {"models": [
    {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1-Sol", "visibility": "list",
     "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}, {"effort": "ultra"}]},
    {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list"},
    {"slug": "gpt-reserve", "display_name": "GPT-Reserve", "visibility": "hide"},
]}


def codex_run(catalog=CODEX_CATALOG, code=0):
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, code, stdout=json.dumps(catalog) if code == 0 else "", stderr="")
    return run


class PreferencesTests(unittest.TestCase):
    def test_load_missing_preferences_is_quiet_but_a_directory_is_an_error(self):
        self.assertIsNone(p.load(self.home))
        path = self.home / ".config/patstack/preferences.json"
        path.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "regular file"):
            p.load(self.home)

    @unittest.skipIf(os.name == "nt", "POSIX FIFOs and symlinks")
    def test_load_dangling_links_and_fifos_fails_without_blocking(self):
        path = self.home / ".config/patstack/preferences.json"
        path.parent.mkdir(parents=True)
        path.symlink_to(self.home / "missing")
        with self.assertRaisesRegex(ValueError, "dangling link"):
            p.load(self.home)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "regular file"):
            p.load(self.home)
        out = io.StringIO()
        self.assertEqual(p.main(["show"], home=self.home, out=out), 1)
        self.assertIn("unreadable", out.getvalue())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in ("PATSTACK_PREFERENCES", "PATSTACK_NOTIFY", "CODEX_HOME"):
            os.environ.pop(key, None)
        cache = self.home / ".claude/cache/model-catalog"
        cache.mkdir(parents=True)
        (cache / "x-cc.json").write_text(json.dumps(CLAUDE_CATALOG))

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def models(self, run=None):
        return p.discover(self.home, run or codex_run())

    def test_discovery_lists_current_models_of_both_clients(self):
        refs = [p.ref(m) for m in self.models()]
        self.assertEqual(refs, ["claude:claude-opus-5-5", "claude:claude-fable-5-2", "codex:gpt-6.1-sol",
                                "codex:gpt-6-astra"])  # overflow and hidden models are left out
        sol = next(m for m in self.models() if m["id"] == "gpt-6.1-sol")
        self.assertEqual((sol["family"], sol["efforts"]), ("sol", ["low", "high"]))

    def test_claude_without_a_catalog_offers_its_aliases(self):
        for path in (self.home / ".claude/cache/model-catalog").glob("*.json"):
            path.unlink()
        models = p.discover(self.home, codex_run(), which=lambda name: "/usr/bin/claude" if name == "claude" else None)
        self.assertEqual([p.ref(m) for m in models if m["provider"] == "claude"],
                         ["claude:opus", "claude:fable", "claude:sonnet", "claude:haiku"])
        prefs = p.propose(models)
        self.assertEqual(prefs["models"]["ranking"]["lead"][0], "claude:opus")
        self.assertEqual(prefs["models"]["reviewPair"], ["claude:opus", "codex:gpt-6.1-sol"])
        self.assertEqual(p.problems(prefs, models), [])
        self.assertEqual(p.discover(self.home, codex_run(), which=lambda name: None)[0]["provider"], "codex")

    def test_codex_cache_file_is_the_fallback(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex/models_cache.json").write_text(json.dumps(CODEX_CATALOG))
        self.assertIn("codex:gpt-6-astra", [p.ref(m) for m in self.models(codex_run(code=1))])

    def test_proposal_follows_the_team_defaults_and_is_valid(self):
        models = self.models()
        prefs = p.propose(models)
        ranking = prefs["models"]["ranking"]
        self.assertEqual(ranking["lead"][0], "claude:claude-opus-5-5")
        self.assertEqual(ranking["implementation"][0], "codex:gpt-6.1-sol")
        self.assertEqual(ranking["ui"][0], "codex:gpt-6-astra")
        self.assertEqual(sorted(ranking["design"]), sorted(p.ref(m) for m in models))  # every model ranked
        self.assertEqual(prefs["models"]["reviewPair"], ["claude:claude-opus-5-5", "codex:gpt-6.1-sol"])
        self.assertEqual(p.problems(prefs, models), [])

    def test_one_provider_gets_one_review_model(self):
        models = [m for m in self.models() if m["provider"] == "claude"]
        prefs = p.propose(models)
        self.assertEqual(len(prefs["models"]["reviewPair"]), 1)
        self.assertEqual(p.problems(prefs, models), [])

    def test_bad_answers_are_named(self):
        models = self.models()
        good = p.propose(models)
        cases = {
            "language": dict(good, language="English"),
            "involvement": dict(good, involvement="sometimes"),
            "above the ceiling": dict(good, effort={"default": "max", "ceiling": "high"}),
            "not offered on this machine": json.loads(json.dumps(good).replace("gpt-6-astra", "gpt-9-nova")),
            "two different providers": dict(good, models={"ranking": good["models"]["ranking"],
                                                          "reviewPair": ["claude:claude-opus-5-5",
                                                                         "claude:claude-fable-5-2"]}),
            "one model although two providers": dict(good, models={"ranking": good["models"]["ranking"],
                                                                   "reviewPair": ["codex:gpt-6.1-sol"]}),
            "unknown key": dict(good, owner="me"),
            "lists a model twice": json.loads(json.dumps(good).replace('"claude:claude-fable-5-2"',
                                                                       '"claude:claude-opus-5-5"', 1)),
        }
        for reason, prefs in cases.items():
            self.assertTrue(any(reason in problem for problem in p.problems(prefs, models)), reason)

    def write(self, prefs, *args):
        out, models = io.StringIO(), self.models()
        with mock.patch.object(p, "discover", lambda home, run=None: models):
            code = p.main(["write", *args], home=self.home, out=out, stdin=io.StringIO(json.dumps(prefs)))
        return code, out.getvalue()

    def test_write_checks_saves_owner_only_and_keeps_the_previous(self):
        prefs = p.propose(self.models())
        path = self.home / ".config/patstack/preferences.json"
        code, out = self.write(prefs)
        self.assertEqual(code, 0, out)
        self.assertFalse(path.exists())  # dry run
        self.assertEqual(self.write(prefs, "--apply")[0], 0)
        saved = json.loads(path.read_text())
        self.assertEqual(saved["models"], prefs["models"])
        self.assertIn("updated", saved)
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.write(dict(prefs, language="nb"), "--apply")[0], 0)
        self.assertEqual(json.loads(path.read_text())["language"], "nb")
        self.assertEqual(len(list(path.parent.glob("preferences.json.*.bak"))), 1)
        code, out = self.write(dict(prefs, reports="long"), "--apply")
        self.assertEqual(code, 3)
        self.assertIn("NOT SAVED", out)
        self.assertEqual(json.loads(path.read_text())["language"], "nb")  # unchanged

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_never_writes_through_a_linked_folder(self):
        outside = self.home / "outside"
        outside.mkdir()
        os.symlink(outside, self.home / ".config")
        code, out = self.write(p.propose(self.models()), "--apply")
        self.assertEqual(code, 3, out)
        self.assertEqual(list(outside.iterdir()), [])

    def test_notify_is_checked_and_never_shows_the_topic(self):
        topic = "patstack-a1b2c3d4e5f6g7h8i9j0"
        out = io.StringIO()
        self.assertEqual(p.main(["notify", "--url", "https://ntfy.sh", "--topic", "has space", "--apply"],
                                home=self.home, out=out), 3)
        out = io.StringIO()
        self.assertEqual(p.main(["notify", "--url", "https://ntfy.sh", "--topic", topic, "--host", "lap-1",
                                 "--apply"], home=self.home, out=out), 0)
        self.assertNotIn(topic, out.getvalue())
        path = self.home / ".config/patstack/notify.json"
        self.assertEqual(json.loads(path.read_text()), {"url": "https://ntfy.sh", "topic": topic, "host": "lap-1"})
        with mock.patch.dict(os.environ, {"PATSTACK_NOTIFY": str(path)}):  # task_status reads it as written
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
            try:
                import task_status
                self.assertEqual(task_status.load_config()["host"], "lap-1")
            finally:
                sys.path.pop(0)

    @unittest.skipIf(os.name == "nt", "POSIX modes and symlinks")
    def test_replacing_a_wide_file_makes_it_private_and_links_are_checked_first(self):
        models = self.models()
        path = self.home / ".config/patstack/preferences.json"
        path.parent.mkdir(parents=True)
        path.write_text("{broken")  # a corrupt file is still replaced, its bytes kept as the backup
        path.chmod(0o644)
        self.assertEqual(self.write(p.propose(models), "--apply")[0], 0)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        (backup,) = path.parent.glob("preferences.json.*.bak")
        self.assertEqual((backup.read_text(), backup.stat().st_mode & 0o777), ("{broken", 0o600))
        notify = path.parent / "notify.json"
        notify.write_text("{}")
        notify.chmod(0o644)
        out = io.StringIO()
        self.assertEqual(p.main(["notify", "--url", "https://ntfy.sh", "--topic", "abc_123", "--apply"],
                                home=self.home, out=out), 0)
        self.assertEqual(notify.stat().st_mode & 0o777, 0o600)
        # A linked folder: refused before any backup is made there.
        outside = self.home / "outside"
        (outside / "patstack").mkdir(parents=True)
        (outside / "patstack/preferences.json").write_text("{}")
        (outside / "patstack/notify.json").write_text("{}")
        for f in list(path.parent.iterdir()):
            f.unlink()
        path.parent.rmdir()
        (self.home / ".config").rmdir()
        os.symlink(outside, self.home / ".config")
        self.assertEqual(self.write(p.propose(models), "--apply")[0], 3)
        out = io.StringIO()
        self.assertEqual(p.main(["notify", "--url", "https://ntfy.sh", "--topic", "abc_123", "--apply"],
                                home=self.home, out=out), 3)
        self.assertEqual(sorted(f.name for f in (outside / "patstack").iterdir()), ["notify.json", "preferences.json"])
        # An override outside HOME whose folder is a link is refused too.
        other = Path(self.tmp.name).parent / (Path(self.tmp.name).name + "-other")
        other.mkdir()
        try:
            os.symlink(outside, other / "linked")
            with mock.patch.dict(os.environ, {"PATSTACK_PREFERENCES": str(other / "linked/p.json")}):
                self.assertEqual(self.write(p.propose(models), "--apply")[0], 3)
            self.assertFalse((outside / "p.json").exists())
        finally:
            for f in other.iterdir():
                f.unlink()
            other.rmdir()

    def test_without_any_catalog_nothing_is_saved(self):
        out = io.StringIO()
        with mock.patch.object(p, "discover", lambda home, run=None: []):
            code = p.main(["write", "--apply"], home=self.home, out=out,
                          stdin=io.StringIO(json.dumps(p.propose(self.models()))))
        self.assertEqual(code, 3)
        self.assertIn("no model catalog", out.getvalue())
        self.assertFalse((self.home / ".config/patstack/preferences.json").exists())

    def test_notify_off_keeps_the_file_and_stops_the_pings(self):
        p.main(["notify", "--url", "https://ntfy.sh", "--topic", "abc_123", "--apply"], home=self.home, out=io.StringIO())
        path = self.home / ".config/patstack/notify.json"
        out = io.StringIO()
        self.assertEqual(p.main(["notify", "--off", "--apply"], home=self.home, out=out), 0)
        self.assertFalse(path.exists())
        self.assertEqual(len(list(path.parent.glob("notify.json.*.off"))), 1)
        with mock.patch.dict(os.environ, {"PATSTACK_NOTIFY": str(path)}):
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
            try:
                import task_status
                self.assertIsNone(task_status.load_config())  # nothing left to ping
            finally:
                sys.path.pop(0)

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_override_with_a_link_further_up_is_refused(self):
        outside = Path(tempfile.mkdtemp())
        other = Path(tempfile.mkdtemp())
        try:
            os.symlink(outside, other / "linked")
            target = other / "linked/a/b/p.json"   # the link is three folders up
            with mock.patch.dict(os.environ, {"PATSTACK_PREFERENCES": str(target)}):
                self.assertEqual(self.write(p.propose(self.models()), "--apply")[0], 3)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            import shutil
            shutil.rmtree(outside)
            shutil.rmtree(other)

    def test_notify_off_follows_the_override_and_never_overwrites_an_archive(self):
        path = self.home / "elsewhere/notify.json"
        path.parent.mkdir()
        with mock.patch.dict(os.environ, {"PATSTACK_NOTIFY": str(path)}):
            for topic in ("first_topic", "second_topic"):  # two turn-offs within the same second
                p.main(["notify", "--url", "https://ntfy.sh", "--topic", topic, "--apply"], home=self.home,
                       out=io.StringIO())
                self.assertEqual(p.main(["notify", "--off", "--apply"], home=self.home, out=io.StringIO()), 0)
                self.assertFalse(path.exists())
            archives = sorted(path.parent.glob("notify.json.*.off"))
            self.assertEqual(len(archives), 2)
            self.assertEqual(sorted(json.loads(a.read_text())["topic"] for a in archives),
                             ["first_topic", "second_topic"])
            self.assertEqual(p.main(["notify", "--off", "--apply"], home=self.home, out=io.StringIO()), 0)  # idempotent

    def test_notify_off_never_replaces_a_competing_archive(self):
        import start_here
        p.main(["notify", "--url", "https://ntfy.sh", "--topic", "mine_now", "--apply"], home=self.home, out=io.StringIO())
        path = self.home / ".config/patstack/notify.json"
        taken = path.with_name("notify.json.20261110000000.off")
        taken.write_text("someone else's archive")
        free = path.with_name("notify.json.20261110000000-1.off")
        with mock.patch.object(start_here, "unique_name", side_effect=[taken, free]):  # taken after the check
            self.assertEqual(p.main(["notify", "--off", "--apply"], home=self.home, out=io.StringIO()), 0)
        self.assertEqual(taken.read_text(), "someone else's archive")
        self.assertEqual(json.loads(free.read_text())["topic"], "mine_now")
        self.assertFalse(path.exists())

    def test_newest_is_by_version_not_catalog_order(self):
        models = [{"provider": "codex", "id": i, "name": i, "family": "sol", "efforts": []}
                  for i in ("gpt-5.6-sol", "gpt-6.1-sol", "gpt-6-sol")]
        self.assertEqual(p.propose(models)["models"]["ranking"]["implementation"][0], "codex:gpt-6.1-sol")

    def test_quiz_metadata_is_checked(self):
        models = self.models()
        good = p.propose(models)
        self.assertEqual(p.problems(dict(good, quiz={"score": 3, "of": 4, "date": "2026-11-10"}), models), [])
        for quiz in ({"score": 99, "of": -1, "date": {"bad": 1}}, {"score": 5, "of": 4, "date": "2026-11-10"},
                     {"score": True, "of": 4, "date": "2026-11-10"}, {"score": 1, "of": 4}):
            self.assertTrue(any("quiz" in x for x in p.problems(dict(good, quiz=quiz), models)), quiz)

    def test_doctor_reports_the_saved_preferences(self):
        report = setup_doctor.Report()
        setup_doctor.check_preferences(self.home, report)
        self.assertEqual(report.rows[-1]["status"], "INFO")
        self.write(p.propose(self.models()), "--apply")
        report = setup_doctor.Report()
        setup_doctor.check_preferences(self.home, report)
        self.assertEqual(report.rows[-1]["status"], "OK")
        self.assertIn("review pair claude:claude-opus-5-5 + codex:gpt-6.1-sol", report.rows[-1]["detail"])
        (self.home / ".config/patstack/preferences.json").write_text('{"version": 1}')
        report = setup_doctor.Report()
        setup_doctor.check_preferences(self.home, report)
        self.assertEqual(report.rows[-1]["status"], "WARN")


if __name__ == "__main__":
    unittest.main()
