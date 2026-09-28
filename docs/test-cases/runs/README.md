# Test execution log

**The record of each time the test cases in [`docs/test-cases/`](../README.md) were run against the real system, and what happened.** The case files say what to test. This folder records that it was tested, when, against which commit, and whether it passed.

The mocked unit suites (pytest, Vitest) keep their own record: every CI run on a pull request uploads a JUnit report per job (`backend-test-report`, `frontend-test-report`), kept for 90 days under the run's **Artifacts** in GitHub Actions.

One file per run, named `<date>-<time>-<method>-<commit>.md` (Singapore time), so runs from different branches never conflict and the folder lists them in order. Never edit a past run. A re-run is a new file.

## Three ways a case gets run

| Method | Covers | Run by | Log written by |
|---|---|---|---|
| **API + database script**: `backend/scripts/verify_live.py` | The cases whose steps are a request or a query: status codes, error text, role gates, token handling. It also runs the rolled-back scripts in `supabase/verification/`. | Anyone, or an agent | The script (`--record`) |
| **Playwright**: `frontend/e2e/*.e2e.js` | Browser behaviour with a checkable outcome: where a page redirects, what a field or banner says, what is stored, which requests are sent. | Anyone, or an agent | The reporter (`npm run test:e2e:record`) |
| **Manual browser check** | Everything that needs a person to judge it. See "What stays manual" below. | A developer | The developer, or an agent writing down the developer's verdicts |

To see whether a case is automated, search for its ID: `grep -rn "TC-AUTH-006" backend/scripts frontend/e2e`. Every automated check's name starts with the ID of the case it runs. A case with no match is manual.

Automated checks sign in as the seeded accounts, never change seeded or shared data, and log out every session they open. The SQL scripts roll back. Sign-up checks create throwaway accounts named `live-check+…@connectsphere.dev`, and every such account is deleted, with everything it owns, before and after each run. That keeps the live project usable as the demo database (`docs/CI.md` §4 item 3, [Team decision]). A check that would have to approve, reject or change a shared record stays manual until it can clean up after itself the same way.

## When to record a run

- **At story or fix verification** (Definition of Done Phase 2): both automated runs with recording on, plus a manual log for the story's cases that need human judgement.
- **At the end of each sprint**: both automated runs with recording on, as regression evidence for the sprint review. No full manual pass. Re-check a story by hand only if its area changed after it was verified.
- Not while you're writing code. Run the checks without recording as often as you like.

## Running the automated checks

Both need the backend running against the live project, and `supabase login` done once for the database scripts.

```bash
# backend/, virtualenv active
python scripts/verify_live.py --record                                  # backend on :8000
python scripts/verify_live.py --record --api http://localhost:8010/api/v1

# frontend/ (first time: npx playwright install chromium)
npm run test:e2e:record                                                 # app on :5173, backend on :8000
E2E_BASE_URL=http://localhost:5177 E2E_API_URL=http://localhost:8010/api/v1 npm run test:e2e:record
```

The frontend under test must point at the same backend (`VITE_API_BASE_URL`), since the specs sign in through it directly. Playwright keeps a screenshot and trace of each failure in `frontend/test-results/` (gitignored). Open one with `npx playwright show-trace <path>`.

### Supabase's sign-in rate limit

Supabase limits sign-ins per IP address; the limit is under **Authentication → Rate Limits** in the dashboard. Every sign-in these checks make goes through your backend, so it counts against your machine's IP, and only yours: teammates on other networks are unaffected, and nothing is locked or damaged. If the limit is reached, sign-ins from your machine, the browser included, are refused for a few minutes.

| Run | Sign-ins with correct credentials | Deliberately wrong |
|---|---|---|
| Script | 12 | 3 |
| Playwright | 21 | 1 |

Both suites back to back, several times within minutes on 2026-09-27 and 28, never hit the limit. Sign-up checks create accounts through the admin API, which this limit doesn't cover.

If a run does hit it, the first refused sign-in is recorded as a **Fail** that says "either sign-in is broken, or Supabase rate-limited this IP", and every later check that needs a sign-in is recorded as **Blocked** without trying, so the run doesn't extend the limit. The backend currently reports the refusal as a 401 wrong password (`docs/DEFECTS.md` D16), so the checks can't tell the two causes apart. Wait about five minutes, run once more, and treat it as a real failure if it repeats.

Don't run the suites in the few minutes before a demo or a teammate's login from the same network.

## What stays manual

A person has to look at:

- **Design and layout**: the Bauhaus look (`docs/PROJECT_OVERVIEW.md` §6), alignment, spacing, colour, and the phone-width (375px) layout.
- **Wording and clarity**: whether a message, empty state or confirmation reads well and says what the user needs.
- **Feel**: nothing flashes, jumps or briefly shows another role's content (TC-RBAC-003's "not even momentarily", TC-ROLE-014), and loading states make sense.
- **Things outside the app**: an `.ics` file opening in a real calendar app, and email.
- **Setup that changes shared state or the environment**: cases that create events, approve or reject, point the backend at a failing server (TC-AUTH-034, 035, 045), or change a Supabase setting (TC-AUTH-048).

## Manual run template

Copy into `<date>-<time>-manual-<commit>.md`:

```markdown
# Manual browser checks — 2026-10-01 14:30 SGT

| | |
|---|---|
| Story / fix | SCRUM-80 |
| Commit | `abc1234` on `feature/scrum-80-organiser-signup` |
| Environment | frontend http://localhost:5173, backend http://localhost:8000, live Supabase |
| Browser | Chrome 141, desktop and 375×812 |
| Run by | <name> |

| Case | What was checked | Result | Notes / defect |
|---|---|---|---|
| TC-AUTH-037 | Sign-up page layout and confirmation message | Pass | |
| TC-AUTH-046 | "Create an account" link on login | Fail | Link text wraps at 375px: D14 |
```

Result is **Pass**, **Fail** (with a defect ID from `docs/DEFECTS.md`, or what went wrong) or **Blocked** (and why). Automated run logs use the same three results.

## Before 2026-09-27

This log starts on 2026-09-27, when the tooling was added. Stories verified before then have no run files. Their real-system verification is recorded as prose in each story's "Verified" and "Not verified" notes in `docs/BUILD_LOG.md` §4, dated by the commit that added them. The first recorded runs cover those stories' automated cases as they stand now. Past runs are not backfilled: a log file here always records a run that actually happened, on the date it shows.
