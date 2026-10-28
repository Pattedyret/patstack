"""setup_doctor tests in a temporary home; never touch live clients or the live KPI store."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

FWD = lambda path: str(path).replace("\\", "/")  # the installer writes forward-slash commands on Windows
from unittest import mock

spec = importlib.util.spec_from_file_location("setup_doctor", Path(__file__).with_name("setup_doctor.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

KPI_SOURCE = Path(__file__).resolve().parent.parent / "monitoring/patstack/kpi_monitor.py"


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / ".harnesses-shared/agent-setup"
        (self.root / "skills/patstack").mkdir(parents=True)
        (self.root / "skills/patstack/SKILL.md").write_text("# Patstack\n")
        (self.root / "monitoring/patstack").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        shutil.copy(Path(__file__).with_name("setup_doctor.py"), self.root / "scripts/setup_doctor.py")
        shutil.copy(Path(__file__).with_name("skill_mirrors.py"), self.root / "scripts/skill_mirrors.py")
        shutil.copy(KPI_SOURCE, self.root / "monitoring/patstack/kpi_monitor.py")
        (self.root / "AGENTS.md").write_text("Read patstack. KPI: monitoring/patstack/README.md\n")
        for client in (".claude", ".codex", ".agents"):
            (self.home / client).mkdir()
        os.symlink(self.root / "skills", self.home / ".claude/skills")
        os.symlink(self.root / "skills", self.home / ".agents/skills")
        os.symlink(self.root / "AGENTS.md", self.home / ".claude/CLAUDE.md")
        os.symlink(self.root / "AGENTS.md", self.home / ".codex/AGENTS.md")
        (self.home / ".local/bin").mkdir(parents=True)
        (self.home / ".local/bin/ticket-ref").write_text("#!/bin/sh\n")
        self.hooks = self.home / ".claude/hooks"
        self.hooks.mkdir()
        for name in d.SAFETY_HOOKS:
            (self.hooks / name).write_text("#!/bin/sh\n")
        self.db = self.home / "kpis.sqlite3"
        self.write_claude()
        self.write_codex(trusted=True)

    def tearDown(self):
        self.tmp.cleanup()

    def kpi(self, runtime):
        return f"{FWD(sys.executable)} {FWD(self.root)}/monitoring/patstack/kpi_monitor.py audit-hook --host devbox --runtime {runtime} --event Stop"

    def status(self, runtime):
        return f"{FWD(sys.executable)} {FWD(self.root)}/scripts/setup_doctor.py --host devbox --hook {runtime}"

    def write_claude(self, extra=None, kpi_runtime="claude"):
        pre = [{"type": "command", "command": str(self.hooks / n)} for n in d.SAFETY_HOOKS[:3]]
        hooks = {
            "PreToolUse": [{"matcher": "Bash", "hooks": pre}],
            "PostToolUse": [{"hooks": [{"type": "command", "command": str(self.hooks / d.SAFETY_HOOKS[3])}]}],
            "Stop": [{"hooks": [{"type": "command", "command": self.kpi(kpi_runtime)}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": self.status("claude")}]}],
            "PostToolUseFailure": [{"matcher": "*", "hooks": [{"type": "command", "command": self.kpi("claude").replace("Stop", "PostToolUseFailure")}]}],
        }
        hooks["PostToolUse"].append({"matcher": "*", "hooks": [{"type": "command", "command": self.kpi("claude").replace("Stop", "PostToolUse")}]})
        if extra:
            hooks.setdefault("SessionStart", []).append({"hooks": [{"type": "command", "command": extra}]})
        (self.home / ".claude/settings.json").write_text(json.dumps({"hooks": hooks}))

    def write_codex(self, trusted):
        hooks_file = self.home / ".codex/hooks.json"
        hooks_file.write_text(json.dumps({"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": self.status("codex")}]}],
            "Stop": [{"hooks": [{"type": "command", "command": self.kpi("codex")}]}],
            "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": self.kpi("codex").replace("Stop", "PostToolUse")}]}]}}))
        trust = "".join(f'[hooks.state.{json.dumps(f"{hooks_file}:{key}")}]\ntrusted_hash = "sha256:abc"\n'
                        for key in ("session_start:0:0", "stop:0:0", "post_tool_use:0:0")) if trusted else ""
        (self.home / ".codex/config.toml").write_text(trust)

    def receipt(self, runtime):
        subprocess.run([sys.executable, str(KPI_SOURCE), "--db", str(self.db), "audit-hook", "--host", "devbox",
                        "--runtime", runtime, "--event", "Stop"], input='{"session_id": "s1"}', text=True, check=True,
                       capture_output=True)

    def statuses(self, check=None):
        report = d.run(self.root, self.home, "devbox", self.db)
        return report, {(r["check"], r["status"]) for r in report.rows if check is None or r["check"] == check}

    def test_healthy_setup_has_no_fail_and_counts_receipts(self):
        self.receipt("claude")
        self.receipt("codex")
        report, rows = self.statuses()
        self.assertFalse(report.failed, report.rows)
        self.assertIn(("claude receipts", "OK"), rows)
        self.assertIn(("codex receipts", "OK"), rows)
        self.assertIn(("codex trust", "INFO"), rows)  # present but unverifiable, never claimed OK
        self.assertNotIn(("codex trust", "OK"), rows)
        self.assertIn(("claude status hook", "OK"), rows)
        self.assertIn(("codex status hook", "OK"), rows)
        self.assertNotIn(("claude tool hook", "WARN"), rows)
        self.assertNotIn(("codex tool hook", "WARN"), rows)

    def test_missing_kpi_hook_fails(self):
        self.write_claude(kpi_runtime="codex")  # wrong runtime is not a Claude KPI hook
        report, rows = self.statuses("claude KPI hook")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("claude KPI hook", "FAIL")})

    def test_broken_hook_path_fails(self):
        self.write_claude(extra=str(self.hooks / "gone.sh"))
        report, _ = self.statuses()
        self.assertTrue(any(r["status"] == "FAIL" and "gone.sh" in r["detail"] for r in report.rows))

    def test_untrusted_codex_hook_warns(self):
        self.write_codex(trusted=False)
        report, _ = self.statuses()
        trust = [r["detail"] for r in report.rows if r["check"] == "codex trust"]
        self.assertEqual(len(trust), 3)  # status, KPI and tool-count hooks
        self.assertTrue(all("not trusted" in x for x in trust), trust)

    def test_unfired_hook_warns(self):
        self.receipt("claude")
        _, rows = self.statuses()
        self.assertIn(("codex receipts", "WARN"), rows)
        self.assertIn(("claude receipts", "OK"), rows)

    def test_retired_and_missing_safety_hooks_warn(self):
        (self.hooks / "agent-work-session-ticket.py").write_text("")
        self.write_claude(extra=str(self.hooks / "agent-work-session-ticket.py"))
        (self.home / ".claude/settings.json").write_text((self.home / ".claude/settings.json").read_text()
                                                       .replace("read-size-guard.sh", "other.sh"))
        report, _ = self.statuses()
        details = [r["detail"] for r in report.rows if r["status"] == "WARN"]
        self.assertTrue(any("agent-work-session-ticket.py" in x for x in details))
        self.assertTrue(any("read-size-guard.sh not wired" in x for x in details))

    def test_closed_outcome_without_verified_success_warns(self):
        snapshot = {"id": "t1", "revision": 1, "workflow": "bugfix", "topic": "x", "mode": "full_send",
                    "status": "completed", "started_at": "2026-10-01T10:00:00+00:00",
                    "updated_at": "2026-10-01T11:00:00+00:00", "ended_at": "2026-10-01T11:00:00+00:00"}
        subprocess.run([sys.executable, str(KPI_SOURCE), "--db", str(self.db), "record"], input=json.dumps(snapshot),
                       text=True, check=True, capture_output=True)
        _, rows = self.statuses("kpi outcomes")
        self.assertEqual(rows, {("kpi outcomes", "WARN")})
        snapshot.update(revision=2, verified_success=True)
        subprocess.run([sys.executable, str(KPI_SOURCE), "--db", str(self.db), "record"], input=json.dumps(snapshot),
                       text=True, check=True, capture_output=True)
        _, rows = self.statuses("kpi outcomes")
        self.assertEqual(rows, {("kpi outcomes", "OK")})

    def test_per_skill_links_are_accepted(self):
        os.unlink(self.home / ".claude/skills")
        (self.home / ".claude/skills").mkdir()
        os.symlink(self.root / "skills/patstack", self.home / ".claude/skills/patstack")  # published layout
        _, rows = self.statuses("skills .claude")
        self.assertEqual(rows, {("skills .claude", "OK")})

    def test_default_root_is_the_tree_containing_the_script(self):
        out = subprocess.run([sys.executable, str(self.root / "scripts/setup_doctor.py"), "--host", "devbox",
                              "--home", str(self.home), "--db", str(self.db), "--json"], capture_output=True, text=True)
        source = [r for r in json.loads(out.stdout) if r["check"] == "source"][0]
        self.assertEqual((source["status"], Path(source["detail"]).resolve()), ("OK", self.root.resolve()))

    def test_every_skill_must_resolve(self):
        (self.root / "skills/review").mkdir()
        (self.root / "skills/review/SKILL.md").write_text("# Review\n")
        os.unlink(self.home / ".claude/skills")
        (self.home / ".claude/skills").mkdir()
        os.symlink(self.root / "skills/patstack", self.home / ".claude/skills/patstack")  # review not linked
        report, rows = self.statuses("skills .claude")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("skills .claude", "FAIL")})
        self.assertIn("review", [r["detail"] for r in report.rows if r["check"] == "skills .claude"][0])

    def windows_mirrors(self):
        sys.path.insert(0, str(self.root / "scripts"))
        import skill_mirrors
        for client in (".claude/skills", ".agents/skills"):
            os.unlink(self.home / client)
            (self.home / client).mkdir()
        skill_mirrors.apply((self.root / "skills").resolve(), self.home, self.home / "mirror-backup")
        return skill_mirrors

    def windows_rows(self):
        report = d.run(self.root, self.home, "windows", self.db)
        return {(r["check"], r["status"]) for r in report.rows if r["check"].startswith("skills ")}

    def test_windows_mirrors_are_checked_for_freshness(self):
        self.windows_mirrors()
        self.assertEqual(self.windows_rows(), {("skills .claude", "OK"), ("skills .agents", "OK")})
        (self.root / "skills/patstack/SKILL.md").write_text("# Patstack v2\n")  # source changes, mirrors do not
        self.assertEqual(self.windows_rows(), {("skills .claude", "WARN"), ("skills .agents", "WARN")})
        os.remove(self.home / ".agents/skills/patstack/SKILL.md")
        self.assertIn(("skills .agents", "FAIL"), self.windows_rows())

    def test_windows_unsupported_source_link_warns(self):
        mirrors = self.windows_mirrors()
        (self.root / "skills/patstack/SKILL.md").write_text("# Patstack\n[x](../patstack/SKILL.md 'unterminated\n")
        mirrors.apply((self.root / "skills").resolve(), self.home, self.home / "mirror-backup")
        details = [r["detail"] for r in d.run(self.root, self.home, "windows", self.db).rows if r["check"] == "skills .claude"]
        self.assertTrue(details[0].startswith("1 source link(s) use syntax the mirror tool cannot rewrite"), details)

    def test_windows_mirror_with_broken_link_warns(self):
        mirrors = self.windows_mirrors()
        (self.root / "skills/patstack/SKILL.md").write_text("# Patstack\n[gone](missing.md)\n")
        mirrors.apply((self.root / "skills").resolve(), self.home, self.home / "mirror-backup")  # fresh, but the link is dead
        self.assertEqual(self.windows_rows(), {("skills .claude", "WARN"), ("skills .agents", "WARN")})

    def test_wrong_skill_link_fails(self):
        os.unlink(self.home / ".agents/skills")
        (self.home / ".agents/skills").mkdir()
        report, rows = self.statuses("skills .agents")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("skills .agents", "FAIL")})

    def test_doctor_changes_no_configuration(self):
        self.receipt("claude")
        def snapshot():  # the KPI store and its SQLite sidecars are excluded by contract
            return {p: p.stat().st_mtime_ns for p in self.home.rglob("*")
                    if p.is_file() and not p.name.startswith(self.db.name)}
        before = snapshot()
        with mock.patch("builtins.print"):
            self.assertIn(d.main(["--host", "devbox", "--home", str(self.home), "--db", str(self.db)]), (0, 1))
        self.assertEqual(before, snapshot())

    def hook(self, runtime, home=None):
        out = subprocess.run([sys.executable, str(Path(__file__).with_name("setup_doctor.py")), "--host", "devbox",
                              "--home", str(home or self.home), "--root", str(self.root), "--db", str(self.db),
                              "--hook", runtime], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_session_hook_reports_status_for_claude_and_context_only_for_codex(self):
        self.receipt("claude")
        claude = self.hook("claude")
        self.assertTrue(claude["systemMessage"].startswith("📈 Patstack monitoring on (1 claude receipts)"), claude)
        self.assertIn("WARN codex receipts", claude["systemMessage"])
        self.assertNotIn("codex trust", claude["systemMessage"])  # INFO rows stay out of the session line
        self.assertIn("--host devbox", claude["systemMessage"])
        self.assertIn(claude["systemMessage"], claude["hookSpecificOutput"]["additionalContext"])
        codex = self.hook("codex")
        self.assertNotIn("systemMessage", codex)
        self.assertEqual(codex["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_session_hook_flags_broken_setup_and_never_fails(self):
        (self.home / ".claude/settings.json").write_text("{not json")
        self.assertTrue(self.hook("claude")["systemMessage"].startswith("⚠ Patstack setup broken"))
        original, d.run = d.run, lambda *a: 1 / 0
        try:
            with mock.patch("sys.stdout") as out:
                self.assertEqual(d.main(["--host", "devbox", "--home", str(self.home), "--hook", "claude"]), 0)
        finally:
            d.run = original
        self.assertIn("could not run", json.loads(out.write.call_args.args[0])["systemMessage"])

    def test_kpi_hook_on_wrong_event_fails(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        data["hooks"]["SessionStart"].append(data["hooks"].pop("Stop")[0])
        settings.write_text(json.dumps(data))
        _, rows = self.statuses("claude KPI hook")
        self.assertEqual(rows, {("claude KPI hook", "FAIL")})

    def test_disable_all_hooks_fails(self):
        settings = self.home / ".claude/settings.json"
        settings.write_text(json.dumps({**json.loads(settings.read_text()), "disableAllHooks": True}))
        report, rows = self.statuses("claude hooks")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("claude hooks", "FAIL")})
        self.assertNotIn("claude KPI hook", {r["check"] for r in report.rows})

    def test_status_hook_mention_is_not_a_status_hook(self):
        settings = self.home / ".claude/settings.json"
        settings.write_text(settings.read_text().replace(self.status("claude"), "echo setup_doctor.py --hook claude"))
        _, rows = self.statuses("claude status hook")
        self.assertEqual(rows, {("claude status hook", "WARN")})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on Windows")
    def test_fifo_settings_fails_without_blocking(self):
        settings = self.home / ".claude/settings.json"
        settings.unlink()
        os.mkfifo(settings)
        report, rows = self.statuses("claude settings")
        self.assertEqual(rows, {("claude settings", "FAIL")})
        started = time.monotonic()
        self.assertTrue(self.hook("claude")["systemMessage"].startswith("⚠ Patstack setup broken"))
        self.assertLess(time.monotonic() - started, 5)

    def test_hook_mode_survives_bad_arguments_and_encoding(self):
        bad = subprocess.run([sys.executable, str(Path(__file__).with_name("setup_doctor.py")), "--hook", "codex"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 0)
        self.assertIn("could not run", json.loads(bad.stdout)["hookSpecificOutput"]["additionalContext"])
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        out = subprocess.run([sys.executable, str(Path(__file__).with_name("setup_doctor.py")), "--host", "devbox",
                              "--home", str(self.home), "--root", str(self.root), "--db", str(self.db), "--hook", "claude"],
                             capture_output=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout.decode("ascii"))["systemMessage"].startswith("📈"))

    def test_hook_mode_times_out_slow_check(self):
        original, d.run = d.run, lambda *a, **k: time.sleep(30)
        started = time.monotonic()
        try:
            with mock.patch("sys.stdout") as out:
                self.assertEqual(d.main(["--host", "devbox", "--home", str(self.home), "--hook", "codex"]), 0)
        finally:
            d.run = original
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("timed out", json.loads(out.write.call_args.args[0])["hookSpecificOutput"]["additionalContext"])

    def test_failed_workflow_needs_no_verified_success(self):
        snapshot = {"id": "t2", "revision": 1, "workflow": "bugfix", "topic": "x", "mode": "full_send",
                    "status": "failed", "started_at": "2026-10-01T10:00:00+00:00",
                    "updated_at": "2026-10-01T11:00:00+00:00", "ended_at": "2026-10-01T11:00:00+00:00"}
        subprocess.run([sys.executable, str(KPI_SOURCE), "--db", str(self.db), "record"], input=json.dumps(snapshot),
                       text=True, check=True, capture_output=True)
        report, rows = self.statuses("kpi outcomes")
        self.assertEqual(rows, {("kpi outcomes", "OK")})
        self.assertIn("completed ones carry", [r["detail"] for r in report.rows if r["check"] == "kpi outcomes"][0])

    def test_hook_help_still_emits_only_json(self):
        out = subprocess.run([sys.executable, str(Path(__file__).with_name("setup_doctor.py")), "--hook", "claude",
                              "--help"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(len(out.stdout.splitlines()), 1, out.stdout)
        json.loads(out.stdout)

    def test_every_accepted_flag_really_runs_both_hooks(self):
        doctor = self.root / "scripts/setup_doctor.py"
        kpi = self.root / "monitoring/patstack/kpi_monitor.py"
        for number, flag in enumerate(sorted(d.FLAGS)):
            self.assertIsNotNone(d.status_runtime(f"{FWD(sys.executable)} {flag} {FWD(doctor)} --host devbox --hook claude", "devbox"))
            out = subprocess.run([sys.executable, flag, str(doctor), "--host", "devbox", "--home", str(self.home),
                                  "--db", str(self.db), "--hook", "claude"], capture_output=True, text=True)
            line = json.loads(out.stdout)["systemMessage"]
            self.assertTrue(line.startswith("📈 Patstack monitoring on"), (flag, line))  # not the "could not run" fallback
            db = self.home / f"flag{number}.sqlite3"  # -s/-S collide on case-insensitive macOS file systems
            subprocess.run([sys.executable, flag, str(kpi), "--db", str(db), "audit-hook", "--host", "devbox",
                            "--runtime", "claude", "--event", "Stop"], input='{"session_id": "s1"}', text=True, check=True)
            report = json.loads(subprocess.run([sys.executable, str(kpi), "--db", str(db), "report"],
                                               capture_output=True, text=True, check=True).stdout)
            self.assertEqual(report["audit_hook_coverage"][0]["receipts"], 1, flag)

    def test_narrow_tool_matcher_is_not_a_counter(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        data["hooks"]["PostToolUseFailure"][0]["matcher"] = "Bash"
        settings.write_text(json.dumps(data))
        report, _ = self.statuses()
        warns = [r["detail"] for r in report.rows if r["check"] == "claude tool hook" and r["status"] == "WARN"]
        self.assertEqual(warns, ["PostToolUseFailure counter missing; run monitoring/patstack/install.py"])

    def test_duplicate_tool_counters_warn(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        counter = data["hooks"]["PostToolUseFailure"][0]["hooks"][0]
        data["hooks"]["PostToolUseFailure"].append({"matcher": "Bash", "hooks": [dict(counter)]})
        settings.write_text(json.dumps(data))
        report, _ = self.statuses()
        warns = [r["detail"] for r in report.rows if r["check"] == "claude tool hook" and r["status"] == "WARN"]
        self.assertEqual(warns, ["2 PostToolUseFailure counters would double-count; rerun monitoring/patstack/install.py"])

    def test_missing_tool_counter_warns(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        del data["hooks"]["PostToolUseFailure"]
        settings.write_text(json.dumps(data))
        report, _ = self.statuses()
        warns = [r["detail"] for r in report.rows if r["check"] == "claude tool hook" and r["status"] == "WARN"]
        self.assertEqual(warns, ["PostToolUseFailure counter missing; run monitoring/patstack/install.py"])

    def test_echo_kpi_command_is_not_a_kpi_hook(self):
        settings = self.home / ".claude/settings.json"
        settings.write_text(settings.read_text().replace(self.kpi("claude"), "echo " + self.kpi("claude").split(" ", 1)[1]))
        _, rows = self.statuses("claude KPI hook")
        self.assertEqual(rows, {("claude KPI hook", "FAIL")})

    def test_only_the_installer_form_is_recognised(self):
        py, kpi, doc = FWD(sys.executable), FWD(self.root / "monitoring/patstack/kpi_monitor.py"), FWD(self.root / "scripts/setup_doctor.py")
        kpi_args, doc_args = "audit-hook --host devbox --runtime claude --event Stop", "--host devbox --hook claude"
        self.assertEqual(d.kpi_runtime(f"{py} {kpi} {kpi_args}", "devbox"), "claude")
        self.assertEqual(d.kpi_runtime(f"{py} -B -u {kpi} {kpi_args}", "devbox"), "claude")
        self.assertEqual(d.status_runtime(f"{py} {doc} {doc_args}", "devbox"), "claude")
        rejected = [  # each of these would not run the hook as installed
            f"echo {kpi} {kpi_args}", f"{py} -c {kpi} {kpi_args}", f"{py} -m {kpi} {kpi_args}",
            f"{py} -X utf8=2 {kpi} {kpi_args}", f"pyenv {kpi} {kpi_args}", f"/usr/bin/env python3 {kpi} {kpi_args}",
            f"VAR=1 {py} {kpi} {kpi_args}", f"{py} {kpi} {kpi_args} --bogus", f"{py} {kpi} {kpi_args} --help",
            f"{py} {kpi.replace('kpi_monitor.py', 'not_kpi_monitor.py')} {kpi_args}", f"{py} {kpi}.missing {kpi_args}",
            f"{py} monitoring/patstack/kpi_monitor.py {kpi_args}", f"/no/such/python3 {kpi} {kpi_args}",
            f"{py} {kpi} {kpi_args.replace('devbox', 'mac')}", f"{py} {kpi} {kpi_args.replace('Stop', 'SessionEnd')}",
            f"{py} {kpi} {kpi_args.replace(' Stop', chr(10) + 'Stop')}", f"{py}  {kpi} {kpi_args}", f"{py}\t{kpi} {kpi_args}",
            f"{py} {kpi} {kpi_args} ; true", f"{py} '{kpi}' {kpi_args}"]
        fake = self.home / "python3"
        if os.name == "nt":  # Windows has no execute bit; the check is POSIX-only
            fake = None
        if fake:
            fake.write_text("#!/bin/sh\n")
            fake.chmod(0o600)
            rejected.append(f"{FWD(fake)} {kpi} {kpi_args}")
        for command in rejected:
            self.assertIsNone(d.kpi_runtime(command, "devbox"), command)
        for command in (f"{py} {doc} {doc_args} --bogus", f"{py} {doc} --hook claude", f"echo {doc} {doc_args}"):
            self.assertIsNone(d.status_runtime(command, "devbox"), command)

if __name__ == "__main__":
    unittest.main()
