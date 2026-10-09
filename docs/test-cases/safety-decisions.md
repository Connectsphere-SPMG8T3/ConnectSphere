# Safety Officer queue and decisions

## Safety review (CR-103 / CR-104)

**Status: implemented on branch; live verification and manual acceptance incomplete, 2026-10-09.** Branch `feature/cr-103-cr-104-safety-review-decision`. Manual mutations require developer-owned disposable data, never seeded/shared fixtures.

**Deployment and live verification (9 Oct 2026):** the migration was not applied. `supabase db push --dry-run` is blocked because remote versions `20261008100000` and `20261009100000` are missing locally. Do not push or repair migration history in this work; integrate the migration owners' files and reconcile the inventory first. SQL parse/review was clean, but the safety-decision SQL assertions, live RLS, transactional success paths and post-application advisors remain unverified. No live Safety Officer account is available.

The [recorded API/database run](runs/2026-10-09-1433-api-db-ab6a851.md) has **67 passed, 3 failed, 1 blocked**. TC-SDEC-001/002 passed. TC-SAFE-002/003 and TC-BOOK-001 failed because eligible Planning event reads depend on the missing decision table; the safety-decision SQL preflight correctly recorded Blocked without executing its script.

**Offline evidence:** `/tmp/safety-backend-final-suite.txt` records **978 passed, 94.48% coverage**; the changed backend executable lines are reported as 100% covered. The fresh full frontend run `npm run test:coverage -- --maxWorkers=2` (`/tmp/safety-recovery-coverage-2workers.log`) records **673 passed, 94.58% coverage**; all **292/292 changed executable lines** are covered. The latest `npm run build` passed (`/tmp/safety-recovery-build.log`). Default parallelism had intermittent existing view-test timeouts in OrganiserDashboard and CoordinatorEventView; the complete two-worker run passed without unrelated code changes. Line coverage is complete for changed code, but branch coverage is not 100%. These results do not establish live database behaviour.

**Recorded browser evidence:** the corrected-CORS run ([run log](runs/2026-10-09-1443-e2e-ab6a851.md)) finished with **52 passed, 3 failed**. TC-SDEC-004 passed for all five seeded roles. TC-BOOK-008, TC-EQR-005/006 and TC-SAFE-004 failed on event pages whose reads returned 503 because the decision table is not deployed. The initial interrupted run is retained as evidence of the spare-port CORS setup error; the existing runtime CORS configuration was corrected before this complete run.

Officer-only 404/409/422 and queue-empty checks require a live account. Lead and inactive-held-officer denials need additional accounts. CR-100/24 dependent fields remain null. CR-104 AC6/AC10 callers are unwired.

| ID | Title | Type | Preconditions | Test Steps | Test Input | Expected Result | Priority | Created | Last run |
|---|---|---|---|---|---|---|---|---|---|
| TC-SDEC-001 | Officer-only endpoint denial matrix | Integration | Existing five seeded roles; branch backend | GET queue/review and POST all three decisions using missing UUID | Valid decision bodies | 403 for all five active roles; missing UUID prevents shared event writes | 🔴 | 2026-10-09 | Pass — [2026-10-09 14:33 API run](runs/2026-10-09-1433-api-db-ab6a851.md) |
| TC-SDEC-002 | Decision comments denied to external/unrelated staff | Integration | Existing organiser, venue staff, tech support, attendee | GET safety-decisions with missing UUID | Existing sessions | 403 for each role; coordinator is intentionally excluded from this role-only denial | 🔴 | 2026-10-09 | Pass — [2026-10-09 14:33 API run](runs/2026-10-09-1433-api-db-ab6a851.md) |
| TC-SDEC-003 | Assigned coordinator and active-role boundary | Manual | Safety Officer account, unassigned coordinator event and multi-role staff account required | Read decisions as assigned/unassigned coordinator; switch officer account to another held role and request all officer endpoints | Developer-owned disposable event | Assigned coordinator allowed; unassigned denied; inactive officer role grants no access; Lead denied | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-004 | Non-officer browser route denials | E2E | Five seeded roles | Open /dashboard/safety and /safety/events/<missing UUID> | Existing sessions | Redirect to own dashboard | 🟢 | 2026-10-09 | 2026-10-09 — Pass |
| TC-SDEC-005 | Queue order and resubmission | Manual | Safety Officer account; developer-owned review events | Open queue; compare waiting times; resubmit corrected event through 82 | Different review times plus tie | Oldest latest entry first; ties by ID; resubmitted event goes to new queue position | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-006 | Empty queue and loading/error state | Manual | Safety Officer account; naturally empty queue or isolated environment | Open /dashboard/safety; inspect loading and error handling without changing shared records | Empty review queue | No events are waiting for a safety check.; no stale rows after error | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-007 | Review context and missing dependent data | Manual | Safety Officer account; developer-owned review event | Open /safety/events/<id>; inspect attendance, times, registration, venue details and equipment | Venue capacity/layout/accessibility; event accessibility needs | Attendance-to-capacity ratio and all available context shown; emergency access/restrictions/exit confirmation null and Not recorded, not falsely ready | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-008 | Crowd-movement comment and phone layout | Manual | Safety Officer account; review page | At desktop and 375px inspect comment hint, venue sections, checkboxes and buttons | Long event/venue names | Crowd-movement hint reads clearly; no horizontal scroll or flashing/jumping; labels usable | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-009 | Approve and notification privacy | Manual | Safety Officer; applied migration; disposable ready review event | Approve; inspect transition, decision row and intended notification recipients | Optional unique officer comment | Confirmed; one private decision/history row; organiser/coordinator/venue staff/tech support notified once, actor excluded; comment absent from history reason/messages | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-010 | Request changes only to selected ready arrangements | Manual | Safety Officer; applied migration; disposable event with approved bookings and reserved/pending equipment | Tick subset; enter comment; request changes | Selected approved booking, reserved equipment and pending equipment | Planning; selected approved booking/reserved equipment re_review; pending equipment untouched; unticked unchanged; coordinator alone notified | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-011 | Reject arrangement and consult assumption | Manual | Safety Officer; applied migration; disposable review event | Tick arrangements; enter reason; inspect reject modal and confirm | Selected booking/equipment IDs | Planning, not Rejected; selected bookings released, rejected venue IDs stored, equipment rejected; coordinator notified; replacement wording clear; same-venue rebooking not blocked | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-012 | Corrected event returns for another review | Manual | Officer/coordinator accounts; applied migration; disposable returned event | Correct arrangements, send using SCRUM-82, open queue again | Ready arrangements | New safety-review entry and queue position; prior private decisions retained | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-013 | No coordinator confirmation bypass | Manual | Coordinator account; disposable event | Use coordinator API actions on ready event | Coordinator active role | Coordinator cannot transition directly to confirmed; approval requires officer | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-014 | Missing event reads/decisions | Manual | Safety Officer account required | GET review and POST each decision for missing UUID | 00000000-0000-4000-8000-000000000000 | 404 without mutation | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-015 | Wrong status and concurrent decision | Manual | Safety Officer; applied migration; disposable non-review event | Request decision outside review; then try competing decisions on disposable review event | Same source/version | 409 without change outside review; only one concurrent decision succeeds and writes one transition/decision | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-016 | Blank/oversized text and invalid affected IDs | Manual | Safety Officer account required | POST changes/reject with blank/whitespace/1001-char text or foreign/unknown IDs | Missing UUID for text validation; disposable event for foreign IDs | 422 and no transition/decision; duplicate valid IDs deduplicated | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-017 | Organiser privacy and coordinator banner | Manual | Applied migration; disposable returned event with unique private comment | Open coordinator planning view, organiser detail/history and inspect organiser-safe responses | Unique comment marker | Coordinator sees decision/comment/affected arrangements; organiser sees fixed reason only, never comment in event/history/notifications | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-018 | No timeout or escalation | Manual | Safety Officer account; review event | Inspect queue after waiting; inspect configured decision flow | No officer action | Event remains in review until officer responds or readiness caller withdraws; no timeout/escalation | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-019 | Approved change returns to planning — unwired | Manual | Story 37 caller required; not delivered here | After approval change attendance/venue/equipment through story 37 | Disposable confirmed event | Planning via approved_details_changed; coordinator notified; pending until caller lands | 🔴 | 2026-10-09 | Not run |
| TC-SDEC-020 | Readiness loss withdraws from queue — unwired | Manual | CR-94/95, 85, 24 callers required; not delivered here | Flag/cancel booking or clear technical readiness via owning story | Disposable review event | Planning, queue entry gone, coordinator/officers notified; pending until each caller lands | 🔴 | 2026-10-09 | Not run |

### Traceability — CR-103 / CR-104

| PBI / acceptance criterion | Cases | Boundary |
|---|---|---|
| CR-103 AC1 | TC-SDEC-005, TC-SDEC-006, TC-SDEC-012 | Officer account pending |
| CR-103 AC2 | TC-SDEC-007, TC-SDEC-014 | CR-100 emergency/restrictions unavailable |
| CR-103 AC3 | TC-SDEC-007 | Story 24 exit confirmation unavailable |
| CR-103 AC4 | TC-SDEC-001, TC-SDEC-003, TC-SDEC-004 | Seeded-role checks written; extra-role checks manual |
| CR-103 AC5 | TC-SDEC-003, TC-SDEC-004 | Role groundwork precedes this delivery |
| CR-103 AC6 | TC-SDEC-007, TC-SDEC-008 | Crowd concerns in comment; dependent fields unavailable |
| CR-104 AC1 | TC-SDEC-009, TC-SDEC-014, TC-SDEC-015 | Migration/account pending |
| CR-104 AC2 | TC-SDEC-010, TC-SDEC-014, TC-SDEC-015, TC-SDEC-016 | Pending equipment unchanged |
| CR-104 AC3 | TC-SDEC-011, TC-SDEC-014, TC-SDEC-015, TC-SDEC-016 | Replacement interpretation awaits consult |
| CR-104 AC4 | TC-SDEC-005, TC-SDEC-012 | Reuse SCRUM-82 submission |
| CR-104 AC5 | TC-SDEC-009, TC-SDEC-013 | No direct coordinator confirmation |
| CR-104 AC6 | TC-SDEC-019 | No story 37 caller wired; not complete |
| CR-104 AC7 | TC-SDEC-003, TC-SDEC-009, TC-SDEC-010, TC-SDEC-011, TC-SDEC-015, TC-SDEC-017 | Private decision history, not public comments |
| CR-104 AC8 | TC-SDEC-001, TC-SDEC-002, TC-SDEC-003, TC-SDEC-004 | Assigned coordinator may read history only |
| CR-104 AC9 | TC-SDEC-018 | No timeout/escalation |
| CR-104 AC10 | TC-SDEC-020 | CR-94/95, 85, 24 callers unwired; not complete |

Automated live checks: `backend/scripts/verify_live.py` registers TC-SDEC-001/002 and the SQL presence preflight; `frontend/e2e/safety-decision.e2e.js` registers TC-SDEC-004 per seeded role. TC-SDEC-001/002 and TC-SDEC-004 have recorded passes above; officer success paths await migration and account setup.

### Frontend branch-coverage gaps

The changed executable-line bar is satisfied (292/292); the following branches remain uncovered and are not claimed verified:

- `SafetyDashboard.vue:31`: missing attendance.
- `SafetyDecisionDetails.vue:15–16`: unknown decision and system actor.
- `SafetyReviewView.vue:28`: guard; `:60`: back button; `:68, :71–72, :83–85, :101`: missing/empty values; `:99`: registration disabled.

### Developer manual pass

After migration and officer-account setup, record verdicts using [runs/README.md](runs/README.md):

- **Queue `/dashboard/safety`:** TC-SDEC-005/006 — check ordering, waiting times, resubmission position and empty/loading/error wording.
- **Review `/safety/events/<id>`:** TC-SDEC-007/008/011 — check context, “Not recorded” fields, crowd-movement wording, rejection selection and 375px layout without jumps or flashes. On disposable events, run TC-SDEC-009–016/018 for decision outcomes, validation, history and notifications; TC-SDEC-003 also needs extra-role accounts.
- **Coordinator `/coordinator/events/<id>` and organiser event detail:** TC-SDEC-017 — compare the full internal banner with the plain external reason and check the rejected-arrangement label.

TC-SDEC-019/020 remain deferred until the owning stories wire their callers. Do not record manual passes without the developer's verdict.
