import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  equipmentApi: { checkEquipmentAvailability: vi.fn(), inventory: vi.fn(), maintenance: vi.fn(), requestList: vi.fn(), catalogue: vi.fn() },
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
    equipmentApi.requestList.mockResolvedValue({ lines: [] });
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

    expect(tile("Under repair").textContent).toContain("0");
    expect(tile("Equipment types").textContent).toContain("1");

    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    equipmentApi.inventory.mockRejectedValue(new Error("down"));
    const failed = await mountDashboard();
    await settle();
    const failedTile = [...failed.el.querySelectorAll("[data-testid=tile]")].find((t) => t.textContent.includes("Under repair"));
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

describe("TechSupportDashboard active requests tile (SCRUM-24)", () => {
  const line = (status) => ({
    id: `l-${status}`, submission_id: "s1", event_id: "event-1", equipment_id: "e1", equipment_name: "4K Projector",
    quantity: 4, technical_requirements: null, status, requested_by: { id: "m1", full_name: "Marcus Lim" },
    created_at: "2026-10-06T02:00:00Z", event_name: "Year-End Dinner", event_starts_at: "2026-11-05T10:00:00Z",
  });
  const activeTile = (el) => [...el.querySelectorAll("[data-testid=tile]")].find((t) => t.textContent.includes("Active requests"));

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    equipmentApi.inventory.mockResolvedValue({ items: [] });
    equipmentApi.maintenance.mockResolvedValue({ items: [] });
  });

  it("counts the lines waiting on tech support and links to the requests page", async () => {
    equipmentApi.requestList.mockResolvedValue({ lines: [line("pending"), line("re_review"), line("reserved")] });

    const { el } = await mountDashboard();
    await vi.waitFor(() => expect(activeTile(el).textContent).toContain("2"));

    expect(activeTile(el).textContent).toContain("Awaiting your decision");
    expect(activeTile(el).getAttribute("href")).toBe("/dashboard/tech-support/requests");
    const tileLabels = [...el.querySelectorAll("[data-testid=tile]")].map((t) => t.textContent);
    expect(tileLabels.some((text) => text.includes("Out of stock"))).toBe(false);
  });

  it("shows a dash, not a zero, when the requests can't load", async () => {
    equipmentApi.requestList.mockRejectedValue(new Error("Service unavailable"));

    const { el } = await mountDashboard();
    await vi.waitFor(() => expect(equipmentApi.requestList).toHaveBeenCalled());
    await settle();

    expect(activeTile(el).textContent).toContain("—");
  });

  it("the full list is no longer on the dashboard", async () => {
    equipmentApi.requestList.mockResolvedValue({ lines: [line("pending")] });

    const { el } = await mountDashboard();
    await settle();

    expect(el.querySelector('[aria-labelledby="equipment-requests-heading"]')).toBeNull();
  });

  it("the inventory can still be filtered to out-of-stock items", async () => {
    equipmentApi.requestList.mockResolvedValue({ lines: [] });
    equipmentApi.inventory.mockResolvedValue({ items: [
      { equipment_id: "x", name: "Projector", total_quantity: 2, reserved_quantity: 2, maintenance_quantity: 0, net_available: 0 },
      { equipment_id: "y", name: "Speaker", total_quantity: 2, reserved_quantity: 0, maintenance_quantity: 0, net_available: 2 },
    ] });

    const { el } = await mountDashboard();
    await vi.waitFor(() => expect(el.textContent).toContain("Speaker"));
    const select = [...el.querySelectorAll("select")].find((s) => [...s.options].some((o) => o.value === "out-of-stock"));
    select.value = "out-of-stock";
    select.dispatchEvent(new Event("change"));
    await settle();

    const table = el.querySelector("table").textContent;
    expect(table).toContain("Projector");
    expect(table).not.toContain("Speaker");
  });
});

describe("TechSupportDashboard inventory window (D46)", () => {
  const ITEM = { equipment_id: "e1", name: "4K Projector", total_quantity: 14, reserved_quantity: 0, maintenance_quantity: 0, net_available: 14 };
  const iso = (local) => new Date(local).toISOString();
  const field = (el, label) => [...el.querySelectorAll("label")].find((l) => l.textContent.includes(label))?.querySelector("input");
  const windowText = (el) => el.querySelector("[data-testid=inventory-window]")?.textContent ?? "";

  async function setField(el, label, value) {
    const input = field(el, label);
    input.value = value;
    input.dispatchEvent(new Event("input"));
    await settle();
  }

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    vi.useRealTimers();
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    equipmentApi.inventory.mockResolvedValue({ items: [ITEM] });
    equipmentApi.maintenance.mockResolvedValue({ items: [] });
    equipmentApi.requestList.mockResolvedValue({ lines: [] });
  });

  it("opens on today 9 am to 5 pm and says which window the table counts", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 19, 22, 30));
    const { el } = await mountDashboard();
    await vi.waitFor(() => expect(el.textContent).toContain("4K Projector"));

    expect(equipmentApi.inventory).toHaveBeenCalledWith(iso("2026-10-19T09:00"), iso("2026-10-19T17:00"), "access");
    expect(field(el, "Window start").value).toBe("2026-10-19T09:00");
    expect(field(el, "Window end").value).toBe("2026-10-19T17:00");
    expect(windowText(el)).toContain("Showing stock for 19 Oct 2026, 9:00 am – 5:00 pm");
    expect(el.textContent).not.toContain("set under Availability");
  });

  it("reloads for a window the developer picks, so an event's reservations show", async () => {
    const { el } = await mountDashboard();
    await vi.waitFor(() => expect(equipmentApi.inventory).toHaveBeenCalledTimes(1));
    equipmentApi.inventory.mockResolvedValue({ items: [{ ...ITEM, reserved_quantity: 11, net_available: 3 }] });

    await setField(el, "Window start", "2031-09-01T09:00");
    await setField(el, "Window end", "2031-09-01T13:00");
    await vi.waitFor(() => expect(windowText(el)).toContain("1 Sep 2031, 9:00 am – 1:00 pm"));

    expect(equipmentApi.inventory).toHaveBeenLastCalledWith(iso("2031-09-01T09:00"), iso("2031-09-01T13:00"), "access");
    const row = [...el.querySelectorAll("tbody tr")].find((r) => r.textContent.includes("4K Projector"));
    expect(row.textContent).toContain("11");
    expect(row.textContent).toContain("PARTIALLY RESERVED");
  });

  it("refuses a window that ends before it starts, and keeps naming the window still shown", async () => {
    const { el } = await mountDashboard();
    await vi.waitFor(() => expect(windowText(el)).toContain("Showing stock for"));
    const shown = windowText(el);

    await setField(el, "Window end", "2000-01-01T09:00");

    expect(el.querySelector("[data-testid=inventory-window-error]").textContent).toContain("End time must be later than the start time.");
    expect(equipmentApi.inventory).toHaveBeenCalledTimes(1);
    expect(windowText(el)).toBe(shown);
  });

  it("shows the latest window's numbers even if an earlier load answers last", async () => {
    const { el } = await mountDashboard();
    await setField(el, "Window end", "2031-12-31T17:00");
    await vi.waitFor(() => expect(equipmentApi.inventory).toHaveBeenCalledTimes(2));
    let answerSlow;
    equipmentApi.inventory
      .mockImplementationOnce(() => new Promise((resolve) => { answerSlow = () => resolve({ items: [{ ...ITEM, name: "Stale" }] }); }))
      .mockResolvedValueOnce({ items: [{ ...ITEM, name: "Fresh" }] });

    await setField(el, "Window start", "2031-09-01T09:00");
    await setField(el, "Window start", "2031-09-02T09:00");
    await vi.waitFor(() => expect(el.textContent).toContain("Fresh"));
    answerSlow();
    // Let the stale answer run all the way through withSession before looking.
    await new Promise((resolve) => setTimeout(resolve, 20));
    await settle();

    expect(el.textContent).toContain("Fresh");
    expect(el.textContent).not.toContain("Stale");
    expect(windowText(el)).toContain("2 Sep 2031");
  });

  it("keeps the availability check's window separate", async () => {
    const { el, router } = await mountDashboard();
    await vi.waitFor(() => expect(equipmentApi.inventory).toHaveBeenCalledTimes(1));
    await setField(el, "Window start", "2031-09-01T09:00");

    await router.push({ name: "dashboard-tech-support", query: { tab: "availability" } });
    await settle();

    expect(field(el, "Start date and time").value).not.toBe("2031-09-01T09:00");
  });
});

describe("TechSupportDashboard availability check items (D47)", () => {
  const CATALOGUE = [
    { equipment_id: "p1", name: "4K Projector", equipment_type: "projector", total_quantity: 14 },
    { equipment_id: "s1", name: "Sound System", equipment_type: "audio", total_quantity: 10 },
    { equipment_id: "x1", name: "Extension Cords", equipment_type: "power", total_quantity: 40 },
  ];
  const pickers = (el) => [...el.querySelectorAll("label")].filter((l) => l.textContent.includes("Equipment ID / type")).map((l) => l.querySelector("select"));
  const button = (el, text) => [...el.querySelectorAll("button")].find((b) => b.textContent.includes(text));

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    equipmentApi.inventory.mockResolvedValue({ items: [] });
    equipmentApi.maintenance.mockResolvedValue({ items: [] });
    equipmentApi.requestList.mockResolvedValue({ lines: [] });
    equipmentApi.catalogue.mockResolvedValue({ items: CATALOGUE });
    equipmentApi.checkEquipmentAvailability.mockResolvedValue({ sufficient: true, items: [] });
  });

  it("offers every item in the live catalogue, not a fixed list", async () => {
    const { el } = await mountDashboard({ tab: "availability" });
    await vi.waitFor(() => expect(pickers(el)[0].options).toHaveLength(3));

    expect(equipmentApi.catalogue).toHaveBeenCalledTimes(1);
    expect([...pickers(el)[0].options].map((o) => o.textContent.trim())).toEqual([
      "4K Projector · projector", "Sound System · audio", "Extension Cords · power",
    ]);
    expect(pickers(el)[0].value).toBe("p1");
  });

  it("checks an item added after the original five", async () => {
    const { el } = await mountDashboard({ tab: "availability" });
    await vi.waitFor(() => expect(pickers(el)[0].options).toHaveLength(3));
    pickers(el)[0].value = "s1";
    pickers(el)[0].dispatchEvent(new Event("change"));
    button(el, "Add item").click();
    await settle();

    expect(pickers(el)[1].value).toBe("p1");
    button(el, "Check real-time availability").click();
    await vi.waitFor(() => expect(equipmentApi.checkEquipmentAvailability).toHaveBeenCalled());

    const [payload] = equipmentApi.checkEquipmentAvailability.mock.calls[0];
    expect(payload.items).toEqual([
      { equipment_id: "s1", quantity_needed: 1 },
      { equipment_id: "p1", quantity_needed: 1 },
    ]);
  });

  it("says so, and won't check, when the catalogue can't load", async () => {
    equipmentApi.catalogue.mockRejectedValue(new Error("down"));
    const { el } = await mountDashboard({ tab: "availability" });
    await vi.waitFor(() => expect(el.textContent).toContain("The equipment catalogue could not be loaded"));

    expect(button(el, "Check real-time availability").disabled).toBe(true);
    expect(equipmentApi.checkEquipmentAvailability).not.toHaveBeenCalled();
  });

  it("loads the catalogue only for the availability check", async () => {
    await mountDashboard();
    await settle();

    expect(equipmentApi.catalogue).not.toHaveBeenCalled();
  });
});


describe("TechSupportDashboard availability results (23-R)", () => {
  afterEach(() => mountedApps.splice(0).forEach((app) => app.unmount()));

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    equipmentApi.catalogue.mockResolvedValue({ items: [
      { equipment_id: "p1", name: "Projector", equipment_type: "projector", total_quantity: 7 },
    ] });
  });

  it.each([
    ["Store A", "Store A", 6, 5, 1, false, "Insufficient"],
    [null, "Not recorded", 5, 5, 0, true, "Sufficient"],
    ["", "Not recorded", 5, 5, 0, true, "Sufficient"],
    ["   ", "Not recorded", 5, 5, 0, true, "Sufficient"],
  ])("shows location %s and the requested, available and missing quantities", async (location, shownLocation, needed, available, missing, sufficient, status) => {
    equipmentApi.checkEquipmentAvailability.mockResolvedValue({ sufficient, items: [{
      equipment_id: "p1", name: "Projector", storage_location: location,
      quantity_needed: needed, quantity_available: available, quantity_missing: missing, sufficient,
    }] });
    const { el } = await mountDashboard({ tab: "availability" });
    await vi.waitFor(() => expect(el.querySelector("select").options).toHaveLength(1));
    el.querySelector('input[type="number"]').value = needed;
    el.querySelector('input[type="number"]').dispatchEvent(new Event("input"));
    await settle();
    [...el.querySelectorAll("button")].find((b) => b.textContent.includes("Check real-time availability")).click();
    await vi.waitFor(() => expect(el.querySelector("tbody tr")).not.toBeNull());

    expect([...el.querySelectorAll("thead th")].map((c) => c.textContent.trim())).toEqual([
      "Equipment name", "Storage location", "Requested", "Available", "Missing", "Status",
    ]);
    expect([...el.querySelectorAll("tbody td")].map((c) => c.textContent.trim())).toEqual([
      "Projector", shownLocation, String(needed), String(available), String(missing), status,
    ]);
    expect(el.textContent).toContain("Storage location is for reference only");
    const [payload] = equipmentApi.checkEquipmentAvailability.mock.calls[0];
    expect(Object.keys(payload).sort()).toEqual(["end_at", "items", "start_at"]);
    const fields = el.querySelectorAll('input[type="datetime-local"]');
    expect(payload.start_at).toBe(new Date(fields[0].value).toISOString());
    expect(payload.end_at).toBe(new Date(fields[1].value).toISOString());
  });
});
