# Template 3 — End-to-End Integration Test Report

**Project Name:** ProcureSphere 360  
**Project Code:** HPE-PRD-2026-PROC01  
**Milestone:** Day 60 Integrated Beta Review (Review Build 2)  
**Partner:** VPD Technologies Pvt. Ltd.  
**Issuing Authority:** HPE Team  
**Evaluation Date:** 2026-11-24  

---

## 1. Executive Summary

This report documents the verification of **integrated, cross-module business workflows** executed on real PostgreSQL database transactions. Every transaction verifies state transitions, financial commitments, database constraints, and audit logging.

---

## 2. Integrated Workflow Test Scenarios

### Workflow 1: Sealed-Bid Sourcing Event & Dual-Stage Evaluation
- **Test ID:** `INT-WF-001`
- **Requirements Covered:** `REQ-SRC-01`, `REQ-SRC-02`, `REQ-SRC-03`, `REQ-SRC-04`
- **Modules Involved:** `sourcing`, `requisitions`, `vendors`, `audit`, `notifications`
- **Preconditions:** Active approved PR exists; at least 3 active KYC-verified vendors exist.
- **Test Steps:**
  1. Procurement Executive initiates Sourcing Event (`RFQ-2026-00001`) from approved PR.
  2. Dispatches `BidInvite` to 3 vendors (Cisco, Dell, HP).
  3. Vendors submit sealed bids with multi-line unit pricing prior to deadline.
  4. Verify blind bidding: competitor bid amounts and bidder identities are inaccessible to other vendors and evaluators.
  5. Sourcing window closes -> Technical evaluation executed. Bids scoring < 75% disqualified.
  6. Commercial evaluation unlocked for qualifying bids.
  7. Procurement Manager reviews evaluation summary and executes award approval.
- **Expected Result:** Award decision generates winning bidder notice; disqualification notices sent; audit trail records each transition.
- **Actual Result:** **Pass.** Winning vendor awarded; bids sealed prior to closing; award state transitions to `AWARDED`.
- **Database Verification:**
  - `sourcing_sourcingevent.status` = `'AWARDED'`
  - `sourcing_awarddecision.winning_bid_id` points to winning `VendorBid`
  - `audit_auditlog` contains entries for `PUBLISH`, `SUBMIT`, `EVALUATE`, and `APPROVE`.

---

### Workflow 2: Purchase Order Generation & Versioned Amendment
- **Test ID:** `INT-WF-002`
- **Requirements Covered:** `REQ-ORD-01`, `REQ-ORD-02`, `REQ-BUD-01`
- **Modules Involved:** `orders`, `sourcing`, `budgets`, `audit`
- **Preconditions:** Sourcing award decision finalized with total value $68,200.00.
- **Test Steps:**
  1. Generate Purchase Order (`PO-2026-00001`) from award decision.
  2. Verify budget transition: `BudgetReservation` converted to `SpendLedger` entry of type `COMMITMENT`.
  3. Vendor logs into portal and executes PO acknowledgement.
  4. Procurement Executive initiates PO amendment: increases line item 1 quantity from 2 to 3.
  5. Review amendment workflow: PO Version 1 preserved; Version 2 created in status `APPROVAL`.
  6. Procurement Manager approves amendment -> Version 2 becomes active.
- **Expected Result:** PO Version 1 remains immutable in history; line item IDs preserved; total commitment updated.
- **Actual Result:** **Pass.** Historical PO version intact; `POLine` primary keys preserved; spend ledger delta recorded.
- **Database Verification:**
  - `orders_purchaseorder.version` = `2`, `status` = `'ACKNOWLEDGED'`
  - `orders_poamendment.revision_number` = `1`, `status` = `'APPROVED'`
  - Prior `orders_poline` records retained; new line quantity reflected.

---

### Workflow 3: Multi-Line Warehouse Receipt, Inspection & Partial Delivery
- **Test ID:** `INT-WF-003`
- **Requirements Covered:** `REQ-REC-01`, `REQ-REC-02`
- **Modules Involved:** `receipts`, `orders`, `inventory`, `audit`
- **Preconditions:** Approved PO exists with 2 distinct line items.
- **Test Steps:**
  1. Warehouse receives initial partial shipment: 10 units of Line 1, 0 units of Line 2.
  2. Stores Receiver creates Goods Receipt Note (`GRN-2026-00001`).
  3. Receiver conducts physical inspection: accepts 8 units, rejects 2 units due to transit damage.
  4. System records `InspectionRecord` and `RejectionRecord` with return-to-vendor disposition.
  5. Verify PO status transitions to `PARTIAL_RECEIPT`.
  6. Final shipment arrives: remaining units received and 100% accepted under `GRN-2026-00002`.
- **Expected Result:** Both GRNs linked to PO; line acceptance counts aggregate correctly; PO status transitions to `COMPLETED`.
- **Actual Result:** **Pass.** Two independent GRN records persisted; rejection logged without destroying receipt history.
- **Database Verification:**
  - `receipts_goodsreceipt` count for PO = 2
  - `receipts_rejectionrecord` records 2 damaged units
  - `orders_purchaseorder.status` = `'COMPLETED'`

---

### Workflow 4: Automated 3-Way Match & Tolerance Exception Resolution
- **Test ID:** `INT-WF-004`
- **Requirements Covered:** `REQ-INV-01`, `REQ-INV-02`, `REQ-INV-03`
- **Modules Involved:** `invoices`, `orders`, `receipts`, `budgets`, `audit`
- **Preconditions:** Completed PO and accepted GRN exist.
- **Test Steps:**
  1. Supplier submits invoice (`INV-2026-001`) with a 4% unit price increase over PO line rate.
  2. System executes automated 3-way match: compares PO unit price, GRN accepted quantity, and Invoice line amount.
  3. Match engine evaluates tolerance: price increase exceeds the configured 2.5% threshold.
  4. System generates `MatchException` of type `PRICE_VARIANCE` and locks invoice in status `EXCEPTION`.
  5. Finance Manager reviews price justification and approves the variance exception.
  6. Invoice status transitions to `READY_FOR_PAYMENT`.
  7. Finance AP Specialist marks invoice paid -> `SpendLedger` transitions commitment to `ACTUAL` spend.
- **Expected Result:** Tolerance failure automatically halts payment; resolution workflow requires dual authorization; spend ledger records actual cash outlay.
- **Actual Result:** **Pass.** 3-way match exception properly flagged, approved, and ledger entry created.
- **Database Verification:**
  - `invoices_matchexception.status` = `'RESOLVED'`
  - `invoices_supplierinvoice.status` = `'PAID'`
  - `budgets_spendledger.entry_type` = `'ACTUAL'`

---

### Workflow 5: Contract Lifecycle & Scheduled Background Alerts
- **Test ID:** `INT-WF-005`
- **Requirements Covered:** `REQ-CON-01`, `REQ-CON-02`, `REQ-CON-03`
- **Modules Involved:** `contracts`, `notifications`, Celery Beat
- **Preconditions:** Active vendor exists.
- **Test Steps:**
  1. Contract Manager drafts annual support contract (`CON-2026-00001`) with renewal date set to 30 days out.
  2. Defines 4 quarterly milestone deliverables and obligation clauses.
  3. Submits for legal review -> Legal Manager executes legal sign-off.
  4. Business owner executes business approval -> Contract transitions to `ACTIVE`.
  5. Celery Beat task `scan_contract_expirations` triggers scheduled execution.
- **Expected Result:** Periodic task identifies contract entering renewal window; generates in-app and email alert to contract owner.
- **Actual Result:** **Pass.** Background worker executed task; `Notification` created and delivered.
- **Database Verification:**
  - `contracts_contract.status` = `'ACTIVE'`
  - `contracts_contractmilestone` records 4 milestones
  - `notifications_notification` contains contract renewal reminder for owner.

---

## 3. Test Execution Summary

| Suite / Test ID | Test Scenario | Status | Executed On |
|:---:|:---|:---:|:---:|
| `INT-WF-001` | RFQ/RFP Sourcing, Sealed Bidding, Evaluation & Award | **PASSED** | Staging / Local Postgres |
| `INT-WF-002` | Purchase Order Generation & Versioned Amendment | **PASSED** | Staging / Local Postgres |
| `INT-WF-003` | Goods Receipt Note, Line Inspection & Rejection | **PASSED** | Staging / Local Postgres |
| `INT-WF-004` | 3-Way Match Engine, Exception Resolution & Payment | **PASSED** | Staging / Local Postgres |
| `INT-WF-005` | Contract Lifecycle, Milestones & Celery Beat Alerts | **PASSED** | Staging / Local Postgres |
| `INT-WF-006` | Multi-Tenant Organization Isolation & Scoping | **PASSED** | Staging / Local Postgres |
| `INT-WF-007` | Vendor Self-Service Portal Quarantined Execution | **PASSED** | Staging / Local Postgres |
