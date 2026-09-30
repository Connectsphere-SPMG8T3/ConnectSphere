import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/services/api";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn(), setActiveRole: vi.fn() },
}));

async function mountNav(profile) {
  // A fresh router (and its beforeEach guard) and a fresh auth store module
  // per test — sharing the router singleton across tests lets one test's
  // in-flight navigation (dynamic route imports are genuinely async) leak
  // into the next test's assertions.
  vi.resetModules();
  const pinia = createPinia();
  setActivePinia(pinia);
  const { useAuthStore } = await import("@/stores/auth");
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = profile;
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/dashboard/coordinator");
  const { default: Nav } = await import("@/components/common/Nav.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(Nav).use(pinia).use(router);
  app.mount(el);
  await nextTick();
  await nextTick();
  return { el, router, authStore };
}

async function settle() {
  await Promise.resolve();
  await nextTick();
  await nextTick();
}

describe("Nav role switcher (SCRUM-74/75)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("shows no role switcher for a single-role profile", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator"],
    });

    expect(el.querySelector('[data-testid="role-switcher"]')).toBeNull();
  });

  it("shows organiser overview and events views in the side navigation", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "event_organiser",
      roles: ["event_organiser"],
    });

    expect(el.querySelector('a[href="/dashboard/organiser?tab=overview"]')).toBeTruthy();
    expect(el.querySelector('a[href="/dashboard/organiser?tab=events"]')).toBeTruthy();
    expect(el.textContent).toContain("Overview");
    expect(el.textContent).toContain("Events");
  });

  it("shows coordinator overview and events views in place of Dashboard", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator"],
    });

    expect(el.querySelector('a[href="/dashboard/coordinator?tab=overview"]')).toBeTruthy();
    expect(el.querySelector('a[href="/dashboard/coordinator?tab=events"]')).toBeTruthy();
    expect(el.querySelector('a[aria-label="Dashboard"]')).toBeNull();
    // Coordinators keep their venue search.
    expect(el.querySelector('a[href="/venues"]')).toBeTruthy();
  });

  it("shows the tech support availability and inventory views in the side navigation", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "tech_support",
      roles: ["tech_support"],
    });

    const inventory = el.querySelector('a[href="/dashboard/tech-support?tab=inventory"]');
    const availability = el.querySelector('a[href="/dashboard/tech-support?tab=availability"]');
    expect(inventory).toBeTruthy();
    expect(availability).toBeTruthy();
    // Inventory is the main view, so it comes first.
    expect(inventory.compareDocumentPosition(availability) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(el.textContent).toContain("Availability");
    expect(el.textContent).toContain("Inventory");
  });

  it("does not show the tech support views to another role", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "tech_support"],
    });

    expect(el.querySelector('a[href^="/dashboard/tech-support"]')).toBeNull();
  });

  it("lists every held role with a human-readable label for a multi-role profile", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "venue_staff"],
    });

    const select = el.querySelector('[data-testid="role-switcher"] select');
    expect(select).toBeTruthy();
    const optionLabels = [...select.querySelectorAll("option")].map((o) => o.textContent.trim());
    expect(optionLabels).toContain("Event Coordinator");
    expect(optionLabels).toContain("Venue Staff");
  });

  it("switches role and navigates to that role's dashboard on selection", async () => {
    const updatedProfile = {
      id: "u1",
      role: "venue_staff",
      roles: ["event_coordinator", "venue_staff"],
    };
    authApi.setActiveRole.mockResolvedValue(updatedProfile);
    const { el, router } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "venue_staff"],
    });

    const select = el.querySelector('[data-testid="role-switcher"] select');
    select.value = "venue_staff";
    select.dispatchEvent(new Event("change"));
    await settle();

    expect(authApi.setActiveRole).toHaveBeenCalledWith("access", "venue_staff");
    // The target route's component is a dynamic import, which vue-router
    // waits on before resolving navigation, so this can take a bit the first
    // time it's loaded in the test process.
    await vi.waitFor(
      () => {
        expect(router.currentRoute.value.path).toBe("/dashboard/venue-staff");
      },
      { timeout: 2000 },
    );
  });

  it("does not remount the select on a successful switch (no revert-then-jump flicker)", async () => {
    const updatedProfile = {
      id: "u1",
      role: "venue_staff",
      roles: ["event_coordinator", "venue_staff"],
    };
    authApi.setActiveRole.mockResolvedValue(updatedProfile);
    const { el, router } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "venue_staff"],
    });

    const selectBefore = el.querySelector('[data-testid="role-switcher"] select');
    selectBefore.value = "venue_staff";
    selectBefore.dispatchEvent(new Event("change"));
    await settle();
    await vi.waitFor(
      () => {
        expect(router.currentRoute.value.path).toBe("/dashboard/venue-staff");
      },
      { timeout: 2000 },
    );

    // A remount (the fix for the rejected/no-op case) would replace this
    // element; a successful switch should update it in place via Vue's
    // normal reactivity instead, since authStore.role actually changed.
    const selectAfter = el.querySelector('[data-testid="role-switcher"] select');
    expect(selectAfter).toBe(selectBefore);
  });

  it("ignores selecting the empty placeholder option, without calling the API", async () => {
    const { el, router } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "venue_staff"],
    });

    const select = el.querySelector('[data-testid="role-switcher"] select');
    select.value = "";
    select.dispatchEvent(new Event("change"));
    await settle();

    expect(authApi.setActiveRole).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe("/dashboard/coordinator");
  });

  it("ignores re-selecting the already-active role, without calling the API", async () => {
    const { el } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "venue_staff"],
    });

    const select = el.querySelector('[data-testid="role-switcher"] select');
    select.value = "event_coordinator";
    select.dispatchEvent(new Event("change"));
    await settle();

    expect(authApi.setActiveRole).not.toHaveBeenCalled();
  });

  it("does not crash and leaves the role unchanged when the switch is rejected", async () => {
    authApi.setActiveRole.mockRejectedValue(new Error("You do not hold the 'venue_staff' role."));
    const { el } = await mountNav({
      id: "u1",
      role: "event_coordinator",
      roles: ["event_coordinator", "venue_staff"],
    });

    const select = el.querySelector('[data-testid="role-switcher"] select');
    select.value = "venue_staff";
    select.dispatchEvent(new Event("change"));
    await settle();

    // The remount (see Nav.vue) only happens once the rejected promise is
    // caught, which needs more ticks than a fixed settle() budgets for — so
    // the element to check is whichever <select> is in the DOM now, not the
    // one captured before the interaction.
    await vi.waitFor(() => {
      const currentSelect = el.querySelector('[data-testid="role-switcher"] select');
      expect(currentSelect.value).toBe("event_coordinator");
    });
  });
});
