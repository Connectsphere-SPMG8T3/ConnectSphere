import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/services/api";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
}));

const STORAGE_KEY = "connectsphere.session";

async function loadAppWithStoredRole(role) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ token: "stored-access", refreshToken: "stored-refresh", profile: { id: "u1", role } }),
  );
  // The store reads localStorage when its module loads, so load fresh copies.
  vi.resetModules();
  setActivePinia(createPinia());
  const { default: router } = await import("@/router");
  const { useAuthStore } = await import("@/stores/auth");
  return { router, authStore: useAuthStore() };
}

describe("router guard with a signed-in role that has no dashboard", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    // Server unreachable: the guard cannot re-verify, so the stored profile is used as-is.
    authApi.me.mockRejectedValue(new TypeError("Failed to fetch"));
  });

  it.each([undefined, "platform_admin"])("shows the login page for role %s instead of redirecting forever", async (role) => {
    const { router, authStore } = await loadAppWithStoredRole(role);

    await router.push("/login");

    expect(router.currentRoute.value.name).toBe("login");
    expect(authStore.isAuthenticated).toBe(false);
    expect(authStore.error).toBeTruthy();
  });

  it("sends a protected route to the login page", async () => {
    const { router, authStore } = await loadAppWithStoredRole("platform_admin");

    await router.push("/dashboard/attendee");

    expect(router.currentRoute.value.name).toBe("login");
    expect(authStore.isAuthenticated).toBe(false);
  });
});
