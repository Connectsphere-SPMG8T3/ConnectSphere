// Profile editing (SCRUM-92) against the real backend and Supabase.
// The attendee account is a live-check throwaway deleted by global setup/teardown.
import { expect, skipIfSignInRefused, test } from "./support/fixtures.js";
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
