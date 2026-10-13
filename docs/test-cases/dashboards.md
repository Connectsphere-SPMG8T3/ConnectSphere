# Role dashboards

Shared environment, seeded accounts and the priority key are in [README.md](README.md). One section per role dashboard.

**Out of scope:** the equipment reservation workflow (SCRUM-24). Organisers cannot raise equipment requests yet, so the Technical Support dashboard's "Active requests" panel has no data source and is tested as an empty state only.

## Event Coordinator dashboard (SCRUM-72)

**Preconditions for every case:** logged in as `coordinator@connectsphere.dev` / `Cs1234`, on `/dashboard/coordinator`.

**A note on how these are run.** `GET /events/dashboard/coordinator` is built (`feature/scrum-72-coordinator-dashboard-api`), so TC-DASH-001–005 and TC-DASH-013–020 run against real seeded data. TC-DASH-006–012 need payloads the seed doesn't produce: every action kind at once, unknown kinds, drafts in the response. They are still run by **stubbing the endpoint response** at the network layer (Playwright `page.route`, or DevTools' local overrides). Several kinds they use (`cancellation_request`, `venue_blocked`) have no data source yet, so the server never sends them.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-DASH-001 | Dashboard loads from the real endpoint | Backend on this branch or later | Open `/dashboard/coordinator` and wait for the network to settle | — | `GET /events/dashboard/coordinator` returns 200. No "Awaiting data" notice and no error banner. The seeded fixture events appear under their status. (Against a backend older than the endpoint, it answers 404 and the page shows "Awaiting data — this server doesn't provide the coordinator dashboard yet" with no error banner; `store.spec.js` covers that path.) | 🔴 |
| TC-DASH-002 | No fabricated metrics are displayed (regression, DEFECTS D8) | As TC-DASH-001 | Read every number on the page and compare it with the events assigned to this coordinator | — | Every counter matches the coordinator's real assigned events (TC-DASH-013). The strings "Requests Awaiting Review", "Venues to Coordinate" and "Events in Progress" do **not** appear — they were the hardcoded placeholders this story removed. | 🔴 |
| TC-DASH-003 | Counts are withheld until the first load settles | Throttle the network (DevTools → Slow 3G) before loading | Open `/dashboard/coordinator` and watch the page while the request is in flight | — | While loading, the page shows "Loading events..." under the header and no counters, tiles or empty states at all. Figures appear only once the request settles. A `0` must never be shown before the answer is known. | 🟠 |
| TC-DASH-004 | A server failure is surfaced, not silently rendered as an empty dashboard | Point the backend at a stub that answers 503, or stop the backend | Reload `/dashboard/coordinator` | — | A red error banner shows the failure message. The dashboard does **not** claim the coordinator has nothing to do. (Contrast with TC-DASH-001: only a 404 is treated as "not built yet".) | 🔴 |
| TC-DASH-005 | The dashboard is usable on a phone-width viewport (NFR-U1) | As TC-DASH-001 | Set the viewport to 390 × 844; open Overview, then Events from the sidebar menu | — | Overview: category tiles and status cards stack to one column. Events: the filters stack, each card keeps its Review button beside the text. No horizontal scrolling on either, all text legible. | 🟠 |
| TC-DASH-006 | AC1 — the action list is ordered by what each item blocks | Stubbed payload containing one item of each kind: `awaiting_review`, `arrangement_issue`, `resubmitted`, `cancellation_request` | Read the numbered action list top to bottom | four action items, mixed order in the payload | Order is: arrangement issue → cancellation requested → amended and resubmitted → awaiting first review (REQUIREMENTS §6.21.1). Each row shows its kind badge, the event date in Asia/Singapore, and the organiser's name. | 🔴 |
| TC-DASH-007 | AC1 — the three named categories are counted separately | Stubbed payload with 2 immediate-action items, 1 `awaiting_review`, 1 `resubmitted` | Read the three counter cards | as above | "Immediate action" = 2, "Awaiting approval" = 1, "Clarification responses" = 1. | 🔴 |
| TC-DASH-008 | AC1 — ties are broken by the soonest event date | Stubbed payload with two `awaiting_review` items, differing only in `starts_at` | Read their relative order | two items, same kind | The event starting sooner appears first. | 🟠 |
| TC-DASH-009 | AC1 — an unrecognised action kind is still shown, ranked last | Stubbed payload containing `"kind": "something_new"` alongside a known kind | Read the list | unknown kind | The unknown item appears, last, with the generic "Needs attention" badge. It is never dropped. | 🟠 |
| TC-DASH-010 | AC2 — every active status is shown with its count and events | Stubbed payload with events in `under_review` (×2), `returned`, `planning`, `confirmed` | Read the "Active events by status" section | five events | Four cards appear — Under review (2), Returned for amendment (1), Planning (1), Confirmed (1) — each listing its events with dates. Statuses with no events still appear, showing `0` and "None." | 🔴 |
| TC-DASH-011 | AC2 — drafts never appear in a coordinator's view (DR-R2) | Stubbed payload including an event with `"status": "draft"` and a terminal-status event | Read the whole page | draft + cancelled event | Neither appears in any card, and neither is counted anywhere. | 🔴 |
| TC-DASH-012 | Flags and the schedule overview render | Stubbed payload with one event flagged `venue_blocked`, and one `planning` event starting in 8 days with `readiness.venue = "pending"` | Read the status cards and the readiness section | as above | The flagged event shows a "VENUE BLOCKED" badge (§7 NFR-R1). "Readiness gaps — next 14 days" lists the event with "Outstanding: Venue". There is no "awaiting assignment" alert: unassigned events are the Event Coordinator Lead's queue (REQUIREMENTS §6.5). | 🟠 |
| TC-DASH-013 | Only the caller's own active events come back | Seed applied; fixture events reset (`event_review_fixture_reset.sql`) | Send `GET /events/dashboard/coordinator` as the coordinator | — | 200. Every `active_events` entry has status `under_review`, `returned`, `planning` or `confirmed` (never `draft` or a terminal status). The fixtures `e0000000-…-0201` and `e0000000-…-0202`, both assigned to this coordinator, are listed. Every action item refers to a listed event. | 🔴 |
| TC-DASH-014 | AC1 — every event under review is an action item, and a returned one isn't | As TC-DASH-013 | Read `action_items` against `active_events` | — | Each `under_review` event has exactly one action item, of kind `awaiting_review` (first review) or `resubmitted` (answered amendment). A `returned` event has none, because it is waiting on the organiser. On the page, fixture `…-0201` is listed under **Awaiting approval** with the organiser's name. | 🔴 |
| TC-DASH-015 | A coordinator's dashboard says nothing about unassigned events | As TC-DASH-013 | Send `GET /events/dashboard/coordinator` as the coordinator; then read the Overview | — | The response has only `action_items` and `active_events` (no unassigned count). The page shows no "awaiting assignment" alert or figure. Unassigned events are the Event Coordinator Lead's queue, not a coordinator's (REQUIREMENTS §6.5). | 🟠 |
| TC-DASH-016 | An organiser can't read the coordinator dashboard | Signed in as `organiser@connectsphere.dev` | Send `GET /events/dashboard/coordinator` directly, bypassing the SPA | — | 403. | 🔴 |
| TC-DASH-017 | A coordinator acting as another role can't read it (SCRUM-76) | Signed in as `coordinator@connectsphere.dev`, which also holds `venue_staff` | Switch the active role to Venue Staff, request the endpoint; switch back and request it again | — | 403 while acting as Venue Staff; 200 after switching back. | 🔴 |
| TC-DASH-018 | No token, no dashboard | — | Send `GET /events/dashboard/coordinator` without an `Authorization` header | — | 401. | 🟠 |
| TC-DASH-019 | Every row opens the event's review page | As TC-DASH-001 | Click an event in **Active events by status**; go back and click an action item | — | Each click opens `/coordinator/events/<that event's id>` showing that event. Rows in "Readiness gaps" open the same page. The rows press flat on click like the venue-staff dashboard's. | 🔴 |
| TC-DASH-021 | The sidebar offers Overview and Events, like the organiser's | As TC-DASH-001 | Read the sidebar; click **Events**, then **Overview** | — | The coordinator sees **Overview**, **Events** and **Venues**, and no **Dashboard** link. Each click highlights its entry and switches the view (`?tab=overview` / `?tab=events`). Acting as Venue Staff, the sidebar shows **Dashboard** again. | 🟠 |
| TC-DASH-022 | A category tile or status heading opens the Events view filtered to it | As TC-DASH-001 | Click the **Awaiting approval** tile; go back and click the **Planning** heading in "My events by status" | — | The tile opens Events with "Showing: Awaiting approval" and only events awaiting a first review. The heading opens Events with the Status filter set to Planning. **Clear** removes both filters. | 🟠 |
| TC-DASH-023 | AC2 — the Events view finds any assigned event | As TC-DASH-001, on Events | Type part of a name; pick statuses; change the sort field and direction | — | One card per assigned active event, split into **Needs your action** and **In progress**, each with its status, date (SGT), outstanding arrangements and a **Review** button that opens its review page. Search is case-insensitive; the status filter keeps any selected status; undated events sort last. "No matching events" when nothing matches. | 🔴 |
| TC-DASH-024 | The dashboard looks like it belongs next to the organiser's | Open `/dashboard/organiser` as the organiser in another window | Compare both Overview views, then both Events views | — | Same header card, tile row, status cards (hover lift, underlined headings, pager), filter bar and event cards: same borders, shadows, type and colours. | 🟠 |
| TC-DASH-020 | AC1 — an amended and resubmitted request shows as a clarification response | Fixture `…-0201` in `under_review`. **Changes shared data:** reset the fixtures with `event_review_fixture_reset.sql` afterwards | As the coordinator, return `…-0201` for amendment. As `organiser@connectsphere.dev`, amend and resubmit it. As the coordinator, reload the dashboard | message and note of your choice | The event is listed under **Clarification responses** (count 1) with the "Amended and resubmitted" badge, ranked above any "Awaiting first review" item, and no longer counted under Awaiting approval. | 🔴 |

| TC-DASH-025 | Summary cards align when labels wrap (D21) | Logged in as the dashboard’s role | Open `/dashboard/coordinator`; resize to 1440, 1280, 1100, 768, 640, 375 and 320px; inspect the summary row, especially Clarification responses | — | Equal card heights and aligned figures/details within each row. Summary text remains visible; its row stays inside the viewport. One/two/three-or-four columns follow available space. Existing category actions still work. | 🟠 |

### Traceability — SCRUM-72

| Acceptance criterion / rule | Covered by |
|---|---|
| AC1 "prioritized list of incoming event requests requiring immediate action" | TC-DASH-006, TC-DASH-007, TC-DASH-008 |
| AC1 "requests awaiting initial approval/rejection" | TC-DASH-007, TC-DASH-010, TC-DASH-014 |
| AC1 "items with newly received client clarification responses" (QA-22, QA-77 return/resubmit) | TC-DASH-007, TC-DASH-020 |
| AC2 "Displays status for each active event" | TC-DASH-010, TC-DASH-011, TC-DASH-013 |
| Only the caller's assigned events; access by active role (SCRUM-76) | TC-DASH-013, TC-DASH-016, TC-DASH-017, TC-DASH-018 |
| Rows open the review page (SCRUM-34/52/33) | TC-DASH-019, TC-DASH-023 |
| Layout follows the organiser dashboard (REQUIREMENTS §6.21.1 [Team decision]) | TC-DASH-021, TC-DASH-022, TC-DASH-024 |
| REQUIREMENTS §6.21 "build a widget only when its data exists; until then, show an empty state" | TC-DASH-001, TC-DASH-003 |
| REQUIREMENTS §6.21.1 prioritisation [Team decision] | TC-DASH-006, TC-DASH-008, TC-DASH-009 |
| DR-R2 (drafts invisible to staff) | TC-DASH-011 |
| Unassigned events belong to the Event Coordinator Lead, not coordinators (REQUIREMENTS §6.5, supersedes AS-R5) | TC-DASH-012, TC-DASH-015 |
| §7 NFR-R1 (flags stay visible until resolved) | TC-DASH-012 |
| NFR-U1 (desktop and mobile friendly) | TC-DASH-005 |
| DEFECTS D8 (fabricated metrics) | TC-DASH-002 |
| Reliability (an outage is not rendered as "nothing to do") | TC-DASH-004 |

Automated equivalents:

- **Vitest**, in `frontend/src/features/events/__tests__/`: `dashboard.spec.js` covers TC-DASH-006, 008, 009, 010, 011 and 012's readiness logic as pure unit tests. `store.spec.js` covers the 404 fallback of TC-DASH-001, plus 003 and 004. `coordinatorDashboard.spec.js` covers TC-DASH-023's search, filter, sort and grouping. `views/__tests__/CoordinatorDashboard.spec.js` covers TC-DASH-003, 004, 019, 022 and 023 in the rendered page, and `components/common/__tests__/Nav.spec.js` covers TC-DASH-021's links.
- **pytest**, in `backend/tests/test_coordinator_dashboard.py`: the server's derivation behind TC-DASH-013–018 and 020 (action kinds, readiness, no unassigned figure, scope, 403/401). The `technical_issue` → `arrangement_issue` rule is covered only there, since no screen can set technical readiness yet.
- **Live checks:** TC-DASH-013–018 in `backend/scripts/verify_live.py`, and TC-DASH-001, 019 and 022 in `frontend/e2e/dashboards.e2e.js`.

TC-DASH-002, 003, 005 and 024 are visual and stay manual. So does TC-DASH-020, because it changes shared data.

## Venue Staff dashboard (SCRUM-70)

**Preconditions for every case:** logged in as `venue.staff@connectsphere.dev` / `Cs1234`, on `/dashboard/venue-staff`, with every migration and `supabase/seed.sql` applied.

**Read this before running any of these.** `coordinator@connectsphere.dev` also holds `venue_staff`, but `require_roles` checks the **session's active role**, not the roles the account holds. That account signs in as `event_coordinator`, so the endpoint answers **403** until the role is switched in the nav dropdown. This is correct behaviour and TC-VSD-005 pins it — do not file it as a bug.

Unlike the coordinator dashboard above, no stubbing is needed: `venues`, `venue_blocks` and `venue_bookings` all exist and are seeded, so every case below runs against real data.

**Expected seeded figures:** 2 pending holds · 1 in re-review · 3 blocks · 8 venues (7 active, 1 inactive). `supabase/seed.sql` carries two `held` bookings — Seminar Room 1 (10 Oct 2026, requested 3 Sep) and Rooftop Terrace (13 Oct 2026, requested 28 Aug) — and both are still upcoming, so both are queued. If the pending tile reads `1` or the re-review tile reads `0`, the live database predates the seed rows added by this story — re-run the seed.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-VSD-001 | The four tiles show real figures from the endpoint | Seed applied | Open `/dashboard/venue-staff` and read the four tiles | — | Pending requests `2`, In re-review `1`, Active & upcoming blocks `3`, Venues `8` with the sub-line "7 active · 1 inactive". Every figure matches `GET /api/v1/venues/dashboard/venue-staff`. | 🔴 |
| TC-VSD-002 | No fabricated metrics remain (regression, DEFECTS D8) | As above | Read every label and number on the page | — | The strings "Venues Managed", "Booking Requests" and "Availability Updates Due" do **not** appear, and no tile reads `12`, `6` or `2` unless that is the true count. Those were the hardcoded placeholders this story removed. | 🔴 |
| TC-VSD-003 | Counts are withheld until the first load settles | Throttle the network (DevTools → Slow 3G) | Reload and watch the tiles while the request is in flight | — | All four tiles show "—", not `0`, and the lists read "Checking for updates…". A `0` must never appear before the answer is known. | 🟠 |
| TC-VSD-004 | A server failure is surfaced, not rendered as an empty queue | Stop the backend, or point it at a stub answering 503 | Reload the dashboard | — | A red error banner shows the failure. The page does **not** say "Nothing is waiting on your decision". | 🔴 |
| TC-VSD-005 | The endpoint is gated on the session's active role, not roles held | Signed in as `coordinator@connectsphere.dev` | `curl` the endpoint with the coordinator's token; then switch the nav dropdown to Venue Staff and retry | coordinator token | First call **403**. After the switch, **200** and the dashboard renders. Confirms the guard reads the active role (SCRUM-74/75). | 🔴 |
| TC-VSD-006 | A coordinator cannot reach the page by URL | Signed in as `coordinator@connectsphere.dev`, active role Event Coordinator | Navigate to `/dashboard/venue-staff` | — | Redirected to `/dashboard/coordinator`. Same for `/bookings/<any-id>`. | 🔴 |
| TC-VSD-007 | The calendar opens on the month that has something in it | Seed applied; system date before October 2026 | Read the calendar header, then press **Today** | — | The header reads **October 2026**, and **Today** is enabled. Pressing it returns to September 2026, after which **Today** is disabled. The header always names the month on screen. | 🟠 |
| TC-VSD-008 | A block's end is exclusive (§6.14, CAL-R2) | Seed applied | In October 2026, inspect the cells for 20, 21 and 22 Oct; then 14 and 15 Oct | — | 20 and 21 Oct are marked (Rooftop Terrace, safety); **22 Oct is not**. 14 Oct is marked (Heritage Hall, renovation); **15 Oct is not**. The seeded blocks run 20–22 and 1–15 Oct. | 🔴 |
| TC-VSD-009 | Selecting a day lists what is on it | Seed applied | Click 10 Oct 2026 | — | Below the grid: "Saturday, 10 October 2026", then the day's items, each with a colour-coded badge, its venue name and its Singapore-time span. Clicking again deselects. | 🟠 |
| TC-VSD-010 | The calendar will not page back before the current period | Seed applied | Press ← repeatedly, in each of Month and Week | — | It steps back to the current month (or week) and the ← control is then disabled. The payload is upcoming-only, so earlier periods would be empty by construction, not by fact. | 🟠 |
| TC-VSD-017 | The week view names each item rather than abstracting it | Seed applied | Press **Week** | — | Seven day columns, Monday first, headed with the week's date range. Each item appears in its day's column with the venue name and its Singapore-time span, colour-coded by kind. A day with more items than fit scrolls within its column. | 🟠 |
| TC-VSD-019 | A multi-day item is one bar, not one mark per day | Seed applied; October 2026 in the month view | Find the Rooftop Terrace safety block (20–22 Oct) and the Heritage Hall renovation (1–15 Oct) | — | The safety block is a single labelled bar covering the 20th and 21st. The renovation runs as a continuous bar across each week row it touches, drawn flat where it meets the week edge so it does not appear to stop on Sunday, and it does not reappear on the 15th. | 🔴 |
| TC-VSD-021 | The calendar exports to a real calendar app | Seed applied | Press **Export**, then open the downloaded file in Calendar, Outlook or Google Calendar | — | A file named `connectsphere-venues-<today>.ics` downloads and imports cleanly. It contains **every** block and pending request, not only the month on screen. Times match the dashboard when the client is set to Singapore. Blocks import as confirmed, pending requests as tentative. Re-importing updates the same entries rather than duplicating them. | 🔴 |
| TC-VSD-022 | Export is offered only when there is something to export | Point the backend at a stub returning four empty lists | Read the **Export** control | — | It is visibly disabled. Pressing it does nothing and no file downloads. | 🟠 |
| TC-VSD-020 | A crowded day counts what it cannot show | Month view; add a third and fourth overlapping item on one day | Read that day's cell | — | Two bars are drawn and the cell shows "+2". Nothing is dropped without being counted, and selecting the day lists all of them in the detail column. | 🟠 |
| TC-VSD-018 | Switching view keeps the period in view | Seed applied | From the month view press → to reach November, then press **Week** | — | The week view opens inside November rather than jumping back to the current week. Pressing **Month** returns to the month the shown week sits in. The arrows step by week while in Week, by month while in Month. | 🟠 |
| TC-VSD-011 | **Superseded by CR-99 (W7 CR-04), see TC-HOLD-006.** Pending requests are ordered longest-waiting first, without SLA framing (BR-R4, LC-R4) | Seed applied (two holds) | Read the "Pending requests" list | — | Now: soonest expiry first, each with "Expires …". "Waiting N days" stays in **neutral ink** — never red, never "overdue". | 🔴 |
| TC-VSD-012 | A request row opens its own page (AC5) | Seed applied | Click a pending request | — | Navigates to `/bookings/<booking id>`, which states that the full request view and the approve/reject decision arrive with SCRUM-19/20 and echoes the booking id back. It does not 404 or dead-end. | 🟠 |
| TC-VSD-013 | Venue rows show status at a glance and open the venue (AC2, AC5) | Seed applied | Read the "All venues" panel, then click a venue | — | All 8 venues listed, needing-attention first: `BLOCKED NOW` (red) / `BLOCK SCHEDULED` (yellow) / `ACTIVE` (green) / `INACTIVE` (grey). Red and yellow mark what wants a decision; green marks what does not. Old Lecture Theatre reads INACTIVE. Clicking opens `/venues/:id`. The panel is headed "All venues" with the pool note (AUTH-R5). | 🔴 |
| TC-VSD-014 | An inactive venue reads inactive even while blocked | Seed applied; add a block on Old Lecture Theatre | Read its row | — | Status is `INACTIVE`, not `BLOCKED NOW`. Out of service entirely outranks a block on it. | 🟠 |
| TC-VSD-015 | Usable on a phone-width viewport (NFR-U1) | Seed applied | Set the viewport to 390 × 844 | — | Tiles stack to one column, the calendar sits below them, both list panels stack, no horizontal scrolling, all 7 calendar columns legible. | 🟠 |
| TC-VSD-016 | Times display in Asia/Singapore (REQUIREMENTS §4) | Set the OS timezone to something other than SGT | Reload and read any period | — | Times are unchanged — rendered in Asia/Singapore regardless of the browser's zone, matching the venue detail page. | 🟠 |
| TC-VSD-023 | AC1 — venue staff reach the work queue by signing in, and nothing else | Logged out, on `/login`; seed applied | 1. Sign in. 2. Touch nothing afterwards — no menu, no second page. | `venue.staff@connectsphere.dev` / `Cs1234` | `POST /auth/login` returns `profile.role = "venue_staff"`; the browser lands on `/dashboard/venue-staff` (`ROLE_DASHBOARD_ROUTES`) with no intermediate page. The view calls `GET /api/v1/venues/dashboard/venue-staff` on mount, and the four tiles, the calendar and both list panels settle to real figures without any further input. | 🔴 |
| TC-VSD-024 | AC4 — a block running right now reads as active, not merely upcoming | Seed applied; insert one block on Grand Ballroom spanning yesterday to tomorrow | Reload; read the blocks tile, the calendar and the Grand Ballroom row | one straddling block | "Active & upcoming blocks" reads `4`. The block is drawn as a bar covering yesterday and today, and the venue row reads `BLOCKED NOW` with "Blocked until <tomorrow>". A block is kept while its **end** is after now (`repository.list_all_upcoming_blocks`), so one already in progress is never dropped for having started in the past. | 🔴 |
| TC-VSD-025 | AC4 — a block that has already finished is not surfaced anywhere | Seed applied; insert one two-hour block on Grand Ballroom entirely in the past | Reload; read the tile, the calendar, the venue row, and the `.ics` export | one past block | The tile still reads `3`. The block appears in none of them, and the venue reads `ACTIVE`. The payload is upcoming-only by construction — which is also why the calendar refuses to page back before the current period (TC-VSD-010). | 🟠 |
| TC-VSD-026 | AC3 — the pending queue spans every venue and names each one | Seed applied | Read the "Pending requests" panel top to bottom | — | Both seeded holds appear on **different** venues — Rooftop Terrace (requested 28 Aug 2026) first, then Seminar Room 1 (3 Sep 2026) — each row headed by its own venue name, with the event reference and the Singapore-time span beneath. There is no venue picker and no "my venues" filter: the scope is the whole catalogue (AUTH-R5, QA-44). | 🔴 |
| TC-VSD-027 | AC4 — "blocks I've set" resolves to every block, because no creator is recorded | Seed applied; add a block through a second route (`psql`, or a different staff session) | Reload as `venue.staff@connectsphere.dev`; read the tile and the calendar | a block this account did not create | It is counted and drawn exactly like the seeded three. `public.venue_blocks` has no creator column (`supabase/migrations/20260915090000_venues_catalogue_and_availability.sql`) and staff work as one pool, so a per-person filter is neither possible nor intended. Confirm no label on the page claims the list is only "mine". | 🟠 |
| TC-VSD-028 | AC2 — a venue's status follows its block across both boundaries | Seed applied; able to move the clock, or to shift the seeded Rooftop Terrace safety block (20–22 Oct 2026) around "now" | Read the Rooftop Terrace row at three moments: before the block starts, while it runs, and after it ends | the seeded safety block | Before: `BLOCK SCHEDULED` (yellow), "Safety from 20 Oct". During: `BLOCKED NOW` (red), "Blocked until 22 Oct". After: `ACTIVE`, showing the venue's location. Status is derived on each load from the block list, never stored on the venue. | 🔴 |
| TC-VSD-029 | AC5 — a request row carries its own identity through to the detail page | Seed applied | Click the Rooftop Terrace hold, note the URL, then open that URL in a fresh tab of the same session | — | The URL is `/bookings/d0000000-0000-4000-8000-000000000004` — the `id` of that row in the dashboard payload, not an index or a placeholder. The deep link loads the same page directly; the route is `venue_staff`-only, so the guard lets this session through (contrast TC-VSD-006). | 🟠 |
| TC-VSD-030 | AC3/AC5 — a re-review request is counted but cannot be opened (known limitation) | Seed applied | Read the "In re-review" tile, then try to reach that request's details from anywhere on the page | — | Current behaviour: the tile reads `1` and the Boardroom Orchid re-review is drawn on 12 Oct in the calendar, but there is no list row for it and calendar items are not links — so nothing navigates to its `/bookings/<id>`. AC3 is met by the count; AC5 is met for the two things it names (a venue, a pending request). **Flag as a follow-up** — either a re-review list or clickable calendar items, to be settled alongside SCRUM-19/20. | 🟠 |
| TC-VSD-031 | AC2 — the venue list filters to one status, and each control carries its count | Seed applied | Read the filter row above "All venues", press **Block scheduled**, then press **All** | — | Against the seed, with today before 1 Oct 2026, the row reads `All 8 · Block scheduled 3 · Active 4 · Inactive 1` — the three blocked venues (Heritage Hall, Grand Ballroom, Rooftop Terrace) all have their blocks still ahead of them, so "Blocked now" is absent until one is running. "All" comes first, the rest worst-first, each carrying the number of venues in that state. The controls themselves are plain: selecting one fills it with ink, and none of them carries a status colour. Pressing one narrows the list to exactly those venues and marks that control pressed; **All** restores all 8. The filter is view state: a reload returns to **All**. | 🔴 |
| TC-VSD-032 | AC2 — a filter that could only ever return nothing is not offered | Seed applied; remove or expire every block so no venue is blocked or block-scheduled | Reload and read the filter row | — | Neither "Blocked now" nor "Block scheduled" appears — a dead control would read as the dashboard hiding something. Only "All" and the states present are shown. If a filter's status disappears while it is applied, the list falls back to **All** rather than going blank. | 🟠 |
| TC-VSD-033 | AC2/AC3 — both list panels scroll instead of pushing the page down | Seed applied; enough rows to overflow (all 8 venues, and more holds than fit) | Read the "All venues" and "Pending requests" panels at a desktop width, then scroll inside each | — | Each list is capped at the same height with its own scrollbar, so every row is reachable without the panel running past the fold, and each row's hard shadow stays visible rather than being clipped at the right edge. Each panel's heading — and the venue filter row — stays put while its list scrolls. Because both caps match, the two columns stay level once either one fills. | 🟠 |
| TC-VSD-034 | AC3 — the pending-requests tile takes you to the list it counts | Seed applied | Hover the "Pending requests" tile, then Tab to it, then press it | — | On hover the tile picks up the same hard shadow every other clickable card uses and "See the list ↓" fades in beside "Awaiting your approval"; nothing is shown before hover, so the tile reads as a figure at rest. Tabbing to it shows the identical cue, and a screen reader hears it either way (it is hidden by opacity, not removed). Pressing it scrolls to the "Pending requests" section with its heading clear of the sticky top bar, and the URL gains `#pending-requests`, so Back returns to the top. Middle-click opens it as an ordinary link. The other three tiles have no hover cue and are not links. | 🟠 |

| TC-VSD-035 | Summary cards align when text wraps (D20) | Signed in as venue staff | Open `/dashboard/venue-staff`; resize to 1440, 1280, 1100, 768, 640, 375 and 320px. Inspect the four summary tiles; focus Pending requests | Existing dashboard data | Equal border heights and aligned numbers/descriptions within each row; one column below 768px, two below 1280px, four above. Text remains readable without clipping or horizontal scrolling; revealing the link cue causes no height jump. | 🟠 |

### Traceability — SCRUM-70

| Acceptance criterion / rule | Covered by |
|---|---|
| AC1 "On successful login, Venue Staff are routed directly to their dashboard" | TC-VSD-023, TC-AUTH-002, TC-RBAC-003 (existing), TC-VSD-005 |
| AC2 "lists all venues … current status (active/blocked) shown at a glance" | TC-VSD-001, TC-VSD-013, TC-VSD-014, TC-VSD-028, TC-VSD-031, TC-VSD-032, TC-VSD-033 |
| AC3 "a count or list of pending booking requests awaiting my decision, across all my venues" | TC-VSD-001, TC-VSD-011, TC-VSD-026, TC-VSD-030, TC-VSD-034 |
| AC4 "any active or upcoming blocks I've set" | TC-VSD-001, TC-VSD-008, TC-VSD-009, TC-VSD-024, TC-VSD-025, TC-VSD-027 |
| AC5 "Selecting a venue or a pending request … navigates directly to its full details" | TC-VSD-012, TC-VSD-013, TC-VSD-029, TC-VSD-030 |
| REQUIREMENTS §6.21 widget priority order (holds → re-review → blocks → venues) | TC-VSD-001 |
| REQUIREMENTS §6.21.2 month and week views | TC-VSD-017, TC-VSD-018 |
| REQUIREMENTS §6.21.2 multi-day items as spanning bars, with counted overflow | TC-VSD-019, TC-VSD-020 |
| REQUIREMENTS §6.21.2 iCalendar export | TC-VSD-021, TC-VSD-022 |
| REQUIREMENTS §6.21 "build a widget only when its data exists" | TC-VSD-003, TC-VSD-012 |
| AUTH-R5 / QA-44 (staff are a pool; scope is all venues) | TC-VSD-013, TC-VSD-026, TC-VSD-027 |
| BR-R4 (as amended by CR-99: holds expire; soonest expiry first) | TC-VSD-011 (superseded), TC-HOLD-006 |
| LC-R4, QA-55, QA-68 (no SLA or deadline framing) | TC-VSD-011 |
| §6.14, CAL-R2 (half-open periods; a block's end is exclusive) | TC-VSD-008 |
| §6.19 (re-review after an approved change) | TC-VSD-001 |
| SCRUM-74/75 (guards read the session's active role) | TC-VSD-005 |
| RBAC (venue staff only) | TC-VSD-006 |
| REQUIREMENTS §4 (stored UTC, displayed Asia/Singapore) | TC-VSD-016 |
| NFR-U1 (desktop and mobile friendly), D20 wrapping regression | TC-VSD-015, TC-VSD-035 |
| DEFECTS D8 (fabricated metrics) | TC-VSD-002 |
| Reliability (an outage is not rendered as "nothing to do") | TC-VSD-004 |

Automated equivalents live in `frontend/src/features/venues/__tests__/` and `backend/tests/`. `calendar.spec.js` covers TC-VSD-007, 008, 010, 019 and 020, and the week-grid half of 017, as pure unit tests, including boundaries a manual pass cannot easily reach (a range ending one millisecond after midnight, and the same instant written two ways). `dashboard.spec.js` covers TC-VSD-011's ordering and TC-VSD-013/014's status precedence. `venueStaffDashboardStore.spec.js` covers TC-VSD-003 and 004. `views/__tests__/venueStaffDashboard.spec.js` covers TC-VSD-001, 002, 009, 012 and 013. `backend/tests/test_venues_api.py` covers TC-VSD-005 and 006's server side. `ics.spec.js` covers the file's format — stamps, escaping, octet-safe folding, stable UIDs, tentative versus confirmed. TC-VSD-015, TC-VSD-016 and the "opens in a real calendar app" half of TC-VSD-021 are visual or need a third-party client, and remain manual.

TC-VSD-023–030 were added when SCRUM-70's user story was restated, to pin the acceptance criteria's own wording rather than only the widgets built for it. Their automated equivalents, where they exist: `backend/tests/test_venue_dashboard.py::TestCrossVenueReads` covers TC-VSD-025's cut-off (blocks are filtered on an open-ended range in Postgres, so a finished one never leaves the database) and TC-VSD-026's server half (every row names its venue); `dashboard.spec.js::venueStatuses` covers TC-VSD-024's and TC-VSD-028's status transitions, including a block that ends exactly now. TC-VSD-023 (login through to a settled queue), TC-VSD-027 (no creator column to filter on), TC-VSD-029 (deep link) and TC-VSD-030 (the re-review gap) are end-to-end or documentary and remain manual.

TC-VSD-031–034 cover the venue-list filter, its scrolling and the tile jump. `dashboard.spec.js::venueStatusFilterOptions` and `::filterVenueStatuses` cover the pure half — the option order and counts, that an absent status is never offered, and that an unknown key falls back to every row rather than to none — and `views/__tests__/venueStaffDashboard.spec.js` covers the wiring: the controls' labels and counts, narrowing and restoring the list, the capped scrolling container, and the tile's `#pending-requests` anchor with a target that clears the sticky bar. What stays manual is what only a browser shows: that the scrollbar is reachable and the shadows are not clipped (TC-VSD-033), and that the jump lands with the heading visible (TC-VSD-034).

TC-VSD-035 is automated in `frontend/e2e/venue-dashboard-layout.e2e.js` against the real venue-staff API. It measures card and paragraph positions after resize transitions settle, checks responsive column counts and overflow, and confirms the focus cue and fragment link still work. Human judgment of spacing/readability remains manual alongside TC-VSD-015 and TC-VSD-034.

## Event Organiser dashboard (SCRUM-71)

**Preconditions for every case:** logged in as `organiser@connectsphere.dev` / `Cs1234`, with owned drafts and requests available, on `/dashboard/organiser`.

| ID | Title | Test Steps | Expected Result | Priority |
|---|---|---|---|---|
| TC-ORG-001 | Owned events are separated into drafts and requests | Open the organiser dashboard and inspect both sections | Only the organiser's owned events are shown; drafts appear under **Drafts**, all other lifecycle statuses under **Requests**; no organisation-wide events are mixed in. | 🔴 |
| TC-ORG-002 | Event cards show decision-useful details | Inspect a draft and a submitted request | Each card shows its name, status, schedule or missing schedule, attendance, venue or unassigned state, and any required attention message. No fabricated counts or metrics appear. | 🔴 |
| TC-ORG-003 | Status and name filters apply without another request | Select a status, then enter part of an event name; inspect the network panel | Only matching cards remain, and no additional events request is sent. **Clear filters** restores the complete owned collection. | 🔴 |
| TC-ORG-004 | Sorting is deterministic and client-side | Sort by event date, name, and status in ascending and descending order | Visible cards reorder according to the selected field and direction; the loaded collection is unchanged and no additional request is sent. | 🟠 |
| TC-ORG-005 | Dashboard actions use the existing event flows | Click **Edit draft**, **Amend and resubmit**, **View event**, and **New event request** as applicable | Drafts and returned requests open `/events/new` with the event id (returned requests in amend mode, SCRUM-33); other requests open `/events/:id`; new requests open `/events/new`. No inline mutation occurs on the dashboard. | 🔴 |
| TC-ORG-006 | Server failure is not presented as an empty success state | Stop the backend or stub the events request with HTTP 503, then reload | A clear error banner is shown and normal event content is not presented as an empty successful dashboard; the session remains signed in. | 🔴 |
| TC-ORG-007 | Dashboard remains usable on a mobile viewport | Set the viewport to 390 × 844 and inspect the page and controls | Filters stack without horizontal scrolling, card text and actions remain readable, and no controls overlap. | 🟠 |
| TC-ORG-008 | Loading is distinct from empty data | Delay the owned-events response, then inspect the dashboard before it resolves; resolve it with no events | A loading state is shown while the request is pending; Drafts/Requests empty states are not shown until the successful empty response arrives. | 🔴 |
| TC-ORG-009 | Coordinator assignment state is clear and non-duplicated | Inspect an unassigned submitted/under-review request and an assigned request | The unassigned request shows **Awaiting assignment** once, while an assigned request shows **Coordinator assigned**. | 🟠 |

| TC-ORG-010 | Summary cards align when labels wrap (D21) | Logged in as the dashboard’s role | Open `/dashboard/organiser`; resize to 1440, 1280, 1100, 768, 640, 375 and 320px; inspect the summary row, especially Returned for amendments | — | Equal card heights and aligned figures/details within each row. Summary text remains visible; its row stays inside the viewport. One/two/three-or-four columns follow available space. Existing category actions still work. | 🟠 |

### Traceability — SCRUM-71

| Requirement | Covered by |
|---|---|
| Owned events are the primary dashboard list; organisation-wide view is deferred | TC-ORG-001 |
| Event details and honest attention states | TC-ORG-002 |
| Frontend filtering and sorting | TC-ORG-003, TC-ORG-004 |
| Mutations occur through existing request/detail flows, not inline dashboard editing | TC-ORG-005 |
| Outages show an error rather than false emptiness | TC-ORG-006 |
| Desktop/mobile usability (NFR-U1) | TC-ORG-007 |
| Loading, empty, and error states are distinguished | TC-ORG-006, TC-ORG-008 |
| Coordinator assignment state is visible | TC-ORG-002, TC-ORG-009 |

Automated equivalents live in `frontend/src/features/events/__tests__/organiserDashboard.spec.js` and `frontend/src/views/__tests__/OrganiserDashboard.spec.js`; together they cover the pure selectors, rendering, filtering, sorting, attention states, action routing, and server-error state. TC-ORG-007 remains a manual browser check.

## Technical Support dashboard (SCRUM-73)

**Preconditions for every case:** logged in as `tech.support@connectsphere.dev` / `Cs1234`, on `/dashboard/tech-support`, with every migration and `supabase/seed.sql` applied.

Like the Venue Staff dashboard and unlike the coordinator dashboard, these run against real data: `equipment`, `equipment_unavailability` and `equipment_reservations` all exist and are seeded.

**Expected seeded figures** (from `supabase/seed.sql`, verified against the live project): **5 equipment types** — 4K Projector (4), HDMI Switchers (6), PA Systems (3), Stage Lighting (8), Wireless Mics (12) — **2 maintenance records** and **3 reservations**, all on 15 Oct 2026. With no window applied the inventory reads:

| Equipment | Total | Reserved | Maintenance | Net available |
|---|---|---|---|---|
| 4K Projector | 4 | 2 | 1 | 1 |
| HDMI Switchers | 6 | 0 | 0 | 6 |
| PA Systems | 3 | 2 | 1 | 0 |
| Stage Lighting | 8 | 0 | 0 | 8 |
| Wireless Mics | 12 | 8 | 0 | 4 |

The two maintenance records are PA Systems 08:00–13:00 UTC ("Amplifier inspection and battery replacement") and 4K Projector 12:00–18:00 UTC ("Scheduled maintenance and lens calibration"). If the inventory shows fewer than five rows, the database predates this story's seed — re-run it.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-TSD-001 | AC1 — the whole equipment list is shown | Seed applied | Open the dashboard and read the inventory table | — | All **5** seeded types are listed, alphabetically, with name, total, reserved, in-maintenance and net-available figures matching the table above. Every figure matches `GET /api/v1/equipment/inventory`. | 🔴 |
| TC-TSD-002 | AC1 — the list can be searched by name | Seed applied | Type `mic` into the inventory search box | `mic` | Only "Wireless Mics" remains. Clearing the box restores all five rows. The filter is case-insensitive. | 🟠 |
| TC-TSD-003 | AC1 — status badges reflect real stock, not a guess | Seed applied | Read each row's status badge | — | Against the seeded figures: **PA Systems** reads OUT OF STOCK (net 0), **4K Projector** reads UNDER REPAIR (1 in maintenance, net 1), **Wireless Mics** reads PARTIALLY RESERVED (8 of 12 reserved), and **HDMI Switchers** and **Stage Lighting** read AVAILABLE. Precedence is out-of-stock → under-repair → partially-reserved → available, so no badge contradicts its own row's numbers. | 🟠 |
| TC-TSD-004 | AC3 — scheduled maintenance is listed from real records | Seed applied | Read the "Scheduled maintenance" panel | — | Exactly **2** records, **oldest first**: PA Systems (15 Oct 08:00–13:00) then 4K Projector (15 Oct 12:00–18:00). Each shows equipment name, the Singapore-time span, and its reason. | 🔴 |
| TC-TSD-005 | AC3 — maintenance status is derived from the clock | Seed applied; system date before 15 Oct 2026 | Read the status badge on each maintenance record | — | Both read **SCHEDULED**. A record whose window has started but not ended reads IN_PROGRESS; one wholly in the past reads COMPLETED. The badge is computed at request time, never stored. | 🟠 |
| TC-TSD-006 | AC3 — past maintenance is not hidden (known behaviour) | Seed applied; system date after 15 Oct 2026, or a record backdated | Read the maintenance panel | — | Finished records still appear, marked COMPLETED — `get_equipment_maintenance` applies no date filter. Pinning current behaviour: if the team decides the panel should show upcoming work only, this case changes with it. | 🟡 |
| TC-TSD-007 | AC2 — active requests are honestly empty, not faked | Seed applied | Read the "Active requests" panel | — | An empty state reads "No request workflow yet" and explains requests appear once SCRUM-24 lands. The strings "Marcus Lim", "Olivia Tan", "PENDING", "Approve" and "Reject" do **not** appear anywhere on the page. | 🔴 |
| TC-TSD-008 | No fabricated data remains (regression, DEFECTS D8) | Seed applied | Read every number and label on the dashboard | — | Every figure traces to an API response. No hardcoded request cards, and no count that cannot be reproduced from `/equipment/inventory` or `/equipment/maintenance`. | 🔴 |
| TC-TSD-009 | Both endpoints are gated on the session's active role | An account holding `tech_support` but signed in as another role | `curl` `/api/v1/equipment/inventory` and `/api/v1/equipment/maintenance` with that token; then switch the nav dropdown to Technical Support and retry | that account's token | First calls **403**, after the switch **200**. Confirms the guard reads the active role, not roles held (SCRUM-76). | 🔴 |
| TC-TSD-010 | Another role cannot reach the page by URL | Signed in as `coordinator@connectsphere.dev`, active role Event Coordinator | Navigate to `/dashboard/tech-support` | — | Redirected to `/dashboard/coordinator`; the equipment data never renders. | 🔴 |
| TC-TSD-011 | A server failure is surfaced, not shown as an empty inventory | Stop the backend, or point it at a stub answering 503 | Reload the dashboard | — | An error message names the failure. The page does **not** render an empty equipment table or an empty maintenance list as though both were genuinely empty. | 🔴 |
| TC-TSD-012 | Figures are withheld until the first load settles | Throttle the network (DevTools → Slow 3G) | Reload and watch the panels while the requests are in flight | — | The maintenance panel shows "Loading maintenance" rather than "No maintenance records scheduled". A false empty state must never appear before the answer is known. | 🟠 |
| TC-TSD-013 | The views are chosen from the sidebar, not an in-page tab bar | Signed in as `tech.support@connectsphere.dev` | Log in; then click **Availability** in the sidebar; then **Inventory** | — | Login lands on the inventory view with **Inventory** highlighted (yellow) as the first sidebar item and **Availability** below it. **Availability** switches to `?tab=availability` and highlights. **Inventory** returns to the inventory. The page has no tab bar and no welcome card, only headed sections like the venue-staff dashboard. The browser Back button returns to the previous view. | 🟠 |
| TC-TSD-014 | The sidebar views are tech support only | An account holding `tech_support` and another role, acting as the other role | Read the sidebar | — | No **Availability** / **Inventory** links; the ordinary **Dashboard** link is shown. Switching the active role to Technical Support shows them. | 🟠 |
| TC-TSD-016 | The tiles summarise the inventory and never guess | Seed applied | Open the dashboard; then repeat with the backend stopped | — | Four tiles: Out of stock **1** (PA Systems), Under repair **1** (4K Projector), Maintenance scheduled **2**, Equipment types **5** with the total units underneath. With the backend stopped, each tile shows **—**, not 0. | 🟠 |
| TC-TSD-015 | Badges use the shared status colours | Seed applied | Open **Inventory**; run an availability check that is sufficient and one that is not | — | OUT OF STOCK red, UNDER REPAIR yellow, PARTIALLY RESERVED blue, AVAILABLE green (the same green as the venue-staff ACTIVE badge). SCHEDULED maintenance is white, IN_PROGRESS yellow, COMPLETED grey. The check result badge is green for SUFFICIENT and red for INSUFFICIENT, and the result only shows on the Availability view. No orange anywhere. | 🟡 |

| TC-TSD-017 | Summary cards align when labels wrap (D21) | Logged in as the dashboard’s role | Open `/dashboard/tech-support`; resize to 1440, 1280, 1100, 768, 640, 375 and 320px; inspect the summary row, especially Maintenance scheduled | — | Equal card heights and aligned figures/details within each row. Summary text remains visible; its row stays inside the viewport. One/two/three-or-four columns follow available space. Existing category actions still work. | 🟠 |

### Traceability — SCRUM-73

| Acceptance criterion / rule | Covered by |
|---|---|
| AC1 "I want to see the entire list of equipment" | TC-TSD-001, TC-TSD-002, TC-TSD-003 |
| AC2 "the list of active requests being sent to me" | TC-TSD-007 (empty state — the workflow itself is SCRUM-24) |
| AC3 "the list of equipment scheduled for maintenance" | TC-TSD-004, TC-TSD-005, TC-TSD-006 |
| REQUIREMENTS §6.21 "build a widget only when its data exists" | TC-TSD-007, TC-TSD-012 |
| DEFECTS D8 (no fabricated dashboard data) | TC-TSD-007, TC-TSD-008 |
| SCRUM-76 (guards read the session's active role) | TC-TSD-009 |
| RBAC (technical support only) | TC-TSD-010 |
| Navigation and design-system consistency (`fix/ui-TechSupportDashboard`) | TC-TSD-013, TC-TSD-014, TC-TSD-015, TC-TSD-016 |
| REQUIREMENTS §4 (stored UTC, displayed Asia/Singapore) | TC-TSD-004 |

**Automated coverage today.** `backend/tests/test_active_role_access.py` covers the server half of TC-TSD-009 and TC-TSD-010 for both endpoints — it enumerates every registered route, so `/equipment/maintenance` and `/equipment/inventory` are both parametrised into it automatically. Everything else in this section is **manual only**: `get_equipment_maintenance` has no functional test, and there is no `TechSupportDashboard` component spec, so TC-TSD-001 through 008, 011 and 012 have no automated equivalent yet. That gap is the first thing to close if this dashboard gains more logic.


## Event Coordinator Lead dashboard (CR-101)

**Preconditions for every case:** the migration `20261013120000_lead_assignment.sql` is applied; logged in as `coordinator.lead@connectsphere.dev` / `Cs1234`, on `/dashboard/coordinator-lead`, unless a case says otherwise. AC6 (the coordinator deactivation refusal, QA3-22) is out of scope for this story, so no case covers it.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-LEAD-001 | AC1, AC4 — the API returns the queue, active events and counts, active statuses only | Signed in as the Lead | Send `GET /events/dashboard/lead` | — | 200 with exactly `unassigned`, `active_events`, `coordinators`. Every status is one of under review, returned, planning, safety review, confirmed. Queue events have no coordinator; active events all have one. | 🔴 |
| TC-LEAD-002 | AC7 — every other role is refused the dashboard | Signed in as each seeded role in turn | Send `GET /events/dashboard/lead` directly, bypassing the SPA | — | 403 for organiser, coordinator, venue staff, tech support and attendee. | 🔴 |
| TC-LEAD-003 | AC7 — every other role is refused reassign | As TC-LEAD-002 | Send `POST /events/<id>/reassign` with a coordinator id | `{"coordinator_id": "<a coordinator>"}` | 403 for every non-Lead role, and the event's coordinator is unchanged. | 🔴 |
| TC-LEAD-004 | AC3 — reassigning an unknown event is 404 | Signed in as the Lead | `POST /events/<unknown id>/reassign` | a coordinator id | 404. | 🟠 |
| TC-LEAD-005 | AC7 — no token, no access | — | Send both requests without an `Authorization` header | — | 401 each. | 🟠 |
| TC-LEAD-006 | The dashboard loads from the real endpoint | Backend on this branch | Open `/dashboard/coordinator-lead` and wait for the network to settle | — | `GET /events/dashboard/lead` returns 200; "Unassigned queue" and "Active events" headings show; no error banner. | 🔴 |
| TC-LEAD-007 | AC7 — a coordinator is sent away from the Lead page | Signed in as `coordinator@connectsphere.dev` | Open `/dashboard/coordinator-lead` | — | Redirected to `/dashboard/coordinator`. | 🔴 |
| TC-LEAD-008 | The assignment columns and `reassign_event` against the real database | Migration applied | Run `supabase/verification/lead_assignment_checks.sql` (rolled back) | — | Prints `CR-101 LEAD ASSIGNMENT CHECKS PASSED`: assign and reassign set coordinator, `assigned_by`, `assigned_at` and bump the version; one history row; new coordinator, previous coordinator and organiser notified, never the Lead; a stale version, a non-coordinator target and a completed event change nothing; `anon` and `authenticated` cannot execute it. | 🔴 |
| TC-LEAD-009 | AC1 — the queue and active events read correctly | At least one unassigned and one assigned active event exist | Read both lists | — | The queue lists unassigned requests with status, date and organiser. Active events show status, date and coordinator name. Wording and layout match the other dashboards. | 🔴 |
| TC-LEAD-010 | AC2 — filters and counts | As TC-LEAD-009, two or more coordinators with events | Choose a coordinator; choose one or more statuses; type part of a name; press **Clear**. Read the workload chips | — | Each filter narrows only the active-events list (the queue is unchanged) and they combine. "No matching events" when nothing fits. Each coordinator's chip shows their active-event count, including 0. | 🔴 |
| TC-LEAD-011 | AC3 — open an event and reassign it. **Changes shared data**: reassign it back, or reset the fixtures, afterwards | An active event and a second coordinator | Click an event; choose a coordinator; **Reassign**; confirm | — | The event page shows its details and current coordinator; the picker omits the current coordinator; **Reassign** is disabled until one is chosen. After confirming: a success message, back on the dashboard with the event under the new coordinator and counts updated. The new coordinator, the previous coordinator and the organiser each get a notification; the event's history shows who reassigned it. A stale page answers "updated by someone else. Reload." and leaves the event unchanged. | 🔴 |
| TC-LEAD-012 | AC5 — scope with more than one Lead (needs a second Lead account) | A second Lead and events assigned by each | As each Lead in turn, read the dashboard | — | Both see the whole unassigned queue. Each sees the assigned events they assigned or last reassigned, plus events assigned before the Lead role existed. Neither sees events the other assigned. With one Lead, they see everything. | 🟠 |
| TC-LEAD-013 | AC4 — closed events disappear from the active list | A coordinator-assigned event in planning | As the coordinator reject it (or complete one), then reload the Lead dashboard | — | The event is gone from Active events and from its coordinator's count. Opening its Lead page says it isn't in scope. | 🟠 |
| TC-LEAD-014 | The dashboard looks like it belongs next to the coordinator's | `/dashboard/coordinator` open as the coordinator in another window | Compare both; resize to 1440, 768 and 375px | — | Same cards, borders, shadows, type and colours. Summary cards, chips, filter bar and rows stay inside the viewport at 375px, with no truncated text. | 🟠 |

### Traceability — CR-101

| Acceptance criterion | Covered by |
|---|---|
| AC1 queue and active events with coordinator and status | TC-LEAD-001, TC-LEAD-006, TC-LEAD-009 |
| AC2 filter by coordinator and status; per-coordinator counts | TC-LEAD-010 |
| AC3 open an event and reassign it | TC-LEAD-003, TC-LEAD-004, TC-LEAD-008, TC-LEAD-011 |
| AC4 closed events are not active | TC-LEAD-001, TC-LEAD-013 |
| AC5 one or more Leads; legacy assignments visible | TC-LEAD-012 (rules in `test_lead_scope.py`) |
| AC6 deactivation refusal | Out of scope for this story |
| AC7 only the active Lead role; others 403 | TC-LEAD-002, TC-LEAD-003, TC-LEAD-005, TC-LEAD-007 |

Automated equivalents:

- **pytest**, in `backend/tests/`: `test_lead_scope.py` (AC5 rules), `test_lead_dashboard.py` (scope, statuses, counts, 403 for every other role), `test_lead_reassign.py` (reassign success, 404/403/409/422, 403 for every other role), `test_lead_repository.py` (the reads and the RPC call), plus the all-routes matrix in `test_active_role_access.py`.
- **Vitest**: `features/events/__tests__/leadDashboard.spec.js`, `leadDashboardStore.spec.js`, `views/__tests__/CoordinatorLeadDashboard.spec.js` and `LeadEventView.spec.js`, plus the all-routes guard in `router/__tests__/activeRoleAccess.spec.js`.
- **Live checks:** TC-LEAD-001–005 in `backend/scripts/verify_live.py`, TC-LEAD-008 through `lead_assignment_checks.sql` in the same script, and TC-LEAD-006–007 in `frontend/e2e/lead-dashboard.e2e.js`.

TC-LEAD-009–014 need a person (wording, layout, phone width) or change shared data, so they stay manual.

## Attendee dashboard — layout audit (D21)

The attendee dashboard remains a placeholder with existing hardcoded metrics (known D8); this case checks layout only and does not validate those figures or implement registrations.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-ATT-001 | Summary cards align when labels wrap (D21) | Signed in as attendee on `/dashboard/attendee` | Resize to 1440, 1280, 1100, 768, 640, 375 and 320px; inspect Upcoming Registrations and Public Events Available | — | Equal card heights and aligned figures within each row, readable text without truncation, and summary row within the viewport. | 🟠 |

### Traceability — dashboard layout fixes D20/D21

`frontend/e2e/dashboard-summary-layout.e2e.js` automates TC-ORG-010, TC-DASH-025, TC-TSD-017 and TC-ATT-001: real rendered positions after resize transitions settle, summary-row bounds, readable content, and organiser/coordinator tile navigation. The venue equivalent remains TC-VSD-035. These implement NFR-U1 and the approved REQUIREMENTS §6.21 layout decision; no new story acceptance criteria are inferred. A developer still judges spacing and readability at desktop/375px. Tech-support’s unrelated inventory-filter page overflow is D22; the summary row is tested independently.
