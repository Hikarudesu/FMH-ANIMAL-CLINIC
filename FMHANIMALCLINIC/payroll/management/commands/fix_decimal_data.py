"""
Management command to find and fix corrupted decimal values in the database.

SQLite stores DecimalField as TEXT/INTEGER/REAL. Problems that cause
decimal.InvalidOperation when Django 6.0 loads a row:
  1. NULL or empty-string values in non-nullable columns.
  2. Non-numeric text (e.g. 'abc', 'NaN').
  3. Values whose integer-digit count exceeds the field's (max_digits - decimal_places),
     because Django 6.0 uses decimal.Context(prec=max_digits).quantize() which raises
     InvalidOperation when the coefficient has too many significant digits.

Run this command to clean the database:
    python manage.py fix_decimal_data
    python manage.py fix_decimal_data --dry-run   # preview only

It is safe to run multiple times (idempotent).
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import connection

# Each entry: table_name -> list of (column_name, is_nullable, max_digits, decimal_places)
# is_nullable=True  → empty strings become NULL; out-of-range → NULL
# is_nullable=False → NULL / empty / out-of-range → '0.00'
DECIMAL_COLUMNS = {
    "employees_staffmember": [
        ("salary", False, 10, 2),
    ],
    "payroll_payrollperiod": [
        ("total_gross", False, 14, 2),
        ("total_deductions", False, 14, 2),
        ("total_net", False, 14, 2),
    ],
    "payroll_payslip": [
        ("base_salary", False, 12, 2),
        ("overtime_hours", False, 5, 2),
        ("overtime_pay", False, 10, 2),
        ("holiday_pay", False, 10, 2),
        ("bonus", False, 10, 2),
        ("allowance", False, 10, 2),
        ("thirteenth_month_pay", False, 10, 2),
        ("sss", False, 10, 2),
        ("philhealth", False, 10, 2),
        ("pagibig", False, 10, 2),
        ("tax", False, 10, 2),
        ("cash_advance", False, 10, 2),
        ("late_deduction", False, 10, 2),
        ("absent_deduction", False, 10, 2),
        ("other_deductions", False, 10, 2),
        ("gross_pay", False, 12, 2),
        ("total_allowances", False, 12, 2),
        ("total_deductions", False, 12, 2),
        ("net_pay", False, 12, 2),
    ],
    "payroll_overtimerate": [
        ("multiplier", False, 4, 2),
    ],
    "payroll_cashadvance": [
        ("amount", False, 12, 2),
    ],
    "payroll_statutorydeductiontable": [
        ("min_salary", False, 12, 2),
        ("employee_rate", False, 5, 4),
        ("employer_rate", False, 5, 4),
        ("max_salary", True, 12, 2),
        ("fixed_amount", True, 10, 2),
    ],
    "inventory_product": [
        ("unit_cost", False, 10, 2),
        ("price", False, 10, 2),
    ],
    "inventory_stockadjustment": [
        ("cost_per_unit", False, 10, 2),
    ],
    "billing_billableitem": [
        ("cost", False, 10, 2),
        ("price", False, 10, 2),
    ],
    "records_medicalrecord": [
        ("weight", True, 5, 2),
        ("temperature", True, 4, 1),
    ],
    "records_recordentry": [
        ("weight", True, 5, 2),
        ("temperature", True, 4, 1),
    ],
}


def _max_abs_value(max_digits, decimal_places):
    """Return the maximum absolute value allowed by a DecimalField's max_digits."""
    # max_digits=10, decimal_places=2 → int digits = 8 → max = 99999999.99
    int_digits = max_digits - decimal_places
    return Decimal(10 ** int_digits)  # exclusive upper bound (e.g. 100000000 for max 99999999.99)


def _value_overflows(val, max_digits, decimal_places):
    """Return True if val would overflow decimal.Context(prec=max_digits).quantize()."""
    try:
        d = Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return True  # unparseable is also bad
    limit = _max_abs_value(max_digits, decimal_places)
    return abs(d) >= limit


def _fix_column(cursor, table, col, nullable, max_digits, decimal_places):
    """
    Fix one decimal column in one table.
    Returns the number of rows repaired.

    Three classes of bad values are fixed:
      1. NULL / empty-string in a non-nullable column  → '0.00'
      2. Non-numeric text (e.g. 'abc')                 → '0.00' / NULL
      3. Values exceeding max_digits precision          → '0.00' / NULL
         (Django 6.0 raises InvalidOperation at the quantize step for these)

    NOTE: table and col are hardcoded in DECIMAL_COLUMNS above — they are
    never derived from user input, so f-string interpolation is safe here.
    """
    fixed = 0
    replacement = "NULL" if nullable else "'0.00'"

    # ── Step 1: Fix NULL and empty-string values via raw SQL (fast path) ──
    if nullable:
        cursor.execute(
            f"UPDATE {table} SET {col} = NULL"  # noqa: S608
            f" WHERE {col} = '' OR TRIM(CAST({col} AS TEXT)) = ''"
        )
    else:
        cursor.execute(
            f"UPDATE {table} SET {col} = '0.00'"  # noqa: S608
            f" WHERE {col} IS NULL OR {col} = ''"
            f" OR TRIM(CAST({col} AS TEXT)) = ''"
        )
    fixed += cursor.rowcount

    # ── Step 2: Python scan — non-parseable values AND values too large for max_digits ──
    # Raw SQL bypasses the ORM type converter, so we see the raw stored value.
    cursor.execute(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")  # noqa: S608
    bad_ids = []
    for row_id, val in cursor.fetchall():
        if _value_overflows(val, max_digits, decimal_places):
            bad_ids.append(row_id)

    if bad_ids:
        # Batch in chunks of 500 to stay within SQLite's expression-tree limit
        for i in range(0, len(bad_ids), 500):
            chunk = bad_ids[i:i + 500]
            placeholders = ", ".join(["%s"] * len(chunk))
            cursor.execute(
                f"UPDATE {table} SET {col} = {replacement}"  # noqa: S608
                f" WHERE id IN ({placeholders})",
                chunk,
            )
        fixed += len(bad_ids)

    return fixed


class Command(BaseCommand):
    help = (
        "Scan every decimal column across all models and replace corrupted "
        "values (NULL, empty string, non-numeric text) with safe defaults. "
        "Safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report corrupted rows without modifying the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved.\n"))

        total_fixed = 0

        with connection.cursor() as cursor:
            for table, columns in DECIMAL_COLUMNS.items():
                # Check the table exists (skip if not yet migrated)
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
                    [table],
                )
                if not cursor.fetchone():
                    self.stdout.write(f"  Skipping {table} (table not found)")
                    continue

                for col, nullable, max_digits, decimal_places in columns:
                    if dry_run:
                        # Count bad rows without updating
                        cursor.execute(
                            f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL",  # noqa: S608
                        )
                        bad = 0
                        # NULL/empty
                        cursor2 = connection.cursor()
                        cursor2.execute(
                            f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                            f" WHERE {col} IS NULL OR {col} = ''"
                            f" OR TRIM(CAST({col} AS TEXT)) = ''",
                        )
                        bad += cursor2.fetchone()[0]
                        # out-of-range
                        cursor.execute(
                            f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL",  # noqa: S608
                        )
                        for _, val in cursor.fetchall():
                            if _value_overflows(val, max_digits, decimal_places):
                                bad += 1
                        if bad:
                            self.stdout.write(
                                f"  {table}.{col}: {bad} corrupted row(s) found"
                            )
                    else:
                        fixed = _fix_column(cursor, table, col, nullable, max_digits, decimal_places)
                        if fixed:
                            self.stdout.write(
                                f"  Fixed {fixed} row(s) in {table}.{col}"
                            )
                            total_fixed += fixed

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run complete. Run without --dry-run to apply fixes."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nDone. Total rows repaired: {total_fixed}")
            )
