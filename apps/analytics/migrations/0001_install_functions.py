"""
Installs all Postgres stored procedures (functions) used for fast analytics
queries. These read raw SQL files from the /sql directory at the project root
so the SQL is easy to review/version-control outside of migration files.

Runs AFTER all domain apps' initial migrations, since the functions reference
their tables (sales_sale, inventory_batch, finance_bank_account, etc).
"""
from pathlib import Path
from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'sql'

SQL_FILES = [
    '001_sales_analytics_functions.sql',
    '002_inventory_analytics_functions.sql',
    '003_finance_analytics_functions.sql',
    '004_supplier_and_owner_dashboard_functions.sql',
]


def install_functions(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        # Stored procedures use plpgsql; skip silently on sqlite (local dev fallback)
        return
    for filename in SQL_FILES:
        sql_path = SQL_DIR / filename
        sql = sql_path.read_text()
        schema_editor.execute(sql)


def drop_functions(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    function_names = [
        'fn_sales_summary', 'fn_daily_sales_trend', 'fn_top_selling_medicines',
        'fn_cashier_performance', 'fn_payment_method_breakdown',
        'fn_stock_valuation', 'fn_stock_valuation_by_branch', 'fn_expiry_report',
        'fn_low_stock_report', 'fn_bank_balance_summary', 'fn_cash_position',
        'fn_expense_breakdown', 'fn_profit_and_loss', 'fn_supplier_dues',
        'fn_supplier_payment_trend', 'fn_owner_dashboard_summary',
    ]
    for name in function_names:
        schema_editor.execute(f"DROP FUNCTION IF EXISTS {name} CASCADE;")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('branches', '0001_initial'),
        ('inventory', '0002_initial'),
        ('suppliers', '0001_initial'),
        ('sales', '0001_initial'),
        ('finance', '0001_initial'),
        ('crm', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(install_functions, reverse_code=drop_functions),
    ]
