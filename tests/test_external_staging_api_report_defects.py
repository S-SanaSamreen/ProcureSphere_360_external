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

    role_admin = Role.objects.get_or_create(
        code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"}
    )[0]
    role_approver = Role.objects.get_or_create(
        code=Role.DEPT_APPROVER, defaults={"name": "Department Approver"}
    )[0]
    role_requester = Role.objects.get_or_create(
        code=Role.REQUESTER, defaults={"name": "Requester"}
    )[0]

    admin_user = User.objects.create_user(
        email="admin@test.com", password="password123", role=role_admin, organization=org
    )
    approver_user = User.objects.create_user(
        email="approver@test.com",
        password="password123",
        role=role_approver,
        department=dept,
        organization=org,
    )
    requester_user = User.objects.create_user(
        email="requester@test.com",
        password="password123",
        role=role_requester,
        department=dept,
        organization=org,
    )
    from apps.vendors.models import VendorCategory

    vcat, _ = VendorCategory.objects.get_or_create(
        code="CAT-TEST", defaults={"name": "Test Category"}
    )

    return {
        "org": org,
        "dept": dept,
        "cc": cc,
        "admin": admin_user,
        "approver": approver_user,
        "requester": requester_user,
        "vcat": vcat,
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
            assert (
                error["details"]
                == "An unexpected error occurred. Please contact the system administrator."
            )

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

    def test_smk_335_procurement_manager_can_approve_requisition_step_2(self, org_and_users):
        """SMK_335 / DEF-004: Procurement Manager must not receive 403 when approving requisition."""
        from django.utils import timezone

        role_pm = Role.objects.get_or_create(
            code=Role.PROC_MGR, defaults={"name": "Procurement Manager"}
        )[0]
        pm_user = User.objects.create_user(
            email="pm_approver@test.com",
            password="password123",
            role=role_pm,
            organization=org_and_users["org"],
        )
        pr = PurchaseRequisition.objects.create(
            pr_number="PR-TEST-SMK-335",
            title="SMK 335 Test PR",
            justification="Valid justification text",
            requester=org_and_users["requester"],
            department=org_and_users["dept"],
            cost_center=org_and_users["cc"],
            status=PurchaseRequisition.STATUS_MANAGER_REVIEW,
            total_amount=Decimal("1000.00"),
            requested_delivery_date=timezone.now().date(),
        )
        client = Client()
        client.force_login(pm_user)
        response = client.post(
            f"/api/v1/requisitions/{pr.id}/approve/",
            {"comments": "Procurement Manager approved"},
            content_type="application/json",
        )
        assert response.status_code != status.HTTP_403_FORBIDDEN

    def test_def_010_cancelled_sourcing_event_reverts_requisition_to_approved(self, org_and_users):
        """DEF-010: Sourcing event cancellation must return requisition to APPROVED state."""
        from django.utils import timezone

        from apps.sourcing.models import SourcingEvent
        from apps.sourcing.services import cancel_sourcing_event_service

        pr = PurchaseRequisition.objects.create(
            pr_number="PR-TEST-DEF-010",
            title="Sourcing Cancel PR",
            justification="Testing cancel reversion",
            requester=org_and_users["requester"],
            department=org_and_users["dept"],
            cost_center=org_and_users["cc"],
            status=PurchaseRequisition.STATUS_SOURCING,
            total_amount=Decimal("500.00"),
            requested_delivery_date=timezone.now().date(),
        )
        event = SourcingEvent.objects.create(
            event_number="RFQ-2026-TEST-DEF-010",
            title="Test RFQ for Cancel Reversion",
            event_type=SourcingEvent.TYPE_RFQ,
            status=SourcingEvent.STATUS_DRAFT,
            requisition=pr,
            bid_start_date=timezone.now(),
            bid_end_date=timezone.now() + timezone.timedelta(days=7),
            created_by=org_and_users["admin"],
        )
        cancel_sourcing_event_service(
            event=event, user=org_and_users["admin"], reason="Testing event cancellation"
        )
        pr.refresh_from_db()
        assert pr.status == PurchaseRequisition.STATUS_APPROVED

    def test_def_011_vendor_cannot_see_draft_or_approval_purchase_orders(self, org_and_users):
        """DEF-011: Vendor user must not see DRAFT or APPROVAL purchase orders."""
        from apps.orders.models import PurchaseOrder
        from apps.orders.selectors import scope_purchase_orders_queryset
        from apps.vendors.models import Vendor

        vendor = Vendor.objects.create(
            legal_name="Vendor DEF-011",
            vendor_number="VND-DEF-011",
            status=Vendor.STATUS_ACTIVE,
            tax_identification_number="TAX-DEF-011",
            category=org_and_users["vcat"],
        )
        role_vendor = Role.objects.get_or_create(
            code=Role.VENDOR_USER, defaults={"name": "Vendor User"}
        )[0]
        vendor_user = User.objects.create_user(
            email="vendor_user_def011@test.com",
            password="password123",
            role=role_vendor,
            vendor=vendor,
        )
        po_draft = PurchaseOrder.objects.create(
            po_number="PO-TEST-DRAFT",
            version=1,
            vendor=vendor,
            cost_center=org_and_users["cc"],
            status=PurchaseOrder.STATUS_DRAFT,
            total_amount=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
        )
        po_issued = PurchaseOrder.objects.create(
            po_number="PO-TEST-ISSUED",
            version=1,
            vendor=vendor,
            cost_center=org_and_users["cc"],
            status=PurchaseOrder.STATUS_ISSUED,
            total_amount=Decimal("200.00"),
            subtotal=Decimal("200.00"),
            tax_amount=Decimal("0.00"),
        )
        scoped = scope_purchase_orders_queryset(PurchaseOrder.objects.all(), vendor_user)
        po_ids = list(scoped.values_list("id", flat=True))
        assert po_draft.id not in po_ids
        assert po_issued.id in po_ids

    def test_def_012_stores_receiver_can_read_purchase_orders(self, org_and_users):
        """DEF-012: Stores/Receiver must be permitted to read purchase orders."""
        from apps.orders.models import PurchaseOrder
        from apps.vendors.models import Vendor

        vendor = Vendor.objects.create(
            legal_name="Vendor DEF-012",
            vendor_number="VND-DEF-012",
            status=Vendor.STATUS_ACTIVE,
            tax_identification_number="TAX-DEF-012",
            category=org_and_users["vcat"],
        )
        po = PurchaseOrder.objects.create(
            po_number="PO-TEST-DEF-012",
            version=1,
            vendor=vendor,
            cost_center=org_and_users["cc"],
            status=PurchaseOrder.STATUS_ISSUED,
            total_amount=Decimal("150.00"),
            subtotal=Decimal("150.00"),
            tax_amount=Decimal("0.00"),
        )
        role_receiver = Role.objects.get_or_create(
            code=Role.STORES_RECEIVER, defaults={"name": "Stores Receiver"}
        )[0]
        receiver_user = User.objects.create_user(
            email="receiver_def012@test.com",
            password="password123",
            role=role_receiver,
            organization=org_and_users["org"],
        )
        client = Client()
        client.force_login(receiver_user)
        response = client.get("/api/v1/purchase-orders/")
        assert response.status_code == status.HTTP_200_OK

    def test_def_013_scorecard_composite_score_matches_component_average(self, org_and_users):
        """DEF-013: Scorecard composite score must equal arithmetic average of 4 core indicators."""
        from apps.scorecards.models import VendorScorecard
        from apps.vendors.models import Vendor

        vendor = Vendor.objects.create(
            legal_name="Vendor DEF-013",
            vendor_number="VND-DEF-013",
            status=Vendor.STATUS_ACTIVE,
            tax_identification_number="TAX-DEF-013",
            category=org_and_users["vcat"],
        )
        card = VendorScorecard.objects.create(
            vendor=vendor,
            evaluation_period="Q1-2026",
            delivery_score=Decimal("100.00"),
            quality_score=Decimal("100.00"),
            price_score=Decimal("100.00"),
            compliance_score=Decimal("80.00"),
            evaluated_by=org_and_users["admin"],
        )
        # Average is (100 + 100 + 100 + 80) / 4 = 95.00
        assert card.composite_score == Decimal("95.00")

    def test_def_014_zero_unit_price_rejected_across_lines(self, org_and_users):
        """DEF-014: Zero unit price on requisition lines must be rejected with 400 Bad Request."""
        from django.utils import timezone

        client = Client()
        client.force_login(org_and_users["requester"])
        payload = {
            "title": "Zero Unit Price Test PR",
            "justification": "Testing zero unit price rejection",
            "department": str(org_and_users["dept"].id),
            "cost_center": str(org_and_users["cc"].id),
            "requested_delivery_date": str(timezone.now().date()),
            "lines": [
                {
                    "item_description": "Free Item",
                    "quantity": 1,
                    "estimated_unit_price": "0.00",
                }
            ],
        }
        response = client.post("/api/v1/requisitions/", payload, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_def_015_invoice_due_date_before_invoice_date_rejected(self, org_and_users):
        """DEF-015: Invoice with due_date earlier than invoice_date must be rejected with 400 Bad Request."""
        from django.utils import timezone

        from apps.orders.models import PurchaseOrder
        from apps.vendors.models import Vendor

        role_finance = Role.objects.get_or_create(
            code=Role.FINANCE_AP, defaults={"name": "Finance / AP"}
        )[0]
        finance_user = User.objects.create_user(
            email="finance_def015@test.com",
            password="password123",
            role=role_finance,
            organization=org_and_users["org"],
        )
        vendor = Vendor.objects.create(
            legal_name="Vendor DEF-015",
            vendor_number="VND-DEF-015",
            status=Vendor.STATUS_ACTIVE,
            tax_identification_number="TAX-DEF-015",
            category=org_and_users["vcat"],
        )
        po = PurchaseOrder.objects.create(
            po_number="PO-TEST-DEF-015",
            version=1,
            vendor=vendor,
            cost_center=org_and_users["cc"],
            status=PurchaseOrder.STATUS_ISSUED,
            total_amount=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
        )
        client = Client()
        client.force_login(finance_user)
        today = timezone.now().date()
        payload = {
            "vendor_id": str(vendor.id),
            "po_id": str(po.id),
            "invoice_number": "INV-DEF-015-TEST",
            "invoice_date": str(today),
            "due_date": str(today - timezone.timedelta(days=10)),
            "line_items": [{"description": "Item 1", "quantity": "1", "unit_price": "100.00"}],
        }
        response = client.post(
            "/api/v1/invoices/create-invoice/", payload, content_type="application/json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_def_016_summary_counters_match_order_by_grouping(self, org_and_users):
        """DEF-016: Summary status counters must not be collapsed by default model ordering."""
        from django.test import RequestFactory

        from apps.vendors.api_urls import VendorViewSet
        from apps.vendors.models import Vendor

        Vendor.objects.create(
            legal_name="Vnd 1",
            vendor_number="VND-S1",
            status=Vendor.STATUS_DRAFT,
            tax_identification_number="TAX-S1",
            category=org_and_users["vcat"],
        )
        Vendor.objects.create(
            legal_name="Vnd 2",
            vendor_number="VND-S2",
            status=Vendor.STATUS_DRAFT,
            tax_identification_number="TAX-S2",
            category=org_and_users["vcat"],
        )
        Vendor.objects.create(
            legal_name="Vnd 3",
            vendor_number="VND-S3",
            status=Vendor.STATUS_DRAFT,
            tax_identification_number="TAX-S3",
            category=org_and_users["vcat"],
        )
        factory = RequestFactory()
        request = factory.get("/api/v1/vendors/summary/")
        request.user = org_and_users["admin"]
        view = VendorViewSet.as_view({"get": "summary"})
        response = view(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["draft_vendors"] >= 3

    def test_def_017_purchase_order_creation_audited(self, org_and_users):
        """DEF-017 / DEF-FT-002: Purchase order creation via API must create a CREATE audit log."""
        from apps.audit.models import AuditLog
        from apps.vendors.models import Vendor

        role_pe = Role.objects.get_or_create(
            code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"}
        )[0]
        pe_user = User.objects.create_user(
            email="pe_def017@test.com",
            password="password123",
            role=role_pe,
            organization=org_and_users["org"],
        )
        vendor = Vendor.objects.create(
            legal_name="Vendor DEF-017",
            vendor_number="VND-DEF-017",
            status=Vendor.STATUS_ACTIVE,
            tax_identification_number="TAX-DEF-017",
            category=org_and_users["vcat"],
        )
        client = Client()
        client.force_login(pe_user)
        payload = {
            "vendor": str(vendor.id),
            "cost_center": str(org_and_users["cc"].id),
            "lines": [
                {"item_description": "Network Switch", "quantity": "1", "unit_price": "250.00"}
            ],
        }
        response = client.post("/api/v1/purchase-orders/", payload, content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        po_id = response.data["id"]
        create_logs = AuditLog.objects.filter(
            target_model="PurchaseOrder", target_object_id=po_id, action=AuditLog.ACTION_CREATE
        )
        assert create_logs.exists()

    def test_def_ft_003_cost_center_create_and_update_audited(self, org_and_users):
        """DEF-FT-003: Cost center create and update must generate CREATE and UPDATE audit logs."""
        from apps.audit.models import AuditLog

        client = Client()
        client.force_login(org_and_users["admin"])
        payload = {
            "name": "Audit Test Cost Center",
            "code": "CC-AUD-TEST-001",
            "department": str(org_and_users["dept"].id),
        }
        res_create = client.post(
            "/api/v1/organization/cost-centers/", payload, content_type="application/json"
        )
        assert res_create.status_code == status.HTTP_201_CREATED
        cc_id = res_create.data["id"]
        assert AuditLog.objects.filter(
            target_model="CostCenter", target_object_id=cc_id, action=AuditLog.ACTION_CREATE
        ).exists()

        res_update = client.patch(
            f"/api/v1/organization/cost-centers/{cc_id}/",
            {"name": "Updated CC Name"},
            content_type="application/json",
        )
        assert res_update.status_code == status.HTTP_200_OK
        assert AuditLog.objects.filter(
            target_model="CostCenter", target_object_id=cc_id, action=AuditLog.ACTION_UPDATE
        ).exists()

    def test_def_rbac_011_stores_receiver_and_legal_cannot_list_requisitions(self, org_and_users):
        """DEF-RBAC-011: Stores Receiver and Legal Manager must receive 403 on requisitions list."""
        role_receiver = Role.objects.get_or_create(
            code=Role.STORES_RECEIVER, defaults={"name": "Stores Receiver"}
        )[0]
        receiver_user = User.objects.create_user(
            email="receiver_rbac011@test.com",
            password="password123",
            role=role_receiver,
            organization=org_and_users["org"],
        )
        client = Client()
        client.force_login(receiver_user)
        response = client.get("/api/v1/requisitions/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_def_018_scorecards_calculate_is_idempotent(self, org_and_users):
        """DEF-018: Calling scorecards/calculate twice for same vendor and period must update, not duplicate."""
        from apps.scorecards.models import VendorScorecard
        from apps.vendors.models import Vendor

        role_pe = Role.objects.get_or_create(
            code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"}
        )[0]
        pe_user = User.objects.create_user(
            email="pe_def018@test.com",
            password="password123",
            role=role_pe,
            organization=org_and_users["org"],
        )
        vendor = Vendor.objects.create(
            legal_name="Vendor DEF-018",
            vendor_number="VND-DEF-018",
            status=Vendor.STATUS_ACTIVE,
            tax_identification_number="TAX-DEF-018",
            category=org_and_users["vcat"],
        )
        client = Client()
        client.force_login(pe_user)
        payload = {
            "vendor_id": str(vendor.id),
            "period": "Q2-2026",
            "comments": "First calculation",
        }
        r1 = client.post("/api/v1/scorecards/calculate/", payload, content_type="application/json")
        assert r1.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

        payload["comments"] = "Second calculation"
        r2 = client.post("/api/v1/scorecards/calculate/", payload, content_type="application/json")
        assert r2.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

        count = VendorScorecard.objects.filter(vendor=vendor, evaluation_period="Q2-2026").count()
        assert count == 1

    def test_obs_001_page_size_query_param_honoured(self, org_and_users):
        """OBS-001: StandardResultsSetPagination must honour page_size query parameter."""
        client = Client()
        client.force_login(org_and_users["admin"])
        response = client.get("/api/v1/accounts/roles/?page_size=3")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) == 3
