import json
import os
import subprocess
import sys
from pathlib import Path

import django
from django.core.management import call_command
from django.core.serializers import deserialize
from django.db import connection, transaction

BASE_DIR = Path(__file__).resolve().parent
FIXTURE_PATH = BASE_DIR / 'sqlite_data.json'
SQLITE_DB = BASE_DIR / 'db.sqlite3'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()


def run_management_command(*args):
    return subprocess.run(
        [sys.executable, 'manage.py', *args],
        cwd=BASE_DIR,
        check=True,
        text=True,
    )


def _disable_signals():
    from django.db.models import signals

    state = {
        'post_save': signals.post_save.receivers[:],
        'pre_save': signals.pre_save.receivers[:],
        'post_delete': signals.post_delete.receivers[:],
        'pre_delete': signals.pre_delete.receivers[:],
        'm2m_changed': signals.m2m_changed.receivers[:],
    }
    signals.post_save.receivers = []
    signals.pre_save.receivers = []
    signals.post_delete.receivers = []
    signals.pre_delete.receivers = []
    signals.m2m_changed.receivers = []
    return state


def _restore_signals(state):
    from django.db.models import signals

    signals.post_save.receivers = state['post_save']
    signals.pre_save.receivers = state['pre_save']
    signals.post_delete.receivers = state['post_delete']
    signals.pre_delete.receivers = state['pre_delete']
    signals.m2m_changed.receivers = state['m2m_changed']


def _flush_database():
    print('Flushing PostgreSQL data...')
    call_command('flush', '--noinput', verbosity=0)


def _load_fixture(dump_path):
    if not dump_path.exists():
        raise SystemExit(f'Fixture file not found: {dump_path}')

    print('Loading fixture:', dump_path)
    call_command('loaddata', str(dump_path), verbosity=1)


if __name__ == '__main__':
    if not SQLITE_DB.exists() and not FIXTURE_PATH.exists():
        raise SystemExit('No SQLite database or fixture file found. Place db.sqlite3 or sqlite_data.json beside this script.')

    print('Running migrations...')
    call_command('migrate', interactive=False, verbosity=0)

    if SQLITE_DB.exists():
        print('Exporting data from SQLite...')
        os.environ['PYTHONUTF8'] = '1'
        run_management_command(
            'dumpdata',
            '--database', 'sqlite',
            '--natural-foreign',
            '--natural-primary',
            '--exclude', 'contenttypes',
            '--exclude', 'auth.permission',
            '--exclude', 'sessions',
            '--exclude', 'admin.logentry',
            '--format', 'json',
            '--output', str(FIXTURE_PATH),
        )
    else:
        print('Using existing fixture:', FIXTURE_PATH)

    print('Flushing existing data and loading fixture into PostgreSQL...')
    signal_state = _disable_signals()
    try:
        _flush_database()
        _load_fixture(FIXTURE_PATH)
    except Exception as exc:
        print(f'Fixture load interrupted: {exc}')
        raise
    finally:
        _restore_signals(signal_state)

    print('SQLite-to-PostgreSQL import completed.')
