"""
Covers Auth-Navigation sheet items and the RBAC sheet from the API test plan.
"""
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestLogin:
    def test_valid_login_returns_role_and_branch_in_response(self, cashier_user, branch):
        client = APIClient()
        response = client.post("/api/auth/login/", {
            "username": "test_cashier", "password": "Cashier@12345",
        }, format="json")
        assert response.status_code == 200
        assert response.data["user"]["role"] == "CASHIER"
        assert response.data["user"]["branch"] == branch.id
        assert "access" in response.data and "refresh" in response.data

    def test_wrong_password_rejected(self, cashier_user):
        client = APIClient()
        response = client.post("/api/auth/login/", {
            "username": "test_cashier", "password": "WrongPassword",
        }, format="json")
        assert response.status_code == 401

    def test_me_endpoint_requires_authentication(self):
        client = APIClient()
        response = client.get("/api/auth/me/")
        assert response.status_code == 401

    def test_me_endpoint_returns_current_user(self, cashier_client):
        response = cashier_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["username"] == "test_cashier"


@pytest.mark.django_db
class TestRoleBasedAccess:
    """A representative slice of the RBAC sheet — expand as needed."""

    def test_only_owner_can_create_branches(self, owner_client, manager_client, cashier_client):
        payload = {"name": "Test Branch", "code": "TST-99"}
        assert owner_client.post("/api/branches/", payload, format="json").status_code == 201
        assert manager_client.post("/api/branches/", {**payload, "code": "TST-98"}, format="json").status_code == 403
        assert cashier_client.post("/api/branches/", {**payload, "code": "TST-97"}, format="json").status_code == 403

    def test_only_pharmacist_manager_owner_can_create_medicines(
        self, pharmacist_client, cashier_client, accountant_client
    ):
        payload = {"name": "Test Med", "sku": "TST-MED-01"}
        assert pharmacist_client.post("/api/inventory/medicines/", payload, format="json").status_code == 201
        assert cashier_client.post("/api/inventory/medicines/", {**payload, "sku": "TST-MED-02"}, format="json").status_code == 403
        assert accountant_client.post("/api/inventory/medicines/", {**payload, "sku": "TST-MED-03"}, format="json").status_code == 403

    def test_only_cashier_manager_owner_can_checkout(self, accountant_client, pharmacist_client):
        payload = {"items": [{"medicine_id": 1, "quantity": 1}], "payments": [{"method": "CASH", "amount": "1.00"}]}
        assert accountant_client.post("/api/sales/checkout/", payload, format="json").status_code == 403
        assert pharmacist_client.post("/api/sales/checkout/", payload, format="json").status_code == 403

    def test_branch_scoping_hides_other_branches_data(self, cashier_client, branch_2):
        """A cashier in Branch A should never see Branch B's data, even
        without an explicit ?branch= filter."""
        response = cashier_client.get("/api/sales/invoices/")
        assert response.status_code == 200
        for invoice in response.data["results"]:
            assert invoice["branch"] != branch_2.id
