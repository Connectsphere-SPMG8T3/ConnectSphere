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

  it("opens on the inventory, loads it, and has no tab bar or welcome card of its own", async () => {
    const { el } = await mountDashboard();
    await settle();

    expect(el.textContent).toContain("Inventory & status");
    expect(el.textContent).not.toContain("Event time window");
    expect(el.textContent).not.toContain("Welcome");
    expect(el.querySelector('nav[aria-label="Technical support views"]')).toBeNull();
    expect(equipmentApi.inventory).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("4K Projector");
  });

  it("shows the availability check when the route asks for it, without loading the inventory", async () => {
    const { el } = await mountDashboard({ tab: "availability" });

    expect(el.textContent).toContain("Event time window");
    expect(el.textContent).not.toContain("Inventory & status");
    expect(equipmentApi.inventory).not.toHaveBeenCalled();
  });

  it("loads the inventory when the sidebar switches to it from the availability check", async () => {
    const { el, router } = await mountDashboard({ tab: "availability" });
    await router.push({ name: "dashboard-tech-support", query: { tab: "inventory" } });
    await settle();
    await settle();

    expect(equipmentApi.inventory).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("4K Projector");
  });

  it("summarises the inventory in tiles, and shows a dash rather than a zero when it could not load", async () => {
    const { el } = await mountDashboard();
    await settle();
    const tile = (label) => [...el.querySelectorAll("[data-testid=tile]")].find((t) => t.textContent.includes(label));

    expect(tile("Out of stock").textContent).toContain("0");
    expect(tile("Equipment types").textContent).toContain("1");

    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    equipmentApi.inventory.mockRejectedValue(new Error("down"));
    const failed = await mountDashboard();
    await settle();
    const failedTile = [...failed.el.querySelectorAll("[data-testid=tile]")].find((t) => t.textContent.includes("Out of stock"));
    expect(failedTile.textContent).toContain("—");
  });

  it("marks fully available stock with the design-system green, not a raw Tailwind colour", async () => {
    const { el } = await mountDashboard();
    await settle();

    const badge = [...el.querySelectorAll("span")].find((span) => span.textContent.trim() === "AVAILABLE");
    expect(badge.className).toContain("bg-bauhaus-green");
    expect(el.innerHTML).not.toMatch(/bg-(green|orange)-\d/);
  });
});
