"""monday_ticket against an in-memory Monday; no network."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import monday_ticket as mt

CFG = {"account": "team", "workspace": 7, "board": 10, "subitems_board": 20, "first_number": 30001,
       "columns": {"ticket": "num", "status": "status", "person": "person"},
       "statuses": {"IN PROGRESS": "Under arbeid", "DONE": "Ferdig", "REVIEW": "Lansert i Stage"}}


class FakeApi:
    """Subitems with ids, numbers and status; items 1..5 are roadmap items on board 10."""

    def __init__(self, numbers=()):
        self.lock = threading.Lock()
        self.next_id = 100
        self.items = {}  # id -> {"number", "status", "name", "parent", "updates"}
        for number in numbers:
            self._add(None, "old", number)
        self.hook = None  # called inside numbers() to interleave another agent
        self.workspace = 7

    def _add(self, parent, name, number=None):
        with self.lock:
            self.next_id += 1
            self.items[self.next_id] = {"number": number, "status": None, "name": name, "parent": parent,
                                        "updates": [], "created": time.time()}
            return self.next_id

    def me(self):
        return {"id": "7", "name": "Tester"}

    def boards(self):
        return [{"id": "10", "name": "Roadmap", "workspace": {"id": str(self.workspace)}, "columns": []},
                {"id": "20", "name": "Subitems", "workspace": {"id": str(self.workspace)},
                 "columns": [{"id": "num"}, {"id": "status"}, {"id": "person"}]}]

    def item_board(self, item_id):
        return 10 if 1 <= item_id <= 5 else (20 if item_id in self.items else None)

    def create_subitem(self, parent, title, values):
        item = self._add(parent, title, int(values["num"]) if "num" in values else None)
        self.items[item]["status"] = (values.get("status") or {}).get("label")
        return item, 20

    def numbers(self):
        snapshot = [(i, v["number"]) for i, v in self.items.items() if v["number"] is not None]
        if self.hook:
            hook, self.hook = self.hook, None
            hook()
        return snapshot

    def set_number(self, item_id, number):
        self.items[item_id]["number"] = number

    def by_number(self, number):
        return [(i, v["name"], v["parent"], v["status"])
                for i, v in list(self.items.items()) if v["number"] == number]

    def set_status(self, item_id, label):
        self.items[item_id]["status"] = label

    def add_update(self, item_id, body):
        self.items[item_id]["updates"].append(body)


class AllocationTests(unittest.TestCase):
    def test_first_ticket_starts_at_the_configured_number(self):
        api = FakeApi()
        self.assertEqual(mt.new(api, CFG, 3, "Første", pause=0)[0], 30001)

    def test_next_number_follows_the_highest(self):
        api = FakeApi(numbers=(30001, 30007))
        self.assertEqual(mt.new(api, CFG, 3, "Neste", pause=0)[0], 30008)

    def test_new_ticket_gets_status_and_person(self):
        api = FakeApi()
        _, item = mt.new(api, CFG, 3, "Ny", pause=0)
        self.assertEqual(api.items[item]["status"], "Under arbeid")

    def test_parent_must_be_a_roadmap_item(self):
        with self.assertRaises(mt.MondayError):
            mt.new(FakeApi(), CFG, 999, "Feil forelder", pause=0)

    def test_a_tie_goes_to_the_lower_id_and_the_other_moves_on(self):
        api = FakeApi()
        lower = api._add(3, "A")       # A exists first and will claim the same number
        def a_claims():
            api.set_number(lower, 30001)
        api.hook = a_claims             # A writes 30001 right after B has read the numbers
        number, b = mt.new(api, CFG, 3, "B", pause=0)
        self.assertGreater(b, lower)
        self.assertEqual(api.items[lower]["number"], 30001)
        self.assertEqual(number, 30002)

    def test_a_late_lower_writer_is_caught_by_the_second_check(self):
        api = FakeApi()
        lower = api._add(3, "A")
        calls = {"n": 0}
        real = api.by_number
        def late(number):
            calls["n"] += 1
            if calls["n"] == 2:          # A writes only after B's first check
                api.set_number(lower, number)
            return real(number)
        api.by_number = late
        number, _ = mt.new(api, CFG, 3, "B", pause=0)
        self.assertEqual(number, 30002)
        self.assertEqual(api.items[lower]["number"], 30001)

    def test_a_stalled_agent_can_share_a_number_but_never_mixes_tickets_up(self):
        # Monday has no lock: A reads the numbers, stalls while B runs to the end, then writes.
        api = FakeApi()
        a = api.create_subitem(3, "A", {})[0]
        taken = [n for _, n in api.numbers()]                       # A has read: nothing taken yet
        number_b, b = mt.new(api, CFG, 3, "B", pause=0)             # B allocates and returns
        api.set_number(a, max([CFG["first_number"] - 1] + taken) + 1)  # A writes what it computed earlier
        self.assertEqual((api.items[a]["number"], number_b), (30001, 30001))
        with self.assertRaises(mt.MondayError) as caught:          # the same machine gets no shortcut either
            mt.resolve(api, CFG, 30001)
        for expected in (str(a), str(b), "--item", "renumber"):
            self.assertIn(expected, str(caught.exception))
        self.assertEqual(mt.resolve(api, CFG, 30001, item=b), b)    # B names its own ID from `new`
        self.assertEqual(mt.allocate(api, CFG, b, pause=0), 30002)  # the newer one takes a fresh number
        self.assertEqual(mt.resolve(api, CFG, 30001), a)

    def test_item_must_hold_the_number_now(self):
        api = FakeApi()
        n1, a = mt.new(api, CFG, 3, "A", pause=0)
        n2, b = mt.new(api, CFG, 3, "B", pause=0)
        for number, item in ((n1, b), (39999, b), (n1, 3)):        # another ticket's ID, no holder, a roadmap item
            with self.subTest(number=number, item=item), self.assertRaises(mt.MondayError):
                mt.resolve(api, CFG, number, item=item)
        api.set_number(a, 30050)                                   # someone renumbered A
        with self.assertRaises(mt.MondayError):
            mt.resolve(api, CFG, n1, item=a)
        self.assertEqual(mt.resolve(api, CFG, 30050), a)

    def test_a_renumber_during_the_write_is_reported_never_confirmed(self):
        # Older B is stalled without a number; newer A holds 30001. A status for that number resolves to A;
        # before the write lands, B writes 30001 and A is renumbered to 30002.
        api = FakeApi()
        b = api.create_subitem(3, "B", {})[0]
        number, a = mt.new(api, CFG, 3, "A", pause=0)
        self.assertEqual(number, 30001)
        real = api.set_status
        def delayed(item, label):
            api.set_number(b, 30001)
            api.set_number(a, 30002)
            real(item, label)
        api.set_status = delayed
        with self.assertRaises(mt.MondayError) as caught:
            mt.write_checked(api, CFG, 30001, None, lambda target: api.set_status(target, "Ferdig"))
        self.assertIn(f"subitem {a} was changed", str(caught.exception))
        self.assertIn(str(b), str(caught.exception))

    def test_overlapping_renumbers_never_confirm_a_number_the_subitem_lost(self):
        # A and C share a label scenario: while A's renumber checks its new number, a stalled C writes that
        # same number and a second repair moves A on. The first renumber must not confirm the lost number.
        api = FakeApi()
        a = api.create_subitem(3, "A", {})[0]
        c = api.create_subitem(3, "C", {})[0]
        real = api.by_number
        calls = {"n": 0}
        def interleaved(number):
            calls["n"] += 1
            if calls["n"] == 1:                       # first check of A's renumber to 30001
                api.set_number(c, number)             # stalled C writes the same number
                api.set_number(a, number + 1)         # a second repair moved A on
            return real(number)
        api.by_number = interleaved
        number = mt.allocate(api, CFG, a, pause=0)
        api.by_number = real
        self.assertEqual(api.items[a]["number"], number)  # whatever it confirms, A really holds it
        self.assertIn(a, [i for i, *_ in real(number)])

    def test_a_cleared_number_is_not_found(self):
        api = FakeApi()
        number, item = mt.new(api, CFG, 3, "A", pause=0)
        api.items[item]["number"] = None
        with self.assertRaises(mt.MondayError):
            mt.resolve(api, CFG, number)

    def test_many_concurrent_agents_get_distinct_numbers(self):
        api = FakeApi(numbers=(30001,))
        results = []
        def agent(n):
            results.append(mt.new(api, CFG, 3, f"T{n}", pause=0.01)[0])
        threads = [threading.Thread(target=agent, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        numbers = [v["number"] for v in api.items.values() if v["number"] is not None]
        self.assertEqual(len(numbers), len(set(numbers)), numbers)
        self.assertEqual(sorted(results), sorted(numbers)[1:])


class CommandTests(unittest.TestCase):
    def test_parent_listing_reads_all_pages_of_only_the_configured_board(self):
        api = mt.Api("fake", CFG)
        with mock.patch.object(api, "_q", side_effect=[
                {"boards": [{"items_page": {"cursor": "next", "items": [{"id": "1", "name": "Første"}]}}]},
                {"next_items_page": {"cursor": None, "items": [{"id": "2", "name": "Andre"}]}}]) as query:
            self.assertEqual(api.parents(), [{"id": 1, "name": "Første"}, {"id": 2, "name": "Andre"}])
        self.assertEqual(query.call_args_list[0].args[1], {"board": [10]})
        self.assertEqual(query.call_args_list[1].args[1], {"cursor": "next"})
        self.assertTrue(all("mutation" not in call.args[0] for call in query.call_args_list))

    def test_a_number_resolves_to_its_subitem(self):
        api = FakeApi()
        number, item = mt.new(api, CFG, 3, "Ting", pause=0)
        self.assertEqual(mt.resolve(api, CFG, number), item)
        with self.assertRaises(mt.MondayError):
            mt.resolve(api, CFG, 39999)

    def test_duplicates_are_refused_not_guessed(self):
        api = FakeApi(numbers=(30005, 30005))
        with self.assertRaises(mt.MondayError):
            mt.resolve(api, CFG, 30005)

    def test_ticket_references_are_strict(self):
        self.assertEqual(mt.parse_ticket("TKT-" + "30001"), 30001)
        for bad in ("30001", "TKT-", "tkt-1", "TKT-1 ; x"):
            with self.assertRaises(mt.MondayError):
                mt.parse_ticket(bad)

    def test_a_board_outside_the_workspace_is_refused_before_anything_else(self):
        api = FakeApi(numbers=(30001,))
        api.workspace = 9                                     # say the board was moved to another workspace
        with self.assertRaises(mt.MondayError) as caught:
            mt.in_scope(api, CFG)
        self.assertIn("outside the configured scope", str(caught.exception))
        with self.assertRaises(mt.MondayError):
            mt.check(api, CFG)
        with self.assertRaises(mt.MondayError):
            mt.in_scope(api, dict(CFG, board=99))            # a board this token cannot see

    def test_check_names_a_missing_column(self):
        api = FakeApi()
        cfg = dict(CFG, columns=dict(CFG["columns"], ticket="gone"))
        with self.assertRaises(mt.MondayError):
            mt.check(api, cfg)
        self.assertIn("Monday OK", mt.check(api, CFG))


class RetryTests(unittest.TestCase):
    def call(self, outcomes, retry):
        api = mt.Api("tok", CFG)
        calls = []
        def fake_open(request, timeout):
            calls.append(1)
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return contextlib.nullcontext(io.BytesIO(json.dumps(outcome).encode()))
        with mock.patch.object(mt.OPENER, "open", fake_open), mock.patch.object(mt.time, "sleep"):
            try:
                return api._q("{ me { id } }", retry=retry), len(calls)
            except mt.MondayError as error:
                return error, len(calls)

    def test_safe_calls_retry_a_timeout(self):
        result, calls = self.call([TimeoutError(), {"data": {"me": {"id": "1"}}}], retry=True)
        self.assertEqual((result, calls), ({"me": {"id": "1"}}, 2))

    def test_creating_is_never_repeated(self):
        result, calls = self.call([TimeoutError(), {"data": {}}], retry=False)
        self.assertIsInstance(result, mt.MondayError)
        self.assertEqual(calls, 1)

    def test_a_quick_client_makes_one_attempt(self):
        api = mt.Api("tok", CFG, timeout=8, tries=1)
        seen = []
        def fake_open(request, timeout):
            seen.append(timeout)
            raise TimeoutError()
        with mock.patch.object(mt.OPENER, "open", fake_open), mock.patch.object(mt.time, "sleep"):
            with self.assertRaises(mt.MondayError):
                api._q("{ me { id } }")
        self.assertEqual(seen, [8])

    def test_retries_stop_after_three_tries(self):
        result, calls = self.call([TimeoutError()] * 3, retry=True)
        self.assertIsInstance(result, mt.MondayError)
        self.assertEqual(calls, 3)


class RedirectTests(unittest.TestCase):
    def test_redirects_are_never_followed(self):
        handler = mt._NoRedirect()
        request = mt.urllib.request.Request(mt.API, method="POST", data=b"{}", headers={"Authorization": "secret"})
        self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, "https://elsewhere.invalid/x"))

    def test_a_redirect_answer_is_refused_without_retry(self):
        api = mt.Api("tok", CFG)
        calls = []
        def fake_open(request, timeout):
            calls.append(1)
            raise mt.urllib.error.HTTPError(mt.API, 302, "Found", {}, None)
        with mock.patch.object(mt.OPENER, "open", fake_open), mock.patch.object(mt.time, "sleep"):
            with self.assertRaises(mt.MondayError) as caught:
                api._q("{ me { id } }")
        self.assertIn("redirect", str(caught.exception))
        self.assertEqual(len(calls), 1)


class SetupTests(unittest.TestCase):
    def test_inapplicable_status_never_reads_a_token(self):
        with mock.patch.object(mt, "load_config", return_value=CFG), \
                mock.patch.object(mt, "read_token", side_effect=AssertionError("must not read credentials")):
            for task, status in (("TKT-1", "DONE"), ("nope", "DONE"), ("TKT-" + "30001", "RETRO")):
                self.assertIsNone(mt.sync_status(task, status))

    def test_non_header_characters_in_tokens_are_rejected_without_echoing(self):
        for char in ("\x00", "\x01", "\x1b", "\x7f", "\t", "\u200b", "ø"):
            secret = "fake" + char + "token"
            for path in (self.dir / "token", self.dir / "pasted"):
                path.write_text(secret, encoding="utf-8")
            for read in (mt.read_token, lambda: mt.store_token(self.dir / "pasted")):
                with self.assertRaises(mt.MondayError) as caught:
                    read()
                self.assertNotIn(secret, str(caught.exception))

    def test_check_prints_unicode_names_on_a_legacy_console(self):
        api = FakeApi()
        boards = api.boards()
        boards[0]["name"] = "Roadmap 🦄"
        api.boards = lambda: boards
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        (self.dir / "token").write_text("fake.token")
        with contextlib.redirect_stdout(stream), mock.patch.object(mt, "Api", return_value=api):
            self.assertEqual(mt.main(["check"]), 0)
        stream.flush()
        self.assertIn(b"Monday OK", raw.getvalue())
        self.assertIn(b"\\U0001f984", raw.getvalue())
        stream.close()

    def test_parents_command_checks_scope_and_prints_json(self):
        api = FakeApi()
        api.parents = mock.Mock(return_value=[{"id": 3, "name": "Første"}])
        code, out, _ = self.run_main(api, "parents")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"id": 3, "name": "Første"})
        api.workspace = 99
        api.parents.reset_mock()
        self.assertEqual(self.run_main(api, "parents")[0], 1)
        api.parents.assert_not_called()

    def test_json_commands_round_trip_unicode_on_a_legacy_console(self):
        api = FakeApi(numbers=(30005,))
        name = "Første 🦄 \u001b"
        api.parents = lambda: [{"id": 3, "name": name}]
        api.items[101]["name"] = name
        (self.dir / "token").write_text("fake.token")
        for argv in (["parents"], ["find", "TKT-" + "30005"]):
            raw = io.BytesIO()
            stream = io.TextIOWrapper(raw, encoding="cp1252")
            with contextlib.redirect_stdout(stream), mock.patch.object(mt, "Api", return_value=api):
                self.assertEqual(mt.main(argv), 0)
            stream.flush()
            self.assertEqual(json.loads(raw.getvalue())["name"], name)
            stream.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"PATSTACK_MONDAY_TOKEN_FILE": str(self.dir / "token"),
                                           "PATSTACK_MONDAY_CONFIG": str(self.dir / "cfg.json")})
        env.start()
        self.addCleanup(env.stop)
        (self.dir / "cfg.json").write_text(json.dumps(CFG))

    def test_token_is_stored_owner_only_and_never_printed(self):
        secret = "abc.def.ghi"
        (self.dir / "pasted").write_text(secret + "\n")
        path = mt.store_token(self.dir / "pasted")
        self.assertEqual(mt.read_token(), secret)
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(mt.Api, "_q", side_effect=mt.MondayError("Monday API answered HTTP 401")):
            code = mt.main(["setup", "--store", str(self.dir / "pasted")])
        self.assertEqual(code, 1)
        self.assertNotIn(secret, out.getvalue() + err.getvalue())

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_an_old_readable_token_file_is_replaced_owner_only(self):
        old = self.dir / "token"
        old.write_text("old")
        old.chmod(0o644)
        inode = old.stat().st_ino
        (self.dir / "pasted").write_text("new.token.value")
        path = mt.store_token(self.dir / "pasted")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(path.stat().st_ino, inode)       # a new file, never the old readable one
        self.assertEqual(mt.read_token(), "new.token.value")
        self.assertFalse(list(self.dir.glob(".token.*.tmp")))

    def test_absent_and_broken_configs_are_told_apart(self):
        ticket = "TKT-" + "30001"
        cfg = self.dir / "cfg.json"
        for broken in ("{", "[]", "3", '{"account": "team"}'):
            with self.subTest(broken=broken):
                cfg.write_text(broken)
                with self.assertRaises(mt.MondayError) as caught:
                    mt.load_config()
                self.assertNotIsInstance(caught.exception, mt.NoConfig)
                self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))     # shown, not swallowed
        cfg.unlink()                                                             # an override that points nowhere
        with self.assertRaises(mt.MondayError) as caught:
            mt.load_config()
        self.assertNotIsInstance(caught.exception, mt.NoConfig)
        os.environ.pop("PATSTACK_MONDAY_CONFIG")
        with mock.patch.object(Path, "home", return_value=self.dir):             # nothing configured anywhere
            with self.assertRaises(mt.NoConfig):
                mt.load_config(self.dir)
            self.assertIsNone(mt.sync_status(ticket, "DONE", root=self.dir))

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX permissions as a normal user")
    def test_an_unreadable_config_folder_is_broken_not_absent_and_never_a_crash(self):
        os.environ.pop("PATSTACK_MONDAY_CONFIG")
        folder = self.dir / ".config/patstack"
        folder.mkdir(parents=True)
        folder.chmod(0)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(folder.chmod, 0o700)                         # runs first: cleanups are last in, first out
        with mock.patch.object(Path, "home", return_value=self.dir):
            with self.assertRaises(mt.MondayError) as caught:
                mt.load_config(self.dir)
            self.assertNotIsInstance(caught.exception, mt.NoConfig)
            self.assertIn("NOT updated", mt.sync_status("TKT-" + "30001", "DONE", root=self.dir))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(mt.main(["check"]), 1)
            self.assertIn("cannot look for the Monday config", err.getvalue())

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX permissions as a normal user")
    def test_a_pack_folder_that_cannot_be_inspected_is_broken_never_absent(self):
        os.environ.pop("PATSTACK_MONDAY_CONFIG")
        team = self.dir / "root/project-packs/team"
        team.mkdir(parents=True)
        (team / "monday.json").write_text(json.dumps(CFG))
        with mock.patch.object(Path, "home", return_value=self.dir / "nohome"):
            self.assertEqual(mt.load_config(self.dir / "root")["board"], 10)
            for locked in (team, team.parent):
                with self.subTest(locked=locked.name):
                    locked.chmod(0)
                    try:
                        with self.assertRaises(mt.MondayError) as caught:
                            mt.load_config(self.dir / "root")
                        self.assertNotIsInstance(caught.exception, mt.NoConfig)
                        self.assertIn("NOT updated", mt.sync_status("TKT-" + "30001", "DONE", root=self.dir / "root"))
                    finally:
                        locked.chmod(0o700)
            self.assertEqual(mt.load_config(self.dir / "root")["board"], 10)

    @unittest.skipIf(os.name == "nt", "native symlink fixture; run on Linux")
    def test_a_dangling_config_link_is_broken_never_absent(self):
        os.environ.pop("PATSTACK_MONDAY_CONFIG")
        ticket = "TKT-" + "30001"
        pack = self.dir / "root/project-packs/team"
        pack.mkdir(parents=True)
        (pack / "monday.json").symlink_to(self.dir / "gone.json")            # bundled config: dangling link
        with mock.patch.object(Path, "home", return_value=self.dir / "nohome"):
            with self.assertRaises(mt.MondayError) as caught:
                mt.load_config(self.dir / "root")
            self.assertNotIsInstance(caught.exception, mt.NoConfig)
            self.assertIn("NOT updated", mt.sync_status(ticket, "DONE", root=self.dir / "root"))
        private = self.dir / "home2/.config/patstack"
        private.mkdir(parents=True)
        (private / "monday.json").symlink_to(self.dir / "gone.json")         # private config: dangling link
        with mock.patch.object(Path, "home", return_value=self.dir / "home2"):
            with self.assertRaises(mt.MondayError) as caught:
                mt.load_config(self.dir / "empty-root")
            self.assertNotIsInstance(caught.exception, mt.NoConfig)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on Windows")
    def test_a_fifo_or_folder_where_a_file_belongs_is_refused_without_blocking(self):
        ticket = "TKT-" + "30001"
        started = time.monotonic()
        (self.dir / "token").write_text("x.y.z")
        (self.dir / "cfg.json").unlink()
        os.mkfifo(self.dir / "cfg.json")                                  # config is a FIFO
        with self.assertRaises(mt.MondayError) as caught:
            mt.load_config()
        self.assertNotIsInstance(caught.exception, mt.NoConfig)
        self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))
        (self.dir / "cfg.json").unlink()
        (self.dir / "cfg.json").write_text(json.dumps(CFG))
        (self.dir / "token").unlink()
        os.mkfifo(self.dir / "token")                                     # token is a FIFO
        with self.assertRaises(mt.MondayError) as caught:
            mt.read_token()
        self.assertNotIsInstance(caught.exception, mt.NoToken)
        self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))
        os.mkfifo(self.dir / "pasted")                                    # the token to store is a FIFO
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(mt.main(["setup", "--store", str(self.dir / "pasted")]), 1)
        (self.dir / "token").unlink()
        (self.dir / "token").mkdir()                                      # token is a folder
        with self.assertRaises(mt.MondayError):
            mt.read_token()
        self.assertLess(time.monotonic() - started, 5)

    @unittest.skipIf(os.name == "nt", "native symlink fixture; run on Linux")
    def test_a_dangling_token_link_is_broken_not_missing(self):
        ticket = "TKT-" + "30001"
        (self.dir / "token").symlink_to(self.dir / "gone")
        with self.assertRaises(mt.MondayError) as caught:
            mt.read_token()
        self.assertNotIsInstance(caught.exception, mt.NoToken)
        self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))
        (self.dir / "token").unlink()
        with self.assertRaises(mt.NoToken):
            mt.read_token()

    def test_home_and_environment_can_be_given_so_every_tool_agrees(self):
        home = self.dir / "other-home"
        (home / ".config/patstack").mkdir(parents=True)
        (home / ".config/patstack/monday.json").write_text(json.dumps(dict(CFG, board=77)))
        (home / ".config/patstack/monday-token").write_text("a.b.c")
        self.assertEqual(mt.load_config(self.dir / "no-root", home=home, env={})["board"], 77)
        self.assertEqual(mt.read_token(home=home, env={}), "a.b.c")
        self.assertEqual(mt.load_config(home=home)["board"], 10)             # this process's override still wins
        with self.assertRaises(mt.MondayError) as caught:                    # a boolean is not a workspace id
            (home / ".config/patstack/monday.json").write_text(json.dumps(dict(CFG, workspace=True)))
            mt.load_config(self.dir / "no-root", home=home, env={})
        self.assertNotIsInstance(caught.exception, mt.NoConfig)

    def test_token_files_that_cannot_be_used_are_reported_cleanly(self):
        ticket = "TKT-" + "30001"
        token = self.dir / "token"
        token.write_bytes(b"\xff\xfe not utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(mt.main(["check"]), 1)
        self.assertIn("unreadable Monday token file", err.getvalue())
        self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))
        self.assertIsNone(mt.sync_status("nope", "DONE"))
        if os.name != "nt" and os.geteuid() != 0:
            token.write_text("x.y.z")
            token.chmod(0)
            try:
                self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))
            finally:
                token.chmod(0o600)
        token.unlink()
        self.assertIsNone(mt.sync_status(ticket, "DONE"))                 # no token at all stays quiet
        for argv in (["setup", "--store", str(self.dir / "missing")],):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                self.assertEqual(mt.main(argv), 1)
            self.assertIn("cannot read the token to store", err.getvalue())
        if os.name != "nt" and os.geteuid() != 0:
            (self.dir / "pasted").write_text("x.y.z")
            locked = self.dir / "locked"
            locked.mkdir()
            locked.chmod(0o500)
            try:
                err = io.StringIO()
                with mock.patch.dict(os.environ, {"PATSTACK_MONDAY_TOKEN_FILE": str(locked / "token")}), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    self.assertEqual(mt.main(["setup", "--store", str(self.dir / "pasted")]), 1)
                self.assertIn("cannot store the token", err.getvalue())
            finally:
                locked.chmod(0o700)

    def test_missing_token_says_how_to_set_up(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(mt.main(["check"]), 1)
        self.assertIn("setup", err.getvalue())
        with contextlib.redirect_stdout(out):
            self.assertEqual(mt.main(["setup"]), 0)
        self.assertIn("https://team.monday.com/apps/manage/tokens", out.getvalue())

    def test_sync_status_is_quiet_when_not_applicable_and_loud_on_failure(self):
        ticket = "TKT-" + "30001"
        self.assertIsNone(mt.sync_status(ticket, "DONE"))                # no token here
        (self.dir / "token").write_text("x.y.z")
        self.assertIsNone(mt.sync_status("TKT-" + "17402", "DONE"))      # a machine-issued number has no subitem
        self.assertIsNone(mt.sync_status(ticket, "RETRO"))               # no Monday status for it
        self.assertIsNone(mt.sync_status("nope", "DONE"))
        api = FakeApi(numbers=(30001,))
        with mock.patch.object(mt, "Api", return_value=api) as made:
            self.assertEqual(mt.sync_status(ticket, "DONE"), f"monday: {ticket} -> Ferdig")
        self.assertEqual(made.call_args.kwargs, {"timeout": 8, "tries": 1})  # one short attempt, never minutes
        self.assertEqual([v["status"] for v in api.items.values()], ["Ferdig"])
        with mock.patch.object(mt.Api, "_q", side_effect=mt.MondayError("Monday API unreachable: TimeoutError")):
            self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))
        moving = FakeApi(numbers=(30001,))
        (only,) = moving.items
        moving.set_status = lambda item, label: moving.set_number(only, 30009)   # renumbered mid-write
        with mock.patch.object(mt, "Api", return_value=moving):
            self.assertIn("moved during the update", mt.sync_status(ticket, "DONE"))
        release = threading.Event()
        def trickle(*_args, **_kwargs):                          # a server that keeps a call open for ever
            release.wait(10)
            return {}
        started = time.monotonic()
        with mock.patch.object(mt.Api, "_q", side_effect=trickle):
            line = mt.sync_status(ticket, "DONE", deadline=0.3)
        release.set()
        self.assertLess(time.monotonic() - started, 2)
        self.assertIn("NOT confirmed", line)

    def run_main(self, api, *argv):
        (self.dir / "token").write_text("x.y.z")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(mt, "Api", return_value=api), mock.patch.object(mt.time, "sleep"):
            code = mt.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_find_lists_every_holder_and_says_so(self):
        api = FakeApi(numbers=(30005, 30005, 30006))
        code, out, err = self.run_main(api, "find", "TKT-" + "30005")
        self.assertEqual(code, mt.AMBIGUOUS)
        self.assertEqual(len(out.splitlines()), 2)
        self.assertIn("renumber", err)
        code, out, _ = self.run_main(api, "find", "TKT-" + "30006")
        self.assertEqual((code, len(out.splitlines())), (0, 1))
        self.assertEqual(self.run_main(api, "find", "TKT-" + "39999")[0], 1)

    def test_every_command_refuses_outside_the_scope_and_writes_nothing(self):
        api = FakeApi(numbers=(30005,))
        api.workspace = 9
        for argv in (("find", "TKT-" + "30005"), ("status", "TKT-" + "30005", "DONE"),
                     ("link", "TKT-" + "30005", "https://example.invalid/x"), ("renumber", "--item", "101"),
                     ("new", "--parent", "3", "--title", "x"), ("check",)):
            with self.subTest(argv=argv):
                code, out, err = self.run_main(api, *argv)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("refusing", err)
        self.assertEqual([(v["number"], v["status"], v["updates"]) for v in api.items.values()], [(30005, None, [])])
        ticket = "TKT-" + "30005"
        with mock.patch.object(mt, "Api", return_value=api):
            self.assertIn("NOT updated", mt.sync_status(ticket, "DONE"))

    def test_item_flag_and_renumber_settle_a_shared_number(self):
        api = FakeApi(numbers=(30005, 30005))
        older, newer = sorted(api.items)
        ticket = "TKT-" + "30005"
        self.assertEqual(self.run_main(api, "status", ticket, "DONE")[0], 1)          # refused: two holders
        self.assertEqual(self.run_main(api, "status", ticket, "DONE", "--item", "3")[0], 1)    # not a holder
        self.assertEqual(self.run_main(api, "status", ticket, "DONE", "--item", str(older))[0], 0)
        self.assertEqual((api.items[older]["status"], api.items[newer]["status"]), ("Ferdig", None))
        code, out, _ = self.run_main(api, "renumber", "--item", str(newer))
        self.assertEqual((code, out.split()[0]), (0, "TKT-" + "30006"))
        self.assertEqual(self.run_main(api, "link", "TKT-" + "30006", "https://example.invalid/pr/2",
                                       "--item", str(older))[0], 1)                       # older holds 30005
        self.assertEqual(self.run_main(api, "link", ticket, "https://example.invalid/pr/1")[0], 0)
        api.add_update = lambda item, body: api.set_number(older, 30077)                     # moved mid-write
        code, out, err = self.run_main(api, "link", ticket, "https://example.invalid/pr/3")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("moved during the update", err)
        self.assertEqual(api.items[older]["updates"], ["https://example.invalid/pr/1"])
        self.assertEqual(self.run_main(api, "renumber", "--item", "3")[0], 1)         # not a subitem

    @unittest.skipUnless(list(mt.ROOT.glob("project-packs/*/monday.json")), "no bundled Monday config (public export)")
    def test_the_bundled_config_is_valid(self):
        os.environ.pop("PATSTACK_MONDAY_CONFIG")
        with mock.patch.object(Path, "home", return_value=self.dir):
            cfg = mt.load_config()
        self.assertGreaterEqual(cfg["first_number"], 30001)


if __name__ == "__main__":
    unittest.main()
