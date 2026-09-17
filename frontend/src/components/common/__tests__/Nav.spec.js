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
});
