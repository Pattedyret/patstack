"""task_steps.py against a local stand-in for the ntfy server; nothing leaves this machine."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import task_steps as steps
from test_task_status import Server

PLAN = """
[x] Map both repos | search and profile endpoints are clear
[>] Independent review | reviewer running
[ ] Mark the PRs ready
"""


class StepsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "notify.json"
        env = mock.patch.dict(os.environ, {"PATSTACK_NOTIFY": str(self.config), "T3CODE_THREAD_ID": ""})
        env.start()
        self.addCleanup(env.stop)
        self.server = Server()
        self.addCleanup(self.server.close)
        self.config.write_text(json.dumps({"url": self.server.url, "topic": "patstack", "host": "mac"}))

    def run_tool(self, text, *args):
        plan = self.root / "plan.txt"
        plan.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = steps.main(["TKT-1", "--file", str(plan), *args])
        return code, out.getvalue(), err.getvalue()

    def test_the_plan_goes_quietly_to_the_board_as_written(self):
        code, out, err = self.run_tool(PLAN, "--project", "invoices", "--thread", "thread-1")
        self.assertEqual((code, out, err), (0, "TKT-1: 1 of 3 steps done, now: Independent review\n", ""))
        sent = self.server.received[0]
        tags = sent.pop("tags")
        self.assertEqual(sent, {
            "topic": "patstack-board", "title": "steps · TKT-1", "priority": 1,
            "message": "1 of 3 steps done, now: Independent review\n"
                       "[x] Map both repos | search and profile endpoints are clear\n"
                       "[>] Independent review | reviewer running\n"
                       "[ ] Mark the PRs ready"})
        self.assertEqual(tags[:3], ["ds:1", "task:TKT-1", "status:steps"])
        self.assertTrue(tags[3].startswith("at:"))
        self.assertEqual(tags[4:], ["project:invoices", "thread:thread-1", "host:mac"])

    def test_the_thread_comes_from_t3_when_not_given(self):
        with mock.patch.dict(os.environ, {"T3CODE_THREAD_ID": "abc-123"}):
            self.run_tool(PLAN)
        self.assertIn("thread:abc-123", self.server.received[0]["tags"])

    def test_standard_input_is_read_as_utf8(self):
        raw = io.BytesIO("[>] Bygg søkeløsningen\n".encode("utf-8"))
        out = io.StringIO()
        with mock.patch("sys.stdin", mock.Mock(buffer=raw)), contextlib.redirect_stdout(out):
            self.assertEqual(steps.main(["TKT-1"]), 0)
        self.assertEqual(self.server.received[0]["message"], "0 of 1 steps done, now: Bygg søkeløsningen\n[>] Bygg søkeløsningen")

    def test_a_line_that_is_not_a_step_sends_nothing(self):
        for text in ("[x] Fine\n- not a step\n", "[]missing space\n", "", "[x]  | detail only\n"):
            code, out, err = self.run_tool(text)
            self.assertEqual((code, out), (2, ""), text)
            self.assertIn("nothing sent", err)
        self.assertEqual(self.server.received, [])

    def test_too_many_steps_are_refused(self):
        code, _, err = self.run_tool("[ ] step\n" * 13)
        self.assertEqual(code, 2)
        self.assertIn("1 to 12 steps", err)
        self.assertEqual(self.server.received, [])

    def test_long_text_is_cut_to_what_one_message_holds(self):
        self.run_tool("".join(f"[x] {'å' * 200} | {'ø' * 400}\n" for _ in range(12)))
        text = self.server.received[0]["message"]
        self.assertLessEqual(len(text.encode("utf-8")), steps.MAX_MESSAGE_BYTES)
        lines = text.split("\n")[1:]
        self.assertEqual(len(lines), 12)
        self.assertTrue(all(len(line.split(" | ")[0]) <= 4 + steps.MAX_TITLE for line in lines))

    def test_four_byte_characters_still_fit_one_message(self):
        face = "\U0001F600"
        plan = "".join(f"[x] {face * 80} | {face * 160}\n" for _ in range(11)) + f"[>] {face * 80}\n"
        code, _, _ = self.run_tool(plan)
        self.assertEqual(code, 0)
        text = self.server.received[0]["message"]
        self.assertLessEqual(len(text.encode("utf-8")), steps.MAX_MESSAGE_BYTES)
        lines = text.split("\n")
        self.assertEqual(len(lines), 13)
        self.assertTrue(all(steps.STEP.fullmatch(line) for line in lines[1:]))

    def test_the_size_limit_is_enforced_not_assumed(self):
        with mock.patch.object(steps, "MAX_MESSAGE_BYTES", 10):
            code, out, err = self.run_tool(PLAN)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("do not fit", err)
        self.assertEqual(self.server.received, [])

    def test_each_step_stays_on_its_own_line(self):
        self.run_tool("[x] Build\t the   thing | fine\r\n\r\n   [>] Next\n")
        self.assertEqual(self.server.received[0]["message"].split("\n")[1:], ["[x] Build the thing | fine", "[>] Next"])

    def test_no_server_prints_the_summary_and_sends_nothing(self):
        self.config.unlink()
        self.assertEqual(self.run_tool(PLAN), (0, "TKT-1: 1 of 3 steps done, now: Independent review\n", ""))

    def test_a_failed_send_is_reported(self):
        self.config.write_text(json.dumps({"url": "http://127.0.0.1:9", "topic": "patstack"}))
        code, out, err = self.run_tool(PLAN)
        self.assertEqual((code, out), (1, "TKT-1: 1 of 3 steps done, now: Independent review\n"))
        self.assertIn("steps NOT sent", err)

    def test_bad_arguments_are_refused(self):
        plan = self.root / "plan.txt"
        plan.write_text(PLAN)
        for args in (["TKT-x"], ["TKT-1", "--thread", "bad thread"], ["TKT-1", "--project", "bad project"]):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(steps.main([*args, "--file", str(plan)]), 2)
        self.assertEqual(self.server.received, [])


if __name__ == "__main__":
    unittest.main()
