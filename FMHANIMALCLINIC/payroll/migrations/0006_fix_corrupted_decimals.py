"""
Data migration: fix corrupted decimal values across all apps.

SQLite stores DecimalField as TEXT. Rows with NULL, empty string, or
non-numeric text in those columns crash Django's ORM with
decimal.InvalidOperation at load time.

This migration sanitises every decimal column once so the database is clean
going forward. It is safe to re-run (idempotent).
"""

from decimal import Decimal, InvalidOperation

from django.db import migrations


# ── Same column map used by the fix_decimal_data management command ──────────
# table -> [(column, is_nullable)]
DECIMAL_COLUMNS = {
    "employees_staffmember": [("salary", False)],
    "payroll_payrollperiod": [
        ("total_gross", False),
        ("total_deductions", False),
        ("total_net", False),
    ],
    "payroll_payslip": [
        ("base_salary", False),
        ("overtime_hours", False),
        ("overtime_pay", False),
        ("holiday_pay", False),
        ("bonus", False),
        ("allowance", False),
        ("thirteenth_month_pay", False),
        ("sss", False),
        ("philhealth", False),
        ("pagibig", False),
        ("tax", False),
        ("cash_advance", False),
        ("late_deduction", False),
        ("absent_deduction", False),
        ("other_deductions", False),
        ("gross_pay", False),
        ("total_allowances", False),
        ("total_deductions", False),
        ("net_pay", False),
    ],
    "payroll_overtimerate": [("multiplier", False)],
    "payroll_cashadvance": [("amount", False)],
    "payroll_statutorydeductiontable": [
        ("min_salary", False),
        ("employee_rate", False),
        ("employer_rate", False),
        ("max_salary", True),
        ("fixed_amount", True),
    ],
    "inventory_product": [("unit_cost", False), ("price", False)],
    "inventory_stockadjustment": [("cost_per_unit", False)],
    "billing_billableitem": [("cost", False), ("price", False)],
    "records_medicalrecord": [("weight", True), ("temperature", True)],
    "records_recordentry": [("weight", True), ("temperature", True)],
}


def _fix_column(cursor, table, col, nullable):
    """
    Repair one decimal column.
    Table/column names are sourced from the hardcoded map above (not user input).
    """
    # Fast SQL fix for NULL and empty strings
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

    # Python scan for remaining non-parseable values
    cursor.execute(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")  # noqa: S608
    bad_ids = []
    for row_id, val in cursor.fetchall():
        try:
            Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            bad_ids.append(row_id)

    if bad_ids:
        replacement = "NULL" if nullable else "'0.00'"
        for i in range(0, len(bad_ids), 500):
            chunk = bad_ids[i:i + 500]
            placeholders = ", ".join(["%s"] * len(chunk))
            cursor.execute(
                f"UPDATE {table} SET {col} = {replacement}"  # noqa: S608
                f" WHERE id IN ({placeholders})",
                chunk,
            )


def fix_corrupted_decimals(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    for table, columns in DECIMAL_COLUMNS.items():
        # Skip tables that don't exist yet (e.g. fresh installs running all migrations)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
            [table],
        )
        if not cursor.fetchone():
            continue
        for col, nullable in columns:
            _fix_column(cursor, table, col, nullable)


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0005_alter_cashadvance_options_and_more"),
    ]

    operations = [
        migrations.RunPython(fix_corrupted_decimals, migrations.RunPython.noop),
    ]
