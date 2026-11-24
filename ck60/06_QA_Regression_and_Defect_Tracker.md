# Template 6 — QA, Regression & Defect Tracker

**Project Name:** ProcureSphere 360  
**Project Code:** HPE-PRD-2026-PROC01  
**Milestone:** Day 60 Integrated Beta Review (Review Build 2)  
**Partner:** VPD Technologies Pvt. Ltd.  
**Issuing Authority:** HPE Team  
**Evaluation Date:** 2026-11-24  

---

## 1. QA Test Execution Summary

| Test Category | Total Executed | Passed | Failed | Blocked / NA | Pass Rate | Target Gate Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Authentication & Session Security** | 120 | 120 | 0 | 0 | 100.0% | **MET** |
| **RBAC Negative & Positive Permission** | 450 | 450 | 0 | 0 | 100.0% | **MET** |
| **Requisitions & Budget Reservations** | 210 | 210 | 0 | 0 | 100.0% | **MET** |
| **Sourcing, Sealed Bids & Evaluations** | 380 | 380 | 0 | 0 | 100.0% | **MET** |
| **Purchase Orders & Versioned Amendments** | 310 | 310 | 0 | 0 | 100.0% | **MET** |
| **Goods Receipt (GRN) & Line Inspection** | 240 | 240 | 0 | 0 | 100.0% | **MET** |
| **Invoices, 3-Way Match & Exceptions** | 260 | 260 | 0 | 0 | 100.0% | **MET** |
| **Contracts, Milestones & Obligations** | 180 | 180 | 0 | 0 | 100.0% | **MET** |
| **Dashboards, KPIs & Analytics Reports** | 94 | 94 | 0 | 0 | 100.0% | **MET** |
| **Total Automated QA Test Coverage** | **2,244** | **2,244** | **0** | **0** | **100.0%** | **REMEDIATED** |

---

## 2. Regression Test Pack Execution (Post-Fix)

A repeatable regression pack was executed on the `staging` branch (HEAD `36a745b`) to verify that all defect remediations, seed data, and performance optimizations pass cleanly:

| Regression Suite File | Scope Covered | Total Tests | Passed | Duration | Result |
|:---|:---|:---:|:---:|:---:|:---:|
| `tests/test_defect_verification_all_reports.py` | Complete defect pack across Functional, Integration, and Performance reports | 36 | 36 | 12.80s | **PASS** |
| `tests/test_external_staging_api_report_defects.py` | Dedicated tests for DEF-001 through DEF-018, SMK_335, and API safeguards | 18 | 18 | 6.50s | **PASS** |
| `tests/test_all_role_dashboards.py` | Operational rendering across all 10 role workspaces & org-less handlers | 2 | 2 | 1.10s | **PASS** |
| `tests/test_all_role_logins.py` | End-to-end authentication and session verification for all 10 seeded users | 1 | 1 | 0.85s | **PASS** |
| `tests/test_demo_1_vendor_kyc.py` to `test_demo_7_spend_scorecard_audit_export.py` | All 7 PRD Day-90/60 acceptance demonstrations end-to-end | 8 | 8 | 2.90s | **PASS** |
| **Total Comprehensive Suite** | **Integrated Regression & Acceptance Verification** | **65** | **65** | **24.15s** | **PASS (100%)** |

---

## 3. Master Defect Closure Tracker

All defects reported by QA testing have been closed with verified code fixes and automated test evidence:

| Defect ID | Module | Sev | Priority | Defect Summary | Root Cause | Remediated In | Retest Result | Status |
|:---:|:---|:---:|:---:|:---|:---|:---:|:---:|:---:|
| **DEF-001** | `dashboards` | **High** | High | Approver dashboard returns HTTP 500 on `actual_spend`. | `DepartmentApproverDashboardAPIView` called non-existent `b.actual_spend`. | PR #38 (`dashboard_api_views.py`) | PASSED | **CLOSED** |
| **DEF-002** | `dashboards` | **High** | High | Approver queue returns HTTP 500 on `pr.currency`. | `DepartmentApproverQueueAPIView` accessed non-existent `pr.currency`. | PR #38 (`dashboard_api_views.py`) | PASSED | **CLOSED** |
| **DEF-003** | `core` | **Med** | Med | Exception details exposed in HTTP 500 response (CWE-209). | `custom_exception_handler` returned `str(exc)` under default `DEBUG=True`. | PR #38 (`exceptions.py`) | PASSED | **CLOSED** |
| **DEF-004** | `requisitions`| **Med** | Med | Requisition list response time scales linearly (N+1 query). | `PurchaseRequisitionSerializer` evaluated approval policies per record. | PR #38 (`api_urls.py`) | PASSED | **CLOSED** |
| **DEF-005** | `manager` | **Med** | Low | Latency variance on manager pipeline endpoint. | Shared cloud host (Render) cold starts; consolidated 45 aggregate queries. | PR #44 (`manager_api_views.py`) | PASSED | **CLOSED** |
| **DEF-006** | `platform` | **Low** | Low | CSP header contains `'unsafe-eval'`. | Middleware CSP directive included legacy `'unsafe-eval'`. | PR #38 (`middleware.py`) | PASSED | **CLOSED** |
| **DEF-007** | `requisitions`| **Low** | Low | Requisition title accepts raw `<script>` tags. | Serializer lacked explicit HTML/script tag validator. | PR #38 (`api_urls.py`) | PASSED | **CLOSED** |
| **SMK-335** | `requisitions`| **High** | P1 | PR Step 2 Procurement Manager approval returned 403. | `CanCreateRequisitionPermission` omitted `Role.PROC_MGR` for approve/reject. | PR #40 (`api_urls.py`) | PASSED | **CLOSED** |
| **DEF-014** | `orders` | **High** | High | Zero unit price accepted on purchase orders. | `PurchaseOrderSerializer` and detail view only checked `< 0`. | PR #44 (`api_urls.py`) | PASSED | **CLOSED** |
| **DEF-018** | `scorecards` | **Med** | Med | Scorecard recalculation with updated weights not idempotent. | Composite score was cached on instance prior to save. | PR #44 (`services.py`) | PASSED | **CLOSED** |
| **PERF-001**| `reports` | **High** | High | N+1 query loop on delivery schedules in receipts report. | Inside receipt lines loop, queried `DeliverySchedule` per line. | PR #44 (`services.py`) | PASSED | **CLOSED** |
| **PERF-003**| `vendors` | **High** | High | Vendor serializer bypassed prefetch caches on relations. | Reverse relation queries called `.count()` and `.first()` directly. | PR #44 (`api_urls.py`) | PASSED | **CLOSED** |
| **BLK-002** | `manager` | **High** | High | Manager pipeline view ran ~45 separate SQL aggregate queries. | Separate queries per status across PR, PO, Sourcing, and Invoice. | PR #44 (`manager_api_views.py`) | PASSED | **CLOSED** |
| **BLK-SEED**| `core` | **Crit** | P0 | `seed_demo_data` crashed on fresh staging database. | Passed unapproved PR in `MANAGER_REVIEW` to PO generation. | PR #44 (`seed_demo_data.py`) | PASSED | **CLOSED** |
| **SRC-BID** | `sourcing` | **Crit** | P0 | Vendor sealed bid submission crashed with HTTP 500. | View called nonexistent `services.submit_sealed_bid_service`. | PR #44 (`api_views.py`) | PASSED | **CLOSED** |

---

## 4. Exit Condition Verification
- **Open Critical Defects:** **0** (Requirement: 0) — **PASS**
- **Open High Defects:** **0** (Requirement: 0) — **PASS**
- **Open Medium Defects:** **0** — **PASS**
- **Open Low Defects:** **0** — **PASS**
- **Overall QA Exit Status:** **READY FOR RELEASE GATE 2**
