"""
Data migration: fix decimal values that exceed their field's max_digits.

Django 6.0 changed the SQLite decimal converter to use:
    decimal.Context(prec=max_digits).create_decimal_from_float(value).quantize(...)

When a stored value has more integer digits than (max_digits - decimal_places),
the quantize call raises decimal.InvalidOperation at load time — even though
the value can be parsed as a Decimal.

Example: salary=20000000000 with max_digits=10, decimal_places=2
  → needs 12 significant digits, but Context(prec=10) only allows 10 → FAIL

This migration resets any out-of-range values to 0 (or NULL for nullable cols).
"""

from decimal import Decimal, InvalidOperation

from django.db import migrations


DECIMAL_COLUMNS = {
    "employees_staffmember": [("salary", False, 10, 2)],
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
    "payroll_overtimerate": [("multiplier", False, 4, 2)],
    "payroll_cashadvance": [("amount", False, 12, 2)],
    "payroll_statutorydeductiontable": [
        ("min_salary", False, 12, 2),
        ("employee_rate", False, 5, 4),
        ("employer_rate", False, 5, 4),
        ("max_salary", True, 12, 2),
        ("fixed_amount", True, 10, 2),
    ],
    "inventory_product": [("unit_cost", False, 10, 2), ("price", False, 10, 2)],
    "inventory_stockadjustment": [("cost_per_unit", False, 10, 2)],
    "billing_billableitem": [("cost", False, 10, 2), ("price", False, 10, 2)],
    "records_medicalrecord": [("weight", True, 5, 2), ("temperature", True, 4, 1)],
    "records_recordentry": [("weight", True, 5, 2), ("temperature", True, 4, 1)],
}


def _fix_column(cursor, table, col, nullable, max_digits, decimal_places):
    """Reset values that would overflow Context(prec=max_digits).quantize()."""
    replacement = "NULL" if nullable else "'0.00'"
    limit = Decimal(10 ** (max_digits - decimal_places))

    cursor.execute(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")  # noqa: S608
    bad_ids = []
    for row_id, val in cursor.fetchall():
        try:
            d = Decimal(str(val))
            if abs(d) >= limit:
                bad_ids.append(row_id)
        except (InvalidOperation, ValueError, TypeError):
            bad_ids.append(row_id)

    if bad_ids:
        for i in range(0, len(bad_ids), 500):
            chunk = bad_ids[i:i + 500]
            placeholders = ", ".join(["%s"] * len(chunk))
            cursor.execute(
                f"UPDATE {table} SET {col} = {replacement}"  # noqa: S608
                f" WHERE id IN ({placeholders})",
                chunk,
            )


def fix_overflow_decimals(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    for table, columns in DECIMAL_COLUMNS.items():
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
            [table],
        )
        if not cursor.fetchone():
            continue
        for col, nullable, max_digits, decimal_places in columns:
            _fix_column(cursor, table, col, nullable, max_digits, decimal_places)


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0006_fix_corrupted_decimals"),
    ]

    operations = [
        migrations.RunPython(fix_overflow_decimals, migrations.RunPython.noop),
    ]
