import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EquipmentRequestPanel from "@/components/equipment/EquipmentRequestPanel.vue";
import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  equipmentApi: {
    catalogue: vi.fn(), eventRequests: vi.fn(), submitRequest: vi.fn(), sendLineForReReview: vi.fn(),
    updateLine: vi.fn(), removeLine: vi.fn(), eventHistory: vi.fn(),
  },
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

  it("shows Technical Support's status, reason and notes, and the exit check (SCRUM-24 AC9)", async () => {
    equipmentApi.eventRequests.mockResolvedValue({
      lines: [
        { ...LINE, status: "rejected", not_available_reason: "Only 2 in stock", technical_notes: "Ask the vendor" },
        { ...LINE, id: "l2", status: "re_review" },
      ],
      technical_status: "issue",
      exit_confirmation: { confirmed_by_name: "Tan Wei", confirmed_at: "2026-10-19T03:00:00Z" },
    });

    await mountPanel();

    const text = document.body.textContent;
    expect(text).toContain("Technical status");
    expect(text).toContain("Issue");
    expect(text).toContain("Not available: Only 2 in stock");
    expect(text).toContain("Technical Support notes: Ask the vendor");
    expect(text).toContain("Technical Support are re-checking this line");
    expect(text).toContain("Confirmed by Tan Wei");
  });

  it("with no lines the exit check is not shown", async () => {
    equipmentApi.eventRequests.mockResolvedValue({ lines: [], technical_status: "not_required", exit_confirmation: null });

    await mountPanel();

    expect(document.body.textContent).toContain("Not required");
    expect(document.body.textContent).not.toContain("Exits and walkways clear");
  });
});

describe("EquipmentRequestPanel re-review (story 37)", () => {
  const MARKED = { ...LINE, status: "reserved", needs_re_review_reason: "Event time changed; 2 free for 4." };

  beforeEach(() => {
    vi.clearAllMocks();
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR, MIC] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [MARKED] });
  });

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows why a line needs re-review and sends it to technical support", async () => {
    await mountPanel();
    expect(document.querySelector('[data-testid="needs-re-review"]').textContent)
      .toContain("Event time changed; 2 free for 4.");
    equipmentApi.sendLineForReReview.mockResolvedValue(null);
    equipmentApi.eventRequests.mockClear();

    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send for re-review").click();
    await nextTick();
    const form = document.querySelector('[role="dialog"][aria-label="Send for re-review"]');
    [...form.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send to technical support").click();

    await vi.waitFor(() => expect(equipmentApi.sendLineForReReview).toHaveBeenCalledWith("l1", null, "access"));
    await vi.waitFor(() => expect(equipmentApi.eventRequests).toHaveBeenCalled());
  });

  it("keeps the lines and shows why when sending is refused", async () => {
    await mountPanel();
    equipmentApi.sendLineForReReview.mockRejectedValue(new Error("This equipment line doesn't need re-review."));

    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send for re-review").click();
    await nextTick();
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send to technical support").click();

    await vi.waitFor(() => expect(document.querySelector('[role="alert"]').textContent)
      .toContain("This equipment line doesn't need re-review."));
    expect(document.body.textContent).toContain("Projector");
  });
});


describe("EquipmentRequestPanel changes and removals (SCRUM-44)", () => {
  const RESERVED = { ...LINE, status: "reserved" };
  const ENTRY = {
    action: "removed", line_label: "2 × Wireless microphone", from_status: "pending", to_status: "released",
    detail: "Removed 2 × Wireless microphone.", actor_name: "Marcus Lim", created_at: "2026-10-26T02:00:00Z",
  };
  const byLabel = (label) => document.querySelector(`button[aria-label="${label}"]`);

  beforeEach(() => {
    vi.clearAllMocks();
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR, MIC] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [RESERVED] });
    equipmentApi.eventHistory.mockResolvedValue({ history: [ENTRY] });
  });

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("offers Edit and Remove on each line while the event is in planning (AC1, AC2)", async () => {
    await mountPanel();

    expect(byLabel("Edit Projector")).not.toBeNull();
    expect(byLabel("Remove Projector from the request")).not.toBeNull();
  });

  it.each(["safety_review", "confirmed", "returned"])("offers neither outside planning (%s) (AC4)", async (status) => {
    await mountPanel({ status });

    expect(byLabel("Edit Projector")).toBeNull();
    expect(byLabel("Remove Projector from the request")).toBeNull();
    expect(document.body.textContent).toContain("Equipment can only be changed while the event is in Planning.");
  });

  it("changes a line and shows it as the API now has it (AC2, AC3)", async () => {
    await mountPanel();
    equipmentApi.updateLine.mockResolvedValue({ line_id: "l1", status: "re_review" });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [{ ...RESERVED, quantity: 6, status: "re_review" }] });

    byLabel("Edit Projector").click();
    await nextTick();
    expect(document.body.textContent).toContain("Its reservation is kept until they re-approve or reject it.");
    await setValue(quantities()[0], "6");
    byLabel("Save changes to Projector").click();

    await vi.waitFor(() => expect(equipmentApi.updateLine).toHaveBeenCalledWith("l1", {
      equipment_id: "p1", quantity: 6, technical_requirements: "HDMI to the lectern", expected_status: "reserved",
    }, "access"));
    await vi.waitFor(() => expect(document.body.textContent).toContain("× 6"));
    expect(byLabel("Save changes to Projector")).toBeNull();
    expect(document.body.textContent).toContain("Re-review");
  });

  it("closes the form on Cancel without saving", async () => {
    await mountPanel();

    byLabel("Edit Projector").click();
    await nextTick();
    byLabel("Cancel").click();
    await nextTick();

    expect(byLabel("Save changes to Projector")).toBeNull();
    expect(equipmentApi.updateLine).not.toHaveBeenCalled();
  });

  it("asks before removing, saying what removal does (AC1)", async () => {
    await mountPanel();
    equipmentApi.removeLine.mockResolvedValue({ line_id: "l1", status: "released" });

    byLabel("Remove Projector from the request").click();
    await nextTick();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("Remove 4 × Projector?");
    expect(dialog.textContent).toContain("Its reservation is released and Technical Support are told.");
    equipmentApi.eventRequests.mockResolvedValue({ lines: [{ ...RESERVED, status: "released" }] });
    byLabel("Remove line").click();

    await vi.waitFor(() => expect(equipmentApi.removeLine).toHaveBeenCalledWith("l1", "reserved", "access"));
    await vi.waitFor(() => expect(document.body.textContent).toContain("No equipment requested yet"));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it("keeps the line when removal is called off", async () => {
    await mountPanel();

    byLabel("Remove Projector from the request").click();
    await nextTick();
    byLabel("Keep line").click();
    await nextTick();

    expect(equipmentApi.removeLine).not.toHaveBeenCalled();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it("shows a refusal above the lines (AC4, AC6)", async () => {
    await mountPanel();
    equipmentApi.removeLine.mockRejectedValue(new Error("This line changed while you were editing it. Reload to see its current status."));

    byLabel("Remove Projector from the request").click();
    await nextTick();
    byLabel("Remove line").click();

    await vi.waitFor(() => expect(document.querySelector('[role="alert"]').textContent)
      .toContain("This line changed while you were editing it."));
  });

  it("shows the equipment history, where a removed line stays (AC8)", async () => {
    await mountPanel();

    await vi.waitFor(() => expect(document.body.textContent).toContain("Removed by the coordinator · 2 × Wireless microphone"));
    expect(document.body.textContent).toContain("Equipment history");
  });

  it("says so, without an alert, when the history can't be read", async () => {
    equipmentApi.eventHistory.mockRejectedValue(new Error("down"));
    await mountPanel();

    await vi.waitFor(() => expect(document.body.textContent).toContain("The equipment history couldn't be loaded."));
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  it("says a line under re-review is being re-checked, whatever sent it there", async () => {
    equipmentApi.eventRequests.mockResolvedValue({ lines: [{ ...LINE, status: "re_review" }] });
    await mountPanel();

    expect(document.body.textContent).toContain("Technical Support are re-checking this line. Its reservation is kept meanwhile.");
    expect(document.body.textContent).not.toContain("The event's time changed");
  });
});
