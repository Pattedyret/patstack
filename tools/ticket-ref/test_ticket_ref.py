import concurrent.futures
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('ticket_ref.py')
spec = importlib.util.spec_from_file_location('ticket_ref', SCRIPT)
ticket_ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ticket_ref)


class ReferencesOnly(unittest.TestCase):
    def test_three_offline_issuers_are_unique_and_above_old_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            references = []
            for slot in (1, 2, 3):
                path = Path(tmp) / str(slot) / 'counter.sqlite3'
                ticket_ref.initialize(path, slot, 9827)
                references += [ticket_ref.allocate(path) for _ in range(25)]
            self.assertEqual(len(references), len(set(references)))
            self.assertTrue(all(int(value[4:]) > 9827 for value in references))
            self.assertEqual(references[0], 'TKT-' + '9901')
            self.assertEqual(references[25], 'TKT-' + '9902')

    def test_concurrent_allocators_never_duplicate_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'counter.sqlite3'
            ticket_ref.initialize(path, 1, 9827)
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                values = list(pool.map(lambda _: ticket_ref.allocate(path), range(100)))
            self.assertEqual(len(values), len(set(values)))
            self.assertEqual(sorted(int(value[4:]) for value in values),
                             list(range(9901, 19901, 100)))

    def test_reinitialization_never_reuses_a_number_or_changes_issuer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'counter.sqlite3'
            ticket_ref.initialize(path, 3, 9827)
            self.assertEqual(ticket_ref.allocate(path), 'TKT-' + '9903')
            ticket_ref.initialize(path, 3, 0)
            self.assertEqual(ticket_ref.allocate(path), 'TKT-' + '10003')
            with self.assertRaises(ValueError):
                ticket_ref.initialize(path, 1, 0)
            self.assertEqual(ticket_ref.allocate(path), 'TKT-' + '10103')

    def test_cli_needs_no_agent_model_role_project_or_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'counter.sqlite3'
            env = {**os.environ, 'DEVSTACK_TICKET_DB': str(path)}
            subprocess.run([sys.executable, str(SCRIPT), 'init', '--slot', '42', '--after', '9827'],
                           env=env, check=True, capture_output=True)
            result = subprocess.run([sys.executable, str(SCRIPT), 'new'], env=env,
                                    check=True, text=True, capture_output=True)
            self.assertEqual(result.stdout.strip(), 'TKT-' + '9942')
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('counter',)])
                self.assertEqual([row[1] for row in connection.execute('PRAGMA table_info(counter)')], ['id', 'slot', 'sequence'])

    def test_missing_counter_and_invalid_bootstrap_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'counter.sqlite3'
            with self.assertRaises(ValueError): ticket_ref.allocate(path)
            self.assertFalse(path.exists())
            for slot, after in [(0, 0), (100, 0), (1, -1)]:
                with self.assertRaises(ValueError): ticket_ref.initialize(path, slot, after)
            self.assertFalse(path.exists())



class SlotTable(unittest.TestCase):
    def cli(self, tmp, *args, table=None):
        env = {**os.environ, 'DEVSTACK_TICKET_DB': str(Path(tmp) / 'counter.sqlite3')}
        if table is not None:
            registry = Path(tmp) / 'slots.json'
            registry.write_text(table if isinstance(table, str) else json.dumps({'slots': table}), encoding='utf-8')
            env['DEVSTACK_TICKET_SLOTS'] = str(registry)
        return subprocess.run([sys.executable, str(SCRIPT), 'init', *args], env=env, text=True, capture_output=True)

    def test_a_slot_listed_for_someone_else_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.cli(tmp, '--slot', '12', '--after', '0', table=[{'slot': 12, 'owner': 'dev-a'}])
            self.assertEqual(1, result.returncode)
            self.assertIn('taken by dev-a', result.stderr)
            self.assertFalse((Path(tmp) / 'counter.sqlite3').exists())
            result = self.cli(tmp, '--slot', '12', '--after', '0', '--owner', 'dev-b', table=[{'slot': 12, 'owner': 'dev-a'}])
            self.assertEqual(1, result.returncode)

    def test_the_listed_owner_and_an_unlisted_slot_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            table = [{'slot': 12, 'owner': 'dev-a'}]
            result = self.cli(tmp, '--slot', '12', '--after', '0', '--owner', 'dev-a', table=table)
            self.assertEqual(0, result.returncode, result.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.cli(tmp, '--slot', '13', '--after', '0', table=[{'slot': 12, 'owner': 'dev-a'}])
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('not in tools/ticket-ref/slots.json yet', result.stdout)

    def test_an_existing_counter_can_always_be_reinitialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            ticket_ref.initialize(Path(tmp) / 'counter.sqlite3', 2, 9827)  # a machine set up before the table
            result = self.cli(tmp, '--slot', '2', '--after', '0', table=[{'slot': 2, 'owner': 'reserved-maintainer'}])
            self.assertEqual(0, result.returncode, result.stderr)

    def test_an_invalid_table_is_refused(self):
        for table in ('not json', json.dumps({'slots': [{'slot': 12, 'owner': 'A Person'}]}),
                      json.dumps({'slots': [{'slot': 12, 'owner': 'dev-a'}, {'slot': 12, 'owner': 'dev-b'}]}),
                      json.dumps({'slots': [{'slot': 100, 'owner': 'dev-a'}]})):
            with tempfile.TemporaryDirectory() as tmp:
                result = self.cli(tmp, '--slot', '20', '--after', '0', table=table)
                self.assertEqual(1, result.returncode, table)
                self.assertIn('not a valid slot table', result.stderr)

    def test_committed_table_is_valid_and_mirrored_in_slots_md(self):
        slots = ticket_ref.load_slots(SCRIPT.with_name('slots.json'))
        self.assertTrue(slots)
        rows = re.findall(r'^\| (\d+) \| `([a-z0-9-]+)` \|', SCRIPT.with_name('SLOTS.md').read_text(encoding='utf-8'), re.M)
        self.assertEqual(slots, {int(slot): owner for slot, owner in rows})


if __name__ == '__main__':
    unittest.main()
