"""
Covers Inventory sheet items INVU-04 and INVU-05: bulk CSV import creates the
right counts, and a single bad row is reported without blocking good rows.
"""
import io
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.inventory.models import Medicine, Batch


def _csv_upload(content: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("medicines.csv", content.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
class TestBulkImport:
    def test_imports_medicines_and_opening_stock(self, pharmacist_client, branch):
        csv_content = (
            "name,sku,category,manufacturer,unit_type,reorder_level,requires_prescription,"
            "branch_code,quantity,cost_price,sale_price,expiry_date\n"
            f"Panadol 500mg,PAN-500,Analgesics,GSK,TABLET,30,FALSE,{branch.code},100,8.00,12.00,2027-12-31\n"
            f"Brufen 400mg,BRU-400,Analgesics,Abbott,TABLET,25,FALSE,{branch.code},50,10.00,15.00,2027-10-31\n"
        )
        response = pharmacist_client.post(
            "/api/inventory/medicines/bulk-import/",
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )
        assert response.status_code == 200, response.data
        assert response.data["created_medicines"] == 2
        assert response.data["created_batches"] == 2
        assert response.data["error_count"] == 0
        assert Medicine.objects.filter(sku="PAN-500").exists()
        assert Batch.objects.filter(medicine__sku="BRU-400", quantity_remaining=50).exists()

    def test_reupload_same_sku_updates_instead_of_duplicating(self, pharmacist_client, branch):
        csv_v1 = f"name,sku,branch_code\nPanadol,PAN-500,\n"
        csv_v2 = "name,sku,reorder_level\nPanadol 500mg Updated,PAN-500,50\n"

        r1 = pharmacist_client.post("/api/inventory/medicines/bulk-import/", {"file": _csv_upload(csv_v1)}, format="multipart")
        assert r1.status_code == 200
        r2 = pharmacist_client.post("/api/inventory/medicines/bulk-import/", {"file": _csv_upload(csv_v2)}, format="multipart")
        assert r2.status_code == 200

        assert Medicine.objects.filter(sku="PAN-500").count() == 1  # no duplicate
        med = Medicine.objects.get(sku="PAN-500")
        assert med.name == "Panadol 500mg Updated"
        assert med.reorder_level == 50

    def test_bad_row_does_not_block_good_rows(self, pharmacist_client, branch):
        """INVU-05: a row with an invalid branch_code should be reported as an
        error while every other valid row still imports successfully."""
        csv_content = (
            "name,sku,branch_code,quantity,cost_price,sale_price,expiry_date\n"
            f"Good Medicine,GOOD-001,{branch.code},10,5.00,8.00,2027-01-01\n"
            "Bad Medicine,BAD-001,NO-SUCH-BRANCH,10,5.00,8.00,2027-01-01\n"
            f"Another Good One,GOOD-002,{branch.code},20,6.00,9.00,2027-01-01\n"
        )
        response = pharmacist_client.post(
            "/api/inventory/medicines/bulk-import/",
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )
        assert response.status_code == 200
        assert response.data["created_medicines"] == 3  # all 3 medicines still created
        assert response.data["created_batches"] == 2    # only the 2 valid-branch rows got stock
        assert response.data["error_count"] == 1
        assert response.data["errors"][0]["row"] == 3  # the bad row (header=1, so data starts at 2)
        assert "NO-SUCH-BRANCH" in response.data["errors"][0]["error"] or "does not exist" in response.data["errors"][0]["error"]

    def test_missing_required_columns_rejected_upfront(self, pharmacist_client):
        csv_content = "generic_name,category\nParacetamol,Analgesics\n"  # missing name & sku
        response = pharmacist_client.post(
            "/api/inventory/medicines/bulk-import/",
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )
        assert response.status_code == 400

    def test_cashier_cannot_bulk_import(self, cashier_client):
        csv_content = "name,sku\nTest,TEST-001\n"
        response = cashier_client.post(
            "/api/inventory/medicines/bulk-import/",
            {"file": _csv_upload(csv_content)},
            format="multipart",
        )
        assert response.status_code == 403
