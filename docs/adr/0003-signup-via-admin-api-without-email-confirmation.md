# ADR-0003 — Create sign-up accounts through the admin API, already confirmed

| | |
|---|---|
| **Status** | Proposed — for team review on the SCRUM-80 pull request |
| **Decided** | 2026-09-27, while designing SCRUM-80 (Event organiser signup) |
| **Deciders** | Ng Xuan Wei (SCRUM-80 assignee) |
| **Applies to** | SCRUM-80, and SCRUM-83 (Attendee signup), which reuses the same endpoint |

## Context

Sign-up (see `CONTEXT.md`) is the one auth flow that creates an `auth.users` row. Two facts about the live Supabase project shaped how it can be built:

1. **Email confirmation is on.** `GET /auth/v1/settings` reports `mailer_autoconfirm: false`. A user created through GoTrue's `sign_up` cannot log in until they click the emailed link, and that email comes from Supabase's built-in sender, which is limited to a few messages an hour per project.
2. **With confirmation on, GoTrue hides duplicate emails.** `sign_up` with an already-registered address returns a fake, unconfirmed user instead of an error, to stop anyone finding out which emails have accounts. The backend cannot tell a duplicate from a genuine new sign-up.

SCRUM-80's acceptance criteria require the opposite of both: *"The system rejects registration if the email address is already registered"* (AC 3), and *"The user can log in using their newly registered credentials"* (AC 6), which has to work live in a sprint review demo.

## Decision

**`POST /auth/signup` creates the account with the secret-key admin client's `auth.admin.create_user(..., email_confirm=True)`.** Accounts are confirmed as soon as they are created; nobody verifies that the sign-up email belongs to the person.

- The request carries `role`, `full_name`, `organisation_name` and `phone_number` as `user_metadata`. `handle_new_user()` still creates the `profiles` and `user_roles` rows, and it still accepts only `event_organiser` or `attendee` from metadata (AUTH-R3, PROJECT_REVIEW D2). The backend also validates `role` before calling Supabase, so a staff role is rejected with a 422, not quietly saved as `attendee`.
- A duplicate email comes back from the admin API as an `AuthApiError` with code `email_exists`. The service maps that **code** (not the message text) to a 409.
- `AuthRetryableError` is caught first and mapped to 503, as for every other auth call.
- The endpoint returns the new profile and never opens a session. The SPA sends the user to `/login`.
- The project-level `mailer_autoconfirm` setting is **left unchanged**. Nothing else depends on it today, and leaving it off means the publishable key in the browser still cannot create usable accounts by calling GoTrue directly without email confirmation.

## Considered options

| Option | Why not |
|---|---|
| **Admin API, confirmed on creation** *(chosen)* | Meets AC 3 and AC 6 exactly, no dependency on email sending, and fits the "the API is the policy-enforcement point" rule. |
| **GoTrue `sign_up` from the backend, confirmation on** | AC 3 cannot be met: duplicates are indistinguishable from new users. AC 6 fails in a demo unless the inbox is to hand, and the email rate limit makes repeated testing unreliable. |
| **Turn on `mailer_autoconfirm` and use `sign_up`** | Fixes AC 6 and makes GoTrue return a real duplicate error. But it's a dashboard setting outside version control, and it also lets anyone holding the publishable key create confirmed accounts straight from the browser, around the backend. |
| **SPA calls `supabase.auth.signUp` directly** | Moves an auth flow out of the API, unlike login, refresh and logout. Also has every problem of the `sign_up` rows above. |

## Consequences

**Positive**

- AC 3 and AC 6 can be demonstrated and tested offline (the admin client is already a mocked seam in `tests/`).
- Sign-up goes through the same backend path as every other auth flow.

**Negative**

- **Nobody verifies email addresses.** Anyone can sign up with an address they don't own. With no emails sent yet this changes little, but it matters once notifications go by email.
- **Emails reveal whether an account exists.** A 409 tells the caller the address is registered. That's what AC 3 asks for, but it's the enumeration GoTrue was designed to prevent.
- **No rate limit or captcha.** The admin API skips GoTrue's sign-up rate limiting, so a script can create confirmed accounts in bulk. Recorded as a known risk in `docs/PROJECT_REVIEW.md`, not addressed in SCRUM-80.
- **Reversing this later affects existing accounts.** Switching to verified sign-up leaves every account created before then confirmed without ever having been verified.

## Revisit when

- The customer asks for verified emails, or email notifications become a real feature, or
- abusive sign-ups appear. The first fix is per-IP rate limiting on `POST /auth/signup`, and after that a switch to GoTrue `sign_up` with confirmation on (rewriting AC 3 to "no second account is created").

## Links

- Jira SCRUM-80 (Event organiser signup), SCRUM-83 (Attendee signup)
- `docs/REQUIREMENTS.md` ACC-R2, ACC-R3, AUTH-R3; `docs/PROJECT_REVIEW.md` D2
- `supabase/migrations/20260919000000_profiles_role_requires_user_roles_membership.sql` — the current `handle_new_user()`
- [ADR-0002](0002-supabase-client-only-data-access.md) — the client factories this uses (the admin client)
