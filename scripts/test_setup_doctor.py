"""setup_doctor tests in a temporary home; never touch live clients."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

FWD = lambda path: str(path).replace("\\", "/")
HOST = "windows" if os.name == "nt" else "devbox"

spec = importlib.util.spec_from_file_location("setup_doctor", Path(__file__).with_name("setup_doctor.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

# Owner-specific shell hooks some users wire themselves; Patstack ships none of them.
USER_HOOKS = ("block-destructive.py", "read-size-guard.sh", "supabase-deploy-gate.sh", "bash-batch-nudge.sh")


class CodexTrustHashTests(unittest.TestCase):
    """Hashes Codex 0.167 itself wrote to config.toml when a person chose 'Trust all and continue'."""

    def test_matches_hashes_codex_recorded(self):
        guard = {"type": "command", "command": "python3 /opt/patstack/tools/merge_guard.py"}
        self.assertEqual(d.codex_hook_hash("pre_tool_use", "Bash", guard),  # algorithm verified against Codex CLI 0.167
                         "sha256:3ce1f59d6a431667228513bc4865182bfed31e46d202c0ead43f74135c33bc0f")
        # A changed field changes the hash, so a stale trust entry is caught.
        self.assertNotEqual(d.codex_hook_hash("pre_tool_use", "Bash", dict(guard, timeout=30)),
                            d.codex_hook_hash("pre_tool_use", "Bash", guard))
        self.assertEqual(d.codex_hook_hash("pre_tool_use", "Bash", dict(guard, timeout=600)),
                         d.codex_hook_hash("pre_tool_use", "Bash", guard))  # 600 is the default
        # Codex: unwrap_or(600).max(1), so a present 0 is 1, not the default.
        self.assertEqual(d.codex_hook_hash("pre_tool_use", "Bash", dict(guard, timeout=0)),
                         d.codex_hook_hash("pre_tool_use", "Bash", dict(guard, timeout=1)))
        self.assertIsNone(d.codex_hook_hash("pre_tool_use", "Bash", dict(guard, timeout="30")))

    def test_no_toml_reader_means_unknown_never_ok(self):
        import builtins
        real_import = builtins.__import__
        text = '[hooks.state."/h/.codex/hooks.json:pre_tool_use:0:0"]\ntrusted_hash = "x"\nenabled = false # off\n'
        with unittest.mock.patch.object(builtins, "__import__",
                                        lambda name, *a, **k: (_ for _ in ()).throw(ImportError) if name == "tomllib"
                                        else real_import(name, *a, **k)):
            self.assertIsNone(d.codex_hook_states(text))  # Python 3.9/3.10: unknown, so WARN
        if sys.version_info >= (3, 11):
            self.assertEqual(d.codex_hook_states(text), {"/h/.codex/hooks.json:pre_tool_use:0:0":
                                                         {"trusted_hash": "x", "enabled": False}})
            self.assertIsNone(d.codex_hook_states(text + "broken = [\n"))


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / "patstack"
        (self.root / "skills/patstack").mkdir(parents=True)
        (self.root / "skills/patstack/SKILL.md").write_text("# Patstack\n")
        (self.root / "scripts").mkdir()
        (self.root / "tools").mkdir()
        (self.root / "tools/merge_guard.py").write_text("")
        shutil.copy(Path(__file__).with_name("setup_doctor.py"), self.root / "scripts/setup_doctor.py")
        shutil.copy(Path(__file__).with_name("skill_mirrors.py"), self.root / "scripts/skill_mirrors.py")
        (self.root / "AGENTS.md").write_text("Read patstack.\n")
        for client in (".claude", ".codex", ".agents"):
            (self.home / client).mkdir()
        if os.name == "nt":
            self.windows_mirrors()
            for relative in (".claude/CLAUDE.md", ".codex/AGENTS.md"):
                shutil.copyfile(self.root / "AGENTS.md", self.home / relative)
        else:
            os.symlink(self.root / "skills", self.home / ".claude/skills")
            os.symlink(self.root / "skills", self.home / ".agents/skills")
            os.symlink(self.root / "AGENTS.md", self.home / ".claude/CLAUDE.md")
            os.symlink(self.root / "AGENTS.md", self.home / ".codex/AGENTS.md")
        (self.home / ".claude.json").write_text("{}")  # Claude Code's own state: the client is in use
        (self.home / ".codex/config.toml").write_text("")  # Codex's own state
        (self.home / ".local/bin").mkdir(parents=True)
        (self.home / ".local/bin" / ("ticket-ref.cmd" if os.name == "nt" else "ticket-ref")).write_text("fixture\n")
        self.hooks = self.home / ".claude/hooks"
        self.hooks.mkdir()
        for name in USER_HOOKS:
            (self.hooks / name).write_text("#!/bin/sh\n")
        self.write_claude()
        self.write_codex()

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self):
        return f"{FWD(sys.executable)} {FWD(self.root)}/tools/merge_guard.py"

    def write_claude(self, extra=None, guard=True):
        pre = [{"type": "command", "command": str(self.hooks / n)} for n in USER_HOOKS[:3]]
        if guard:
            pre.append({"type": "command", "command": self.guard()})
        hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": pre}],
                 "PostToolUse": [{"hooks": [{"type": "command", "command": str(self.hooks / USER_HOOKS[3])}]}]}
        if extra:
            hooks.setdefault("SessionStart", []).append({"hooks": [{"type": "command", "command": extra}]})
        (self.home / ".claude/settings.json").write_text(json.dumps({"hooks": hooks}))

    def write_codex(self, guard=True, trusted=True, state=None):
        hooks_file = self.home / ".codex/hooks.json"
        hook = {"type": "command", "command": self.guard()}
        groups = [{"matcher": "Bash", "hooks": [hook]}] if guard else []
        hooks_file.write_text(json.dumps({"hooks": {"PreToolUse": groups}}))
        if state is None:
            state = f'trusted_hash = "{d.codex_hook_hash("pre_tool_use", "Bash", hook)}"\n' if trusted else None
        key = json.dumps(f"{hooks_file}:pre_tool_use:0:0")
        trust = f'[hooks.state.{key}]\n{state}' if state else ""
        (self.home / ".codex/config.toml").write_text('model = "x"\n\n[hooks.state]\n\n' + trust)

    def statuses(self, check=None, host=HOST):
        report = d.run(self.root, self.home, host)
        return report, {(r["check"], r["status"]) for r in report.rows if check is None or r["check"] == check}

    def test_healthy_setup_has_no_fail_or_warn(self):
        report, rows = self.statuses()
        self.assertFalse(report.failed, report.rows)
        self.assertFalse([r for r in report.rows if r["status"] == "WARN"], report.rows)
        self.assertIn(("claude merge guard", "OK"), rows)
        self.assertIn(("codex merge guard", "OK"), rows)

    def test_codex_merge_guard_must_be_wired_and_trusted(self):
        # Codex runs a hook only after the person trusts it; an untrusted one is skipped silently.
        self.write_codex(trusted=False)
        _, rows = self.statuses("codex merge guard")
        self.assertEqual(rows, {("codex merge guard", "WARN")})
        report, _ = self.statuses()
        self.assertIn("Trust all and continue", " ".join(r["detail"] for r in report.rows))
        self.write_codex(guard=False)
        self.assertEqual(self.statuses("codex merge guard")[1], {("codex merge guard", "WARN")})
        (self.home / ".codex/hooks.json").unlink()
        self.assertEqual(self.statuses("codex merge guard")[1], {("codex merge guard", "WARN")})
        # Codex trusts only the exact current hook and never runs a disabled one.
        for state, advice in (('trusted_hash = ""\n', "changed"), ('trusted_hash = "sha256:obsolete"\n', "changed"),
                              ("trusted_hash = false\n", "not trusted"), ("enabled = false\n", "turned off")):
            self.write_codex(state=state)
            report, rows = self.statuses("codex merge guard")
            self.assertEqual(rows, {("codex merge guard", "WARN")}, state)
            self.assertIn(advice, " ".join(r["detail"] for r in report.rows if r["check"] == "codex merge guard"))
        good = d.codex_hook_hash("pre_tool_use", "Bash", {"type": "command", "command": self.guard()})
        self.write_codex(state=f'trusted_hash = "{good}"\nenabled = false\n')
        self.assertEqual(self.statuses("codex merge guard")[1], {("codex merge guard", "WARN")})
        (self.home / ".codex/config.toml").write_text("[hooks.state\n")  # unreadable TOML
        self.assertEqual(self.statuses("codex merge guard")[1], {("codex merge guard", "WARN")})
        # A correct hash with enabled = false and a trailing comment is still off.
        self.write_codex(state=f'trusted_hash = "{good}"\nenabled = false # intentionally off\n')
        self.assertEqual(self.statuses("codex merge guard")[1], {("codex merge guard", "WARN")})
        # Trust recorded for another hook position does not count.
        self.write_codex()
        toml = self.home / ".codex/config.toml"
        toml.write_text(toml.read_text().replace(":pre_tool_use:0:0", ":pre_tool_use:1:0"))
        self.assertEqual(self.statuses("codex merge guard")[1], {("codex merge guard", "WARN")})

    def test_template_pack_and_bench_are_reported(self):
        _, rows = self.statuses()
        self.assertIn(("template .claude", "INFO"), rows)  # hand-written instructions still work
        self.assertIn(("project pack", "INFO"), rows)
        self.assertIn(("bench", "INFO"), rows)
        (self.root / "AGENTS.md").write_text(d.TEMPLATE_MARKER + "\nRead patstack.\n")
        if os.name == "nt":
            for relative in (".claude/CLAUDE.md", ".codex/AGENTS.md"):
                shutil.copyfile(self.root / "AGENTS.md", self.home / relative)
        (self.root / "project-packs/sample").mkdir(parents=True)
        (self.root / "project-packs/sample/INDEX.md").write_text("# Pack\n")
        (self.root / "bench").mkdir()
        (self.root / "bench/bench.py").write_text("")
        report, rows = self.statuses()
        for check in ("template .claude", "template .codex", "project pack", "bench"):
            self.assertIn((check, "OK"), rows)
        self.assertFalse(report.failed)
        real = d.run(d.SELF_ROOT, self.home, "devbox")  # this checkout ships the pack and the bench
        found = {r["check"]: r["status"] for r in real.rows}
        self.assertEqual(found["bench"], "OK")
        self.assertEqual(found["project pack"], "OK" if list(d.SELF_ROOT.glob("project-packs/*/INDEX.md")) else "INFO")

    def test_missing_merge_guard_warns(self):
        self.write_claude(guard=False)
        report, rows = self.statuses("claude merge guard")
        self.assertFalse(report.failed)
        self.assertEqual(rows, {("claude merge guard", "WARN")})

    def test_merge_guard_must_run_for_bash_with_a_real_interpreter(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        guard = {"type": "command", "command": self.guard()}
        cases = {"read only": [{"matcher": "Read", "hooks": [guard]}],
                 "no interpreter": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"python-does-not-exist {FWD(self.root)}/tools/merge_guard.py"}]}],
                 "guard file gone": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"{FWD(sys.executable)} {FWD(self.home)}/elsewhere/merge_guard.py"}]}],
                 "not python": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"/usr/bin/true {FWD(self.root)}/tools/merge_guard.py"}]}],
                 "python -c": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"{FWD(sys.executable)} -c pass {FWD(self.root)}/tools/merge_guard.py"}]}],
                 "python -m": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"{FWD(sys.executable)} -m merge_guard {FWD(self.root)}/tools/merge_guard.py"}]}],
                 "shell tail": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"{FWD(sys.executable)} {FWD(self.root)}/tools/merge_guard.py ; true"}]}]}
        for name, groups in cases.items():
            with self.subTest(name):
                settings.write_text(json.dumps({"hooks": {**data["hooks"], "PreToolUse": groups}}))
                _, rows = self.statuses("claude merge guard")
                self.assertEqual(rows, {("claude merge guard", "WARN")})
        flagged = {"type": "command", "command": f"{FWD(sys.executable)} -B -u {FWD(self.root)}/tools/merge_guard.py"}
        settings.write_text(json.dumps({"hooks": {**data["hooks"], "PreToolUse": [{"matcher": "Bash", "hooks": [flagged]}]}}))
        self.assertEqual(self.statuses("claude merge guard")[1], {("claude merge guard", "OK")})
        for matcher in ("Read|Bash", "*", None, ".*"):
            with self.subTest(matcher=matcher):
                group = {"hooks": [guard]} if matcher is None else {"matcher": matcher, "hooks": [guard]}
                settings.write_text(json.dumps({"hooks": {**data["hooks"], "PreToolUse": [group]}}))
                _, rows = self.statuses("claude merge guard")
                self.assertEqual(rows, {("claude merge guard", "OK")})

    @unittest.skipIf(os.name == "nt", "POSIX shell stand-in")
    def test_a_placeholder_interpreter_that_cannot_run_is_not_a_guard(self):
        fake = self.home / "bin/python3"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\nexit 9\n")  # like the Windows Store placeholder, which exits 9009
        fake.chmod(0o755)
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        hook = {"type": "command", "command": f"{fake} {FWD(self.root)}/tools/merge_guard.py"}
        settings.write_text(json.dumps({"hooks": {**data["hooks"], "PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}}))
        self.assertEqual(self.statuses("claude merge guard")[1], {("claude merge guard", "WARN")})

    def test_the_probe_starts_python_with_the_hooks_own_flags(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        hook = {"type": "command", "command": f"{FWD(sys.executable)} -E {FWD(self.root)}/tools/merge_guard.py"}
        settings.write_text(json.dumps({"hooks": {**data["hooks"], "PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}}))
        with mock.patch.dict(os.environ, {"PYTHONHOME": str(self.home / "no-such-python-home")}):
            self.assertEqual(self.statuses("claude merge guard")[1], {("claude merge guard", "OK")})  # -E ignores it

    def test_a_byte_order_mark_warns_but_still_reads(self):
        settings = self.home / ".claude/settings.json"
        settings.write_bytes(b"\xef\xbb\xbf" + settings.read_bytes())
        report, rows = self.statuses()
        self.assertIn(("claude settings", "WARN"), rows)
        self.assertIn(("claude merge guard", "OK"), rows)
        self.assertFalse(report.failed)

    def test_quoted_windows_style_guard_command_is_recognised(self):
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        quoted = {"type": "command", "command": f'"{sys.executable}" "{self.root / "tools/merge_guard.py"}"'}
        settings.write_text(json.dumps({"hooks": {**data["hooks"], "PreToolUse": [{"matcher": "Bash", "hooks": [quoted]}]}}))
        windows_split = lambda command: shlex.split(command, posix=False)  # what split() does on Windows: quotes stay
        with mock.patch.object(d, "split", windows_split):
            self.assertEqual(self.statuses("claude merge guard")[1], {("claude merge guard", "OK")})

    def test_broken_hook_path_fails(self):
        self.write_claude(extra=str(self.hooks / "gone.sh"))
        report, _ = self.statuses()
        self.assertTrue(any(r["status"] == "FAIL" and "gone.sh" in r["detail"] for r in report.rows))

    def test_retired_hooks_warn_in_both_clients(self):
        (self.hooks / "agent-work-session-ticket.py").write_text("")
        kpi = self.root / "monitoring/patstack/kpi_monitor.py"
        kpi.parent.mkdir(parents=True)
        kpi.write_text("")
        self.write_claude(extra=f"{FWD(sys.executable)} {FWD(kpi)} audit-hook --host devbox --runtime claude --event Stop")
        settings = self.home / ".claude/settings.json"
        data = json.loads(settings.read_text())
        data["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": str(self.hooks / "agent-work-session-ticket.py")}]}]
        settings.write_text(json.dumps(data))
        doctor = f"{FWD(sys.executable)} {FWD(self.root)}/scripts/setup_doctor.py --host devbox --hook codex"
        (self.home / ".codex/hooks.json").write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": doctor}]}]}}))
        report, _ = self.statuses()
        warns = [r["detail"] for r in report.rows if r["status"] == "WARN"]
        for name in ("agent-work-session-ticket.py", "kpi_monitor.py", "setup_doctor.py --host devbox --hook"):
            self.assertTrue(any(name in w for w in warns), (name, warns))
        self.assertFalse(report.failed)

    def test_owner_safety_hooks_are_not_judged(self):
        settings = self.home / ".claude/settings.json"
        settings.write_text(settings.read_text().replace("read-size-guard.sh", "block-destructive.py"))
        report, _ = self.statuses()
        self.assertFalse([r for r in report.rows if r["status"] in ("WARN", "FAIL")], report.rows)

    def test_disable_all_hooks_fails(self):
        settings = self.home / ".claude/settings.json"
        settings.write_text(json.dumps({**json.loads(settings.read_text()), "disableAllHooks": True}))
        report, rows = self.statuses("claude hooks")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("claude hooks", "FAIL")})

    def test_codex_hooks_file_is_checked_when_present(self):
        (self.home / ".codex/hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": str(self.hooks / "gone.sh")}]}]}}))
        report, _ = self.statuses()
        self.assertTrue(any(r["check"] == "codex hook" and r["status"] == "FAIL" for r in report.rows))
        (self.home / ".codex/hooks.json").write_text("{not json")
        _, rows = self.statuses("codex hooks")
        self.assertEqual(rows, {("codex hooks", "FAIL")})

    def client_rows(self, clients=None, which=lambda name: None):
        report = d.run(self.root, self.home, HOST, clients=clients, which=which)
        return report, report.rows

    def test_claude_only_install_has_no_codex_fail_or_warn(self):
        (self.home / ".codex/config.toml").unlink()
        shutil.rmtree(self.home / ".agents")
        report, rows = self.client_rows()
        self.assertFalse(report.failed, rows)
        codex = [r for r in rows if "codex" in r["check"] or r["check"] == "skills .agents"]
        self.assertTrue(codex)
        self.assertEqual({"INFO"}, {r["status"] for r in codex}, codex)

    def test_codex_only_install_has_no_claude_fail_or_warn(self):
        (self.home / ".claude.json").unlink()
        shutil.rmtree(self.home / ".claude")
        report, rows = self.client_rows()
        self.assertFalse(report.failed, rows)
        claude = [r for r in rows if "claude" in r["check"]]
        self.assertTrue(claude)
        self.assertEqual({"INFO"}, {r["status"] for r in claude}, claude)

    def test_both_clients_are_checked_when_both_are_in_use(self):
        report, rows = self.client_rows()
        found = {(r["check"], r["status"]) for r in rows}
        for check in ("skills .claude", "skills .agents", "instructions .claude", "instructions .codex", "claude merge guard"):
            self.assertIn((check, "OK"), found)
        self.assertFalse(report.failed)

    def test_explicit_clients_override_detection(self):
        shutil.rmtree(self.home / ".agents")
        (self.home / ".codex/config.toml").unlink()
        report, _ = self.client_rows(clients=["claude", "codex"])
        self.assertIn(("skills .agents", "FAIL"), {(r["check"], r["status"]) for r in report.rows})
        report, _ = self.client_rows(clients=["claude"])
        self.assertFalse(report.failed)

    def test_detection_uses_binaries_or_client_state_only(self):
        (self.home / ".claude.json").unlink()
        (self.home / ".codex/config.toml").unlink()
        self.assertEqual([], d.detect_clients(self.home, which=lambda name: None))
        self.assertEqual(["codex"], d.detect_clients(self.home, which=lambda name: "/bin/x" if name == "codex" else None))
        report, rows = self.client_rows()  # nothing found: both are checked rather than silently skipped
        self.assertIn(("clients", "INFO"), {(r["check"], r["status"]) for r in rows})
        self.assertIn(("claude merge guard", "OK"), {(r["check"], r["status"]) for r in rows})

    @unittest.skipIf(os.name == "nt", "POSIX linked installation; Windows uses mirrors")
    def test_per_skill_links_are_accepted(self):
        os.unlink(self.home / ".claude/skills")
        (self.home / ".claude/skills").mkdir()
        os.symlink(self.root / "skills/patstack", self.home / ".claude/skills/patstack")  # published layout
        _, rows = self.statuses("skills .claude")
        self.assertEqual(rows, {("skills .claude", "OK")})

    def test_default_root_is_the_tree_containing_the_script(self):
        out = subprocess.run([sys.executable, str(self.root / "scripts/setup_doctor.py"), "--host", "devbox",
                              "--home", str(self.home), "--json"], capture_output=True, text=True)
        source = [r for r in json.loads(out.stdout) if r["check"] == "source"][0]
        self.assertEqual((source["status"], Path(source["detail"]).resolve()), ("OK", self.root.resolve()))

    def test_every_skill_must_resolve(self):
        (self.root / "skills/review").mkdir()
        (self.root / "skills/review/SKILL.md").write_text("# Review\n")
        if os.name != "nt":
            os.unlink(self.home / ".claude/skills")
            (self.home / ".claude/skills").mkdir()
            os.symlink(self.root / "skills/patstack", self.home / ".claude/skills/patstack")  # review not linked
        report, rows = self.statuses("skills .claude")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("skills .claude", "FAIL")})
        self.assertIn("review", [r["detail"] for r in report.rows if r["check"] == "skills .claude"][0])

    def windows_mirrors(self):
        import skill_mirrors
        for client in (".claude/skills", ".agents/skills"):
            path = self.home / client
            if path.is_symlink():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
            path.mkdir()
        skill_mirrors.apply((self.root / "skills").resolve(), self.home, self.home / "mirror-backup")
        return skill_mirrors

    def windows_rows(self):
        report = d.run(self.root, self.home, "windows")
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
        details = [r["detail"] for r in d.run(self.root, self.home, "windows").rows if r["check"] == "skills .claude"]
        self.assertTrue(details[0].startswith("1 source link(s) use syntax the mirror tool cannot rewrite"), details)

    def test_windows_mirror_with_broken_link_warns(self):
        mirrors = self.windows_mirrors()
        (self.root / "skills/patstack/SKILL.md").write_text("# Patstack\n[gone](missing.md)\n")
        mirrors.apply((self.root / "skills").resolve(), self.home, self.home / "mirror-backup")  # fresh, but the link is dead
        self.assertEqual(self.windows_rows(), {("skills .claude", "WARN"), ("skills .agents", "WARN")})

    def test_wrong_skill_link_fails(self):
        path = self.home / ".agents/skills"
        if path.is_symlink():
            path.unlink()
        else:
            shutil.rmtree(path)
        path.mkdir()
        report, rows = self.statuses("skills .agents")
        self.assertTrue(report.failed)
        self.assertEqual(rows, {("skills .agents", "FAIL")})

    BOARD = {"account": "team", "workspace": 7, "board": 10, "subitems_board": 20, "first_number": 30001,
             "columns": {"ticket": "num", "status": "status", "person": "person"}, "statuses": {}}

    def board_rows(self, env=None):
        report = d.run(self.root, self.home, HOST, env=env or {})
        return report, {(r["check"], r["status"]) for r in report.rows if r["check"] == "ticket board"}

    def board_detail(self, env=None):
        return next(r["detail"] for r in self.board_rows(env)[0].rows if r["check"] == "ticket board")

    def test_ticket_board_row_follows_config_and_token(self):
        self.assertEqual(self.board_rows()[1], set())                       # no board anywhere: no row
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        (pack / "monday.json").write_text(json.dumps(self.BOARD))
        self.assertEqual(self.board_rows()[1], {("ticket board", "WARN")})  # no token yet
        self.assertIn("no token", self.board_detail())
        token = self.home / ".config/patstack/monday-token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text("t.o.k")
        if os.name != "nt":
            token.chmod(0o644)
            self.assertEqual(self.board_rows()[1], {("ticket board", "WARN")})  # readable by others
            token.chmod(0o600)
        report, rows = self.board_rows()
        self.assertEqual(rows, {("ticket board", "OK")})
        self.assertNotIn("t.o.k", json.dumps(report.rows))                  # the token is never shown

    def test_a_broken_board_config_warns_even_with_a_good_token(self):
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        token = self.home / ".config/patstack/monday-token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text("t.o.k")
        token.chmod(0o600)
        for broken in ("{", "[]", "{}", json.dumps(dict(self.BOARD, workspace=True))):
            with self.subTest(broken=broken):
                (pack / "monday.json").write_text(broken)
                self.assertEqual(self.board_rows()[1], {("ticket board", "WARN")})
                self.assertIn("configuration is broken", self.board_detail())
        (pack / "monday.json").unlink()
        override = {"PATSTACK_MONDAY_CONFIG": str(self.home / "nowhere.json")}  # an override that points nowhere
        self.assertIn("configuration is broken", self.board_detail(override))
        (self.home / "bad.json").write_text("{")
        self.assertIn("configuration is broken", self.board_detail({"PATSTACK_MONDAY_CONFIG": str(self.home / "bad.json")}))

    @unittest.skipIf(os.name == "nt", "dangling symlinks require privileges on Windows; run on Linux")
    def test_dangling_board_configs_warn(self):
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        (self.home / ".config/patstack").mkdir(parents=True)
        (pack / "monday.json").symlink_to(self.home / "gone.json")          # a dangling bundled config
        self.assertIn("configuration is broken", self.board_detail())
        (pack / "monday.json").unlink()
        self.assertEqual(self.board_rows()[1], set())
        private = self.home / ".config/patstack/monday.json"
        private.symlink_to(self.home / "gone.json")                        # a dangling private config
        self.assertIn("configuration is broken", self.board_detail())
        private.unlink()

    def test_a_token_that_cannot_be_used_warns(self):
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        (pack / "monday.json").write_text(json.dumps(self.BOARD))
        token = self.home / ".config/patstack/monday-token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_bytes(b"\xff\xfe")                                      # not UTF-8
        self.assertIn("cannot be used", self.board_detail())
        token.write_text("")                                                # empty
        self.assertIn("cannot be used", self.board_detail())

    @unittest.skipIf(os.name == "nt", "dangling symlinks require privileges on Windows; run on Linux")
    def test_a_dangling_token_link_warns(self):
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        (pack / "monday.json").write_text(json.dumps(self.BOARD))
        token = self.home / ".config/patstack/monday-token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.symlink_to(self.home / "gone")
        self.assertIn("link to nothing", self.board_detail())

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX permissions as a normal user")
    def test_folders_that_cannot_be_read_warn_and_never_crash(self):
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        (pack / "monday.json").write_text(json.dumps(self.BOARD))
        config = self.home / ".config/patstack"
        config.mkdir(parents=True, exist_ok=True)
        for locked in (config, pack, pack.parent):
            with self.subTest(locked=locked.name):
                locked.chmod(0)
                try:
                    report, rows = self.board_rows()
                finally:
                    locked.chmod(0o700)
                self.assertEqual(rows, {("ticket board", "WARN")})
                if locked == config:
                    self.assertIn(("preferences", "WARN"), {(r["check"], r["status"]) for r in report.rows})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on Windows")
    def test_fifos_where_files_belong_warn_without_blocking(self):
        pack = self.root / "project-packs/sample"
        pack.mkdir(parents=True)
        config = self.home / ".config/patstack"
        config.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        os.mkfifo(pack / "monday.json")
        self.assertIn("configuration is broken", self.board_detail())
        (pack / "monday.json").unlink()
        (pack / "monday.json").write_text(json.dumps(self.BOARD))
        os.mkfifo(config / "monday-token")
        self.assertIn("cannot be used", self.board_detail())
        os.mkfifo(config / "preferences.json")
        report = d.run(self.root, self.home, HOST, env={})
        self.assertIn(("preferences", "WARN"), {(r["check"], r["status"]) for r in report.rows})
        self.assertLess(time.monotonic() - started, 5)

    def test_preferences_path_comes_from_the_given_environment(self):
        elsewhere = self.home / "elsewhere.json"
        elsewhere.write_text("{")                                          # an invalid file the real env points to
        status = lambda env: {r["status"] for r in d.run(self.root, self.home, HOST, env=env).rows
                              if r["check"] == "preferences"}
        with mock.patch.dict(os.environ, {"PATSTACK_PREFERENCES": str(elsewhere)}):
            self.assertEqual(status({}), {"INFO"})                         # env={} means: not that variable
            self.assertEqual(status({"PATSTACK_PREFERENCES": str(elsewhere)}), {"WARN"})
            self.assertEqual(status(None), {"WARN"})                       # no env given: this process's own

    @unittest.skipIf(os.name == "nt", "dangling symlinks require privileges on Windows; run on Linux")
    def test_a_dangling_preferences_link_is_unreadable_not_unset(self):
        prefs = self.home / ".config/patstack/preferences.json"
        prefs.parent.mkdir(parents=True, exist_ok=True)
        prefs.symlink_to(self.home / "gone.json")
        report = d.run(self.root, self.home, HOST, env={})
        self.assertIn(("preferences", "WARN"), {(r["check"], r["status"]) for r in report.rows})

    def test_doctor_changes_no_configuration(self):
        def snapshot():
            return {p: p.stat().st_mtime_ns for p in self.home.rglob("*") if p.is_file()}
        before = snapshot()
        with mock.patch("builtins.print"):
            self.assertIn(d.main(["--host", "devbox", "--home", str(self.home)]), (0, 1))
        self.assertEqual(before, snapshot())

    def test_retired_flags_are_refused(self):
        for flag in ("--hook", "--db"):
            out = subprocess.run([sys.executable, str(self.root / "scripts/setup_doctor.py"), "--host", "devbox", flag, "x"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 2, flag)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on Windows")
    def test_fifo_settings_fails_without_blocking(self):
        settings = self.home / ".claude/settings.json"
        settings.unlink()
        os.mkfifo(settings)
        started = time.monotonic()
        report, rows = self.statuses("claude settings")
        self.assertEqual(rows, {("claude settings", "FAIL")})
        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
