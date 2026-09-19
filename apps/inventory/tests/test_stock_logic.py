"""
Covers Business-Logic sheet items LOGIC-04, LOGIC-15, LOGIC-16.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from freezegun import freeze_time

from apps.inventory.models import Batch


@pytest.mark.django_db
class TestStockValuation:
    def test_batch_stock_value_is_quantity_times_cost(self, batch_far_expiry):
        """LOGIC-04: stock value must equal quantity_remaining x cost_price."""
        expected = batch_far_expiry.quantity_remaining * batch_far_expiry.cost_price
        assert batch_far_expiry.stock_value == expected

    def test_stock_value_updates_after_quantity_changes(self, batch_far_expiry):
        batch_far_expiry.quantity_remaining = 40
        batch_far_expiry.save(update_fields=["quantity_remaining"])
        batch_far_expiry.refresh_from_db()
        assert batch_far_expiry.stock_value == 40 * batch_far_expiry.cost_price


@pytest.mark.django_db
class TestLowStockBoundary:
    def test_medicine_exactly_at_reorder_level_counts_as_low_stock(
        self, pharmacist_client, branch, medicine, batch_far_expiry
    ):
        """LOGIC-16: the boundary is <=, not strictly <. A medicine whose
        total remaining stock EQUALS its reorder_level must still be flagged."""
        medicine.reorder_level = batch_far_expiry.quantity_remaining  # exact match: 100 == 100
        medicine.save(update_fields=["reorder_level"])

        response = pharmacist_client.get(
            "/api/inventory/medicines/low_stock/", {"branch": branch.id}
        )
        assert response.status_code == 200
        flagged_ids = [row["medicine_id"] for row in response.data]
        assert medicine.id in flagged_ids

    def test_medicine_one_above_reorder_level_is_not_flagged(
        self, pharmacist_client, branch, medicine, batch_far_expiry
    ):
        medicine.reorder_level = batch_far_expiry.quantity_remaining - 1  # 99 < 100 remaining
        medicine.save(update_fields=["reorder_level"])

        response = pharmacist_client.get(
            "/api/inventory/medicines/low_stock/", {"branch": branch.id}
        )
        flagged_ids = [row["medicine_id"] for row in response.data]
        assert medicine.id not in flagged_ids


@pytest.mark.django_db
class TestExpiryMath:
    @freeze_time("2026-09-12")
    def test_days_to_expiry_is_calendar_accurate(self, pharmacist_client, branch, medicine):
        batch = Batch.objects.create(
            medicine=medicine, branch=branch, batch_number="EXP-CHECK-01",
            quantity_received=10, quantity_remaining=10,
            cost_price=Decimal("5.00"), sale_price=Decimal("8.00"),
            expiry_date=date(2026, 10, 2),  # exactly 20 days from the frozen "today"
        )
        response = pharmacist_client.get(
            "/api/analytics/inventory/expiry-report/", {"branch": branch.id, "days": 90}
        )
        assert response.status_code == 200
        row = next(r for r in response.data["results"] if r["batch_id"] == batch.id)
        assert row["days_to_expiry"] == 20
