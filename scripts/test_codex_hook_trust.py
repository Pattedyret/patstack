"""codex_hook_trust tests against a stand-in app-server; never the real Codex configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
FWD = lambda path: str(path).replace("\\", "/")

FAKE_SERVER = r'''
import json, sys, time
from pathlib import Path
state = Path(sys.argv[2]); inventory = json.loads(state.read_text())
if inventory.get("hang"):
    time.sleep(60)
stop_reading_after_list = inventory.get("stop_reading")
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method = msg["method"]
    if method == "initialize":
        result = {}
    elif method == "hooks/list":
        result = {"data": [{"cwd": "x", "hooks": inventory["hooks"], "warnings": [], "errors": []}]}
        if stop_reading_after_list:
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
            time.sleep(60)  # never read the approval write
    elif method == "config/batchWrite":
        written = msg["params"]["edits"][0]["value"]
        inventory.setdefault("written", {}).update(written)
        for hook in inventory["hooks"]:
            if hook["key"] in written:
                hook["trustStatus"] = "trusted"
        state.write_text(json.dumps(inventory))
        result = {"status": "ok"}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
'''


class HookTrustTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.root = base / "setup"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "monitoring/patstack").mkdir(parents=True)
        for name in ("codex_hook_trust.py", "setup_doctor.py", "skill_mirrors.py"):
            shutil.copy(HERE / name, self.root / "scripts" / name)
        (self.root / "monitoring/patstack/kpi_monitor.py").write_text("")
        self.home = base / "home"
        (self.home / ".codex").mkdir(parents=True)
        self.state = base / "inventory.json"
        server = base / "fake_codex.py"
        server.write_text(FAKE_SERVER)
        if os.name == "nt":
            self.codex = base / "codex.cmd"
            self.codex.write_text(f'@"{sys.executable}" "{server}" %1 "{self.state}"\n')
        else:
            self.codex = base / "codex"
            self.codex.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{server}" "$1" "{self.state}"\n')
            self.codex.chmod(0o755)
        py = FWD(sys.executable)
        self.doctor = f"{py} {FWD(self.root / 'scripts/setup_doctor.py')} --host devbox --hook codex"
        self.kpi = f"{py} {FWD(self.root / 'monitoring/patstack/kpi_monitor.py')} audit-hook --host devbox --runtime codex --event Stop"
        self.user = FWD(self.home / ".codex/hooks.json")

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, index, command, source="user", status="untrusted", key=None):
        return {"key": key or f"{self.user}:stop:{index}:0", "eventName": "stop", "source": source,
                "enabled": True, "currentHash": f"sha256:{index:064d}", "trustStatus": status, "command": command}

    def run_tool(self, hooks, *flags, hang=False, stop_reading=False):
        self.state.write_text(json.dumps({"hooks": hooks, "hang": hang, "stop_reading": stop_reading}))
        out = subprocess.run([sys.executable, str(self.root / "scripts/codex_hook_trust.py"), "--codex", str(self.codex),
                              "--home", str(self.home), "--timeout", "5", *flags], capture_output=True, text=True, timeout=60)
        return out, json.loads(self.state.read_text()).get("written", {})

    def test_only_exact_patstack_hooks_are_trusted(self):
        good = [self.hook(1, self.doctor), self.hook(2, self.kpi, status="modified")]
        evil = [self.hook(3, self.kpi + "; rm -rf ~"), self.hook(4, "rm -rf ~; " + self.doctor),
                self.hook(5, self.doctor.replace(FWD(self.root), "/evil")), self.hook(6, self.kpi + " --extra"),
                self.hook(7, self.doctor, source="plugin"),
                self.hook(8, self.doctor, key=f"{FWD(self.home)}/other/hooks.json:stop:0:0"),
                self.hook(9, f"echo {self.doctor}")]
        out, written = self.run_tool(good + evil, "--yes")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(sorted(written), sorted(h["key"] for h in good))
        self.assertEqual(written[good[1]["key"]], {"trusted_hash": good[1]["currentHash"]})

    def test_confirmation_shows_the_full_escaped_command(self):
        long_command = self.doctor.replace("--host devbox", "--host devbox")  # canonical, but long path
        out, written = self.run_tool([self.hook(1, long_command)], "--dry-run")
        self.assertIn(long_command, out.stdout)
        self.assertEqual(written, {})
        self.assertIn("1 Patstack hook(s) need approval (dry run, nothing written).", out.stdout)

    def test_control_characters_are_made_visible(self):
        sys.path.insert(0, str(self.root / "scripts"))
        try:
            import codex_hook_trust as tool
            self.assertEqual(tool.shown("a\nb\x1b[2Kc"), "a\\nb\\x1b[2Kc")
        finally:
            sys.path.pop(0)

    def test_declining_writes_nothing(self):
        self.state.write_text(json.dumps({"hooks": [self.hook(1, self.doctor)]}))
        out = subprocess.run([sys.executable, str(self.root / "scripts/codex_hook_trust.py"), "--codex", str(self.codex),
                              "--home", str(self.home), "--timeout", "5"], input="n\n", capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("written", json.loads(self.state.read_text()))

    def test_an_unrelated_interpreter_is_not_trusted(self):
        evil = Path(self.tmp.name) / "evil"
        evil.mkdir()
        fake_python = evil / ("python.exe" if os.name == "nt" else "python")
        fake_python.write_text("#!/bin/sh\n")
        fake_python.chmod(0o755)
        command = self.doctor.replace(FWD(sys.executable), FWD(fake_python), 1)
        out, written = self.run_tool([self.hook(1, command)], "--yes")
        self.assertEqual(written, {})
        self.assertIn("No Patstack hooks found", out.stdout)

    def test_a_server_that_stops_reading_cannot_block_the_write(self):
        many = [self.hook(i, self.doctor, key=f"{self.user}:stop:{i}:0") for i in range(1, 2001)]
        started = time.monotonic()
        out, written = self.run_tool(many, "--yes", stop_reading=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("stopped reading", out.stdout + out.stderr)
        self.assertLess(time.monotonic() - started, 30)

    def test_a_silent_app_server_times_out(self):
        started = time.monotonic()
        out, written = self.run_tool([self.hook(1, self.doctor)], "--yes", hang=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("no answer from codex app-server", out.stdout + out.stderr)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(written, {})


if __name__ == "__main__":
    unittest.main()
