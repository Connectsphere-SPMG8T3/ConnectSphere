# 23-R review fixes implementation plan

Goal: correct D57/D58 before manual acceptance, then prepare isolated runtime testing.
Architecture: retain the shared SQL availability RPC and existing request validation conventions. No new library, shared migration deployment or stock mutation.

## Design and scope
Retired catalogue stock has zero free units. Preserve total/outage/reserved counters, event-only bounds and existing reservations. Maintenance remains quantity-based through timed outages. Duplicate IDs are rejected consistently with equipment request submissions; the form explains that quantities must be combined. Aggregation was considered but would change the response-row contract unnecessarily. User authorized these fixes and isolated testing with “ok fix it then”.

## Task 1: correct availability input and catalogue status
- [x] RED: extend real-SQL verification with a retired item (zero free), restoration to active and unchanged counters; run against existing RPC inside rollback and observe failure.
- [x] RED: HTTP test sends duplicate IDs with quantities 5+5; expect 422. Vue test adds a duplicate, submits and sees combine-quantities guidance without a request; correction to a distinct item permits submission.
- [x] GREEN: add a generated migration replacing public.equipment_availability(p_equipment_ids uuid[], p_start_at timestamptz, p_end_at timestamptz, p_exclude_reservation_id uuid default null). Return shape stays (equipment_id,total_quantity,outage_quantity,reserved_quantity,free_quantity); only retired free_quantity changes to zero.
- [x] GREEN: EquipmentAvailabilityRequest rejects repeated UUIDs. TechSupportDashboard.validateForm() rejects repeated selections. Existing unique requests and active-role guards remain covered.
- [x] Verify: full pytest --cov, npm run test:coverage, npm run build; rollback candidate migration plus SQL checks. Record RED/GREEN and remaining live gates; update requirements, map, build log, defects and case descriptions.
- [x] Independent Claude read-only review, then commit named files only.

## Task 2: isolated manual-test environment
- [x] Inspect local native/containers and existing Supabase development branches. Never seed/reset shared data.
- [ ] If feasible, provision isolated stack, apply migrations and isolated test fixtures, point branch servers at it and record API/browser checks.
- [ ] A paid hosted branch requires organization and explicit quoted-cost approval. If unavailable, record the exact blocker; do not claim runtime acceptance.

Review focus: retired with confirmed reservations must retain reservations; maintenance with partial outages; adjacent event bounds; UUID-equivalent duplicate inputs; fixing a duplicate must unblock submission.

## Execution notes
- D58 RED: two API cases accepted duplicates (200 rather than 422); Vue duplicate case sent a request and lacked guidance. GREEN: API cases and actual Vue interaction/recovery passed.
- D57 RED: rolled-back SQL raised “retired stock must have 0 free units, got 5”. GREEN: candidate SQL plus rollback checks passed, including held counters, exclude-self, actual time-change recheck to Re-review and re-reserve refusal.
- Claude read-only review session d8dfb35c-4cb8-4bc6-93a7-4187a6345a15 confirmed an inventory mismatch. Added inventory/repository regressions: 3 failed before, 39 equipment tests passed after. Inventory now zeros retired free stock in both modes while preserving counters.
- Review ruling: retirement is enforced in the shared RPC for reserve/recheck too. Existing recheck behavior marks insufficient held lines Re-review and preserves the hold; tested and documented, no notification redesign.
- Review cleanup concern: TC-EQR-039 retires only its own throwaway item, deleted in finally. PROJECTOR_ID is only read for the 422 duplicate check. No shared stock changed.
- Worktree moved using git worktree move to /home/jclim/projects/ConnectSphere-pbi-23-r, per user request. Git validates the moved checkout; desktop reattachment reports it is no longer a managed worktree.
- Isolated environment gate: no Docker/Podman/nerdctl or native stack command in installed CLI 2.121.0; no existing Supabase development branches. Paid branch creation has not been authorized. No shared migration deployed.

Final verification: backend 1887 passed (97.44%); frontend 1503 passed (97.44%, one worker); build passed; changed executable lines covered. Initial frontend timeout/navigation failures and one-worker diagnostic failure are retained in the evidence, not claimed as fixed product defects. Isolated runtime setup remains blocked, so the story is not accepted.
