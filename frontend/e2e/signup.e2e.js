// Organiser and Attendee sign-up (SCRUM-80/83), against the real backend and Supabase.
// Cases: docs/test-cases/auth.md, the SCRUM-80 and SCRUM-83 signup sections. Accounts made here are
// live-check+… throwaways, deleted by global setup/teardown (support/throwaway.js).
import { ACCOUNTS, expect, seedSession, skipIfSignInRefused, test } from "./support/fixtures.js";
import { THROWAWAY_PASSWORD, throwawayEmail } from "./support/throwaway.js";

const PASSWORD_RULE = "Password must be at least 8 characters and include at least one letter and one digit.";

async function fillSignup(page, { email, password = THROWAWAY_PASSWORD, fullName = "Olivia Organiser" }) {
  await page.getByLabel("Full name").fill(fullName);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByLabel("Organisation name").fill("SMU Events Club");
  await page.getByLabel("Phone number").fill("+65 9123 4567");
}

function trackSignupRequests(page) {
  const requests = [];
  page.on("request", (request) => request.url().endsWith("/auth/signup") && requests.push(request));
  return requests;
}

test("TC-AUTH-037 TC-AUTH-038 an organiser signs up, signs in and opens a new event request", async ({ page }) => {
  skipIfSignInRefused();
  const email = throwawayEmail("037");
  await page.goto("/login");
  await page.getByRole("main").getByRole("link", { name: "Create organiser account" }).click();
  await expect(page).toHaveURL("/signup/organiser");

  await fillSignup(page, { email });
  await page.getByRole("button", { name: "Create Account" }).click();

  await expect(page).toHaveURL("/login");
  await expect(page.getByText("Account created. Please sign in.")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue(email);
  expect(page.url()).not.toContain("live-check");

  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(ACCOUNTS.event_organiser.dashboard);

  await page.getByRole("button", { name: "New event request" }).first().click();
  await expect(page).toHaveURL("/events/new");
  await expect(page.getByRole("heading", { name: "Start an event" })).toBeVisible();
});

test("TC-AUTH-051 an attendee signs up without organiser fields and lands on the attendee dashboard", async ({ page }) => {
  skipIfSignInRefused();
  const email = throwawayEmail("051");
  await page.goto("/signup/attendee");
  await expect(page.getByRole("heading", { name: "Create an Attendee Account" })).toBeVisible();
  await expect(page.getByLabel("Account Type")).toHaveCount(0);
  await expect(page.getByLabel("Organisation name")).toHaveCount(0);
  await expect(page.getByLabel("Phone number")).toHaveCount(0);
  await page.getByLabel("Full name").fill("Avery Attendee");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);

  const [request] = await Promise.all([
    page.waitForRequest((item) => item.url().endsWith("/auth/signup")),
    page.getByRole("button", { name: "Create Account" }).click(),
  ]);
  expect(request.postDataJSON()).toEqual({
    role: "attendee",
    full_name: "Avery Attendee",
    email,
    password: THROWAWAY_PASSWORD,
  });

  await expect(page).toHaveURL("/login");
  await expect(page.getByText("Account created. Please sign in.")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue(email);
  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(ACCOUNTS.attendee.dashboard);
});

test("TC-AUTH-039 empty required fields are named before anything is sent", async ({ page }) => {
  const signups = trackSignupRequests(page);
  await page.goto("/signup/organiser");

  await page.getByLabel("Full name").fill("   ");
  await page.getByRole("button", { name: "Create Account" }).click();

  for (const message of [
    "Full name is required.",
    "Email is required.",
    "Password is required.",
    "Organisation name is required.",
  ]) {
    await expect(page.getByText(message)).toBeVisible();
  }
  await expect(page.getByLabel("Phone number")).not.toHaveAttribute("aria-invalid", "true");
  expect(signups).toHaveLength(0);
});

test("TC-AUTH-040 a malformed email is explained before anything is sent", async ({ page }) => {
  const signups = trackSignupRequests(page);
  await page.goto("/signup/organiser");
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
  await page.goto("/signup/organiser");
  await fillSignup(page, { email: throwawayEmail("041") });

  for (const bad of ["Abc" + "1234", "Pass" + "word", "1234" + "5678"]) {
    await page.getByLabel("Password").fill(bad);
    await page.getByRole("button", { name: "Create Account" }).click();
    await expect(page.getByText(PASSWORD_RULE), bad).toBeVisible();
  }
  expect(signups).toHaveLength(0);
});

test("TC-AUTH-042 an email that already has an account is refused under Email", async ({ page }) => {
  await page.goto("/signup/organiser");
  await fillSignup(page, { email: ACCOUNTS.event_organiser.email });

  await page.getByRole("button", { name: "Create Account" }).click();

  await expect(page.getByText("An account with this email already exists.")).toBeVisible();
  await expect(page).toHaveURL("/signup/organiser");
  await expect(page.getByLabel("Full name")).toHaveValue("Olivia Organiser");
  await expect(page.getByLabel("Organisation name")).toHaveValue("SMU Events Club");
});

test("TC-AUTH-046 the sign-up page is only for signed-out visitors", async ({ page, browser, sharedSessions }) => {
  await seedSession(page, await sharedSessions("attendee"));
  await page.goto("/signup/attendee");
  await expect(page).toHaveURL(ACCOUNTS.attendee.dashboard);

  const signedOut = await browser.newContext();
  try {
    const visitor = await signedOut.newPage();
    await visitor.goto("/login");
    await expect(visitor.getByText("New Event Organiser?")).toBeVisible();
    await expect(visitor.getByRole("main").getByRole("link", { name: "Create organiser account" })).toHaveAttribute(
      "href",
      "/signup/organiser",
    );
    await expect(visitor.getByRole("main").getByRole("link", { name: "Create attendee account" })).toHaveAttribute(
      "href",
      "/signup/attendee",
    );
    await visitor.getByRole("main").getByRole("link", { name: "Create attendee account" }).click();
    await expect(visitor).toHaveURL("/signup/attendee");
    await expect(visitor.getByRole("heading", { name: "Create an Attendee Account" })).toBeVisible();
  } finally {
    await signedOut.close();
  }
});

test("TC-AUTH-047 an email typed with spaces is sent trimmed and signs in", async ({ page }) => {
  skipIfSignInRefused();
  const email = throwawayEmail("047");
  await page.goto("/signup/organiser");
  await fillSignup(page, { email: `  ${email}  ` });

  const [request] = await Promise.all([
    page.waitForRequest((r) => r.url().endsWith("/auth/signup")),
    page.getByRole("button", { name: "Create Account" }).click(),
  ]);
  expect(request.postDataJSON().email).toBe(email);

  await expect(page).toHaveURL("/login");
  await expect(page.getByLabel("Email")).toHaveValue(email);
  await page.getByLabel("Password").fill(THROWAWAY_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(ACCOUNTS.event_organiser.dashboard);
});

test("TC-AUTH-052 role-specific signup pages fit a 375px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const viewportWidth = page.viewportSize().width;

  for (const [path, heading] of [
    ["/signup/organiser", "Create an Event Organiser Account"],
    ["/signup/attendee", "Create an Attendee Account"],
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    const rightmostContent = await page.locator("h1, h2, input, button").evaluateAll((nodes) =>
      Math.max(...nodes.map((node) => node.getBoundingClientRect().right)),
    );
    const wordmarkOverflows = await page.locator("h1").evaluate((heading) => heading.scrollWidth > heading.clientWidth);

    expect(rightmostContent, path).toBeLessThanOrEqual(viewportWidth);
    expect(wordmarkOverflows, path).toBe(false);
  }
});
