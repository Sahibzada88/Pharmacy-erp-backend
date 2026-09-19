# Pharmacy Chain ERP — Backend

Multi-branch Pharmacy Chain ERP backend: **Inventory + POS + Suppliers + Finance + CRM + Analytics**,
with role-based dashboards for **Owner, Branch Manager, Cashier, Accountant, and Pharmacist**.

- **Framework:** Django 5 + Django REST Framework
- **Database:** Supabase (Postgres) — with **Postgres stored procedures (plpgsql functions)**
  powering all analytics endpoints for speed (no heavy ORM aggregation on read-heavy reports)
- **Auth:** JWT (access + refresh) via `djangorestframework-simplejwt`, role embedded in the token
- **Deployment:** Dockerfile + `railway.json` (Railway backend deploy), CORS ready for a Next.js frontend on Vercel

---

## 1. Architecture overview

```
apps/
  accounts/     Custom User model (roles), JWT auth, staff management, permissions
  branches/     Pharmacy chain branches (multi-location)
  inventory/    Medicines, Batches (expiry/FEFO), Stock movements, transfers, low-stock/expiry alerts
  suppliers/    Suppliers, Purchase Orders, receiving stock into inventory, Supplier Payments (payables)
  sales/        POS: Checkout (cart -> invoice), multi-payment split, returns
  finance/      Bank accounts, bank transactions, daily cash register, expenses
  crm/          Customers, loyalty points, customer notes
  analytics/    NO models — calls Postgres stored procedures for every report/dashboard
sql/            Raw SQL: the actual stored procedures (functions), installed via a Django migration
config/         Django settings/urls (Supabase Postgres connection, JWT, CORS, DRF)
```

### Why stored procedures for analytics?
Analytics queries (sales trends, stock valuation, profit & loss, supplier dues, etc.) join and
aggregate across large tables. Instead of doing this in Python/ORM on every request, the heavy
lifting is done **inside Postgres** via `plpgsql` functions (see `/sql/*.sql`). Django just calls
`SELECT * FROM fn_name(...)` through a raw cursor (see `apps/analytics/db.py`) and returns the rows
as JSON — this is dramatically faster and scales better as your sales history grows.

### Role-based access model
| Role        | Access |
|-------------|--------|
| **OWNER**       | Everything, every branch, chain-wide analytics, can open/close branches, manage all staff |
| **MANAGER**     | Full operational access (inventory, POS, suppliers, finance, CRM) for their **own branch only** |
| **CASHIER**     | POS checkout, returns, customer lookup — for their own branch |
| **ACCOUNTANT**  | Finance & sales-value analytics, bank accounts, supplier payments, P&L — chain-wide or per branch (not staff performance) |
| **PHARMACIST**  | Inventory: medicines, batches, stock adjustments, expiry/low-stock reports |

Every branch-scoped model uses `BranchScopedQuerysetMixin` (`apps/accounts/mixins.py`), so a
cashier automatically only ever sees their own branch's data, while the Owner can see everything
or filter by `?branch=<id>`.

---

## 2. Local setup

### 2.1 Create a Supabase project
1. Go to supabase.com → New Project.
2. Go to **Project Settings → Database → Connection string → URI** (use the "Transaction pooler"
   connection string if you'll deploy on Railway/serverless).
3. Copy it — you'll paste it into `.env` as `DATABASE_URL`.

### 2.2 Install & configure
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# now edit .env and paste your Supabase DATABASE_URL, and a real SECRET_KEY
```

### 2.3 Generate migrations & set up the database
Migration files are intentionally **not pre-generated** in this zip (so they exactly match your
Django/DB version). Generate and apply them:

```bash
python manage.py makemigrations accounts branches inventory suppliers sales finance crm
python manage.py migrate
```

The **last** migration to run is `analytics.0001_install_functions`, which installs all 16 Postgres
stored procedures from `/sql/*.sql` into your Supabase database automatically. You can verify with:
```sql
select proname from pg_proc where proname like 'fn_%';
```

### 2.4 Seed demo data (branch + one user per role)
```bash
python manage.py seed_demo_data
```
This prints login credentials for `owner`, `manager1`, `cashier1`, `accountant1`, `pharmacist1`.

### 2.5 Run the server
```bash
python manage.py runserver
```
API docs (Swagger): `http://localhost:8000/api/docs/`
Django admin: `http://localhost:8000/admin/` (create one with `python manage.py createsuperuser`, or use the seeded `owner` account after also running `createsuperuser` for it if needed)

---

## 3. Running with Docker
```bash
docker-compose up --build
```
This builds the image, runs migrations, and starts the dev server on `http://localhost:8000`.

## 4. Deploying to Railway
1. Push this repo to GitHub.
2. In Railway: New Project → Deploy from GitHub repo. Railway detects the `Dockerfile` automatically
   (or reads `railway.json`).
3. Add environment variables in Railway's dashboard (same keys as `.env.example`): `SECRET_KEY`,
   `DEBUG=False`, `ALLOWED_HOSTS=<your-railway-domain>`, `DATABASE_URL=<supabase-uri>`,
   `CORS_ALLOWED_ORIGINS=<your-vercel-frontend-url>`.
4. Deploy. The container automatically runs `migrate` and `collectstatic` on every deploy (see
   `Dockerfile` CMD), then starts `gunicorn`.
5. Point your Next.js frontend's API base URL at the Railway domain.

## 4.1 Deploying to Vercel (serverless — alternative)

Railway/Docker is the primary, recommended path (a real long-running Django server). Vercel can also
host this backend as a **Python serverless function**, which is how this project has actually been
deployed and tested — but it comes with real trade-offs: cold starts, per-request timeout limits, and
no long-running background processes. Use this if you specifically need free/serverless hosting.

Two extra files make this work, both already included:

- **`vercel.json`** (repo root) — routes every request to the Python entry point:
  ```json
  {
    "routes": [
      { "src": "/(.*)", "dest": "api/index.py" }
    ]
  }
  ```
  Do **not** add a `"functions"` block with a pinned `"runtime"` version (e.g. `@vercel/python@3.0.0`)
  — Vercel's builder-pin resolution is finicky and this exact minimal config is what worked.

- **`api/index.py`** — boots Django as a WSGI app for Vercel's Python runtime:
  ```python
  import os, sys
  from pathlib import Path

  ROOT = Path(__file__).resolve().parent.parent
  sys.path.insert(0, str(ROOT))
  os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

  import django
  django.setup()
  from django.core.wsgi import get_wsgi_application
  app = get_wsgi_application()
  ```

**Setup steps:**
1. Push to GitHub as its own repo (e.g. `pharmacy_erp_backend`) — keep it separate from the frontend
   repo to avoid mix-ups.
2. In Vercel: **Add New → Project → Import** this repo.
3. **Framework Preset: Django**, **Root Directory: `/`** (the repo root — `manage.py` lives there).
4. Add environment variables (Project Settings → Environment Variables):
   ```
   SECRET_KEY=your-strong-secret
   DEBUG=False
   DATABASE_URL=<your Supabase connection string>
   ALLOWED_HOSTS=*                (or your exact *.vercel.app domain)
   CORS_ALLOWED_ORIGINS=*         (or your exact frontend URL — see note below)
   ```
5. Deploy. `requirements.txt` already includes `setuptools>=75.0.0` — without it, the build fails with
   `ModuleNotFoundError: No module named 'pkg_resources'` (needed by `drf-yasg`) on Vercel's Python
   runtime specifically (this doesn't happen on Railway/Docker, which is why it's easy to miss).
6. **The root URL (`/`) will 404 — this is expected.** There's no homepage view; this is an API. Test
   real routes instead: `/api/docs/`, `/api/auth/login/` (POST), `/admin/`.
7. `ALLOWED_HOSTS=*` and `CORS_ALLOWED_ORIGINS=*` are fine for initial testing (Django and this
   project's `settings.py` both natively support `*` as "allow everything") but should be narrowed to
   your exact domains before real use — see the CORS/`ALLOWED_HOSTS` notes in `.env.example`.

---



## 5. Authentication

```
POST /api/auth/login/          { "username": "...", "password": "..." }
  -> { "access": "...", "refresh": "...", "user": {...role, branch...} }

POST /api/auth/token/refresh/  { "refresh": "..." }
GET  /api/auth/me/             (Authorization: Bearer <access>)
POST /api/auth/change-password/
GET/POST /api/auth/staff/      (Owner/Manager: manage staff accounts)
```

The JWT access token's payload includes `role`, `branch_id`, and `full_name`, so your Next.js
frontend can route to the correct dashboard (Owner / Cashier / Accountant / Pharmacist / Manager)
immediately after login without an extra API call.

---

## 6. Key API endpoints

### Inventory
```
GET/POST      /api/inventory/medicines/
GET           /api/inventory/medicines/low_stock/
POST          /api/inventory/medicines/bulk-import/  (CSV upload — add hundreds of medicines + opening stock at once)
GET/POST      /api/inventory/batches/
GET           /api/inventory/batches/expiring_soon/?days=60
POST          /api/inventory/batches/adjust/          (damaged/expired write-off)
POST          /api/inventory/batches/transfer/        (move stock between branches)
GET           /api/inventory/stock-movements/         (full audit trail)
```

### Suppliers
```
GET/POST      /api/suppliers/suppliers/
GET/POST      /api/suppliers/purchase-orders/
POST          /api/suppliers/purchase-orders/{id}/receive/   (creates inventory batches)
GET/POST      /api/suppliers/payments/                 (money paid to suppliers)
```

### POS / Sales
```
POST          /api/sales/checkout/     (main POS endpoint — cart -> invoice, FEFO stock deduction)
POST          /api/sales/returns/
GET           /api/sales/invoices/
```

### Finance
```
GET/POST      /api/finance/bank-accounts/
GET/POST      /api/finance/bank-transactions/
GET/POST      /api/finance/cash-registers/
POST          /api/finance/cash-registers/{id}/close/
GET/POST      /api/finance/expenses/
```

### CRM
```
GET/POST      /api/crm/customers/
GET           /api/crm/loyalty-transactions/
GET/POST      /api/crm/notes/
```

### Analytics (stored-procedure powered — all accept `?branch=<id>&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`)
```
GET  /api/analytics/owner-dashboard/                 (combined KPI card)
GET  /api/analytics/sales/summary/
GET  /api/analytics/sales/daily-trend/
GET  /api/analytics/sales/top-medicines/
GET  /api/analytics/sales/cashier-performance/
GET  /api/analytics/sales/payment-methods/
GET  /api/analytics/inventory/stock-valuation/
GET  /api/analytics/inventory/stock-valuation-by-branch/   (Owner only)
GET  /api/analytics/inventory/expiry-report/?days=60
GET  /api/analytics/inventory/low-stock/
GET  /api/analytics/finance/bank-balance/
GET  /api/analytics/finance/cash-position/
GET  /api/analytics/finance/expense-breakdown/
GET  /api/analytics/finance/profit-and-loss/
GET  /api/analytics/suppliers/dues/                  ("kitne supplier ko dene hain")
GET  /api/analytics/suppliers/payment-trend/
```

---

## 7. Sample POS checkout request

```json
POST /api/sales/checkout/
{
  "customer": null,
  "items": [
    { "medicine_id": 12, "quantity": 2, "discount_amount": 0 },
    { "medicine_id": 47, "quantity": 1 }
  ],
  "payments": [
    { "method": "CASH", "amount": 850.00 }
  ],
  "discount_amount": 0,
  "tax_amount": 0
}
```
The backend automatically:
1. Picks stock using **FEFO** (first-expiry-first-out) across the medicine's batches at the
   cashier's branch.
2. Deducts `quantity_remaining` from the batch(es) and writes a `StockMovement(SALE_OUT)` row.
3. Snapshots `unit_cost_snapshot` on every sale line — this is what makes profit analytics accurate
   even if purchase costs change later.
4. Validates that the payment split adds up to the invoice total.

---

## 9. Automated testing

An automated pytest suite lives alongside the manual test plan spreadsheets and covers the
highest-value scenarios: FEFO stock deduction, atomic checkout rollback, low-stock boundary
conditions, bulk CSV import, and — most importantly — a **regression test for the exact
Owner-Dashboard-vs-Finance profit mismatch bug** found during manual testing, so it can never
silently come back after a future SQL change.

### Setup (isolated from your real Supabase data — never run tests against production data)
```bash
pip install -r requirements-dev.txt

# Spin up a throwaway local Postgres just for tests:
docker compose -f docker-compose.test.yml up -d

# Point Django at it (only for this terminal session):
# macOS/Linux:
export DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pharmacy_test
# Windows PowerShell:
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5433/pharmacy_test"

pytest
```
Postgres (not SQLite) is required because several tests exercise the actual `/sql/*.sql` stored
procedures — those are silently skipped on non-Postgres backends by the
`analytics.0001_install_functions` migration, and tests needing them auto-skip with a clear reason
if run on the wrong backend.

### What's covered so far
- `apps/sales/tests/test_checkout.py` — FEFO batch selection & splitting, insufficient-stock
  rejection, atomic rollback on payment mismatch, stock-movement audit trail, returns.
- `apps/inventory/tests/test_stock_logic.py` — stock valuation math, low-stock `<=` boundary,
  expiry-day calendar accuracy.
- `apps/inventory/tests/test_bulk_import.py` — CSV import counts, upsert-by-SKU behavior, one bad
  row not blocking the rest of the file.
- `apps/accounts/tests/test_auth.py` — login/JWT claims, a representative slice of role-based
  access control, branch-scoping data isolation.
- `apps/analytics/tests/test_profit_consistency.py` — **the regression test for the profit-formula
  bug**: asserts Owner Dashboard, Finance P&L, and Sales Summary all report identical gross profit
  for the same data, and that tax is never counted as profit.

This isn't 1:1 coverage of every row in the manual test plan spreadsheets — it automates the
scenarios most likely to silently break (money math, stock integrity) so those get caught
immediately on every push, while UI/visual checks stay in the manual spreadsheets.

### Continuous Integration
`.github/workflows/backend-tests.yml` runs this full suite automatically on every push/PR to
`main`, spinning up a real Postgres service container in GitHub Actions (no setup needed on your
end beyond pushing to GitHub — check the "Actions" tab on your repo after pushing).

### Adding more tests
Follow the existing pattern: fixtures in `conftest.py` (`owner_client`, `cashier_client`, `branch`,
`medicine`, etc. — reuse them, don't recreate similar setup in every test file), one test class per
feature area, one `def test_...` per Business-Logic row you want automated. Prioritize anything
that touches money, stock quantities, or cross-page number consistency — those are the bugs that
are easy to introduce silently and hard to catch by eye.

---

## 10. Extending this backend
- **Frontend**: pairs naturally with Next.js (Vercel) — CORS is pre-configured; just set
  `CORS_ALLOWED_ORIGINS` in `.env`.
- **Prescriptions / e-Rx**: add a `Prescription` model in `crm` or a new `prescriptions` app; link
  it to `Sale` and to `Medicine.requires_prescription`.
- **Barcode scanning**: `Medicine.barcode` and `Medicine.sku` are already indexed and searchable
  (`?search=<barcode>` on `/api/inventory/medicines/`).
- **More stored procedures**: add new `.sql` files to `/sql`, list them in
  `apps/analytics/migrations/0001_install_functions.py` `SQL_FILES`, then create a new migration
  (`0002_more_functions.py`) with the same `RunPython` pattern to install them without re-running
  the first migration.
