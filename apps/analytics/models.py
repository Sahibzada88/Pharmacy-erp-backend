"""
This app has no models of its own — it reads from sales, inventory, suppliers,
and finance tables via raw SQL calls to Postgres stored procedures/functions
defined in /sql and installed via migration 0001_install_functions.py.
"""
