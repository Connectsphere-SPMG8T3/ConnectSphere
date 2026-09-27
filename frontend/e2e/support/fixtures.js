import { test as base, expect } from "@playwright/test";

// The backend the frontend under test talks to. It must match the frontend's
// VITE_API_BASE_URL, since the specs sign in through it directly.
export const API_URL = process.env.E2E_API_URL || "http://localhost:8000/api/v1";

export const SEEDED_PASSWORD = "Cs1234"; // supabase/seed.sql
export const STORAGE_KEY = "connectsphere.session"; // stores/auth.js

export const ACCOUNTS = {
  event_organiser: { email: "organiser@connectsphere.dev", name: "Olivia Tan", dashboard: "/dashboard/organiser" },
  event_coordinator: { email: "coordinator@connectsphere.dev", name: "Marcus Lim", dashboard: "/dashboard/coordinator" },
  venue_staff: { email: "venue.staff@connectsphere.dev", name: "Priya Nair", dashboard: "/dashboard/venue-staff" },
  tech_support: { email: "tech.support@connectsphere.dev", name: "Daniel Wong", dashboard: "/dashboard/tech-support" },
  attendee: { email: "attendee@connectsphere.dev", name: "Siti Rahman", dashboard: "/dashboard/attendee" },
};

export async function apiLogin(role) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: ACCOUNTS[role].email, password: SEEDED_PASSWORD }),
  });
  if (response.status === 429) throw new Error("Supabase rate-limited sign-in (429); wait a few minutes and re-run");
  if (!response.ok) throw new Error(`API login as ${role} failed: HTTP ${response.status}`);
  const body = await response.json();
  return { token: body.access_token, refreshToken: body.refresh_token, profile: body.profile };
}

async function apiLogout(token) {
  if (!token) return;
  await fetch(`${API_URL}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {});
}

// Puts a session into localStorage before the app's first script runs, the
// same shape stores/auth.js persists, so a spec starts already signed in.
export async function seedSession(page, session) {
  await page.addInitScript(
    ([key, value]) => {
      if (!window.sessionStorage.getItem("e2e.seeded")) {
        window.localStorage.setItem(key, value);
        window.sessionStorage.setItem("e2e.seeded", "1");
      }
    },
    [STORAGE_KEY, JSON.stringify(session)],
  );
}

export async function signInThroughForm(page, email, password = SEEDED_PASSWORD) {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign In" }).click();
}

export const test = base.extend({
  // One session per role for the whole run, for specs that only read. A spec
  // that signs out, refreshes or switches role opens its own with apiLogin.
  sharedSessions: [
    async ({}, use) => {
      const cache = {};
      const get = async (role) => (cache[role] ??= await apiLogin(role));
      get.isShared = (token) => Object.values(cache).some((session) => session.token === token);
      await use(get);
      for (const session of Object.values(cache)) await apiLogout(session.token);
    },
    { scope: "worker" },
  ],

  // Revoke whatever session a spec's page ends with, so a run leaves no
  // signed-in sessions behind on the shared project. Shared sessions are
  // left for the worker teardown above.
  page: async ({ page, sharedSessions }, use) => {
    await use(page);
    const stored = await page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY).catch(() => null);
    const token = stored ? JSON.parse(stored).token : null;
    if (token && !sharedSessions.isShared(token)) await apiLogout(token);
  },
});

export { expect };
