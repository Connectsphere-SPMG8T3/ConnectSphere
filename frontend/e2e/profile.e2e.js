// Profile editing (SCRUM-92) and profile details (SCRUM-50) against the real backend and Supabase.
// TC-AUTH-055 uses a live-check throwaway attendee deleted by global setup/teardown; the SCRUM-50
// cases only read the seeded accounts. Cases: docs/test-cases/auth.md.
import { ACCOUNTS, expect, seedSession, skipIfSignInRefused, test } from "./support/fixtures.js";
import { THROWAWAY_PASSWORD, throwawayEmail } from "./support/throwaway.js";

test("TC-AUTH-055 an attendee edits their own profile and sees the saved values", async ({ page }) => {
  skipIfSignInRefused();
  const email = throwawayEmail("055");
  await page.goto("/signup/attendee");
  await page.getByLabel("Full name").fill("Avery Attendee");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Create Account" }).click();
  await expect(page).toHaveURL("/login");

  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/dashboard/attendee");
  await page.goto("/profile/me");
  await expect(page.getByRole("heading", { name: "My profile" })).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit profile" })).toBeVisible();

  const updates = [];
  page.on(
    "request",
    (request) => request.method() === "PATCH" && request.url().endsWith("/auth/me") && updates.push(request),
  );
  await page.getByRole("button", { name: "Edit profile" }).click();
  await page.getByLabel("Full name").fill("   ");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Full name is required.")).toBeVisible();
  expect(updates).toHaveLength(0);

  await page.getByLabel("Full name").fill("Avery Updated");
  await page.getByLabel("Phone number").fill("+65 9000 0001");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "Avery Updated" })).toBeVisible();
  await expect(page.getByText("+65 90000001")).toBeVisible();
  expect(updates).toHaveLength(1);
  expect(updates[0].postDataJSON().phone_number).toBe("+6590000001");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Avery Updated" })).toBeVisible();
  await expect(page.getByText("+65 90000001")).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
});

// SCRUM-50 seed data (supabase/seed.sql): phone, department and organisation per account.
const STAFF = [
  { role: "event_coordinator", label: "Event Coordinator", department: "Event Planning" },
  { role: "event_coordinator_lead", label: "Event Coordinator Lead", department: "Event Planning" },
  { role: "venue_staff", label: "Venue Staff", department: "Venue Operations" },
  { role: "tech_support", label: "Technical Support", department: "Technical Services" },
  { role: "safety_officer", label: "Safety Officer", department: "Operational Safety" },
];

async function openProfileAs(page, sharedSessions, role) {
  const session = await sharedSessions(role);
  await seedSession(page, session);
  await page.goto("/profile/me");
  await expect(page.getByRole("heading", { name: "My profile" })).toBeVisible();
  return session.profile;
}

// Scoped to the page body: the top bar's role switcher also lists role names.
// The page shows a valid Singapore number as "+65 ########" (spaces and hyphens in the stored value
// ignored) and anything else as stored. Shared accounts can be edited, so expect whatever the API
// holds rather than the seeded value.
const shownPhone = (stored) => {
  const compact = stored.replace(/[\s-]/g, "");
  return /^\+65\d{8}$/.test(compact) ? `${compact.slice(0, 3)} ${compact.slice(3)}` : stored;
};

const detail = (page, label) => page.locator("main").getByText(label, { exact: true });
const roleBadge = (page) => page.locator("main span.bg-bauhaus-yellow");

test("TC-AUTH-057 the profile shows full name, email, phone number and current role", async ({
  page,
  sharedSessions,
}) => {
  const profile = await openProfileAs(page, sharedSessions, "event_coordinator");

  await expect(page.getByRole("heading", { name: ACCOUNTS.event_coordinator.name })).toBeVisible();
  await expect(roleBadge(page)).toHaveText("Event Coordinator");
  await expect(page.getByText(ACCOUNTS.event_coordinator.email)).toBeVisible();
  await expect(detail(page, shownPhone(profile.phone_number))).toBeVisible();
});

// One test per role: seedSession seeds a page once, so roles can't share a page.
for (const { role, label, department } of STAFF) {
  test(`TC-AUTH-058 ${label} sees their department and no organisation`, async ({ page, sharedSessions }) => {
    await openProfileAs(page, sharedSessions, role);

    await expect(roleBadge(page)).toHaveText(label);
    await expect(detail(page, "Department")).toBeVisible();
    await expect(detail(page, department)).toBeVisible();
    await expect(detail(page, "Organisation")).toHaveCount(0);
  });
}

test("TC-AUTH-059 an Event Organiser sees their organisation and no department", async ({ page, sharedSessions }) => {
  await openProfileAs(page, sharedSessions, "event_organiser");

  await expect(detail(page, "Organisation")).toBeVisible();
  await expect(detail(page, "Tan & Partners Events")).toBeVisible();
  await expect(detail(page, "Department")).toHaveCount(0);
});

test("TC-AUTH-060 an Attendee sees neither a department nor an organisation", async ({ page, sharedSessions }) => {
  const profile = await openProfileAs(page, sharedSessions, "attendee");

  await expect(page.getByRole("heading", { name: ACCOUNTS.attendee.name })).toBeVisible();
  await expect(page.getByText(ACCOUNTS.attendee.email)).toBeVisible();
  await expect(detail(page, shownPhone(profile.phone_number))).toBeVisible();
  await expect(detail(page, "Department")).toHaveCount(0);
  await expect(detail(page, "Organisation")).toHaveCount(0);
});
