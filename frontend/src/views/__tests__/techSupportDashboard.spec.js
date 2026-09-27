import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  equipmentApi: { checkEquipmentAvailability: vi.fn(), inventory: vi.fn(), maintenance: vi.fn() },
}));

const mountedApps = [];

async function settle() {
  await Promise.resolve();
  await nextTick();
  await nextTick();
}

async function mountDashboard(query = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "tech-1", full_name: "Tan Wei", role: "tech_support" };
  authStore.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "dashboard-tech-support", query });
  const { default: TechSupportDashboard } = await import("@/views/dashboards/TechSupportDashboard.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(TechSupportDashboard).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await settle();
  return { el, router };
}

describe("TechSupportDashboard tabs", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    equipmentApi.inventory.mockResolvedValue({
      items: [
        {
          equipment_id: "e1",
          name: "4K Projector",
          total_quantity: 4,
          reserved_quantity: 0,
          maintenance_quantity: 0,
          net_available: 4,
        },
      ],
    });
    equipmentApi.maintenance.mockResolvedValue({ items: [] });
  });

  it("opens on the availability check and has no tab bar of its own", async () => {
    const { el } = await mountDashboard();

    expect(el.textContent).toContain("Event time window");
    expect(el.querySelector('nav[aria-label="Technical support views"]')).toBeNull();
    expect(equipmentApi.inventory).not.toHaveBeenCalled();
  });

  it("shows and loads the inventory when the route asks for it", async () => {
    const { el } = await mountDashboard({ tab: "inventory" });
    await settle();

    expect(el.textContent).toContain("Inventory & status overview");
    expect(el.textContent).not.toContain("Event time window");
    expect(equipmentApi.inventory).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("4K Projector");
  });

  it("loads the inventory when the sidebar switches to it", async () => {
    const { el, router } = await mountDashboard();
    await router.push({ name: "dashboard-tech-support", query: { tab: "inventory" } });
    await settle();
    await settle();

    expect(equipmentApi.inventory).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("4K Projector");
  });

  it("marks fully available stock with the design-system green, not a raw Tailwind colour", async () => {
    const { el } = await mountDashboard({ tab: "inventory" });
    await settle();

    const badge = [...el.querySelectorAll("span")].find((span) => span.textContent.trim() === "AVAILABLE");
    expect(badge.className).toContain("bg-bauhaus-green");
    expect(el.innerHTML).not.toMatch(/bg-(green|orange)-\d/);
  });
});
