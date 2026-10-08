# Interrupted API/database verification — SCRUM-82

Run by Codex against this branch on http://127.0.0.1:8012/api/v1, 2026-10-08. The process was interrupted before automatic recording completed. This preserves its partial evidence; it does not claim a completed regression run.

The API and browser suites were initially run concurrently. Their shared throwaway cleanup collided; the browser run also used an origin not allowed by the backend CORS setting. The server was restarted with the correct existing CORS environment setting, then suites were scheduled serially. No application code was changed for either setup issue.

- PASS  TC-SAFE-001                  Only an active coordinator can send for safety check
- PASS  TC-SAFE-002                  An unapproved booking blocks send without changing data
- PASS  TC-SAFE-003                  The coordinator read carries the same missing booking reason
- PASS  TC-AUTH-001                  Coordinator login returns tokens and the coordinator profile
- PASS  TC-AUTH-002                  Every other seeded role logs in with its own role
- PASS  TC-AUTH-003                  Login response carries the full profile
- PASS  TC-AUTH-006                  Wrong password is rejected with the generic message
- PASS  TC-AUTH-007                  Unregistered email gets the same message as a wrong password
- PASS  TC-AUTH-010                  Malformed email is rejected by schema validation
- PASS  TC-AUTH-011                  Reserved-TLD email is rejected by schema validation
- PASS  TC-AUTH-012                  Email padded with spaces still logs in
- PASS  TC-AUTH-013                  Email in a different case still logs in
- PASS  TC-AUTH-014                  SQL-injection password is an ordinary wrong password
- PASS  TC-AUTH-020                  /auth/me without a token is 401 with WWW-Authenticate
- PASS  TC-AUTH-021                  /auth/me with a malformed token is 401
- PASS  TC-AUTH-022                  /auth/me with a token signed by the wrong key is 401
- PASS  TC-AUTH-019                  /auth/me returns the caller's own profile
- PASS  TC-AUTH-049                  Parallel requests after the backend sits idle all succeed (D18)
- PASS  TC-AUTH-028                  Logout without a token is 401
- PASS  TC-AUTH-029                  Logging out one user leaves another user's session working
- PASS  TC-AUTH-032                  Refresh rejects an unknown token (401) and an empty one (422)
- PASS  TC-RBAC-006                  A venue-staff-only endpoint refuses an attendee
- PASS  TC-RBAC-007                  The same endpoint opens for venue staff
- PASS  TC-ROLE-006                  Switching to a role the account doesn't hold is 403
- PASS  TC-ROLE-007                  Switching roles without a token is 401
- PASS  TC-ROLE-008                  Login and /auth/me both list every role the account holds
- PASS  TC-ROLE-017                  A held but inactive role doesn't open its endpoint
- PASS  TC-ROLE-018                  The endpoint opens after switching role and closes after switching back
- PASS  TC-DASH-013                  Coordinator dashboard returns only the caller's active events
- PASS  TC-DASH-014                  Every event under review is one action item; a returned one is none
- PASS  TC-DASH-015                  A coordinator's dashboard says nothing about unassigned events
- PASS  TC-DASH-016                  An organiser can't read the coordinator dashboard
- PASS  TC-DASH-017                  The coordinator dashboard closes while acting as venue staff and reopens after
- PASS  TC-DASH-018                  The coordinator dashboard without a token is 401
- PASS  TC-CMT-009                   The organiser and the assigned coordinator both read the event's comment thread
- PASS  TC-CMT-008                   Venue staff, tech support and attendees can neither read nor post comments
- PASS  TC-BOOK-001                  Requesting a free venue holds it for the event's period and notifies venue staff
- PASS  TC-BOOK-002                  An overlapping request is refused; a back-to-back one is accepted
- PASS  TC-BOOK-003                  A request overlapping a venue block is refused
- PASS  TC-BOOK-004                  An event that already holds a venue can't request another
- PASS  TC-BOOK-005                  A returned or under-review event can't request a venue
- PASS  TC-BOOK-006                  Only the event's assigned coordinator, acting as coordinator, can request
- PASS  TC-BOOK-007                  Two simultaneous overlapping requests leave exactly one hold
- PASS  TC-EQR-001                   Coordinators and tech support read the equipment catalogue; organisers can't
- PASS  TC-EQR-002                   A submission on a planning event is saved pending, above inventory, and visible to both sides
- PASS  TC-EQR-004                   Quantities that aren't whole numbers of at least 1, and empty submissions, are refused
- PASS  TC-EQR-008                   An event that isn't in planning refuses an equipment request

All remaining cases and database scripts were not verified by this interrupted run. The subsequent recorded run is the regression evidence.
