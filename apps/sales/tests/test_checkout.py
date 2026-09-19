"""
Covers Business-Logic sheet items LOGIC-07 through LOGIC-12 from the manual
test plan: FEFO correctness, batch-splitting, atomic rollback on payment
mismatch, insufficient-stock rejection, and return handling.
"""
import pytest
from apps.sales.models import Sale, SaleItem
from apps.inventory.models import Batch, StockMovement


@pytest.mark.django_db
class TestCheckoutFEFO:
    def test_deducts_from_soonest_expiring_batch_first(
        self, cashier_client, medicine, batch_near_expiry, batch_far_expiry
    ):
        """LOGIC-09: FEFO must exhaust the near-expiry batch before touching
        the far-expiry one, even though both belong to the same medicine."""
        response = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 3}],
            "payments": [{"method": "CASH", "amount": "36.00"}],  # 3 x 12.00
        }, format="json")

        assert response.status_code == 201, response.data
        batch_near_expiry.refresh_from_db()
        batch_far_expiry.refresh_from_db()
        assert batch_near_expiry.quantity_remaining == 2  # 5 - 3
        assert batch_far_expiry.quantity_remaining == 100  # untouched

    def test_splits_sale_across_batches_when_nearest_is_insufficient(
        self, cashier_client, medicine, batch_near_expiry, batch_far_expiry
    ):
        """LOGIC-10: selling more than the near batch holds should spill the
        remainder into the next-soonest-expiring batch automatically."""
        response = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 8}],
            "payments": [{"method": "CASH", "amount": "96.00"}],  # 8 x 12.00
        }, format="json")

        assert response.status_code == 201, response.data
        batch_near_expiry.refresh_from_db()
        batch_far_expiry.refresh_from_db()
        assert batch_near_expiry.quantity_remaining == 0     # fully depleted first
        assert batch_far_expiry.quantity_remaining == 97     # 100 - (8-5)

        sale = Sale.objects.get(id=response.data["id"])
        assert sale.items.count() == 2  # one line per batch touched


@pytest.mark.django_db
class TestCheckoutValidation:
    def test_rejects_insufficient_stock_and_creates_nothing(self, cashier_client, medicine, batch_far_expiry):
        response = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 9999}],
            "payments": [{"method": "CASH", "amount": "1.00"}],
        }, format="json")

        assert response.status_code == 400
        assert Sale.objects.count() == 0
        batch_far_expiry.refresh_from_db()
        assert batch_far_expiry.quantity_remaining == 100  # untouched

    def test_payment_mismatch_rolls_back_completely(self, cashier_client, medicine, batch_far_expiry):
        """LOGIC-12: a mismatched payment total must leave NO trace — no
        Sale, no SaleItem, no stock deduction, no StockMovement."""
        response = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 2}],
            "payments": [{"method": "CASH", "amount": "5.00"}],  # should be 24.00
        }, format="json")

        assert response.status_code == 400
        assert Sale.objects.count() == 0
        assert SaleItem.objects.count() == 0
        assert StockMovement.objects.count() == 0
        batch_far_expiry.refresh_from_db()
        assert batch_far_expiry.quantity_remaining == 100

    def test_owner_without_branch_gets_clear_error_not_a_crash(self, owner_client, medicine, batch_far_expiry):
        """LOGIC/POS-11: owner has no home branch, must specify one explicitly."""
        response = owner_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 1}],
            "payments": [{"method": "CASH", "amount": "12.00"}],
        }, format="json")

        assert response.status_code == 400
        assert response.status_code != 500  # must never be an unhandled crash

    def test_owner_with_branch_specified_succeeds(self, owner_client, branch, medicine, batch_far_expiry):
        response = owner_client.post("/api/sales/checkout/", {
            "branch": branch.id,
            "items": [{"medicine_id": medicine.id, "quantity": 1}],
            "payments": [{"method": "CASH", "amount": "12.00"}],
        }, format="json")
        assert response.status_code == 201, response.data


@pytest.mark.django_db
class TestCheckoutAuditTrail:
    def test_creates_stock_movement_matching_the_sale(self, cashier_client, medicine, batch_far_expiry):
        """LOGIC-08: every stock deduction must leave an audit trail entry."""
        response = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 4}],
            "payments": [{"method": "CASH", "amount": "48.00"}],
        }, format="json")
        assert response.status_code == 201, response.data

        movement = StockMovement.objects.get(batch=batch_far_expiry)
        assert movement.movement_type == StockMovement.MovementType.SALE_OUT
        assert movement.quantity == -4
        assert movement.reference == response.data["invoice_number"]


@pytest.mark.django_db
class TestSaleReturns:
    def test_return_restores_stock_and_logs_movement(self, cashier_client, medicine, batch_far_expiry):
        """LOGIC-11: returning items must add stock back and log RETURN_IN."""
        checkout = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 5}],
            "payments": [{"method": "CASH", "amount": "60.00"}],
        }, format="json")
        assert checkout.status_code == 201, checkout.data
        sale_item_id = checkout.data["items"][0]["id"]

        batch_far_expiry.refresh_from_db()
        assert batch_far_expiry.quantity_remaining == 95  # 100 - 5

        return_response = cashier_client.post("/api/sales/returns/", {
            "sale_item": sale_item_id,
            "quantity": 2,
            "reason": "Customer changed mind",
        }, format="json")
        assert return_response.status_code == 201, return_response.data

        batch_far_expiry.refresh_from_db()
        assert batch_far_expiry.quantity_remaining == 97  # 95 + 2 back

        return_in = StockMovement.objects.filter(
            batch=batch_far_expiry, movement_type=StockMovement.MovementType.RETURN_IN
        ).first()
        assert return_in is not None
        assert return_in.quantity == 2

        sale = Sale.objects.get(id=checkout.data["id"])
        assert sale.status == Sale.Status.PARTIALLY_RETURNED

    def test_cannot_return_more_than_sold(self, cashier_client, medicine, batch_far_expiry):
        checkout = cashier_client.post("/api/sales/checkout/", {
            "items": [{"medicine_id": medicine.id, "quantity": 2}],
            "payments": [{"method": "CASH", "amount": "24.00"}],
        }, format="json")
        sale_item_id = checkout.data["items"][0]["id"]

        response = cashier_client.post("/api/sales/returns/", {
            "sale_item": sale_item_id,
            "quantity": 999,
        }, format="json")
        assert response.status_code == 400
