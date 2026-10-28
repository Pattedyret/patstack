import json
import os
import subprocess
import sys
import tempfile
import unittest

FWD = lambda path: str(path).replace("\\", "/")  # the installer writes forward-slash commands on Windows
from pathlib import Path

import kpi_monitor as k
import install as installer


NOW = "2026-10-26T12:00:00+00:00"


def sample(identity="task-1", **changes):
    row = {
        "id": identity, "revision": 1, "workflow": "development",
        "topic": "api", "mode": "full_send", "status": "completed",
        "started_at": "2026-10-01T10:00:00+00:00",
        "updated_at": "2026-10-11T10:02:00+00:00",
        "ended_at": "2026-10-01T10:02:00+00:00",
        "verified_success": True, "human_interventions": 0,
        "contacts": 1, "turns": 4, "questions": 0,
        "handoff": "none", "support_eligible": False,
        "followup_checked_at": "2026-10-10T10:02:00+00:00",
        "repeat_contact": False,
    }
    row.update(changes)
    return row


class MetricsTests(unittest.TestCase):
    def test_missing_labels_are_unknown_not_perfect(self):
        result = k.summarize([sample(verified_success=None, human_interventions=None)], NOW)
        self.assertIsNone(result["task_completion_rate"]["percent"])
        self.assertIsNone(result["autonomous_resolution_rate"]["percent"])
        self.assertEqual(result["task_completion_rate"]["eligible"], 1)
        self.assertEqual(result["task_completion_rate"]["observed"], 0)

    def test_active_work_not_abandoned_or_timed_as_completed(self):
        result = k.summarize([sample(status="open", ended_at=None, verified_success=None)], NOW)
        self.assertEqual(result["counts"]["open"], 1)
        self.assertEqual(result["counts"]["abandoned"], 0)
        self.assertEqual(result["time_to_complete_seconds"]["count"], 0)

    def test_full_stop_is_planned_not_failed_escalation(self):
        rows = [sample(), sample("hands-on", mode="full_stop", handoff="planned",
                                 human_interventions=1)]
        result = k.summarize(rows, NOW)
        self.assertEqual(result["task_completion_rate"]["percent"], 100)
        self.assertEqual(result["autonomous_resolution_rate"]["eligible"], 1)
        self.assertEqual(result["autonomous_resolution_rate"]["percent"], 100)
        self.assertEqual(result["unexpected_handoff_rate"]["percent"], 0)
        self.assertEqual(result["handoffs"]["planned"], 1)

    def test_deflection_requires_declared_support_eligibility(self):
        rows = [sample(), sample("help", workflow="support", support_eligible=True),
                sample("transfer", workflow="support", support_eligible=True,
                       status="handed_off", verified_success=False,
                       human_interventions=1, handoff="unexpected")]
        result = k.summarize(rows, NOW)
        self.assertEqual(result["deflection_rate"]["eligible"], 2)
        self.assertEqual(result["deflection_rate"]["percent"], 50)

    def test_fcr_waits_for_observed_followup_window(self):
        rows = [sample(), sample("return", contacts=2, repeat_contact=True),
                sample("not-followed", followup_checked_at=None),
                sample("too-soon", followup_checked_at="2026-10-02T10:02:00+00:00")]
        result = k.summarize(rows, NOW)
        self.assertEqual(result["first_contact_resolution_rate"]["percent"], 50)
        self.assertEqual(result["first_contact_resolution_rate"]["observed"], 2)
        self.assertEqual(result["first_contact_resolution_rate"]["eligible"], 4)

    def test_errors_and_retention_use_audited_denominators(self):
        result = k.summarize([sample(responses_reviewed=20, response_errors=2,
                                    hallucinations=1, tool_calls=10,
                                    invalid_tool_calls=1, tool_failures=2,
                                    outputs_reviewed=4, outputs_kept=3)], NOW)
        self.assertEqual(result["response_error_rate"]["percent"], 10)
        self.assertEqual(result["hallucination_rate"]["percent"], 5)
        self.assertEqual(result["invalid_tool_call_rate"]["percent"], 10)
        self.assertEqual(result["output_retention_rate"]["percent"], 75)

    def test_frustration_signal_is_not_confirmed_rage(self):
        result = k.summarize([sample(frustration_signal=True, frustration_confirmed=False)], NOW)
        self.assertEqual(result["frustration_signal_rate"]["percent"], 100)
        self.assertEqual(result["confirmed_frustration_rate"]["percent"], 0)

    def test_duration_filter_is_explicit_and_does_not_drop_outcomes(self):
        rows = [sample(), sample("slow", ended_at="2026-10-01T11:00:00+00:00",
                                 updated_at="2026-10-11T11:00:00+00:00")]
        all_runs = k.summarize(rows, NOW)
        trimmed = k.summarize(rows, NOW, max_duration=300)
        self.assertEqual(all_runs["time_to_complete_seconds"]["median"], 1860)
        self.assertEqual(trimmed["time_to_complete_seconds"]["median"], 120)
        self.assertEqual(trimmed["time_to_complete_seconds"]["excluded"], 1)
        self.assertEqual(trimmed["task_completion_rate"]["eligible"], 2)

    def test_node_results_are_separate_from_workflow_completion(self):
        row = sample(nodes=[{"id": "login", "status": "pass"},
                            {"id": "live-proof", "status": "blocked"}])
        result = k.report([row], NOW)
        self.assertEqual(result["by_node"]["login"]["pass"], 1)
        self.assertEqual(result["by_node"]["live-proof"]["blocked"], 1)
        self.assertEqual(result["overall"]["counts"]["total"], 1)

    def test_invalid_records_fail_without_echoing_private_values(self):
        for changes in [dict(password="must-not-appear"), dict(turns=True),
                        dict(responses_reviewed=1, response_errors=2),
                        dict(ended_at="2026-09-01T00:00:00+00:00"),
                        dict(status="completed", ended_at=None),
                        dict(nodes=[{"id": "a", "status": "pass"},
                                    {"id": "a", "status": "fail"}])]:
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError) as ctx:
                k.validate(sample(**changes))
            self.assertNotIn("must-not-appear", str(ctx.exception))

    def test_snapshot_deduplication_conflicts_resume_and_asof(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "metrics.sqlite3"
            first = sample(status="open", ended_at=None, verified_success=None,
                           updated_at="2026-10-01T10:02:00+00:00", followup_checked_at=None)
            self.assertTrue(k.record(db, first))
            self.assertFalse(k.record(db, first))
            with self.assertRaises(ValueError):
                k.record(db, {**first, "questions": 3})
            second = sample(revision=2, updated_at="2026-10-12T12:00:00+00:00")
            k.record(db, second)
            self.assertEqual(len(k.latest(db, NOW)), 1)
            self.assertEqual(k.latest(db, NOW)[0]["revision"], 2)
            earlier = k.latest(db, "2026-10-01T12:00:00+00:00")
            self.assertEqual(earlier[0]["status"], "open")

    def test_read_of_missing_store_is_side_effect_free(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "absent.sqlite3"
            self.assertEqual(k.latest(db, NOW), [])
            self.assertFalse(db.exists())

    def test_all_hosts_and_environments_show_missing_coverage(self):
        result = k.report([sample(host="mac", environment="stage")], NOW)
        self.assertEqual(result["by_host"]["mac"]["coverage"], "recorded")
        self.assertEqual(result["by_host"]["windows"]["coverage"], "unmeasured")
        self.assertIsNone(result["by_environment"]["production"]["task_completion_rate"]["percent"])

    def test_future_followup_does_not_count_as_observed(self):
        result = k.summarize([sample(followup_checked_at="2026-11-10T10:00:00+00:00")], NOW)
        self.assertEqual(result["first_contact_resolution_rate"]["observed"], 0)

    def test_reference_only_collection_never_invokes_the_old_registry(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory, patch('subprocess.run') as process:
            db = Path(directory) / 'not-created.sqlite3'
            for host in ('mac', 'devbox', 'windows'):
                result = k.collect(db, host)
                self.assertEqual(result['coverage'], 'numbering_only')
                self.assertEqual(result['inserted'], 0)
            process.assert_not_called()
            self.assertFalse(db.exists())

    def test_registry_discovery_does_not_invent_outcomes(self):
        task = {"id": "t-123", "revision": 2, "state": "done", "work_type": "backend",
                "created_at": 1790000000, "updated_at": 1790000400,
                "summary": "secret-must-not-be-copied", "context": "private"}
        row = k.registry_snapshot(task, "mac")
        self.assertNotIn("secret-must-not-be-copied", json.dumps(row))
        result = k.report([row], NOW)
        self.assertEqual(result["registry_observations"]["count"], 1)
        self.assertEqual(result["overall"]["counts"]["total"], 0)
        self.assertIsNone(result["overall"]["task_completion_rate"]["percent"])

    def test_reverse_arrival_same_timestamp_and_cross_host_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "k.sqlite3"
            k.record(db, sample(host="mac", revision=2))
            k.record(db, sample(host="mac", revision=1))
            self.assertEqual(k.latest(db, NOW)[0]["revision"], 2)
            with self.assertRaises(ValueError):
                k.record(db, sample(host="devbox", revision=3))

    def test_hook_never_copies_or_opens_private_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "audit.sqlite3"
            payload = {"session_id": "private-native-id", "transcript_path": "/DO-NOT-OPEN",
                       "last_assistant_message": "secret", "tool_input": {"token": "secret"}}
            k.audit_pulse(db, payload, "mac", "codex", "Stop", NOW)
            k.audit_pulse(db, payload, "mac", "codex", "Stop", NOW)
            coverage = k.audit_coverage(db)
            self.assertEqual(coverage[0]["sessions"], 1)
            self.assertEqual(coverage[0]["receipts"], 2)
            self.assertEqual(k.latest(db, NOW), [])
            self.assertNotIn(b"private-native-id", db.read_bytes())
            self.assertNotIn(b"secret", db.read_bytes())

    def test_installer_preserves_hooks_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "keep-me"}]}]},
                        "unrelated_setting": True}
            settings.write_text(json.dumps(existing))
            one = installer.install(Path(__file__).parent, home, "windows")
            after = json.loads(settings.read_text())
            self.assertEqual(after["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
            self.assertTrue(after["unrelated_setting"])
            self.assertTrue(one["changed"])
            self.assertEqual(installer.install(Path(__file__).parent, home, "windows")["changed"], [])

    def test_installer_reads_utf8_instructions_on_any_platform(self):
        # Windows defaults to cp1252, where the UTF-8 bytes of "”" (0x9d) are undefined.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / ".harnesses-shared/agent-setup/AGENTS.md"
            agents.parent.mkdir(parents=True)
            agents.write_text("Patstack ”kilde” – æøå\n", encoding="utf-8")
            (home / ".claude").mkdir()
            (home / ".claude/settings.json").write_text(json.dumps({"note": "”"}), encoding="utf-8")
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            self.assertIn("”kilde”", agents.read_text(encoding="utf-8"))
            self.assertEqual(json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))["note"], "”")

    def test_installer_adds_one_session_status_hook_when_doctor_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            banner = {"hooks": [{"type": "command", "command": "banner.sh"}]}
            settings.write_text(json.dumps({"hooks": {"SessionStart": [banner]}}))
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            self.assertEqual(json.loads(settings.read_text())["hooks"]["SessionStart"], [banner])  # no doctor shipped yet
            mention = {"hooks": [{"type": "command", "command": "echo setup_doctor.py --hook claude"}]}
            settings.write_text(json.dumps({"hooks": {"SessionStart": [banner, mention]}}))
            doctor = home / ".harnesses-shared/agent-setup/scripts/setup_doctor.py"
            doctor.parent.mkdir(parents=True)
            doctor.write_text("")
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            starts = json.loads(settings.read_text())["hooks"]["SessionStart"]
            self.assertEqual(starts[:2], [banner, mention])
            self.assertEqual(len(starts), 3)  # a mere mention does not suppress the real hook; reruns add none
            command = starts[2]["hooks"][0]["command"]
            self.assertTrue(command.endswith(f"{FWD(doctor)} --host devbox --hook claude"), command)

    def hook_run(self, db, runtime, event, body):
        out = subprocess.run([sys.executable, str(Path(__file__).with_name("kpi_monitor.py")), "--db", str(db), "audit-hook",
                              "--host", "devbox", "--runtime", runtime, "--event", event], input=body, capture_output=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, b"{}"), out.stderr)

    def test_tool_events_and_oversized_envelopes_count_without_content(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "k.sqlite3"
            small = json.dumps({"session_id": "s1", "tool_name": "Bash", "tool_response": {"stdout": "secret-output"}}).encode()
            big = json.dumps({"session_id": "s1", "tool_response": {"stdout": "x" * 2_000_000}}).encode()
            self.hook_run(db, "claude", "PostToolUse", small)
            self.hook_run(db, "claude", "PostToolUse", big)  # 2 MB: drained, session id kept
            self.hook_run(db, "claude", "PostToolUseFailure", small)
            self.hook_run(db, "claude", "Stop", small)
            self.hook_run(db, "codex", "PostToolUse", json.dumps({"thread_id": "t1"}).encode())
            self.assertNotIn(b"secret-output", db.read_bytes())
            kpis = {(r["runtime"]): r for r in k.session_kpis(db)}
            self.assertEqual((kpis["claude"]["sessions"], kpis["claude"]["turns"]), (1, 1))
            self.assertEqual((kpis["claude"]["tool_calls"], kpis["claude"]["tool_failures"]), (3, 1))
            self.assertEqual((kpis["codex"]["tool_calls"], kpis["codex"]["tool_failures"]), (1, None))

    def test_large_envelope_uses_only_the_top_level_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "k.sqlite3"
            body = json.dumps({"tool_input": {"session_id": "nested"}, "session_id": "top",
                               "tool_response": {"stdout": "y" * 2_000_000}}).encode()
            self.hook_run(db, "claude", "PostToolUse", body)
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(db)) as con:  # closed, so Windows can remove the temp dir
                keys = [r[0] for r in con.execute("SELECT session FROM audit_receipts")]
            top = __import__("hashlib").sha256(b"devbox:claude:top").hexdigest()[:32]
            self.assertEqual(keys, [top])

    def test_installer_replaces_a_narrow_tool_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude").mkdir()
            narrow = {"matcher": "Bash", "hooks": [{"type": "command", "command": "keep-me-narrow"}]}
            (home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PostToolUse": [narrow]}}))
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            groups = json.loads((home / ".claude/settings.json").read_text())["hooks"]["PostToolUse"]
            self.assertEqual(groups[0], narrow)  # an unrelated narrow hook is preserved
            self.assertEqual(groups[1]["matcher"], "*")  # plus a counter that sees every tool

    def test_installer_removes_a_narrow_kpi_counter_instead_of_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude").mkdir()
            kpi = FWD(home / ".harnesses-shared/agent-setup/monitoring/patstack/kpi_monitor.py")
            (home / ".harnesses-shared/agent-setup/monitoring/patstack").mkdir(parents=True)
            (home / ".harnesses-shared/agent-setup/monitoring/patstack/kpi_monitor.py").write_text("")
            narrow_counter = {"type": "command", "command": f"{FWD(sys.executable)} -B {kpi} audit-hook --host devbox --runtime claude --event PostToolUse"}
            other = {"type": "command", "command": "keep-me"}
            (home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PostToolUse": [
                {"matcher": "Bash", "hooks": [narrow_counter, other]}, {"matcher": "Edit", "hooks": [dict(narrow_counter)]}]}}))
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            groups = json.loads((home / ".claude/settings.json").read_text())["hooks"]["PostToolUse"]
            self.assertEqual(groups[0], {"matcher": "Bash", "hooks": [other]})  # counter removed, other hook kept
            self.assertEqual(len(groups), 2)  # the counter-only Edit group is gone; one full counter added
            self.assertEqual(groups[1]["matcher"], "*")

    def test_installer_keeps_a_same_named_counter_owned_by_someone_else(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude").mkdir()
            foreign = home / "unrelated-owner/kpi_monitor.py"
            foreign.parent.mkdir(); foreign.write_text("")
            theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command":
                      f"{FWD(sys.executable)} {FWD(foreign)} audit-hook --host devbox --runtime claude --event PostToolUse"}]}
            (home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PostToolUse": [theirs]}}))
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            groups = json.loads((home / ".claude/settings.json").read_text())["hooks"]["PostToolUse"]
            self.assertEqual(groups[0], theirs)

    def test_session_minutes_span_first_to_last_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "k.sqlite3"
            k.audit_pulse(db, {"session_id": "a"}, "mac", "claude", "Stop", "2026-10-01T10:00:00+00:00")
            k.audit_pulse(db, {"session_id": "a"}, "mac", "claude", "PostToolUse", "2026-10-01T10:30:00+00:00")
            k.audit_pulse(db, {"session_id": "b"}, "mac", "claude", "Stop", "2026-10-01T11:00:00+00:00")
            (row,) = k.session_kpis(db)
            self.assertEqual(row["session_minutes"], {"median": 15.0, "mean": 15.0})  # 30 and 0 minutes
            self.assertEqual((row["sessions"], row["tool_sessions"], row["tool_calls"], row["tool_failures"]), (2, 1, 1, 0))

    def test_installer_adds_tool_counters_once_per_client(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for rel in (".claude/settings.json", ".codex/hooks.json"):
                (home / rel).parent.mkdir(parents=True, exist_ok=True)
                (home / rel).write_text("{}")
            installer.install(Path(__file__).parent, home, "devbox")
            installer.install(Path(__file__).parent, home, "devbox")
            claude = json.loads((home / ".claude/settings.json").read_text())["hooks"]
            codex = json.loads((home / ".codex/hooks.json").read_text())["hooks"]
            self.assertEqual([len(claude["PostToolUse"]), len(claude["PostToolUseFailure"]), len(codex["PostToolUse"])], [1, 1, 1])
            self.assertNotIn("PostToolUseFailure", codex)
            self.assertEqual((claude["PostToolUse"][0]["matcher"], codex["PostToolUse"][0]["matcher"]), ("*", ".*"))
            command = claude["PostToolUseFailure"][0]["hooks"][0]["command"]
            self.assertTrue(command.endswith("audit-hook --host devbox --runtime claude --event PostToolUseFailure"), command)

    def test_installer_recognises_only_its_own_command_form(self):
        with tempfile.TemporaryDirectory() as directory:
            doctor_path, kpi_path = Path(directory) / "setup_doctor.py", Path(directory) / "kpi_monitor.py"
            doctor_path.write_text(""); kpi_path.write_text("")
            py, doctor, kpi = FWD(sys.executable), FWD(doctor_path), FWD(kpi_path)
            self.assertTrue(installer.is_status_hook(f"{py} {doctor} --host devbox --hook claude", "devbox", "claude"))
            self.assertTrue(installer.is_status_hook(f"{py} -B {doctor} --host devbox --hook claude", "devbox", "claude"))
            self.assertTrue(installer.is_kpi_hook(f"{py} {kpi} audit-hook --host devbox --runtime claude --event Stop", "devbox", "claude"))
            for command in (f"echo {doctor} --host devbox --hook claude", f"{py} {doctor} --host devbox --hook codex",
                            f"{py} -c {doctor} --host devbox --hook claude", f"{py} -X utf8=2 {doctor} --host devbox --hook claude",
                            f"/usr/bin/env python3 {doctor} --host devbox --hook claude", f"{py} {doctor} --host devbox --hook claude --bogus",
                            f"{py} {doctor.replace('setup_doctor.py', 'not_setup_doctor.py')} --host devbox --hook claude",
                            f"{py} {doctor} --host mac --hook claude"):
                self.assertFalse(installer.is_status_hook(command, "devbox", "claude"), command)
            fake_path = Path(directory) / "python3"
            fake_path.write_text(""); fake_path.chmod(0o600)
            fake = FWD(fake_path) if os.name != "nt" else "C:/missing/python3"
            for command in (f"{py} {kpi} audit-hook --host devbox --runtime claude --event Stop --bogus",
                            f"echo {kpi} audit-hook --host devbox --runtime claude --event Stop",
                            f"{py} {kpi} audit-hook --host devbox --runtime claude --event\nStop",
                            f"{fake} {kpi} audit-hook --host devbox --runtime claude --event Stop"):
                self.assertFalse(installer.is_kpi_hook(command, "devbox", "claude"), command)

    def test_installer_keeps_existing_recognised_status_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            doctor = home / ".harnesses-shared/agent-setup/scripts/setup_doctor.py"
            doctor.parent.mkdir(parents=True)
            doctor.write_text("")
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            existing = {"hooks": [{"type": "command", "command": f"{FWD(sys.executable)} -B {FWD(doctor)} --host devbox --hook claude"}]}
            settings.write_text(json.dumps({"hooks": {"SessionStart": [existing]}}))
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            self.assertEqual(json.loads(settings.read_text())["hooks"]["SessionStart"], [existing])

    def test_patstack_installer_only_updates_new_retro_and_preserves_old_overlay(self):
        for version in ["1.0.0", "1.1.0"]:
          for expose in ({}, {"retro": {"body_prefix": "historical retro"}}):
            with self.subTest(version=version, expose=expose), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                root = home / ".harnesses-shared/agent-setup"
                relative = "skills/retro/SKILL.md" if version == "1.1.0" else "skills/patstack/references/retro.md"
                retro = root / relative
                retro.parent.mkdir(parents=True)
                retro.write_text("# Patstack Retro\nKeep this guidance.\n")
                (root / "AGENTS.md").write_text("Keep global guidance.\n")
                (root / "manifest.json").write_text(json.dumps({"active_stack": {"name": "patstack", "version": version, "global_skills": ["patstack", "retro"] if version == "1.1.0" else ["patstack"]}}))
                overlay = root / "vendor/mattpocock-skills/overlay.json"
                overlay.parent.mkdir(parents=True)
                overlay.write_text(json.dumps({"expose": expose}))
                before = overlay.read_bytes()
                installer.install(Path(__file__).parent, home, "mac")
                self.assertEqual(overlay.read_bytes(), before)
                self.assertIn(installer.POINTER.rstrip(), retro.read_text())
                self.assertIn("Keep this guidance.", retro.read_text())
                other = "skills/patstack/references/retro.md" if version == "1.1.0" else "skills/retro/SKILL.md"
                self.assertFalse((root / other).exists())
                self.assertEqual(installer.install(Path(__file__).parent, home, "mac")["changed"], [])

    def test_legacy_installer_keeps_existing_overlay_render_path(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / ".harnesses-shared/agent-setup"
            overlay = root / "vendor/mattpocock-skills/overlay.json"
            overlay.parent.mkdir(parents=True)
            overlay.write_text(json.dumps({"expose": {"retro": {"body_prefix": "Keep legacy guidance"}}}))
            script = root / "scripts/mp_skills.py"
            script.parent.mkdir(parents=True)
            script.write_text("def render_skill(name, config):\n    return {'SKILL.md': config['body_prefix'].encode()}\n")
            installer.install(Path(__file__).parent, home, "mac")
            self.assertIn(installer.POINTER.rstrip(), (root / "skills/retro/SKILL.md").read_text())
            self.assertIn("Keep legacy guidance", (root / "skills/retro/SKILL.md").read_text())
            self.assertFalse((root / "skills/patstack").exists())

    def test_real_registry_states_are_exposed_without_outcome_claims(self):
        task = {"id": "t-1", "revision": 1, "created_at": 1790000000, "updated_at": 1790000100}
        rows = [k.registry_snapshot({**task, "id": "t-" + state, "state": state}, "mac")
                for state in ("done", "handoff", "cancelled", "ready", "active", "blocked")]
        result = k.report(rows, NOW)
        self.assertEqual(result["registry_observations"]["by_host"]["mac"],
                         {"total": 6, "closed": 3, "open": 3})
        self.assertEqual(result["overall"]["counts"]["total"], 0)

    def test_known_fcr_failures_do_not_need_followup(self):
        result = k.summarize([sample(), sample("failed", status="failed", verified_success=False,
                            followup_checked_at=None), sample("recontact", contacts=3,
                            repeat_contact=True, followup_checked_at=None)], NOW)
        self.assertEqual(result["first_contact_resolution_rate"]["observed"], 3)
        self.assertEqual(result["first_contact_resolution_rate"]["percent"], 33.33)

    def test_null_omit_idempotence_and_invalid_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "k.sqlite3"
            k.record(db, sample())
            self.assertFalse(k.record(db, sample(tool_calls=None, nodes=None, host=None)))
        with self.assertRaises(ValueError):
            k.validate(sample(status="handed_off", verified_success=False, handoff="none"))
        with self.assertRaises(ValueError):
            k.validate(sample(started_at=None))

    def test_windows_hook_paths_survive_bash_and_unsafe_paths_reject(self):
        import shlex
        command = installer.hook_command(r"C:\Users\Rick\python.exe",
                  r"C:\Users\Rick\monitor.py", "windows", "codex", True)
        self.assertEqual(shlex.split(command)[:2],
                         ["C:/Users/Rick/python.exe", "C:/Users/Rick/monitor.py"])
        with self.assertRaises(RuntimeError):
            installer.hook_command(r"C:\Users\Other User\python.exe", "script.py",
                                   "windows", "codex", True)

    def test_pointer_updates_existing_marker_without_touching_other_text(self):
        previous = "keep\n" + installer.MARKER + "\nold\n" + installer.END + "\nafter\n"
        actual = installer.with_pointer(previous)
        self.assertTrue(actual.startswith("keep\n"))
        self.assertTrue(actual.endswith("\nafter\n"))
        self.assertIn(installer.POINTER.rstrip(), actual)


if __name__ == "__main__":
    unittest.main()
