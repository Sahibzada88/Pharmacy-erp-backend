"""
LOGIC-01/02/03/19 from the manual test plan — and a direct regression test
for the real bug we found: Owner Dashboard and Finance > P&L computing
"gross profit" with two different formulas (one ignored tax, the other
incorrectly counted tax as profit). All three analytics endpoints below now
share one formula: Gross Profit = Net Sales - Tax - Cost of Goods.

REQUIRES POSTGRES — these call the plpgsql functions in /sql, which are
only installed on a Postgres backend (see analytics.0001_install_functions).
Run against docker-compose.test.yml, not SQLite.
"""
import pytest
from decimal import Decimal
from django.db import connection

pytestmark = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Analytics stored procedures only exist on Postgres — see docker-compose.test.yml",
)


@pytest.mark.django_db
class TestProfitConsistencyAcrossDashboards:
    def _make_sale_with_tax(self, cashier_client, medicine, batch_far_expiry):
        """Sale of 2 units @ 12.00 = 24.00 subtotal, plus 5.00 tax -> total 29.00.
        cost_price is 8.00/unit -> COGS = 16.00.
        Correct gross profit = (29.00 - 5.00 tax) - 16.00 = 8.00 (NOT 13.00,
        which is what you'd get if tax were wrongly counted as profit)."""
        response = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 2}],
            "payments": [{"method": "CASH", "amount": "29.00"}],
            "tax_amount": "5.00",
        }, format="json")
        assert response.status_code == 201, response.data
        return response.data

    def test_owner_dashboard_and_finance_pnl_report_identical_gross_profit(
        self, cashier_client, owner_client, branch, medicine, batch_far_expiry
    ):
        self._make_sale_with_tax(cashier_client, medicine, batch_far_expiry)

        params = {"branch": branch.id, "date_from": "2000-01-01", "date_to": "2100-01-01"}
        owner_resp = owner_client.get("/api/analytics/owner-dashboard/", params)
        pnl_resp = owner_client.get("/api/analytics/finance/profit-and-loss/", params)
        summary_resp = owner_client.get("/api/analytics/sales/summary/", params)

        assert owner_resp.status_code == pnl_resp.status_code == summary_resp.status_code == 200

        owner_profit = Decimal(str(owner_resp.data["summary"]["gross_profit"]))
        pnl_profit = Decimal(str(pnl_resp.data["summary"]["gross_profit"]))
        summary_profit = Decimal(str(summary_resp.data["summary"]["gross_profit"]))

        # THE regression check: all three must agree exactly.
        assert owner_profit == pnl_profit == summary_profit

    def test_tax_is_excluded_from_gross_profit_everywhere(
        self, cashier_client, owner_client, branch, medicine, batch_far_expiry
    ):
        """LOGIC-19: tax_amount must never inflate profit. With the numbers
        in _make_sale_with_tax, correct gross profit is exactly 8.00."""
        self._make_sale_with_tax(cashier_client, medicine, batch_far_expiry)

        params = {"branch": branch.id, "date_from": "2000-01-01", "date_to": "2100-01-01"}
        response = owner_client.get("/api/analytics/finance/profit-and-loss/", params)

        assert response.status_code == 200
        assert Decimal(str(response.data["summary"]["gross_profit"])) == Decimal("8.00")
        # if this ever reads 13.00 instead, tax is being counted as profit again.

    def test_net_sales_matches_across_all_three_endpoints(
        self, cashier_client, owner_client, branch, medicine, batch_far_expiry
    ):
        self._make_sale_with_tax(cashier_client, medicine, batch_far_expiry)
        params = {"branch": branch.id, "date_from": "2000-01-01", "date_to": "2100-01-01"}

        owner_sales = Decimal(str(owner_client.get("/api/analytics/owner-dashboard/", params).data["summary"]["net_sales"]))
        pnl_sales = Decimal(str(owner_client.get("/api/analytics/finance/profit-and-loss/", params).data["summary"]["net_sales"]))
        summary_sales = Decimal(str(owner_client.get("/api/analytics/sales/summary/", params).data["summary"]["net_sales"]))

        assert owner_sales == pnl_sales == summary_sales == Decimal("29.00")


@pytest.mark.django_db
class TestSupplierDuesConsistency:
    def test_owner_dashboard_total_matches_suppliers_dues_total(self, owner_client, branch):
        """LOGIC-05: the payable total on the Owner Dashboard must equal the
        sum shown on the dedicated Suppliers > Amounts Owed endpoint."""
        from apps.suppliers.models import Supplier, PurchaseOrder, PurchaseOrderItem
        from apps.inventory.models import Medicine

        supplier = Supplier.objects.create(name="Test Supplier")
        medicine = Medicine.objects.create(name="Test Med", sku="DUES-TEST-01")
        po = PurchaseOrder.objects.create(branch=branch, supplier=supplier, po_number="DUES-PO-01", status="RECEIVED")
        PurchaseOrderItem.objects.create(
            purchase_order=po, medicine=medicine, quantity_ordered=10,
            quantity_received=10, unit_cost=Decimal("10.00"), unit_sale_price=Decimal("15.00"),
        )
        # No payment made -> full 100.00 should be outstanding.

        params = {"branch": branch.id, "date_from": "2000-01-01", "date_to": "2100-01-01"}
        dashboard = owner_client.get("/api/analytics/owner-dashboard/", params)
        dues = owner_client.get("/api/analytics/suppliers/dues/", {"branch": branch.id})

        assert Decimal(str(dashboard.data["summary"]["total_supplier_dues"])) == Decimal(str(dues.data["total_due"])) == Decimal("100.00")
