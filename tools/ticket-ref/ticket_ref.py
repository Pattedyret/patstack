#!/usr/bin/env python3
"""Allocate reference numbers, with no task state or agent eligibility rules."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3


def database_path():
    return Path(os.environ.get('PATSTACK_TICKET_DB',
                Path.home() / '.local/state/patstack/tickets.sqlite3')).expanduser()


def connect(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Ticket counter must not be a symlink')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=20, isolation_level=None)
    if os.name != 'nt':
        path.chmod(0o600)
    return connection


def initialize(path, slot, after):
    if type(slot) is not int or not 1 <= slot <= 99:
        raise ValueError('Use a unique issuer slot from 1 through 99')
    if type(after) is not int or after < 0:
        raise ValueError('The historical high-water number must be nonnegative')
    with closing(connect(path)) as connection:
        try:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('CREATE TABLE IF NOT EXISTS counter '
                               '(id INTEGER PRIMARY KEY CHECK(id=1), slot INTEGER NOT NULL, sequence INTEGER NOT NULL)')
            row = connection.execute('SELECT slot, sequence FROM counter WHERE id=1').fetchone()
            if row and row[0] != slot:
                raise ValueError('Existing counter has another issuer slot; do not change or clone it')
            sequence = max(row[1] if row else 0, after // 100)
            connection.execute('INSERT OR REPLACE INTO counter VALUES (1, ?, ?)', (slot, sequence))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def allocate(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Ticket counter is not initialized on this host')
    with closing(connect(path)) as connection:
        try:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT slot, sequence FROM counter WHERE id=1').fetchone()
            if not row or not 1 <= row[0] <= 99 or row[1] < 0:
                raise ValueError('Invalid private ticket counter')
            slot, sequence = row[0], row[1] + 1
            connection.execute('UPDATE counter SET sequence=? WHERE id=1', (sequence,))
            connection.commit()
            return f'TKT-{sequence * 100 + slot:04d}'
        except BaseException:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Bootstrap one host with its unique issuer slot')
    init.add_argument('--slot', type=int, required=True)
    init.add_argument('--after', type=int, required=True)
    commands.add_parser('new', help='Allocate one reference for a new designated task')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            initialize(database_path(), args.slot, args.after)
            print('Ticket reference counter initialized; no task created.')
        else:
            print(allocate(database_path()))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'ticket-ref: {error}\n')


if __name__ == '__main__':
    main()
