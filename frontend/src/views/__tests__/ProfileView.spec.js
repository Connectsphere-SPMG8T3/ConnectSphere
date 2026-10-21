import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn(), setActiveRole: vi.fn() },
}));

async function mountProfileView(profile) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = profile;
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/profile/me");
  const { default: ProfileView } = await import("@/views/ProfileView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(ProfileView).use(pinia).use(router);
  app.mount(el);
  await nextTick();
  await nextTick();
  return { el };
}

describe("ProfileView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("does not show an all-roles list for a single-role account", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
    });

    expect(el.textContent).not.toContain("All roles");
  });

  it("lists every held role with human-readable labels for a multi-role account", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Marcus Lim",
      email: "coordinator@connectsphere.dev",
      role: "venue_staff",
      roles: ["event_coordinator", "venue_staff"],
    });

    expect(el.textContent).toContain("All roles");
    expect(el.textContent).toContain("Event Coordinator");
    expect(el.textContent).toContain("Venue Staff");
  });
});
