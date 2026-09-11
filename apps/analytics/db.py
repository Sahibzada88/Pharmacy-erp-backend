"""
Small helper to call a Postgres function (`SELECT * FROM fn_name(...)`) and
return a list of dicts. Keeps analytics views thin and fast — no ORM overhead,
straight to the stored procedure.
"""
from django.db import connection


def call_function(function_name, params):
    """
    params: tuple of positional arguments matching the function's signature.
    Returns: list[dict] — one dict per returned row, keyed by column name.
    """
    placeholders = ', '.join(['%s'] * len(params))
    query = f"SELECT * FROM {function_name}({placeholders})"
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def call_function_one(function_name, params):
    """Same as call_function but returns the single row (or None) — for
    summary-style functions that return exactly one row."""
    rows = call_function(function_name, params)
    return rows[0] if rows else None
