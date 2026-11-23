from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.test import Client, override_settings
from rest_framework import status

from apps.accounts.models import Role, User
from apps.core.exceptions import custom_exception_handler
from apps.organization.models import CostCenter, Department, Organization
from apps.requisitions.models import PurchaseRequisition


@pytest.fixture
def org_and_users(db):
    org = Organization.objects.create(name="HPE Global", code="HPE-GLOBAL")
    dept = Department.objects.create(name="IT Ops", code="IT-OPS", organization=org)
    cc = CostCenter.objects.create(code="CC-IT-01", name="IT Center", department=dept)

    role_admin = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})[0]
    role_approver = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Department Approver"})[0]
    role_requester = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})[0]

    admin_user = User.objects.create_user(
        email="admin@test.com", password="password123", role=role_admin, organization=org
    )
    approver_user = User.objects.create_user(
        email="approver@test.com", password="password123", role=role_approver, department=dept, organization=org
    )
    requester_user = User.objects.create_user(
        email="requester@test.com", password="password123", role=role_requester, department=dept, organization=org
    )

    return {
        "org": org,
        "dept": dept,
        "cc": cc,
        "admin": admin_user,
        "approver": approver_user,
        "requester": requester_user,
    }


@pytest.mark.django_db
class TestExternalStagingAPIDefectRemediations:
    def test_def_001_approver_dashboard_no_500(self, org_and_users):
        """DEF-001: Approver dashboard must return 200 and not crash on actual_spend attribute."""
        client = Client()
        client.force_login(org_and_users["approver"])
        response = client.get("/api/v1/approver/dashboard/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "available_budget" in data
        assert "pending_approvals" in data

    def test_def_002_approver_queue_no_500(self, org_and_users):
        """DEF-002: Approver queue must return 200 and not crash on currency attribute."""
        from django.utils import timezone
        PurchaseRequisition.objects.create(
            pr_number="PR-TEST-001",
            title="Hardware Requisition",
            justification="Upgrading servers",
            requester=org_and_users["requester"],
            department=org_and_users["dept"],
            cost_center=org_and_users["cc"],
            status=PurchaseRequisition.STATUS_MANAGER_REVIEW,
            total_amount=Decimal("5000.00"),
            requested_delivery_date=timezone.now().date(),
        )

        client = Client()
        client.force_login(org_and_users["approver"])
        response = client.get("/api/v1/approver/queue/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1
        assert data[0]["currency"] in ["USD", "INR", "EUR"]

    def test_def_003_exception_details_sanitized_in_production(self):
        """DEF-003: 500 exceptions must not leak internal exception details when DEBUG=False."""
        exc = RuntimeError("Sensitive internal model/attribute details: /etc/secrets")
        context = {"request": MagicMock()}

        with override_settings(DEBUG=False):
            response = custom_exception_handler(exc, context)
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            error = response.data["error"]
            assert error["code"] == "INTERNAL_SERVER_ERROR"
            assert "secrets" not in error["details"]
            assert error["details"] == "An unexpected error occurred. Please contact the system administrator."

    def test_def_006_content_security_policy_removes_unsafe_eval(self):
        """DEF-006: Content-Security-Policy must not contain 'unsafe-eval'."""
        client = Client()
        response = client.get("/api/v1/health/")
        assert response.status_code == status.HTTP_200_OK
        csp = response.headers.get("Content-Security-Policy", "")
        assert "unsafe-eval" not in csp
        assert "default-src 'self'" in csp

    def test_def_007_requisition_title_rejects_xss_script(self, org_and_users):
        """DEF-007: Creating requisition with <script> tag in title must return 400 validation error."""
        from django.utils import timezone
        client = Client()
        client.force_login(org_and_users["requester"])
        payload = {
            "title": "QA_AUTO_<script>alert(1)</script>",
            "justification": "Valid justification text",
            "department": str(org_and_users["dept"].id),
            "cost_center": str(org_and_users["cc"].id),
            "requested_delivery_date": str(timezone.now().date()),
            "lines": [
                {
                    "item_description": "Server Rack",
                    "quantity": 1,
                    "estimated_unit_price": "100.00",
                }
            ],
        }
        response = client.post("/api/v1/requisitions/", payload, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        # Check details for title validation error
        assert "title" in str(data["error"]["details"]).lower()
