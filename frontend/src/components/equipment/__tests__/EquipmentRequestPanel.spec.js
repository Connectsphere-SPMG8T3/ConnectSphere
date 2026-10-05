import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EquipmentRequestPanel from "@/components/equipment/EquipmentRequestPanel.vue";
import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  equipmentApi: { catalogue: vi.fn(), eventRequests: vi.fn(), submitRequest: vi.fn() },
}));

const PROJECTOR = { equipment_id: "p1", name: "Projector", equipment_type: "AV", total_quantity: 20 };
const MIC = { equipment_id: "m1", name: "Wireless microphone", equipment_type: "Audio", total_quantity: 8 };
const LINE = {
  id: "l1", submission_id: "s1", event_id: "event-1", equipment_id: "p1", equipment_name: "Projector",
  quantity: 4, technical_requirements: "HDMI to the lectern", status: "pending",
  requested_by: { id: "m9", full_name: "Marcus Lim" }, created_at: "2026-10-06T02:00:00Z",
};
const mounted = [];

async function mountPanel(props = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "m9", role: "event_coordinator", full_name: "Marcus Lim" };
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EquipmentRequestPanel, { eventId: "event-1", status: "planning", ...props }) });
  app.use(pinia);
  app.mount(el);
  mounted.push(app);
  await vi.waitFor(() => expect(equipmentApi.eventRequests).toHaveBeenCalled());
  await vi.waitFor(() => expect(document.body.textContent).not.toContain("Loading equipment"));
}

async function setValue(element, value, eventName = "input") {
  element.value = value;
  element.dispatchEvent(new Event(eventName));
  await nextTick();
}

const selects = () => [...document.querySelectorAll("select")];
const quantities = () => [...document.querySelectorAll('input[type="number"]')];
const textareas = () => [...document.querySelectorAll("textarea")];
const submitButton = () => document.querySelector('button[aria-label="Submit equipment request"]');
const addButton = () => document.querySelector('button[aria-label="Add another item"]');

describe("EquipmentRequestPanel (SCRUM-45)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR, MIC] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [LINE] });
  });

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("lists the event's lines with their status and technical requirements (AC6)", async () => {
    await mountPanel();

    const text = document.body.textContent;
    expect(text).toContain("Projector");
    expect(text).toContain("× 4");
    expect(text).toContain("Pending");
    expect(text).toContain("HDMI to the lectern");
  });

  it("offers catalogue items with their totals (AC1)", async () => {
    await mountPanel();

    const labels = [...selects()[0].options].map((option) => option.textContent.trim());
    expect(labels).toContain("Projector (20 in catalogue)");
    expect(labels).toContain("Wireless microphone (8 in catalogue)");
  });

  it("keeps Submit disabled until a line has an item and a whole quantity (AC3, AC4)", async () => {
    await mountPanel();
    expect(submitButton().disabled).toBe(true);

    await setValue(selects()[0], "p1", "change");
    await setValue(quantities()[0], "0");
    expect(submitButton().disabled).toBe(true);
    expect(document.body.textContent).toContain("Quantity must be a whole number of at least 1.");

    await setValue(quantities()[0], "2");
    expect(submitButton().disabled).toBe(false);
  });

  it("warns above the catalogue total but still lets the request go (AC5)", async () => {
    await mountPanel();

    await setValue(selects()[0], "p1", "change");
    await setValue(quantities()[0], "25");

    expect(document.body.textContent).toContain("Only 20 exist in the catalogue. You can still submit.");
    expect(submitButton().disabled).toBe(false);
  });

  it("counts technical requirements against the 1000-character limit (AC2)", async () => {
    await mountPanel();

    await setValue(textareas()[0], "HDMI");

    expect(document.body.textContent).toContain("4 / 1000");
    expect(textareas()[0].getAttribute("maxlength")).toBe("1000");
  });

  it("submits every line together and shows them as pending (AC6)", async () => {
    const saved = [
      { ...LINE, id: "l2", submission_id: "s2", quantity: 25, technical_requirements: null },
      { ...LINE, id: "l3", submission_id: "s2", equipment_id: "m1", equipment_name: "Wireless microphone", quantity: 2, technical_requirements: "Lapel" },
    ];
    equipmentApi.submitRequest.mockResolvedValue({ lines: saved });
    await mountPanel();

    await setValue(selects()[0], "p1", "change");
    await setValue(quantities()[0], "25");
    addButton().click();
    await nextTick();
    await setValue(selects()[1], "m1", "change");
    await setValue(quantities()[1], "2");
    await setValue(textareas()[1], "Lapel");
    submitButton().click();

    await vi.waitFor(() => expect(equipmentApi.submitRequest).toHaveBeenCalledTimes(1));
    expect(equipmentApi.submitRequest).toHaveBeenCalledWith(
      {
        event_id: "event-1",
        items: [
          { equipment_id: "p1", quantity: 25, technical_requirements: null },
          { equipment_id: "m1", quantity: 2, technical_requirements: "Lapel" },
        ],
      },
      "access",
    );
    await vi.waitFor(() => expect(document.body.textContent).toContain("Lapel"));
    expect(document.body.textContent).toContain("× 25");
    // The form starts again with one empty line.
    expect(selects()).toHaveLength(1);
    expect(selects()[0].value).toBe("");
  });

  it("refuses the same item on two lines", async () => {
    await mountPanel();

    await setValue(selects()[0], "p1", "change");
    await setValue(quantities()[0], "1");
    addButton().click();
    await nextTick();
    await setValue(selects()[1], "p1", "change");
    await setValue(quantities()[1], "1");

    expect(document.body.textContent).toContain("is already on this request");
    expect(submitButton().disabled).toBe(true);
  });

  it("removes a line", async () => {
    await mountPanel();
    addButton().click();
    await nextTick();
    expect(selects()).toHaveLength(2);

    document.querySelector('button[aria-label="Remove item 2"]').click();
    await nextTick();

    expect(selects()).toHaveLength(1);
  });

  it("shows the API's refusal and keeps what was entered", async () => {
    equipmentApi.submitRequest.mockRejectedValue(new Error("Only the event's assigned coordinator can do this."));
    await mountPanel();

    await setValue(selects()[0], "p1", "change");
    await setValue(quantities()[0], "3");
    submitButton().click();

    await vi.waitFor(() => expect(document.body.textContent).toContain("Only the event's assigned coordinator can do this."));
    expect(selects()[0].value).toBe("p1");
  });

  it.each(["under_review", "returned", "confirmed"])("offers no form outside planning (%s) (AC7)", async (status) => {
    await mountPanel({ status });

    expect(submitButton()).toBeNull();
    expect(document.body.textContent).toContain("Projector");
  });

  it("says so when nothing has been requested yet", async () => {
    equipmentApi.eventRequests.mockResolvedValue({ lines: [] });
    await mountPanel();

    expect(document.body.textContent).toContain("No equipment requested yet");
  });
});
