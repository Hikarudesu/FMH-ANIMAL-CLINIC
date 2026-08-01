import json
import os
import subprocess
import sys
from pathlib import Path

import django
from django.core.management import call_command
from django.db import connection

BASE_DIR = Path(__file__).resolve().parent
DB_SQLITE = BASE_DIR / 'db.sqlite3'

if not DB_SQLITE.exists():
    raise SystemExit(f'SQLite database not found at {DB_SQLITE}')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()


def run_management_command(*args):
    return subprocess.run(
        [sys.executable, 'manage.py', *args],
        cwd=BASE_DIR,
        check=True,
        text=True,
    )


def _load_fixture(dump_path):
    try:
        call_command('loaddata', str(dump_path), verbosity=0, database='default', stdout=sys.stdout, stderr=sys.stderr)
    except Exception as exc:
        print(f'Fixture load interrupted: {exc}')
        raise


def _disable_signals():
    from django.db.models import signals

    state = {
        'post_save': signals.post_save.receivers[:],
        'pre_save': signals.pre_save.receivers[:],
        'post_delete': signals.post_delete.receivers[:],
        'pre_delete': signals.pre_delete.receivers[:],
    }
    signals.post_save.receivers = []
    signals.pre_save.receivers = []
    signals.post_delete.receivers = []
    signals.pre_delete.receivers = []
    return state


def _restore_signals(state):
    from django.db.models import signals

    signals.post_save.receivers = state['post_save']
    signals.pre_save.receivers = state['pre_save']
    signals.post_delete.receivers = state['post_delete']
    signals.pre_delete.receivers = state['pre_delete']


if __name__ == '__main__':
    print('SQLite database detected:', DB_SQLITE)
    print('Running migrations...')
    call_command('migrate', interactive=False, verbosity=0)

    print('Preparing PostgreSQL for import...')
    with connection.cursor() as cursor:
        cursor.execute("SELECT setval(pg_get_serial_sequence('accounts_activitylog','id'), COALESCE((SELECT MAX(id)+1 FROM accounts_activitylog), 1), false)")
        cursor.execute("SELECT setval(pg_get_serial_sequence('branches_branch','id'), COALESCE((SELECT MAX(id)+1 FROM branches_branch), 1), false)")

    dump_path = BASE_DIR / 'sqlite_data.json'
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
        '--output', str(dump_path),
    )

    print('Loading data into PostgreSQL...')
    signal_state = _disable_signals()
    try:
        _load_fixture(dump_path)
    except Exception as exc:
        print(f'Fixture load interrupted: {exc}')
    finally:
        _restore_signals(signal_state)

    print('SQLite-to-PostgreSQL import completed.')
