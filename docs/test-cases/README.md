# ConnectSphere — Manual Test Cases

Manual test cases for every implemented story, one file per area of the system. Each case names the exact code path it exercises, so it can be turned into an automated test later, and each story's section ends with a traceability table mapping its acceptance criteria to cases and automated tests.

See [SCENARIO.md](../SCENARIO.md) for requirement context and [SETUP.md](../SETUP.md) for environment setup.

## Where to find a case

| File | Stories | ID prefixes |
|---|---|---|
| [auth.md](auth.md) | SCRUM-48 login, session, logout; SCRUM-80 organiser sign-up | TC-AUTH |
| [roles-and-access.md](roles-and-access.md) | SCRUM-48 routing and data-layer security; SCRUM-74/75/76/78 role switching | TC-RBAC, TC-ROLE, TC-DATA |
| [venues.md](venues.md) | SCRUM-39 venue search, SCRUM-67 venue profile | TC-VENUE |
| [events.md](events.md) | SCRUM-8 request creation, SCRUM-34/52 approve and reject, SCRUM-33 return for amendment | TC-EVENT, TC-REV, TC-AMD |
| [dashboards.md](dashboards.md) | SCRUM-72 coordinator, SCRUM-70 venue staff, SCRUM-71 organiser, SCRUM-73 technical support | TC-DASH, TC-VSD, TC-ORG, TC-TSD |

## Environment

- A Supabase project with every migration in `supabase/migrations/` applied and `supabase/seed.sql` run. The live project (`vuiryrzzyfecjqftwicj`) has both.
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

**Dashboard route map** (`frontend/src/stores/auth.js::ROLE_DASHBOARD_ROUTES`): `event_organiser → /dashboard/organiser`, `event_coordinator → /dashboard/coordinator`, `venue_staff → /dashboard/venue-staff`, `tech_support → /dashboard/tech-support`, `attendee → /dashboard/attendee`.

**Priority key:** 🔴 High (blocks core AC) · 🟠 Medium (important edge case) · 🟢 Low (nice-to-have / defensive).

## Running the cases and recording results

Many cases are also automated against the real system: API and database cases by `backend/scripts/verify_live.py`, and browser cases by the Playwright specs in `frontend/e2e/`. Each automated check starts with the ID of the case it runs, so `grep -rn "<case ID>" backend/scripts frontend/e2e` shows whether a case is automated. The rest, mostly ones that need a person to judge layout, wording or feel, are run by hand.

Every run, automated or manual, is recorded in [runs/](runs/README.md). That folder explains when to record a run, the commands, and the template for a manual run.

## Adding cases for a new story

1. Put the story in the file for its area. Start a new file only for a new area, and add it to the table above.
2. Give it a `## <Story name> (SCRUM-<n>)` section: preconditions, then the case table, then `### Traceability — SCRUM-<n>`, then a short note naming the automated tests that cover each case.
3. Continue the area's ID prefix and numbering. Never renumber or reuse an existing ID; other docs and tests cite them.
4. Where a case's outcome can be checked by a request or a browser assertion without changing shared data, add an automated check for it, named with its ID (root `AGENTS.md`, "Live checks and the manual browser pass").

Case table columns:

```markdown
| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
```
