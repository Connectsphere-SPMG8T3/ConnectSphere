# ConnectSphere — Roadmap

**The release plan across the four sprints, and the detailed plan for the current one.**

Drafted in the 13 Sep 2026 design review ([`archive/2026-09-13-design-review.md`](https://github.com/chasingsunsets/ConnectSphere/blob/91fec10aab05070169286fbbed5268fef9cf6930/docs/archive/2026-09-13-design-review.md)), where it was Part C of `docs/PROJECT_REVIEW.md`; section labels C1–C4 are kept so older references still resolve. Behaviour specs cited as §x.y are in [`REQUIREMENTS.md`](REQUIREMENTS.md). The [Product backlog sheet](https://docs.google.com/spreadsheets/d/18y09jIMc9t1FtvTEM_6u74uWNAg8hrW0eF_LehVgWVY/edit) is the source of truth for current priority (Jira was, until Sprint 2); this file records the plan and its reasoning.

### C1. Constraints

- **4 sprints total**, each 2 weeks. Sprint 1 runs 8–22 Sep. **[Assumed dates, check against the academic calendar and recess week]** Sprint 2 runs 22 Sep–6 Oct, Sprint 3 runs 6–20 Oct, and Sprint 4 runs 20 Oct to the first week of November. The final sprint must end by Friday of Week 12.
- **Sprint 4 is the "showcase sprint".** It should demonstrate the process at its best, so plan it **lighter** than Sprint 3 and leave room for integration, end-to-end hardening, and recorded ceremonies. Don't back-load features into it.
- **The Week 7 process consultation** falls around the end of Sprint 2. Bring the Sprint 1 retrospective actions and the Sprint 2 burndown.
- **Velocity is unknown until Sprint 1 closes.** Sprint 1 committed 27 SP across 6 developers. The Sprint 2 list below is **ordered with a cut line**; commit up to the team's *actual* Sprint 1 completed points, plus at most about 20%.
- **Three parallel streams** of 2 developers each keep hand-offs low:
  - **Stream A:** event workflow
  - **Stream B:** venues and bookings
  - **Stream C:** equipment, registration, notifications, and cross-cutting work

### C2. Roadmap across the 4 sprints

| Sprint | Goal | Stream A (Events) | Stream B (Venues) | Stream C (Equipment / Registration / Cross-cutting) |
|---|---|---|---|---|
| **1** (now → 22 Sep) | *Users log in securely and land on a role dashboard; the shared data foundation is in place* | 48 ✔, 50 (+D7), 71 shell, 8 (create form) | 39a view catalogue, 70 shell | 23 (pure availability function), 72/73 shells. **Plus:** D1–D3 fixes, CI pipeline, core schema migration |
| **2** (22 Sep → 6 Oct) | *An organiser can sign up, draft and submit a request that is auto-assigned to a coordinator for review; coordinators can find suitable venues; everyone is notified* | Organiser/attendee sign-up, 9, 8 (submit), lifecycle state machine, 12 auto-assignment, 49 review details, change history (data + tab) | 39b search and filter, 18 suitability, add venue, 63 update venue | Notification centre, equipment catalogue and outages, 45 equipment request, 40 request queue |
| **3** (6 Oct → 20 Oct) | *An approved event gets an exclusive venue hold approved and its equipment fully reserved, and can be confirmed* | 33 return and resubmit, 34 approve, 52 reject, hand over, technical readiness and confirm, 62 planning details | 19 booking request as tentative hold (DB-1), 21 conflict detection, 36/38 approve/reject, 47 booking list, 57 calendar, 51 block | 23 wire-up, 24 reserve all-or-nothing (DB-4), 41 update status, 44 modify; registration settings, 43 register, 56 my registrations |
| **4** (20 Oct → Wk 12) *showcase* | *Changes and cancellations flow through re-review and release consistently, with everyone notified* | 32 change and cancellation requests, 37 process with impact preview, significant-edit rules, complete event | Venue re-review after change, 54 shorten block, 64 deactivate, "venue changed/blocked" flags, 70/72 dashboards finished | Equipment re-review, outage flags, 55 withdraw, 35/59 registration views, browse events, 53 change notifications; end-to-end workflow test, coverage gaps, final evidence |

Everything in REQUIREMENTS §8 (P3) stays in the backlog at Low priority and is pulled in only if a sprint finishes early.

### C3. Immediately — the rest of Sprint 1 (13–22 Sep)

SCRUM-48 is done, so **Jie Ching has spare capacity** for the rest of the sprint. The highest-leverage use of that time is unblocking the other five developers:

1. **Move SCRUM-48 to Done.** Add a comment linking PR #1 and noting the email-vs-username decision.
2. **Fix D1 to D3 and D6** in one PR: a per-request auth client, correct logout, a trigger that accepts only `event_organiser`/`attendee` from sign-up (QA-3, QA-4), the `current_user_role()` helper that removes the RLS recursion, and `search_path` fixes. Add regression tests. Log it as a Sprint 1 bug with sub-tasks.
3. **Update the 11 contradicted stories in B2a** and comment on each with its QA citation. This takes about 30 minutes and is high-value evidence.
4. ~~**Add a CI pipeline** (GitHub Actions: ruff, pytest with coverage, frontend build).~~ **Done** on `chore/ci-pipeline` — `.github/workflows/ci.yml` runs pytest, Vitest and the frontend build on every PR. Ruff and coverage reporting were deferred; see the design review's A3 item 9.
5. **Draft the core schema migration** (`client_organisations`, `events`, `event_status_history`, `amendment_requests`, `change_requests`, `venues` with layouts and facilities, `venue_bookings` with the exclusion constraint over held/approved/re_review, `venue_blocks`, `equipment_types`, `equipment_outages`, `equipment_requests`, `equipment_reservations`, `registrations`, `notifications`, `change_history`) per REQUIREMENTS §4. **Review it with the whole team at stand-up before merging.**
6. Add the domain event dispatcher skeleton (`core/events.py`) and a per-module `repository.py` pattern to the `auth` module, so others copy the pattern rather than invent one.
7. Bring REQUIREMENTS §9 (9 remaining open questions, including the approved-vs-confirmed contradiction) to the next customer Q&A.

### C4. Sprint 2 plan (22 Sep – 6 Oct)

**Proposed sprint goal:** *"An Event Organiser can sign up, draft and submit an event request that the system automatically assigns to an Event Coordinator for review; coordinators can search for suitable venues; and all parties receive in-app notifications of these steps."*

**Candidate backlog in priority order.** Suggested story points seed planning poker only; re-estimate as a team.

| Order | Key | Story | Stream | Suggested SP | Running total | Acceptance criteria source | Depends on |
|---|---|---|---|---|---|---|---|
| 1 | NEW | Event lifecycle state machine + status history (enabler) | A | 3 | 3 | §5 | Core schema (S1) |
| 2 | NEW | Sign up as Event Organiser or Attendee | A | 2 | 5 | §2.1, §6.1 | D2 fix (S1) |
| 3 | SCRUM-9 (+65 merged) | Save and edit draft event requests | A | 3 | 8 | §6.3 | 1 |
| 4 | SCRUM-8 | Submit event request with validation | A | 3 | 11 | §6.2 | 3 |
| 5 | SCRUM-12 (+68 merged) | Auto-assign least-loaded coordinator on submission | A | 3 | 14 | §6.5 | 4 |
| 6 | NEW | In-app notification centre (bell, list, mark read) + dispatcher wiring | C | 5 | 19 | §6.20 | Dispatcher (S1) |
| 7 | SCRUM-49 | Review submitted event request details | A | 2 | 21 | §6.4 | 5 |
| 8 | SCRUM-18 | Venue suitability checking (rule engine) | B | 3 | 24 | §6.11 | 39a (S1) |
| 9 | NEW (39b) | Search and filter venues for an event | B | 5 | **29** | §6.10 | 8 |
| ─ | | **Likely cut line (≈ Sprint 1 velocity + ~10%)** | | | | | |
| 10 | NEW | Change history: record + History tab | C | 3 | 32 | §6.7, QA-70 | 1 |
| 11 | NEW | Add a new venue (venue staff) | B | 3 | 35 | §6.8 | – |
| 12 | NEW | Equipment catalogue view + record outages | C | 2 | 37 | §6.16 | Schema |
| 13 | SCRUM-45 | Record and submit an equipment request | C | 3 | 40 | §6.15 | 12, and a planning-status event (Sprint 3) or seeded data |
| 14 | SCRUM-63 | Update venue details (with affected-booking warning) | B | 3 | 43 | §6.8 | 11 |
| 15 | SCRUM-40 | Tech support equipment request queue | C | 2 | 45 | §6.15 | 13 |

**Why this order:**
- Items 1–7 form the thin vertical slice (sign up → draft → submit → auto-assign → notify → review) that Sprint 3's return, approval, and booking work needs.
- Items 8–9 run in parallel on Stream B with no dependency on Stream A.
- Item 10 sits just below the cut line only because its *data capture* can ride along with item 1's status history. Pull it above the line if velocity allows: the customer explicitly wants history in the UI (QA-70).
- Items 11–15 are safe to move to Sprint 3 without breaking the goal.

**Example task breakdown** (repeat the pattern for every story during planning). For SCRUM-8, "Submit event request":
- Migration check: event fields and constraints exist (DB).
- `events/schemas.py` submit schema with the field validators from §6.2.
- `events/service.submit()` → `lifecycle.transition(draft→submitted)` → publish `EventSubmitted`.
- `events/policies.ensure_owner()`.
- Router `POST /events/{id}/submit` returning `409` on the wrong status.
- Unit tests for validation boundaries (attendance 0/1, `ends_at` = `starts_at`, past start).
- Integration test for submit, including a second submit returning `409`.
- Vue: request form submit, a field error summary, and a status badge.
- Manual test cases TC-EVT-0xx in `docs/test-cases/events.md`, linked to the Jira key.
- A PR description recording what was built and how it was verified (a `BUILD_LOG.md` entry until the log was frozen on 1 Nov 2026).

**Definition of Done** — from Sprint 3 the team's DoD is the one in the Scrum playbook §6, mirrored in [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md), with the step-by-step process in [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md). It replaced the checklist this review proposed. CI now exists, and the 100% coverage target is set in [`CI.md`](CI.md) §4 item 2.

**Sprint 2 risks:**
- The notification centre (item 6) touches every module. Build the dispatcher contract on day 1 so other stories can publish events before the UI is ready.
- Venue search performance with range overlap: add GiST indexes in the schema migration.
- Customer answers to REQUIREMENTS §9 (Q1 statuses, Q2 reassignment, Q6 organiser edits) may change items 1, 5, and 7. Keep acceptance criteria editable, and record every change as a Jira comment citing the Q&A row.

**Scrum evidence to capture in Sprint 2** (graded deliverable 4):
- Planning: sprint goal, committed backlog screenshot, planning-poker record.
- Daily: board screenshot at least 2–3 times per week; burndown at the end.
- Review: a demo of the thin slice (sign up → draft → submit → auto-assign → notify → review), plus customer feedback captured as backlog changes.
- Retrospective: a board with actions, and in Sprint 3's retrospective an explicit check of whether Sprint 2's actions were done ("inspect and adapt" evidence).
- Week 7 consultation: bring the Sprint 1 and Sprint 2 burndowns and retrospective actions.
