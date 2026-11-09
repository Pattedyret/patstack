"""task_status.py against a local stand-in for the ntfy server; nothing leaves this machine."""
import contextlib
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

import task_status as ts


class Server:
    """Records each JSON body posted to it, and answers with `status`."""

    def __init__(self, status=200):
        received = self.received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, args=(0.01,), daemon=True).start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()


def snapshot(task, status="open", verified=None, hours_ago=0, revision=1):
    started = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return (task, revision, started.isoformat(), json.dumps({
        "id": task, "status": status, "verified_success": verified, "topic": "app",
        "started_at": started.isoformat()}))


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "kpis.sqlite3"
        self.config = self.root / "notify.json"
        env = mock.patch.dict(os.environ, {"DEVSTACK_NOTIFY": str(self.config), "T3CODE_THREAD_ID": ""})
        env.start()
        self.addCleanup(env.stop)
        self.server = Server()
        self.addCleanup(self.server.close)
        self.configure(self.server.url)

    def configure(self, url, topic="devstack"):
        self.config.write_text(json.dumps({"url": url, "topic": topic}))

    def store(self, *rows):
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT, revision INTEGER, updated TEXT, body TEXT)")
            con.executemany("INSERT INTO snapshots VALUES (?,?,?,?)", rows)
        con.close()

    def run_tool(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ts.main(["--db", str(self.db), *args] if args[0] != "sweep"
                           else ["sweep", "--db", str(self.db), *args[1:]])
        return code, out.getvalue(), err.getvalue()


class StatusTests(Base):
    def test_deployed_prints_the_title_and_pings_with_the_link(self):
        code, out, _ = self.run_tool("TKT-1", "DEPLOYED ON STAGE", "--title", "New invoice flow",
                                     "--url", "https://stage.example.invalid/x")
        self.assertEqual((code, out), (0, "🔵 [TKT-1 · DEPLOYED ON STAGE] New invoice flow\n"))
        sent = self.server.received[0]
        tags = sent.pop("tags")
        self.assertEqual(self.server.received, [{
            "topic": "devstack", "title": "🔵 DEPLOYED ON STAGE · TKT-1", "message": "New invoice flow",
            "priority": 3, "click": "https://stage.example.invalid/x"}])
        self.assertEqual(tags[:3], ["ds:1", "task:TKT-1", "status:deployed-on-stage"])

    def test_waiting_on_u_pings_loudest(self):
        self.run_tool("TKT-1", "WAITING ON YOU", "--title", "Flow", "--note", "Heroku login missing")
        sent = self.server.received[0]
        self.assertEqual((sent["priority"], sent["message"]), (4, "Flow\nHeroku login missing"))
        self.assertNotIn("click", sent)

    def test_quiet_statuses_reach_only_the_board_topic(self):
        for status in ("IN PROGRESS", "REVIEW", "RETRO"):
            code, out, _ = self.run_tool("TKT-1", status, "--title", "Flow")
            self.assertEqual(code, 0)
            self.assertIn(f"[TKT-1 · {status}]", out)
        self.assertEqual({sent["topic"] for sent in self.server.received}, {"devstack-board"})
        self.assertEqual({sent["priority"] for sent in self.server.received}, {1})
        self.assertEqual([sent["tags"][2] for sent in self.server.received],
                         ["status:in-progress", "status:review", "status:retro"])

    def test_a_quiet_status_with_no_server_stays_silent(self):
        self.config.unlink()
        self.assertEqual(self.run_tool("TKT-1", "REVIEW", "--title", "Flow"),
                         (0, "🟣 [TKT-1 · REVIEW] Flow\n", ""))

    def test_a_failed_quiet_status_is_reported_and_keeps_the_title(self):
        self.configure("http://127.0.0.1:9")
        code, out, err = self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        self.assertEqual((code, out), (1, "🟣 [TKT-1 · REVIEW] Flow\n"))
        self.assertIn("ping FAILED", err)

    def test_known_fields_are_tagged_and_unknown_ones_left_out(self):
        self.store(("TKT-1", 1, "x", json.dumps({"topic": "invoices", "host": "mac"})))
        self.run_tool("TKT-1", "REVIEW", "--title", "Flow", "--pr", "owner/repo#12",
                      "--thread", "thread:delegated%3Aabc")
        tags = self.server.received[0]["tags"]
        self.assertIn("project:invoices", tags)
        self.assertIn("host:mac", tags)
        self.assertIn("pr:owner/repo#12", tags)
        self.assertIn("thread:thread:delegated%3Aabc", tags)

        self.run_tool("TKT-2", "REVIEW", "--title", "Flow")
        self.assertEqual({tag.split(":")[0] for tag in self.server.received[1]["tags"]},
                         {"ds", "task", "status", "at"})

    def test_sender_time_is_milliseconds(self):
        self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        stamp = next(tag for tag in self.server.received[0]["tags"] if tag.startswith("at:"))
        self.assertGreater(int(stamp[3:]), 10 ** 12)

    def test_the_machine_host_beats_where_the_task_started(self):
        self.store(("TKT-1", 1, "x", json.dumps({"host": "mac"})))
        self.config.write_text(json.dumps({"url": self.server.url, "topic": "devstack", "host": "devbox"}))
        self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        self.assertIn("host:devbox", self.server.received[0]["tags"])

    def test_the_thread_comes_from_the_session_unless_given(self):
        with mock.patch.dict(os.environ, {"T3CODE_THREAD_ID": "from-env"}):
            self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
            self.run_tool("TKT-1", "REVIEW", "--title", "Flow", "--thread", "from-flag")
        self.assertIn("thread:from-env", self.server.received[0]["tags"])
        self.assertIn("thread:from-flag", self.server.received[1]["tags"])

    def test_a_bad_thread_in_the_session_is_left_out(self):
        with mock.patch.dict(os.environ, {"T3CODE_THREAD_ID": "bad id\nx"}):
            code, _, _ = self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        self.assertEqual(code, 0)
        self.assertFalse([tag for tag in self.server.received[0]["tags"] if tag.startswith("thread:")])

    def test_a_broken_store_still_sends_the_status(self):
        self.db.write_text("this is not a database")
        code, _, _ = self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.server.received), 1)

    def test_ping_flag_sends_a_quiet_status(self):
        self.run_tool("TKT-1", "IN PROGRESS", "--title", "Flow", "--ping", "--note", "Do not test yet")
        self.assertEqual(self.server.received[0]["title"], "🟡 IN PROGRESS · TKT-1")
        self.assertEqual(self.server.received[0]["message"], "Flow\nDo not test yet")
        self.assertEqual(self.server.received[0]["topic"], "devstack")

    def test_done_needs_recorded_proof(self):
        cases = [("no snapshot", ()), ("open", (snapshot("TKT-1"),)),
                 ("unknown", (snapshot("TKT-1", "completed", None, revision=2),)),
                 ("failed", (snapshot("TKT-1", "completed", False, revision=3),))]
        for name, rows in cases:
            with self.subTest(name):
                self.store(*rows) if rows else None
                code, out, err = self.run_tool("TKT-1", "DONE", "--title", "Flow")
                self.assertEqual((code, out), (2, ""))
                self.assertIn("WAITING ON YOU", err)
        self.assertEqual(self.server.received, [])

    def test_done_with_proof_pings_quietly(self):
        self.store(snapshot("TKT-1"), snapshot("TKT-1", "completed", True, revision=2))
        code, out, _ = self.run_tool("TKT-1", "DONE", "--title", "Flow")
        self.assertEqual((code, out), (0, "🟢 [TKT-1 · DONE] Flow\n"))
        self.assertEqual(self.server.received[0]["priority"], 2)

    def test_latest_snapshot_decides_done(self):
        self.store(snapshot("TKT-1", "completed", True), snapshot("TKT-1", "completed", False, revision=2))
        self.assertEqual(self.run_tool("TKT-1", "DONE", "--title", "Flow")[0], 2)

    def test_bad_input_is_refused_before_anything_is_sent(self):
        for args in (["TKT-1", "SHIPPED", "--title", "Flow"], ["nope", "REVIEW", "--title", "Flow"],
                     ["TKT-1", "REVIEW", "--title", "Flow", "--thread", "bad id"],
                     ["TKT-1", "REVIEW", "--title", "Flow", "--pr", "not a pr"],
                     ["TKT-1", "WAITING ON U", "--title", "Flow"],
                     ["TKT-1", "DEPLOYED ON STAGE", "--title", "Flow", "--url", "file:///etc/passwd"]):
            with self.subTest(args):
                self.assertEqual(self.run_tool(*args)[0], 2)
        self.assertEqual(self.server.received, [])

    def test_long_multiline_text_stays_title_and_note_lines(self):
        code, out, _ = self.run_tool("TKT-1", "WAITING ON YOU", "--title", "a\nb" + "c" * 400, "--note", "n\n" * 400)
        self.assertEqual((code, out.count("\n")), (0, 1))
        sent = self.server.received[0]["message"]
        self.assertEqual(sent.count("\n"), 1)
        self.assertLess(len(sent), ts.MAX_TITLE + ts.MAX_NOTE + 3)


class MetadataTests(Base):
    def test_a_malformed_snapshot_is_ignored_not_fatal(self):
        for body in ("[1]", "3", '"x"', "null", None):
            with self.subTest(body=body):
                self.db.unlink(missing_ok=True)
                self.store(("TKT-1", 1, "x", body))
                self.server.received.clear()
                code, _, err = self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(len(self.server.received), 1)

    def test_malformed_snapshot_fields_are_left_out(self):
        self.store(("TKT-1", 1, "x", json.dumps({"topic": ["no"], "host": "bad host"})))
        self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        self.assertEqual({tag.split(":")[0] for tag in self.server.received[0]["tags"]},
                         {"ds", "task", "status", "at"})

    def test_a_malformed_snapshot_is_not_proof(self):
        self.store(("TKT-1", 1, "x", "[1]"))
        code, _, _ = self.run_tool("TKT-1", "DONE", "--title", "Flow")
        self.assertEqual(code, 2)

    def test_a_topic_too_long_for_its_board_topic_is_refused(self):
        self.configure(self.server.url, topic="t" * 59)
        code, _, err = self.run_tool("TKT-1", "REVIEW", "--title", "Flow")
        self.assertEqual(code, 1)
        self.assertIn("ping FAILED", err)
        self.assertEqual(self.server.received, [])

    def test_a_deployed_status_must_say_where_and_keeps_its_title(self):
        for status in ts.DEPLOYED:
            code, out, err = self.run_tool("TKT-1", status, "--title", "Flow")
            self.assertEqual(code, 2)
            self.assertIn(f"[TKT-1 · {status}] Flow", out)
            self.assertIn("--how", err)
        self.assertEqual(self.server.received, [])

    def test_a_deployment_with_no_web_page_says_how_to_test(self):
        code, _, _ = self.run_tool("TKT-1", "DEPLOYED ON STAGE", "--title", "App", "--how", "Install TestFlight build 12")
        self.assertEqual(code, 0)
        sent = self.server.received[0]
        self.assertEqual(sent["message"], "App\nInstall TestFlight build 12")
        self.assertNotIn("click", sent)


class DeliveryTests(Base):
    def test_no_config_prints_the_title_and_sends_nothing(self):
        self.config.unlink()
        code, out, err = self.run_tool("TKT-1", "DEPLOYED ON STAGE", "--title", "Flow", "--url", "https://stage.example.invalid")
        self.assertEqual(code, 0)
        self.assertIn("[TKT-1 · DEPLOYED ON STAGE]", out)
        self.assertIn("not configured", err)
        self.assertEqual(self.server.received, [])

    def test_unreachable_server_keeps_the_title_and_says_so(self):
        self.configure("http://127.0.0.1:9")
        code, out, err = self.run_tool("TKT-1", "WAITING ON YOU", "--title", "Flow")
        self.assertEqual(code, 1)
        self.assertIn("[TKT-1 · WAITING ON YOU]", out)
        self.assertIn("ping FAILED", err)

    def test_server_error_is_a_failed_ping(self):
        broken = Server(status=500)
        self.addCleanup(broken.close)
        self.configure(broken.url)
        self.assertEqual(self.run_tool("TKT-1", "WAITING ON YOU", "--title", "Flow")[0], 1)

    def test_invalid_config_is_a_failed_ping_not_a_crash(self):
        for text in ("{not json", "[]", '{"url": "ftp://x", "topic": "t"}', '{"url": "http://x", "topic": "a/b"}'):
            with self.subTest(text):
                self.config.write_text(text)
                self.assertEqual(self.run_tool("TKT-1", "WAITING ON YOU", "--title", "Flow")[0], 1)
        self.assertEqual(self.server.received, [])


    def test_a_url_python_cannot_open_is_a_failed_ping_not_a_crash(self):
        self.configure("http://127.0.0.1:2586/ bad")
        code, out, err = self.run_tool("TKT-1", "WAITING ON YOU", "--title", "Flow")
        self.assertEqual(code, 1)
        self.assertIn("[TKT-1 · WAITING ON YOU]", out)
        self.assertIn("ping FAILED", err)

    def test_a_garbled_server_reply_is_a_failed_ping_not_a_crash(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)

            def answer():
                connection, _ = listener.accept()
                with connection:
                    connection.recv(65536)
                    connection.sendall(b"this is not http\r\n\r\n")

            thread = threading.Thread(target=answer, daemon=True)
            thread.start()
            self.configure(f"http://127.0.0.1:{listener.getsockname()[1]}")
            code, out, err = self.run_tool("TKT-1", "WAITING ON YOU", "--title", "Flow")
            thread.join(5)
        self.assertEqual(code, 1)
        self.assertIn("[TKT-1 · WAITING ON YOU]", out)
        self.assertIn("ping FAILED", err)


class WindowsConsoleTests(Base):
    def test_a_legacy_console_encoding_still_prints_the_title(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(ts.__file__)), "--db", str(self.db), "TKT-1", "IN PROGRESS", "--title", "Flow"],
            capture_output=True, env=dict(os.environ, PYTHONIOENCODING="cp1252"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode("utf-8").strip(), "🟡 [TKT-1 · IN PROGRESS] Flow")


class SweepTests(Base):
    def test_lists_only_old_open_tickets_oldest_first(self):
        self.store(snapshot("TKT-1", hours_ago=30), snapshot("TKT-2", hours_ago=90),
                   snapshot("TKT-3", hours_ago=2), snapshot("req-old-chat", hours_ago=90),
                   snapshot("TKT-4", hours_ago=90), snapshot("TKT-4", "completed", True, 90, revision=2))
        code, out, _ = self.run_tool("sweep")
        self.assertEqual((code, out), (0, "TKT-2 app 90h\nTKT-1 app 30h\n"))
        self.assertEqual(self.server.received[0]["title"], "⚫ 2 open past 24h, may be stalled")

    def test_nothing_old_sends_nothing(self):
        self.store(snapshot("TKT-1", hours_ago=2))
        self.assertEqual(self.run_tool("sweep")[0], 0)
        self.assertEqual(self.server.received, [])

    def test_missing_store_is_quiet(self):
        self.assertEqual(self.run_tool("sweep"), (0, "", ""))

    def test_long_list_is_capped(self):
        self.store(*(snapshot(f"TKT-{n}", hours_ago=30) for n in range(20)))
        self.run_tool("sweep")
        self.assertIn("and 12 more", self.server.received[0]["message"])

    def test_age_limit_is_adjustable(self):
        self.store(snapshot("TKT-1", hours_ago=5))
        self.assertEqual(self.run_tool("sweep", "--older-than-hours", "4")[1], "TKT-1 app 5h\n")


if __name__ == "__main__":
    unittest.main()
