import concurrent.futures
import importlib.util
import os
from pathlib import Path
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
            env = {**os.environ, 'PATSTACK_TICKET_DB': str(path)}
            subprocess.run([sys.executable, str(SCRIPT), 'init', '--slot', '2', '--after', '9827'],
                           env=env, check=True, capture_output=True)
            result = subprocess.run([sys.executable, str(SCRIPT), 'new'], env=env,
                                    check=True, text=True, capture_output=True)
            self.assertEqual(result.stdout.strip(), 'TKT-' + '9902')
            with sqlite3.connect(path) as connection:
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


if __name__ == '__main__':
    unittest.main()
