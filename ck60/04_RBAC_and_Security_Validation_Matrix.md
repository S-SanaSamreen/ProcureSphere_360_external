# Template 4 — RBAC & Security Validation Matrix

**Project Name:** ProcureSphere 360  
**Project Code:** HPE-PRD-2026-PROC01  
**Milestone:** Day 60 Integrated Beta Review (Review Build 2)  
**Partner:** VPD Technologies Pvt. Ltd.  
**Issuing Authority:** HPE Team  
**Evaluation Date:** 2026-11-24  

---

## 1. 10-Role Permission Matrix

The platform implements backend-enforced RBAC across all 12 domain modules. Access is verified in Django view functions and DRF permission classes (`rest_framework.permissions.BasePermission`):

| Role Name | Role Code | Primary Permissions & Workspaces | Prohibited / Restricted Endpoints | Backend Permission Guard |
|:---|:---|:---|:---|:---|
| **Super Administrator** | `SUPER_ADMIN` | Global config, all tenants, all organizations, audit logs, user management. | None (Global platform administrator). | `IsAuthenticated`, `_is_super_admin()` |
| **Purchase Requester** | `REQUESTER` | Create & edit draft PRs, submit PRs for own department / cost center. | Cannot approve PRs, cannot access sourcing events, cannot manage contracts. | `CanCreateRequisitionPermission`, `is_requester` |
| **Department Approver** | `DEPT_APPROVER` | Review & approve/reject PRs for assigned department, view department budget. | Cannot draft PRs for other departments, cannot award sourcing bids, cannot pay invoices. | `IsDepartmentApprover`, `is_dept_approver` |
| **Procurement Executive** | `PROC_EXEC` | Sourcing RFQ/RFP creation, publish events, bid technical scoring, draft POs. | Cannot execute award approvals, cannot approve budgets, cannot pay invoices. | `IsProcurementExecutive`, `CanManageSourcing` |
| **Procurement Manager** | `PROC_MGR` | Approve awards, approve PO amendments, policy exception review, manage contracts. | Cannot create goods receipts, cannot execute invoice payments. | `IsProcurementManager`, `CanManageContract` |
| **Finance / AP** | `FINANCE_AP` | Budget reviews, 3-way match exception approvals, invoice payment execution. | Cannot create sourcing events, cannot inspect physical shipments. | `IsFinanceUser`, `IsAPSpecialist` |
| **Stores / Receiver** | `STORES_RECEIVER` | Warehouse goods receipt (GRN), line inspection, rejection recording. | Cannot modify purchase order terms, cannot approve supplier invoices. | `IsStoresReceiver` |
| **Legal Manager** | `LEGAL_MGR` | Contract drafting, legal review, milestone tracking, termination. | Cannot issue purchase orders, cannot approve budget overruns. | `CanManageContract` |
| **Compliance Auditor** | `AUDITOR` | **Read-only** access to audit logs, approval chains, lifecycle traceability, exports. | Strictly blocked from all write mutations (`POST`, `PUT`, `PATCH`, `DELETE`). | `AuditorReadOnlyPermission` |
| **Vendor User** | `VENDOR_USER` | Restricted self-service: submit bids, acknowledge POs, submit invoices. | **Strictly blocked** from internal buyer APIs (PRs, budgets, approvals, other vendors). | `VendorPortalIsolationMiddleware` |

---

## 2. Negative Authorization (HTTP 403) Verification

Every sensitive endpoint enforces positive and negative authorization tests. Below is verified evidence from test runs:

| Test Case ID | Role Under Test | Target Endpoint | HTTP Method | Expected Result | Actual Result | Status |
|:---|:---|:---|:---:|:---:|:---:|:---:|
| `TC-API-001-RBAC-approver-deny` | `DEPT_APPROVER` | `/api/v1/admin/dashboard/` | GET | HTTP 403 Forbidden | HTTP 403 `Admin access required.` | **PASS** |
| `TC-API-001-RBAC-vendor-deny` | `VENDOR_USER` | `/api/v1/admin/dashboard/` | GET | HTTP 403 Forbidden | HTTP 403 `Admin access required.` | **PASS** |
| `TC-API-010-RBAC-finance-deny` | `FINANCE_AP` | `/api/v1/superadmin/dashboard/` | GET | HTTP 403 Forbidden | HTTP 403 `Super Admin access required.` | **PASS** |
| `TC-API-013-RBAC-requester-deny` | `REQUESTER` | `/api/v1/accounts/users/` | GET | HTTP 403 Forbidden | HTTP 403 `Permission Denied` | **PASS** |
| `TC-RBAC-W-users-approver` | `DEPT_APPROVER` | `/api/v1/accounts/users/` | POST | HTTP 403 Forbidden | HTTP 403 `Permission Denied` | **PASS** |
| `TC-API-020-RBAC-vendor-deny` | `VENDOR_USER` | `/api/v1/approvals/actions/` | GET | HTTP 403 Forbidden | HTTP 403 `Permission Denied` | **PASS** |
| `TC-API-037-RBAC-procexec-deny` | `PROC_EXEC` | `/api/v1/audit/approval-history/` | GET | HTTP 403 Forbidden | HTTP 403 `Permission Denied` | **PASS** |
| `TC-WF-REQ-RBAC-01-vendor-deny` | `VENDOR_USER` | `/api/v1/requisitions/` | POST | HTTP 403 Forbidden | HTTP 403 `External vendors strictly prohibited` | **PASS** |
| `TC-WF-REQ-BIZ-05-self-approval` | `REQUESTER` | `/api/v1/requisitions/<id>/approve/` | POST | HTTP 403 Forbidden | HTTP 403 `Requesters cannot approve own PR` | **PASS** |
| `TC-BOLA-USERS-approver` | `DEPT_APPROVER` | `/api/v1/auth/users/<other-id>/` | GET | HTTP 403 Forbidden | HTTP 403 `Permission Denied` | **PASS** |

---

## 3. Platform Security Baseline Verification

### 3.1 Content-Security-Policy (CSP) Hardening
- **Header:** `Content-Security-Policy`
- **Value:** `default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net data:; img-src 'self' data: https:; media-src 'self'; connect-src 'self' https://cdn.jsdelivr.net https://unpkg.com;`
- **Verification:** The `'unsafe-eval'` directive was eliminated in PR #38. Verified in `test_def_006_content_security_policy_removes_unsafe_eval`.

### 3.2 Information Disclosure Mitigation (CWE-209)
- **Header/Body:** In unhandled HTTP 500 error scenarios, `custom_exception_handler` suppresses internal model attribute names, database queries, and Python tracebacks.
- **Payload:**
  ```json
  {
    "error": {
      "code": "INTERNAL_SERVER_ERROR",
      "message": "An unexpected internal server error occurred.",
      "details": "An unexpected error occurred. Please contact the system administrator.",
      "request_id": "8f347b45-9dd5-42c1-92fc-d36ee611480c"
    }
  }
  ```
- **Verification:** Verified via `test_def_003_exception_details_sanitized_in_production`.

### 3.3 Cross-Site Scripting (XSS) Sanitization
- **Validation:** Serializers enforce `validate_no_html_or_script` on all user-supplied text fields (e.g. `title`, `justification`, `comments`), immediately rejecting `<script>` tags with HTTP 400.
- **Template Safety:** Verified all Django templates use standard auto-escaping (`{{ pr.title }}`) with zero use of `|safe` on user inputs.

### 3.4 Session & Cookie Hardening
- `sessionid` Cookie: `SameSite=Lax`, `HttpOnly=True`, `Secure=True` (on HTTPS/TLS).
- `csrftoken` Cookie: `SameSite=Lax`, `HttpOnly=False`, `Secure=True` (on HTTPS/TLS).
- CSRF Protection: Enforced across all state-changing endpoints (`POST`, `PUT`, `PATCH`, `DELETE`).
- Brute Force Lockout: `django-axes` throttles repeated failed logins returning HTTP 429.
