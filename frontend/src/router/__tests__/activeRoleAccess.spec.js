import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/services/api";

// SCRUM-76: a page opens for the role the session is *acting as*, never for
// every role the account holds. The guard is UX (the API enforces the real
// permission), but a page that opened for a merely-held role would flash
// another role's screen and its failed requests.

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
}));

const STORAGE_KEY = "connectsphere.session";
const ROLES = [
  "event_organiser",
  "event_coordinator",
  "event_coordinator_lead",
  "venue_staff",
  "tech_support",
  "safety_officer",
  "attendee",
];
// Routes that need no allowedRoles: the public sign-in and sign-up pages
// (a signed-in session is sent to its dashboard) and the shared profile.
const OPEN_TO_ANY_ROLE = ["login", "signup", "profile"];

async function loadAppActingAs(activeRole, heldRoles = ROLES) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      token: "stored-access",
      refreshToken: "stored-refresh",
      profile: { id: "u1", role: activeRole, roles: heldRoles },
    }),
  );
  vi.resetModules();
  setActivePinia(createPinia());
  const { default: router } = await import("@/router");
  return router;
}

async function protectedRoutes() {
  const router = await loadAppActingAs("attendee");
  return router
    .getRoutes()
    .filter((route) => route.name && !OPEN_TO_ANY_ROLE.includes(route.name))
    .map((route) => ({
      name: route.name,
      allowedRoles: route.meta.allowedRoles,
      // Fill `:id`-style params so the path resolves.
      path: route.path.replace(/:[^/]+/g, "x"),
    }));
}

describe("route access follows the active role (SCRUM-76)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    // Server unreachable: the guard uses the stored profile as-is.
    authApi.me.mockRejectedValue(new TypeError("Failed to fetch"));
  });

  it("gives every route except the shared ones a role list", async () => {
    const routes = await protectedRoutes();

    const withoutRoles = routes.filter((route) => !route.allowedRoles?.length).map((route) => route.name);
    expect(withoutRoles).toEqual([]);
  });

  // Extended timeout: it re-imports the router once per role x held-role combination.
  it("opens each route only for the role the session is acting as, even when the account holds all of them", async () => {
    const routes = await protectedRoutes();

    for (const activeRole of ROLES) {
      const router = await loadAppActingAs(activeRole);
      for (const route of routes) {
        await router.push("/profile/me");
        await router.push(route.path);

        const opened = router.currentRoute.value.name === route.name;
        expect(opened, `${route.name} while acting as ${activeRole}`).toBe(route.allowedRoles.includes(activeRole));
      }
    }
  }, 20_000);

  it("sends a session acting as another role to its own dashboard", async () => {
    // An organiser who also holds the coordinator role, currently acting as the organiser.
    const router = await loadAppActingAs("event_organiser", ["event_organiser", "event_coordinator"]);

    await router.push("/dashboard/coordinator");

    expect(router.currentRoute.value.path).toBe("/dashboard/organiser");
  });

  // 12 AC12 / CR-103 AC5: each new staff role has a dashboard only it can open.
  it.each([
    ["event_coordinator_lead", "/dashboard/coordinator-lead"],
    ["safety_officer", "/dashboard/safety"],
  ])("gives %s a dashboard at %s that only that role opens", async (role, path) => {
    const routes = await protectedRoutes();
    const dashboard = routes.find((route) => route.path === path);

    expect(dashboard, `no route at ${path}`).toBeTruthy();
    expect(dashboard.allowedRoles).toEqual([role]);

    const router = await loadAppActingAs(role);
    await router.push(path);
    expect(router.currentRoute.value.path).toBe(path);
  });
});
