# 23-R second review — d9bb919 — 2026-10-24

| Field | Value |
|---|---|
| Scope | Product commit d9bb919 against c70b159, plus surrounding requirements, services, SQL and tests |
| Reviewers | Codex verification, independent condition-semantics explorer, fresh Claude read-only check |
| Verdict | Needs changes; AC1 and AC4 cannot be certified across the identified boundary cases |
| Product changes during review | None |

| Finding | Status | Evidence |
|---|---|---|
| D57: retired stock counted as available | Confirmed, Medium, pre-existing but affects AC1 | Live rolled-back SQL probe: total 7, status retired, no outages/reservations → free 7, sufficient for 6. The real shared function does not inspect equipment.status; service.py:71 uses its result verbatim. New request submission rejects retired stock. |
| Maintenance-status interpretation | Confirmed behavior; business meaning unresolved | Same live probe with maintenance status also returned 7. Quantity-specific timed outages are excluded correctly. Whether this catalogue status should block all units is not explicitly settled; this is not proof that all maintenance stock is unusable. |
| D58: duplicate equipment demand checked independently | Confirmed, Medium, pre-existing but affects AC4 | Actual service call with the external repository seams supplying 7 free and two same-ID lines of 5 → overall sufficient true, missing quantities [0, 0], although total demand is 10 and shortage is 3. Form addItem and validateForm do not prevent duplicate selections. |
| Missing migration | Confirmed deployment gate | Read-only live schema query returned storage_location_deployed false. No permanent migration was applied. |
| SQL-probe cleanup | Confirmed | Both test items were inserted only within BEGIN/ROLLBACK. Follow-up query found zero rows named 23-R review stock (rolled back). No seeded records were changed. |

**Verified source locations:** `supabase/migrations/20261019120000_equipment_reservation.sql:166–169` (status omitted); `backend/app/modules/equipment/service.py:68–80` (per-row comparisons); `backend/app/modules/equipment/schemas.py:13–21` (no duplicate validation); `frontend/src/views/dashboards/TechSupportDashboard.vue:179–198` (duplicate rows allowed). Availability tests fake the RPC at `backend/tests/test_equipment_availability.py:77–96`; their equipment fixture lacks status. The SQL verification file creates default-active stock, so the recorded passing outage cases do not cover catalogue status changes.

**No issue found in the added single-row shortage arithmetic, blank-location fallback, Vue text escaping, reference-only location handling, half-open event-time boundaries or unchanged active-role API guard.** This does not make the PBI accepted: deployment, the live/manual acceptance gates, D57 and D58 remain open.

**Other Claude observations evaluated:**

- Direct-table visibility mechanics are confirmed: the live equipment SELECT policy is `using (true)` for authenticated users, with table SELECT granted. After deployment the new field inherits this visibility. Whether a storage location must be private to staff is not specified by these ACs; this is an unresolved policy classification, not a confirmed new confidentiality defect. No role restriction was invented in this review.
- The manual availability form has no event ID and checks the remaining stock pool. Event-linked re-reservation passes its own reservation exclusion ID. Different numbers alone do not establish a defect or authorize an added self-exclusion feature.
- The existing evidence explicitly labels candidate-only rollback tests, stubbed rendering, undeployed migration and red/blocked full live runs. Pre-commit SHA plus uncommitted changes is expected for tests performed before the commit, not proof the evidence is false. Passing unit totals are valid for the exercised cases but do not prove the missing condition/duplicate cases. This review does not classify every unrelated live failure as caused or fixed by 23-R.
- Subtracting independent outage and reservation peaks matches the current documented formula; changing that algorithm is outside this review without a clarified requirement.

**Recommended correction scope:** prevent retired stock from being reported as requestable/usable; settle maintenance-status semantics; reject or aggregate duplicate item demand; add failing regression tests at the real SQL and API/form boundaries before changing implementation. Preserve story-24 overlap semantics and existing reservations. No product fix, deployment, fixture reset or backlog edit was performed by this review.
