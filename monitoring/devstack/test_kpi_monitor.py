import json
import os
import shlex
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
            one = installer.install(Path(__file__).parent, home, "windows", root=home / "devstack")
            after = json.loads(settings.read_text())
            self.assertEqual(after["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
            self.assertTrue(after["unrelated_setting"])
            self.assertTrue(one["changed"])
            self.assertEqual(installer.install(Path(__file__).parent, home, "windows", root=home / "devstack")["changed"], [])

    def test_installer_names_hooks_of_another_checkout_without_removing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            old = str(home / "moved away" / "devstack")
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            stale = shlex.join([sys.executable, old + "/monitoring/devstack/kpi_monitor.py", "audit-hook", "--host",
                                "devbox", "--runtime", "claude", "--event", "Stop"])
            user = shlex.join([sys.executable, old + "/monitoring/devstack/kpi_monitor.py", "report"])
            settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": stale},
                                                                          {"type": "command", "command": user}]}]}}))
            result = installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            self.assertEqual([old], result["other_checkouts"])
            self.assertIn("scripts/detach.py --from", result["hint"][0])
            commands = [h["command"] for g in json.loads(settings.read_text())["hooks"]["Stop"] for h in g["hooks"]]
            self.assertIn(stale, commands)  # detection only
            self.assertIn(user, commands)
            again = installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            self.assertEqual([old], again["other_checkouts"])  # its own new hooks are never reported

    def test_installer_reports_no_other_checkout_for_its_own_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            result = installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            self.assertNotIn("other_checkouts", result)

    def test_installer_defaults_to_this_checkout_and_backs_up_outside_it(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            settings.write_text(json.dumps({"keep": True}))
            before = sorted(p.name for p in Path(__file__).parent.iterdir())
            installer.install(Path(__file__).parent, home, "devbox", skip_codex_hook=True)
            self.assertEqual(sorted(p.name for p in Path(__file__).parent.iterdir()), before)  # nothing copied or backed up here
            stop = json.loads(settings.read_text())["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn(FWD(installer.CHECKOUT / "monitoring/devstack/kpi_monitor.py"), stop)
            self.assertTrue(list((home / ".local/state/devstack/install-backups").glob("*/*settings.json")))

    def test_installer_root_outside_home_and_invalid_input_writes_nothing(self):
        with tempfile.TemporaryDirectory() as home_dir, tempfile.TemporaryDirectory() as root_dir:
            home, root = Path(home_dir), Path(root_dir) / "setup"
            (home / ".claude").mkdir()
            settings = home / ".claude/settings.json"
            settings.write_text("{not json")
            with self.assertRaisesRegex(RuntimeError, "nothing was changed"):
                installer.install(Path(__file__).parent, home, "devbox", root=root, skip_codex_hook=True)
            self.assertFalse(root.exists())
            self.assertEqual(settings.read_text(), "{not json")
            settings.write_text("{}")
            result = installer.install(Path(__file__).parent, home, "devbox", root=root, skip_codex_hook=True)
            self.assertIn(str(root.resolve() / "monitoring/devstack/kpi_monitor.py"), result["changed"])
            self.assertIn(".claude/settings.json", result["changed"])
            self.assertTrue((root / "monitoring/devstack/kpi_monitor.py").is_file())

    def test_installer_rejects_wrong_shapes_before_any_write(self):
        bad = ["[]", '{"hooks": []}', '{"hooks": {"Stop": {}}}', '{"hooks": {"Stop": [1]}}',
               '{"hooks": {"Stop": [{"hooks": {}}]}}', '{"hooks": {"Stop": [{"hooks": [1]}]}}',
               '{"hooks": {"Stop": [{"hooks": [{"command": 5}]}]}}', '{"hooks": {"PostToolUse": [{"matcher": 3, "hooks": []}]}}']
        for text in bad + ["incomplete marker"]:
            with self.subTest(settings=text), tempfile.TemporaryDirectory() as home_dir, tempfile.TemporaryDirectory() as root_dir:
                home, root = Path(home_dir), Path(root_dir) / "setup"
                (home / ".claude").mkdir()
                settings = home / ".claude/settings.json"
                settings.write_text("{}" if text == "incomplete marker" else text)
                if text == "incomplete marker":
                    (home / ".claude/CLAUDE.md").write_text("<!-- devstack-kpi:start -->\nno end\n")
                before = sorted(str(p) for p in home.rglob("*"))
                with self.assertRaisesRegex(RuntimeError, "nothing was changed"):
                    installer.install(Path(__file__).parent, home, "devbox", root=root, skip_codex_hook=True)
                self.assertFalse(root.exists())
                self.assertEqual(sorted(str(p) for p in home.rglob("*")), before)  # no backups, no new files

    def test_installer_checks_the_active_retro_marker_before_any_write(self):
        for version in ("1.0.0", "1.1.0"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as home_dir, tempfile.TemporaryDirectory() as root_dir:
                home, root = Path(home_dir), Path(root_dir)
                relative = "skills/retro/SKILL.md" if version == "1.1.0" else "skills/devstack/references/retro.md"
                retro = root / relative
                retro.parent.mkdir(parents=True)
                retro.write_text("# Retro\n<!-- devstack-kpi:start -->\nno end marker\n")
                (root / "AGENTS.md").write_text("Keep global guidance.\n")
                (root / "manifest.json").write_text(json.dumps({"active_stack": {"name": "devstack", "version": version,
                    "global_skills": ["devstack", "retro"] if version == "1.1.0" else ["devstack"]}}))
                (home / ".claude").mkdir()
                (home / ".claude/settings.json").write_text("{}")
                before = {p: p.read_bytes() for tree in (home, root) for p in tree.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(RuntimeError, "nothing was changed"):
                    installer.install(Path(__file__).parent, home, "mac", root=root, skip_codex_hook=True)
                after = {p: p.read_bytes() for tree in (home, root) for p in tree.rglob("*") if p.is_file()}
                self.assertEqual(after, before)  # no package copy, no backup, no pointer, no hook
                self.assertFalse((root / "monitoring").exists())

    def test_installer_replaces_a_pre_rename_pointer_block(self):
        old = "Keep me.\n\n<!-- patstack-kpi:start -->\nold pointer\n<!-- patstack-kpi:end -->\nAfter.\n"
        text = installer.with_pointer(old)
        self.assertEqual(text.count("devstack-kpi:start"), 1)
        self.assertNotIn("old pointer", text)
        self.assertTrue(text.startswith("Keep me.") and text.rstrip().endswith("After."))
        self.assertEqual(installer.with_pointer(text), text)

    def test_installer_reads_utf8_instructions_on_any_platform(self):
        # Windows defaults to cp1252, where the UTF-8 bytes of "”" (0x9d) are undefined.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / "devstack/AGENTS.md"
            agents.parent.mkdir(parents=True)
            agents.write_text("DevStack ”kilde” – æøå\n", encoding="utf-8")
            (home / ".claude").mkdir()
            (home / ".claude/settings.json").write_text(json.dumps({"note": "”"}), encoding="utf-8")
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            self.assertIn("”kilde”", agents.read_text(encoding="utf-8"))
            self.assertEqual(json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))["note"], "”")

    def test_installer_adds_one_session_status_hook_when_doctor_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            banner = {"hooks": [{"type": "command", "command": "banner.sh"}]}
            settings.write_text(json.dumps({"hooks": {"SessionStart": [banner]}}))
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            self.assertEqual(json.loads(settings.read_text())["hooks"]["SessionStart"], [banner])  # no doctor shipped yet
            mention = {"hooks": [{"type": "command", "command": "echo setup_doctor.py --hook claude"}]}
            settings.write_text(json.dumps({"hooks": {"SessionStart": [banner, mention]}}))
            doctor = home / "devstack/scripts/setup_doctor.py"
            doctor.parent.mkdir(parents=True)
            doctor.write_text("")
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
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
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            groups = json.loads((home / ".claude/settings.json").read_text())["hooks"]["PostToolUse"]
            self.assertEqual(groups[0], narrow)  # an unrelated narrow hook is preserved
            self.assertEqual(groups[1]["matcher"], "*")  # plus a counter that sees every tool

    def test_installer_removes_a_narrow_kpi_counter_instead_of_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude").mkdir()
            kpi = FWD(home / "devstack/monitoring/devstack/kpi_monitor.py")
            (home / "devstack/monitoring/devstack").mkdir(parents=True)
            (home / "devstack/monitoring/devstack/kpi_monitor.py").write_text("")
            narrow_counter = {"type": "command", "command": f"{FWD(sys.executable)} -B {kpi} audit-hook --host devbox --runtime claude --event PostToolUse"}
            other = {"type": "command", "command": "keep-me"}
            (home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PostToolUse": [
                {"matcher": "Bash", "hooks": [narrow_counter, other]}, {"matcher": "Edit", "hooks": [dict(narrow_counter)]}]}}))
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
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
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
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
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack")
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack")
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
            doctor = home / "devstack/scripts/setup_doctor.py"
            doctor.parent.mkdir(parents=True)
            doctor.write_text("")
            settings = home / ".claude/settings.json"
            settings.parent.mkdir()
            existing = {"hooks": [{"type": "command", "command": f"{FWD(sys.executable)} -B {FWD(doctor)} --host devbox --hook claude"}]}
            settings.write_text(json.dumps({"hooks": {"SessionStart": [existing]}}))
            installer.install(Path(__file__).parent, home, "devbox", root=home / "devstack", skip_codex_hook=True)
            self.assertEqual(json.loads(settings.read_text())["hooks"]["SessionStart"], [existing])

    def test_devstack_installer_only_updates_new_retro_and_preserves_old_overlay(self):
        for version in ["1.0.0", "1.1.0"]:
          for expose in ({}, {"retro": {"body_prefix": "historical retro"}}):
            with self.subTest(version=version, expose=expose), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                root = home / "devstack"
                relative = "skills/retro/SKILL.md" if version == "1.1.0" else "skills/devstack/references/retro.md"
                retro = root / relative
                retro.parent.mkdir(parents=True)
                retro.write_text("# DevStack Retro\nKeep this guidance.\n")
                (root / "AGENTS.md").write_text("Keep global guidance.\n")
                (root / "manifest.json").write_text(json.dumps({"active_stack": {"name": "devstack", "version": version, "global_skills": ["devstack", "retro"] if version == "1.1.0" else ["devstack"]}}))
                overlay = root / "vendor/mattpocock-skills/overlay.json"
                overlay.parent.mkdir(parents=True)
                overlay.write_text(json.dumps({"expose": expose}))
                before = overlay.read_bytes()
                installer.install(Path(__file__).parent, home, "mac", root=home / "devstack")
                self.assertEqual(overlay.read_bytes(), before)
                self.assertIn(installer.POINTER.rstrip(), retro.read_text())
                self.assertIn("Keep this guidance.", retro.read_text())
                other = "skills/devstack/references/retro.md" if version == "1.1.0" else "skills/retro/SKILL.md"
                self.assertFalse((root / other).exists())
                self.assertEqual(installer.install(Path(__file__).parent, home, "mac", root=home / "devstack")["changed"], [])

    def test_legacy_installer_keeps_existing_overlay_render_path(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / "devstack"
            overlay = root / "vendor/mattpocock-skills/overlay.json"
            overlay.parent.mkdir(parents=True)
            overlay.write_text(json.dumps({"expose": {"retro": {"body_prefix": "Keep legacy guidance"}}}))
            script = root / "scripts/mp_skills.py"
            script.parent.mkdir(parents=True)
            script.write_text("def render_skill(name, config):\n    return {'SKILL.md': config['body_prefix'].encode()}\n")
            installer.install(Path(__file__).parent, home, "mac", root=home / "devstack")
            self.assertIn(installer.POINTER.rstrip(), (root / "skills/retro/SKILL.md").read_text())
            self.assertIn("Keep legacy guidance", (root / "skills/retro/SKILL.md").read_text())
            self.assertFalse((root / "skills/devstack").exists())

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
        command = installer.hook_command("C:" + chr(92) + "Users" + chr(92) + "Example" + chr(92) + "python.exe",
                  "C:" + chr(92) + "Users" + chr(92) + "Example" + chr(92) + "monitor.py", "windows", "codex", True)
        self.assertEqual(shlex.split(command)[:2],
                         ["/".join(("C:", "Users", "Example", "python.exe")), "/".join(("C:", "Users", "Example", "monitor.py"))])
        with self.assertRaises(RuntimeError):
            installer.hook_command("C:" + chr(92) + "Users" + chr(92) + "Other User" + chr(92) + "python.exe", "script.py",
                                   "windows", "codex", True)

    def test_pointer_updates_existing_marker_without_touching_other_text(self):
        previous = "keep\n" + installer.MARKER + "\nold\n" + installer.END + "\nafter\n"
        actual = installer.with_pointer(previous)
        self.assertTrue(actual.startswith("keep\n"))
        self.assertTrue(actual.endswith("\nafter\n"))
        self.assertIn(installer.POINTER.rstrip(), actual)



class AggregateExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "kpis.sqlite3"

    def export(self, *args):
        return subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(self.db), "export", *args, "--as-of", NOW],
                              capture_output=True, text=True)

    def test_export_is_counts_only_per_topic_workflow_status_host(self):
        rows = [sample("TKT-41", host="devbox", slices=2, review_rounds=3, nodes=[{"id": "ci", "status": "not_run"}]),
                sample("req-secretish-77", host="devbox", slices=4),
                sample("TKT-43", topic="web", status="failed", verified_success=False, host="mac"),
                sample("TKT-44", topic="web", status="open", ended_at=None, verified_success=None)]
        for row in rows:
            k.record(self.db, row)
        out = self.export("--aggregate")
        self.assertEqual(out.returncode, 0, out.stderr)
        text = out.stdout
        for row in rows:
            self.assertNotIn(row["id"], text)
        self.assertNotRegex(text, r"\d{2}:\d{2}")  # no timestamps finer than a day
        data = json.loads(text)
        self.assertEqual(data["as_of_day"], "2026-10-26")
        groups = {(g["topic"], g["workflow"], g["status"], g["host"]): g for g in data["groups"]}
        api = groups[("api", "development", "completed", "devbox")]
        self.assertEqual((api["count"], api["verified_yes"], api["slices_total"], api["slices_observed"]), (2, 2, 6, 2))
        self.assertEqual((api["review_rounds_total"], api["review_rounds_observed"], api["ci_not_run"]), (3, 1, 1))
        self.assertEqual(groups[("web", "development", "failed", "mac")]["verified_no"], 1)
        self.assertEqual(groups[("web", "development", "open", "unknown")]["verified_unknown"], 1)
        allowed = {"topic", "workflow", "status", "host", "count", "verified_yes", "verified_no", "verified_unknown",
                   "full_send", "full_stop", "other_mode", "slices_total", "slices_observed",
                   "review_rounds_total", "review_rounds_observed", "ci_not_run"}
        for group in data["groups"]:
            self.assertLessEqual(set(group), allowed)
            self.assertTrue(all(isinstance(v, int) for key, v in group.items() if key not in ("topic", "workflow", "status", "host")))

    def test_export_requires_aggregate_and_skips_registry_history(self):
        self.assertEqual(self.export().returncode, 2)
        k.record(self.db, k.registry_snapshot({"id": "t-1", "state": "done", "revision": 1, "created_at": 1760000000,
                                               "updated_at": 1760000100}, "devbox"))
        self.assertEqual(json.loads(self.export("--aggregate").stdout)["groups"], [])

    def test_report_breaks_down_new_observations_by_topic(self):
        rows = [sample("a", slices=2, review_rounds=1), sample("b", slices=4, review_rounds=3, topic="web")]
        report = k.report(rows, NOW)
        self.assertEqual(report["by_topic"]["api"]["slices"]["mean"], 2)
        self.assertEqual(report["by_topic"]["web"]["review_rounds"]["mean"], 3)
        self.assertEqual(report["overall"]["slices"]["count"], 2)
        with self.assertRaises(ValueError):
            k.validate(sample(slices=-1))


class TargetsTests(unittest.TestCase):
    """Owner-set targets: the scorecard and the hill-climb verdict."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def targets(self, data):
        path = self.dir / "targets.json"
        path.write_text(json.dumps(data))
        return path

    def test_evaluate_reports_pass_miss_unknown_and_the_gap(self):
        rows = k.evaluate({"kvalitet": 90, "security_holes_pct": 0, "median_minutes": 5.5},
                          {"kvalitet": ">=95", "security_holes_pct": "<=0", "median_minutes": "<= 4", "overall": ">=80"})
        self.assertEqual([(r["metric"], r["status"], r["gap"]) for r in rows],
                         [("kvalitet", "MISS", 5.0), ("security_holes_pct", "PASS", 0.0),
                          ("median_minutes", "MISS", 1.5), ("overall", "UNKNOWN", None)])
        self.assertEqual(rows[2]["target"], "<=4")

    def test_verdict_keeps_only_a_pareto_climb(self):
        specs = {"kvalitet": ">=95", "security_holes_pct": "<=0", "median_minutes": "<=4"}
        rows = lambda **values: k.evaluate(values, specs)
        base = rows(kvalitet=90, security_holes_pct=10, median_minutes=6)
        self.assertEqual(k.climb_verdict(base, rows(kvalitet=93, security_holes_pct=0, median_minutes=6))[0], "KEEP")
        self.assertEqual(k.climb_verdict(base, rows(kvalitet=96, security_holes_pct=0, median_minutes=3.5))[0], "TOP")
        self.assertEqual(k.climb_verdict(base, base)[0], "REVERT")  # no improvement is not a climb
        verdict, reason = k.climb_verdict(rows(kvalitet=93, security_holes_pct=0, median_minutes=6),
                                          rows(kvalitet=99, security_holes_pct=10, median_minutes=3))
        self.assertEqual((verdict, reason), ("REVERT", "worse: security_holes_pct"))
        # a missed security target cannot get worse in exchange for speed
        self.assertEqual(k.climb_verdict(rows(kvalitet=96, security_holes_pct=20, median_minutes=100),
                                         rows(kvalitet=96, security_holes_pct=30, median_minutes=5))[0], "REVERT")
        self.assertEqual(k.climb_verdict(base, rows(security_holes_pct=0, median_minutes=3))[0], "REVERT")  # unknown is never met
        # an unmeasured base proves nothing about a measured candidate
        self.assertEqual(k.climb_verdict(rows(security_holes_pct=0, median_minutes=3),
                                         rows(kvalitet=1, security_holes_pct=0, median_minutes=3))[0], "NOT COMPARABLE")
        self.assertEqual(k.climb_verdict(rows(security_holes_pct=0, median_minutes=3),
                                         rows(kvalitet=99, security_holes_pct=0, median_minutes=3))[0], "NOT COMPARABLE")
        self.assertEqual(k.climb_verdict(rows(median_minutes=3), rows(median_minutes=3))[0], "NOT COMPARABLE")

    def test_zero_tolerance_targets_compare_exact_values(self):
        row = k.evaluate({"security_holes_pct": 100 / 201}, {"security_holes_pct": "<=0"})[0]
        self.assertEqual(row["status"], "MISS")
        self.assertEqual(k.evaluate({"security_holes_pct": 0.004}, {"security_holes_pct": "<=0"})[0]["status"], "MISS")

    def test_rates_below_the_sample_floor_stay_unknown(self):
        rows = k.evaluate({"verified_success_pct": 100.0}, {"verified_success_pct": ">=95"}, {"verified_success_pct": 1}, 3)
        self.assertEqual((rows[0]["status"], rows[0]["n"]), ("UNKNOWN", 1))
        rows = k.evaluate({"verified_success_pct": 100.0}, {"verified_success_pct": ">=95"}, {"verified_success_pct": 3}, 3)
        self.assertEqual(rows[0]["status"], "PASS")

    def test_load_targets_rejects_unknown_metrics_and_bad_specs(self):
        self.assertIsNone(k.load_targets(self.dir / "missing.json"))
        for bad in ({"bench": {"speed": "<=4"}}, {"work": {"median_minutes": "4"}}, {"work_days": 0},
                    {"bench_arm": "../x"}, {"extra": 1}, {"work": {"tasks": ">= 1; rm"}},
                    {"bench": {"overall": ">=" + "9" * 400}}, {"min_samples": 0}):
            with self.assertRaises(ValueError, msg=bad):
                k.load_targets(self.targets(bad))
        loaded = k.load_targets(self.targets({"work": {"tasks": ">=1"}}))
        self.assertEqual((loaded["work_days"], loaded["bench_arm"], loaded["bench"], loaded["min_samples"]), (7, "devstack", {}, 3))

    def test_work_metrics_count_designated_tasks_that_ended_in_the_window(self):
        rows = [sample("in-window", ended_at="2026-10-25T10:00:00+00:00", started_at="2026-10-25T09:30:00+00:00",
                       updated_at="2026-10-25T10:00:00+00:00"),
                sample("too-old", ended_at="2026-10-01T10:02:00+00:00"),
                sample("chat", workflow="discussion", verification="not_applicable",
                       ended_at="2026-10-25T10:00:00+00:00", updated_at="2026-10-25T10:00:00+00:00"),
                sample("open", status="open", ended_at=None, verified_success=None, followup_checked_at=None, updated_at="2026-10-25T10:00:00+00:00")]
        rows = [{key: value for key, value in row.items() if value is not None} for row in rows]
        samples, metrics = k.work_metrics([k.validate(r) for r in rows], NOW, 7)
        self.assertEqual(samples["verified_success_pct"], 1)
        self.assertEqual((metrics["tasks"], metrics["median_minutes"], metrics["verified_success_pct"]), (1, 30.0, 100.0))

    def test_work_targets_judge_unrounded_values(self):
        rows = [sample(f"t{i}", started_at="2026-10-25T10:00:00+00:00", ended_at="2026-10-25T10:04:02.400000+00:00",
                       updated_at="2026-10-25T10:05:00+00:00", verified_success=i < 2) for i in range(3)]
        samples, metrics = k.work_metrics([k.validate(r) for r in rows], NOW, 7)
        self.assertAlmostEqual(metrics["median_minutes"], 4.04)
        rows_out = k.evaluate(metrics, {"median_minutes": "<=4", "verified_success_pct": ">=66.67"}, samples, 2)  # 2 verified durations
        self.assertEqual([r["status"] for r in rows_out], ["MISS", "MISS"])   # 4.04 > 4 and 66.666… < 66.67

    def test_one_unlabelled_task_leaves_a_rate_unknown(self):
        done = dict(started_at="2026-10-25T10:00:00+00:00", ended_at="2026-10-25T10:10:00+00:00",
                    updated_at="2026-10-25T10:10:00+00:00", review_rounds=1)
        rows = [sample(f"t{i}", **done) for i in range(3)]
        rows.append({k: v for k, v in sample("t3", **done).items()
                     if k not in ("verified_success", "handoff", "review_rounds", "human_interventions")})
        samples, metrics = k.work_metrics([k.validate(r) for r in rows], NOW, 7)
        specs = {"verified_success_pct": ">=100", "autonomous_resolution_pct": ">=100",
                 "unexpected_handoff_pct": "<=0", "review_rounds_mean": "<=1"}
        statuses = {r["metric"]: r["status"] for r in k.evaluate(metrics, specs, samples, 3)}
        self.assertEqual(set(statuses.values()), {"UNKNOWN"}, statuses)   # never PASS on three of four

    def test_node_targets_are_pass_rates_where_not_run_is_a_miss(self):
        nodes = lambda *statuses: [{"id": "vault-context", "status": st} for st in statuses]
        rows = [sample(f"t{i}", started_at="2026-10-25T10:00:00+00:00", ended_at="2026-10-25T10:10:00+00:00",
                       updated_at="2026-10-25T10:10:00+00:00", nodes=node) for i, node in
                enumerate((nodes("pass"), nodes("pass"), nodes("not_run"), nodes("blocked"), []))]
        samples, metrics = k.work_metrics([k.validate(r) for r in rows], NOW, 7, ["vault-context", "vault-writeback"])
        self.assertEqual((metrics["node:vault-context"], samples["node:vault-context"]), (50.0, 4))  # the task without it is not counted
        self.assertEqual((metrics["node:vault-writeback"], samples["node:vault-writeback"]), (None, 0))  # never recorded: unknown
        loaded = k.load_targets(self.targets({"work": {"node:vault-context": ">=95"}, "packs": {"demo": {"repos_mapped_pct": ">=90"}}}))
        self.assertEqual(loaded["packs"], {"demo": {"repos_mapped_pct": ">=90"}})
        for bad in ({"work": {"node:": ">=1"}}, {"work": {"node:Bad_Id": ">=1"}}, {"bench": {"node:x": ">=1"}},
                    {"packs": {"demo": {"x": "90"}}}, {"packs": {"../x": {}}}, {"packs": []},
                    {"work": None}, {"bench": []}, {"packs": None}):
            with self.assertRaises(ValueError, msg=bad):
                k.load_targets(self.targets(bad))

    def test_scorecard_cli_reads_the_latest_bench_scoreboard_for_the_arm(self):
        runs = self.dir / "runs"
        for name, kvalitet in (("20261101T000000Z", 80), ("20261102T000000Z", 96)):
            (runs / name).mkdir(parents=True)
            (runs / name / "scoreboard.json").write_text(json.dumps({"complete": True, "summary": {"devstack": {"exact": {"kvalitet": kvalitet, "security_holes_pct": 10}}}}))
        path = self.targets({"bench": {"kvalitet": ">=95", "security_holes_pct": "<=0"}, "work": {"tasks": ">=1"}})
        db = self.dir / "kpis.sqlite3"
        out = subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(db), "scorecard", "--targets", str(path),
                              "--runs", str(runs), "--as-of", NOW, "--json"], capture_output=True, text=True, check=True)
        card = json.loads(out.stdout)
        self.assertEqual((card["bench_run"], card["met"], card["total"]), ("20261102T000000Z", 1, 3))
        self.assertEqual([r["status"] for r in card["bench"]], ["PASS", "MISS"])
        text = subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(db), "scorecard", "--targets", str(path),
                               "--runs", str(runs), "--as-of", NOW], capture_output=True, text=True, check=True).stdout
        self.assertTrue(text.startswith("🎯 targets 1/3 met · MISS tasks 0 (>=1); MISS security_holes_pct 10 (<=0)"), text)
        (runs / "20261103T000000Z").mkdir()  # newest, but incomplete: its values prove nothing
        (runs / "20261103T000000Z" / "scoreboard.json").write_text(json.dumps({"complete": False, "summary": {"devstack": {"kvalitet": 99, "security_holes_pct": 0}}}))
        card = json.loads(subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(db), "scorecard", "--targets", str(path),
                                          "--runs", str(runs), "--as-of", NOW, "--json"], capture_output=True, text=True, check=True).stdout)
        self.assertEqual((card["bench_run"], card["bench_complete"], [r["status"] for r in card["bench"]]),
                         ("20261103T000000Z", False, ["UNKNOWN", "UNKNOWN"]))
        (runs / "20261104T000000Z").mkdir()  # complete but scored before exact values: rounded legacy values prove nothing
        (runs / "20261104T000000Z" / "scoreboard.json").write_text(json.dumps({"complete": True, "summary": {"devstack": {"kvalitet": 100, "security_holes_pct": 0}}}))
        card = json.loads(subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(db), "scorecard", "--targets", str(path),
                                          "--runs", str(runs), "--as-of", NOW, "--json"], capture_output=True, text=True, check=True).stdout)
        self.assertEqual([r["status"] for r in card["bench"]], ["UNKNOWN", "UNKNOWN"])
        none = subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(db), "scorecard", "--targets", str(self.dir / "no.json")],
                              capture_output=True, text=True, check=True).stdout
        self.assertIn("No targets set", none)

    def test_report_carries_the_scorecard_line_and_survives_a_broken_targets_file(self):
        db = self.dir / "kpis.sqlite3"
        good = self.targets({"work": {"tasks": ">=1"}})
        report = lambda path: json.loads(subprocess.run([sys.executable, str(Path(k.__file__)), "--db", str(db), "report",
                                                         "--targets", str(path)], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(report(good)["scorecard"]["line"], "🎯 targets 0/1 met · MISS tasks 0 (>=1)")
        broken = self.dir / "broken.json"
        broken.write_text("{not json")
        self.assertEqual(report(broken)["scorecard"], {"error": "targets file invalid"})
        self.assertIsNone(report(self.dir / "absent.json")["scorecard"])


if __name__ == "__main__":
    unittest.main()
