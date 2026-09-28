// Organiser sign-up (SCRUM-80), against the real backend and Supabase.
// Cases: docs/test-cases/auth.md, "Sign-up — SCRUM-80". Accounts made here are
// live-check+… throwaways, deleted by global setup/teardown (support/throwaway.js).
import { ACCOUNTS, expect, seedSession, test } from "./support/fixtures.js";
import { THROWAWAY_PASSWORD, throwawayEmail } from "./support/throwaway.js";

const PASSWORD_RULE = "Password must be at least 8 characters and include at least one letter and one digit.";

async function fillSignup(page, { email, password = THROWAWAY_PASSWORD, fullName = "Olivia Organiser" }) {
  await page.getByLabel("Full Name").fill(fullName);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByLabel("Organisation Name").fill("SMU Events Club");
  await page.getByLabel("Phone Number").fill("+65 9123 4567");
}

function trackSignupRequests(page) {
  const requests = [];
  page.on("request", (request) => request.url().endsWith("/auth/signup") && requests.push(request));
  return requests;
}

test("TC-AUTH-037 TC-AUTH-038 an organiser signs up, signs in and opens a new event request", async ({ page }) => {
  const email = throwawayEmail("037");
  await page.goto("/login");
  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page).toHaveURL("/signup");

  await fillSignup(page, { email });
  await page.getByRole("button", { name: "Create Account" }).click();

  await expect(page).toHaveURL("/login");
  await expect(page.getByText("Account created. Please sign in.")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue(email);
  expect(page.url()).not.toContain("live-check");

  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL(ACCOUNTS.event_organiser.dashboard);

  await page.getByRole("button", { name: "New event request" }).first().click();
  await expect(page).toHaveURL("/events/new");
  await expect(page.getByRole("heading", { name: "Start an event" })).toBeVisible();
});

test("TC-AUTH-039 empty required fields are named before anything is sent", async ({ page }) => {
  const signups = trackSignupRequests(page);
  await page.goto("/signup");

  await page.getByLabel("Full Name").fill("   ");
  await page.getByRole("button", { name: "Create Account" }).click();

  for (const message of [
    "Full name is required.",
    "Email is required.",
    "Password is required.",
    "Organisation name is required.",
  ]) {
    await expect(page.getByText(message)).toBeVisible();
  }
  await expect(page.getByLabel("Phone Number")).not.toHaveAttribute("aria-invalid", "true");
  expect(signups).toHaveLength(0);
});

test("TC-AUTH-040 a malformed email is explained before anything is sent", async ({ page }) => {
  const signups = trackSignupRequests(page);
  await page.goto("/signup");
  await fillSignup(page, { email: throwawayEmail("040") });

  for (const bad of ["not-an-email", "olivia@", "@connectsphere.dev"]) {
    await page.getByLabel("Email").fill(bad);
    await page.getByRole("button", { name: "Create Account" }).click();
    await expect(page.getByText("Enter a valid email address."), bad).toBeVisible();
  }
  expect(signups).toHaveLength(0);
});

test("TC-AUTH-041 a password that breaks the rule is explained before anything is sent", async ({ page }) => {
  const signups = trackSignupRequests(page);
  await page.goto("/signup");
  await fillSignup(page, { email: throwawayEmail("041") });

  for (const bad of ["Abc" + "1234", "Pass" + "word", "1234" + "5678"]) {
    await page.getByLabel("Password").fill(bad);
    await page.getByRole("button", { name: "Create Account" }).click();
    await expect(page.getByText(PASSWORD_RULE), bad).toBeVisible();
  }
  expect(signups).toHaveLength(0);
});

test("TC-AUTH-042 an email that already has an account is refused under Email", async ({ page }) => {
  await page.goto("/signup");
  await fillSignup(page, { email: ACCOUNTS.event_organiser.email });

  await page.getByRole("button", { name: "Create Account" }).click();

  await expect(page.getByText("An account with this email already exists.")).toBeVisible();
  await expect(page).toHaveURL("/signup");
  await expect(page.getByLabel("Full Name")).toHaveValue("Olivia Organiser");
  await expect(page.getByLabel("Organisation Name")).toHaveValue("SMU Events Club");
});

test("TC-AUTH-046 the sign-up page is only for signed-out visitors", async ({ page, browser, sharedSessions }) => {
  await seedSession(page, await sharedSessions("attendee"));
  await page.goto("/signup");
  await expect(page).toHaveURL(ACCOUNTS.attendee.dashboard);

  const signedOut = await browser.newContext();
  try {
    const visitor = await signedOut.newPage();
    await visitor.goto("/login");
    await expect(visitor.getByText("New Event Organiser?")).toBeVisible();
    await visitor.getByRole("link", { name: "Create an account" }).click();
    await expect(visitor).toHaveURL("/signup");
  } finally {
    await signedOut.close();
  }
});

test("TC-AUTH-047 an email typed with spaces is sent trimmed and signs in", async ({ page }) => {
  const email = throwawayEmail("047");
  await page.goto("/signup");
  await fillSignup(page, { email: `  ${email}  ` });

  const [request] = await Promise.all([
    page.waitForRequest((r) => r.url().endsWith("/auth/signup")),
    page.getByRole("button", { name: "Create Account" }).click(),
  ]);
  expect(request.postDataJSON().email).toBe(email);

  await expect(page).toHaveURL("/login");
  await expect(page.getByLabel("Email")).toHaveValue(email);
  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL(ACCOUNTS.event_organiser.dashboard);
});
