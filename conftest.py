"""
Shared fixtures for the automated test suite. Run with:

    docker compose -f docker-compose.test.yml up -d
    set DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pharmacy_test   (Windows PowerShell: $env:DATABASE_URL=...)
    pytest

Postgres is required (not SQLite) because several tests exercise the
plpgsql stored procedures in /sql — those are installed by the
`analytics.0001_install_functions` migration and are silently skipped on
non-Postgres backends, which would make those specific tests fail for the
wrong reason (missing function) rather than a real bug.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.branches.models import Branch
from apps.inventory.models import Category, Manufacturer, Medicine, Batch

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


def _auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture
def branch(db):
    return Branch.objects.create(name="Main Pharmacy", code="MAIN-01", city="Islamabad")


@pytest.fixture
def branch_2(db):
    return Branch.objects.create(name="North Branch", code="NTH-02", city="Rawalpindi")


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        username="test_owner", password="Owner@12345", role=User.Role.OWNER,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def manager_user(db, branch):
    return User.objects.create_user(
        username="test_manager", password="Manager@12345", role=User.Role.MANAGER, branch=branch,
    )


@pytest.fixture
def cashier_user(db, branch):
    return User.objects.create_user(
        username="test_cashier", password="Cashier@12345", role=User.Role.CASHIER, branch=branch,
    )


@pytest.fixture
def accountant_user(db, branch):
    return User.objects.create_user(
        username="test_accountant", password="Accountant@12345", role=User.Role.ACCOUNTANT, branch=branch,
    )


@pytest.fixture
def pharmacist_user(db, branch):
    return User.objects.create_user(
        username="test_pharmacist", password="Pharmacist@12345", role=User.Role.PHARMACIST, branch=branch,
    )


@pytest.fixture
def owner_client(owner_user):
    return _auth_client(owner_user)


@pytest.fixture
def manager_client(manager_user):
    return _auth_client(manager_user)


@pytest.fixture
def cashier_client(cashier_user):
    return _auth_client(cashier_user)


@pytest.fixture
def accountant_client(accountant_user):
    return _auth_client(accountant_user)


@pytest.fixture
def pharmacist_client(pharmacist_user):
    return _auth_client(pharmacist_user)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Analgesics")


@pytest.fixture
def manufacturer(db):
    return Manufacturer.objects.create(name="GSK", country="Pakistan")


@pytest.fixture
def medicine(db, category, manufacturer):
    return Medicine.objects.create(
        name="Panadol 500mg", generic_name="Paracetamol", sku="PAN-500",
        category=category, manufacturer=manufacturer, unit_type=Medicine.UnitType.TABLET,
        reorder_level=30,
    )


@pytest.fixture
def batch_far_expiry(db, medicine, branch):
    """Plenty of stock, expires far in the future — the 'later' FEFO batch."""
    return Batch.objects.create(
        medicine=medicine, branch=branch, batch_number="FAR-EXP-01",
        quantity_received=100, quantity_remaining=100,
        cost_price=Decimal("8.00"), sale_price=Decimal("12.00"),
        expiry_date=date.today() + timedelta(days=365),
    )


@pytest.fixture
def batch_near_expiry(db, medicine, branch):
    """Small stock, expires soon — FEFO should deplete this one FIRST."""
    return Batch.objects.create(
        medicine=medicine, branch=branch, batch_number="NEAR-EXP-01",
        quantity_received=5, quantity_remaining=5,
        cost_price=Decimal("8.00"), sale_price=Decimal("12.00"),
        expiry_date=date.today() + timedelta(days=10),
    )
