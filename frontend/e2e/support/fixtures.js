import { existsSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { test as base, expect } from "@playwright/test";

import { THROWAWAY_PASSWORD } from "./throwaway.js";

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

// Seeded W7 staff (CR-101). Kept out of ACCOUNTS, whose loops assert a denial for every role in it.
export const LEAD_ACCOUNT = {
  email: "coordinator.lead@connectsphere.dev",
  name: "Grace Chua",
  dashboard: "/dashboard/coordinator-lead",
};
const W7_ACCOUNTS = { event_coordinator_lead: LEAD_ACCOUNT,
  safety_officer: { email: "safety.officer@connectsphere.dev", name: "Officer", dashboard: "/dashboard/safety" } };

// Supabase limits sign-ins per IP, and the backend currently reports that
// refusal as a 401 "Invalid email or password." (DEFECTS D16), so a
// refused sign-in with known-good credentials can't be told apart from broken
// sign-in. After the first one, every step that would sign in skips its spec
// instead, which the run log records as Blocked: each further attempt would
// only extend the limit.
const GOOD_PASSWORDS = new Set([SEEDED_PASSWORD, THROWAWAY_PASSWORD]);
export const SIGN_IN_REFUSED =
  "Correct credentials were refused. Either sign-in is broken, or Supabase rate-limited this IP, " +
  "which the backend reports as a 401 (DEFECTS D16). Wait about 5 minutes and re-run.";
const BLOCKED = "Blocked: an earlier sign-in was refused, so no further sign-ins were attempted.";

// A file, not a variable: Playwright restarts the worker process after a
// failed spec, which would reset one. Global setup clears it for each run.
export const SIGN_IN_REFUSED_FLAG = path.join(os.tmpdir(), "connectsphere-e2e-sign-in-refused");
const markSignInRefused = () => writeFileSync(SIGN_IN_REFUSED_FLAG, new Date().toISOString());

// Call before any step that signs in, including a deliberately wrong password,
// whose rate-limited 401 would otherwise pass for a correct refusal.
export function skipIfSignInRefused() {
  if (existsSync(SIGN_IN_REFUSED_FLAG)) test.info().skip(true, BLOCKED);
}

export async function apiLogin(role) {
  skipIfSignInRefused();
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: (ACCOUNTS[role] ?? W7_ACCOUNTS[role]).email, password: SEEDED_PASSWORD }),
  });
  if (response.status === 401 || response.status === 429) {
    markSignInRefused();
    throw new Error(`${SIGN_IN_REFUSED} (HTTP ${response.status} signing in as ${role})`);
  }
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
  skipIfSignInRefused();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
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
  //
  // It also watches the page's own sign-ins: a refused one with known-good
  // credentials sets the flag above and is noted on the failing spec.
  page: async ({ page, sharedSessions }, use, testInfo) => {
    page.on("response", (response) => {
      if (!response.url().endsWith("/auth/login") || ![401, 429].includes(response.status())) return;
      const password = response.request().postDataJSON()?.password;
      if (GOOD_PASSWORDS.has(password)) {
        markSignInRefused();
        testInfo.annotations.push({ type: "sign-in refused", description: SIGN_IN_REFUSED });
      }
    });
    await use(page);
    const stored = await page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY).catch(() => null);
    const token = stored ? JSON.parse(stored).token : null;
    if (token && !sharedSessions.isShared(token)) await apiLogout(token);
  },
});

export { expect };
