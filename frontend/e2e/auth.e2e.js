// Sign-in, session and sign-out, against the real backend and Supabase.
// Cases: docs/test-cases/auth.md. Each title starts with the case it runs.
import {
  ACCOUNTS,
  API_URL,
  SEEDED_PASSWORD,
  STORAGE_KEY,
  apiLogin,
  expect,
  seedSession,
  signInThroughForm,
  skipIfSignInRefused,
  test,
} from "./support/fixtures.js";

// The coordinator, organiser, venue staff and tech support dashboards open straight onto their data, with no welcome heading.
const WELCOME_HEADING = new Set(["attendee"]);

test.describe("Login", () => {
  for (const [role, account] of Object.entries(ACCOUNTS)) {
    const caseId = role === "event_coordinator" ? "TC-AUTH-001" : "TC-AUTH-002";

    test(`${caseId} ${role} signs in and lands on their own dashboard`, async ({ page }) => {
      await page.goto("/login");
      await signInThroughForm(page, account.email);

      await expect(page).toHaveURL(account.dashboard);
      if (WELCOME_HEADING.has(role)) {
        await expect(page.getByRole("heading", { name: `Welcome, ${account.name}` })).toBeVisible();
      }
    });
  }

  test("TC-AUTH-005 signing in returns to the page that asked for it", async ({ page }) => {
    await page.goto("/profile/me");
    await expect(page).toHaveURL("/login?redirect=/profile/me");

    await signInThroughForm(page, ACCOUNTS.attendee.email);

    await expect(page).toHaveURL("/profile/me");
  });

  test("TC-AUTH-006 a wrong password shows the error and stays on login", async ({ page }) => {
    await page.goto("/login");
    await signInThroughForm(page, ACCOUNTS.event_coordinator.email, SEEDED_PASSWORD + "x");

    await expect(page.getByRole("alert")).toHaveText(/Invalid email or password\./i);
    await expect(page).toHaveURL("/login");
    expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY)).toBeNull();
  });

  test("TC-AUTH-008 empty fields are caught before any request", async ({ page }) => {
    const loginRequests = [];
    page.on("request", (request) => request.url().endsWith("/auth/login") && loginRequests.push(request));
    await page.goto("/login");

    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Email is required.")).toBeVisible();
    await expect(page.getByText("Password is required.")).toBeVisible();
    expect(loginRequests).toHaveLength(0);
  });

  test("TC-AUTH-009 an empty password alone is caught before any request", async ({ page }) => {
    const loginRequests = [];
    page.on("request", (request) => request.url().endsWith("/auth/login") && loginRequests.push(request));
    await page.goto("/login");

    await page.getByLabel("Email").fill(ACCOUNTS.attendee.email);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Password is required.")).toBeVisible();
    await expect(page.getByText("Email is required.")).toHaveCount(0);
    expect(loginRequests).toHaveLength(0);
  });

  test("TC-AUTH-036 pressing Enter in either field signs in", async ({ page }) => {
    skipIfSignInRefused();
    const { email, dashboard } = ACCOUNTS.event_organiser;

    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(SEEDED_PASSWORD);
    await page.getByLabel("Password").press("Enter");
    await expect(page).toHaveURL(dashboard);

    await page.getByRole("button", { name: "Logout" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(SEEDED_PASSWORD);
    await page.getByLabel("Email").press("Enter");
    await expect(page).toHaveURL(dashboard);
  });
});

test.describe("Session", () => {
  test("TC-AUTH-004 a session survives a page reload", async ({ page, sharedSessions }) => {
    await seedSession(page, await sharedSessions("event_organiser"));
    await page.goto(ACCOUNTS.event_organiser.dashboard);

    await page.reload();

    await expect(page).toHaveURL(ACCOUNTS.event_organiser.dashboard);
    await expect(page.getByRole("heading", { name: "Event status" })).toBeVisible();
  });

  test("TC-AUTH-030 an expired access token is renewed without signing in again", async ({ page }) => {
    const session = await apiLogin("attendee");
    await seedSession(page, { ...session, token: "not-a-valid-access-token" });
    const calls = [];
    page.on("response", (response) => {
      const path = new URL(response.url()).pathname;
      if (path.endsWith("/auth/me") || path.endsWith("/auth/refresh")) calls.push(`${path.split("/").pop()} ${response.status()}`);
    });

    await page.goto(ACCOUNTS.attendee.dashboard);

    await expect(page.getByRole("heading", { name: `Welcome, ${ACCOUNTS.attendee.name}` })).toBeVisible();
    expect(calls.slice(0, 3)).toEqual(["me 401", "refresh 200", "me 200"]);
    const stored = JSON.parse(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY));
    expect(stored.token).not.toBe("not-a-valid-access-token");
    expect(stored.refreshToken).not.toBe(session.refreshToken); // Supabase rotates it
  });

  test("TC-AUTH-031 a session that can't be renewed signs out with a message", async ({ page, sharedSessions }) => {
    const { profile } = await sharedSessions("attendee");
    await seedSession(page, { token: "invalid-access", refreshToken: "invalid-refresh", profile });

    await page.goto(ACCOUNTS.attendee.dashboard);

    await expect(page).toHaveURL(/\/login\?redirect=/);
    await expect(page.getByRole("alert")).toHaveText(/Your session has expired\. Please sign in again\./i);
    expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY)).toBeNull();
  });
});

test.describe("Logout", () => {
  test("TC-AUTH-026 logout clears the session and revokes it on the server", async ({ page }) => {
    const session = await apiLogin("venue_staff");
    await seedSession(page, session);
    await page.goto(ACCOUNTS.venue_staff.dashboard);

    await page.getByRole("button", { name: "Logout" }).click();

    await expect(page).toHaveURL(/\/login/);
    expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY)).toBeNull();
    await page.goto(ACCOUNTS.venue_staff.dashboard);
    await expect(page).toHaveURL(/\/login/);

    const refresh = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    expect(refresh.status).toBe(401);
  });
});
