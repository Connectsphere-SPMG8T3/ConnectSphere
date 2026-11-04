# ConnectSphere — Manual Test Cases

Manual test cases for every implemented story, one file per area of the system. Each case names the exact code path it exercises, so it can be turned into an automated test later, and each story's section ends with a traceability table mapping its acceptance criteria to cases and automated tests.

See [REQUIREMENTS.md](../REQUIREMENTS.md) for the rules each case checks, each story's PR description (or, before 1 Nov 2026, [BUILD_LOG.md](../BUILD_LOG.md)) for how it was built, and [SETUP.md](../SETUP.md) for environment setup.

## Where to find a case

| File | Stories | ID prefixes |
|---|---|---|
| [auth.md](auth.md) | SCRUM-48 login, session, logout; SCRUM-50 profile details; SCRUM-80 Organiser and SCRUM-83 Attendee sign-up | TC-AUTH |
| [roles-and-access.md](roles-and-access.md) | SCRUM-48 routing and data-layer security; SCRUM-74/75/76/78 role switching | TC-RBAC, TC-ROLE, TC-DATA |
| [venues.md](venues.md) | SCRUM-39 venue search, SCRUM-67 venue profile, SCRUM-19 venue booking request, CR-99 hold expiry, SCRUM-38 booking rejection, CR-98 space-scoped venue selection, CR-94 venue-edit re-check and Unsuitable flag, CR-97 several venues per event, SCRUM-21 booking conflict detection, CR-95 affected bookings and replacements, CR-100 venue defaults and safety details, SCRUM-57 venue availability calendar, SCRUM-85 booking cancellation | TC-VENUE, TC-BOOK, TC-HOLD, TC-SPACE, TC-VCAL, TC-BCAN |
| [events.md](events.md) | SCRUM-8 request creation, SCRUM-34/52 approve and reject, SCRUM-33 return for amendment, SCRUM-61 comments, CR-98 event-space requirements, Story 43 public event discovery and registration, SCRUM-35 manager registrations, SCRUM-55 withdrawal, SCRUM-56 registered events, SCRUM-86 waitlist, 84 cancellation requests, 115 cancel an event, 32 change requests, 37 deciding change requests and re-review, 62 change history | TC-EVENT, TC-REV, TC-AMD, TC-CMT, TC-SAFE, TC-SPACE, TC-REG, TC-CANCEL, TC-CHANGE, TC-HIST |
| [dashboards.md](dashboards.md) | SCRUM-72 coordinator, SCRUM-70 venue staff, SCRUM-71 organiser, SCRUM-73 technical support, CR-101 Event Coordinator Lead, SCRUM-12 Coordinator assignment, CR-106 reassignment request, 77 navigation sidebar and top bar | TC-DASH, TC-VSD, TC-ORG, TC-TSD, TC-LEAD, TC-ASSIGN, TC-REASSIGN, TC-NAV |
| [safety-decisions.md](safety-decisions.md) | CR-103 queue/review (AC1–4, AC6), CR-104 safety decisions | TC-SDEC |
| [equipment.md](equipment.md) | SCRUM-45 equipment request, SCRUM-24 reservation, 23-R availability, CR-110 technical preparation | TC-EQR, TC-TPREP |
| [notifications.md](notifications.md) | SCRUM-113 in-app notifications, SCRUM-53 attendee notices, SCRUM-90 reminders | TC-NOTIF |

## Environment

- A Supabase project with migrations applied and `supabase/seed.sql` run. Check the linked migration inventory before database work. On 2026-10-13, the linked ledger includes remote-only versions through `20261012140000`; CR-98's corrective grant migration `20261013100000` is pending merge/deployment.
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`.
- Data-layer cases run as a real role inside a rolled-back transaction (`set_config('request.jwt.claims', ...)` plus `set local role authenticated`), not with the service key. Several are automated by the scripts in `supabase/verification/`; each file says which.

**Seeded accounts** (all share the password `Cs1234`, per `supabase/seed.sql`):

| Role | Email | Notes |
|------|-------|-------|
| Event Organiser | `organiser@connectsphere.dev` | Single role |
| Event Coordinator | `coordinator@connectsphere.dev` | Dual-role account (double hat): `event_coordinator` (default) + `venue_staff` in `user_roles` |
| Venue Staff | `venue.staff@connectsphere.dev` | Single role |
| Technical Support | `tech.support@connectsphere.dev` | Single role |
| Attendee | `attendee@connectsphere.dev` | Single role |
| Event Coordinator Lead | `coordinator.lead@connectsphere.dev` | Single role (Grace Chua) |
| Event Coordinator Lead (second) | `coordinator.lead2@connectsphere.dev` | Single role (Daniel Foo); the second Lead for TC-LEAD-012 and TC-LEAD-015 |

**Safety review prerequisites (CR-103/104):** seeded Safety Officer and Event Coordinator Lead accounts are available; officer decision walkthrough cases remain subject to the manual checklist. Grant any additional staff roles using `SETUP.md`.

**Historical deployment check (9 Oct 2026):** at that point, local migration files were missing from the linked inventory and safety-decision verification was blocked. This state was superseded when the CR-98 and CR-103/104 migration files were integrated and applied.

**Current migration status (13 Oct 2026):** the linked ledger includes remote-only versions through `20261012140000`. The CR-98 D32 privilege-revocation migration `20261013100000_revoke_event_space_trigger_execution.sql` is pending merge and deployment. The live database currently still grants direct execution on the two trigger functions; see [the historical run, recorded as D26](runs/2026-10-12-1433-api-db-d234eb1.md).

The [recorded API/database run](runs/2026-10-09-1433-api-db-ab6a851.md) has **67 passed, 3 failed, 1 blocked**. TC-SDEC-001/002 passed. TC-SAFE-002/003 and TC-BOOK-001 failed because eligible Planning event reads depend on the missing decision table; the safety-decision SQL preflight correctly recorded Blocked without executing its script.

**Offline evidence:** `/tmp/safety-backend-final-suite.txt` records **978 passed, 94.48% coverage**; the changed backend executable lines are reported as 100% covered. The fresh full frontend run `npm run test:coverage -- --maxWorkers=2` (`/tmp/safety-recovery-coverage-2workers.log`) records **673 passed, 94.58% coverage**; all **292/292 changed executable lines** are covered. The latest `npm run build` passed (`/tmp/safety-recovery-build.log`). Default parallelism had intermittent existing view-test timeouts in OrganiserDashboard and CoordinatorEventView; the complete two-worker run passed without unrelated code changes. Line coverage is complete for changed code, but branch coverage is not 100%. These results do not establish live database behaviour.

**Recorded browser evidence:** the corrected-CORS run ([run log](runs/2026-10-09-1443-e2e-ab6a851.md)) finished with **52 passed, 3 failed**. TC-SDEC-004 passed for all five seeded roles. TC-BOOK-008, TC-EQR-005/006 and TC-SAFE-004 failed on event pages whose reads returned 503 because the decision table is not deployed. The initial interrupted run is retained as evidence of the spare-port CORS setup error; the existing runtime CORS configuration was corrected before this complete run.

**Dashboard route map** (`frontend/src/stores/auth.js::ROLE_DASHBOARD_ROUTES`): `event_organiser → /dashboard/organiser`, `event_coordinator → /dashboard/coordinator`, `venue_staff → /dashboard/venue-staff`, `tech_support → /dashboard/tech-support`, `attendee → /dashboard/attendee`.

**Priority key:** 🔴 High (blocks core AC) · 🟠 Medium (important edge case) · 🟢 Low (nice-to-have / defensive).

## Running the cases and recording results

Many cases are also automated against the real system: API and database cases by `backend/scripts/verify_live.py`, and browser cases by the Playwright specs in `frontend/e2e/`. Each automated check starts with the ID of the case it runs, so `grep -rn "<case ID>" backend/scripts frontend/e2e` shows whether a case is automated. The rest, mostly ones that need a person to judge layout, wording or feel, are run by hand.

Every run, automated or manual, is recorded in [runs/](runs/README.md). That folder explains when to record a run, the commands, and the template for a manual run.

## Adding cases for a new story

1. Put the story in the file for its area. Start a new file only for a new area, and add it to the table above.
2. Give it a `## <Story name> (<PBI ID>)` section, where the PBI ID is `SCRUM-<n>`, `CR-<n>` or the plain number, as the Product backlog shows it. The section has the preconditions, then the case table, then `### Traceability — <PBI ID>`, then a short note naming the automated tests that cover each case.
3. Continue the area's ID prefix and numbering. Never renumber or reuse an existing ID; other docs and tests cite them.
4. Where a case's outcome can be checked by a request or a browser assertion without changing shared data, add an automated check for it, named with its ID (root `AGENTS.md`, "Live checks and the manual browser pass").

Case table columns, for cases added from 2026-10-06:

```markdown
| ID | Title | Type | Preconditions | Test Steps | Test Input | Expected Result | Priority | Created | Last run |
|----|-------|------|----------------|------------|-------------|------------------|----------|---------|----------|
| TC-EVENT-040 | … | E2E | … | … | … | … | 🔴 | 2026-10-08 | 2026-10-09 · Pass · [run](runs/2026-10-09-1430-e2e-abc1234.md) |
```

- **Type** is how the case is run: **Unit**, **Integration** (an API or database check, including `verify_live.py`), **E2E** (a Playwright spec), or **Manual**. Use the type of the strongest check that runs it.
- **Created** is the date the case was written.
- **Last run** is the date, result and run file of the most recent recorded run (Pass, Fail or Blocked, as in [runs/](runs/README.md)). Update it when you commit a new run log that includes the case.

Cases written before 2026-10-06 use the older seven columns and are not backfilled here. The team copies every case into the Test cases sheet before submission. Playbook §9.4 asks the sheet to show, for each case, its PBI ID, the acceptance criterion, the test type, the expected result and the latest status. The traceability table supplies the PBI ID and acceptance criterion, and the run files supply who ran each run and when.
