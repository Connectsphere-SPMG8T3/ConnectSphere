import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), createSpace: vi.fn(), updateSpace: vi.fn(), removeSpace: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), resubmit: vi.fn() },
}));

const AMENDMENT = {
  id: "a1", message: "Please confirm the attendance",
  flagged_fields: ["expected_attendance", "starts_at"], returned_at: "2026-09-24T03:00:00Z",
};

function returnedEvent(overrides = {}) {
  return {
    id: "returned-1", name: "Product Briefing", status: "returned", event_timezone: "Asia/Singapore",
    purpose: "Brief partners", description: null,
    starts_at: "2026-12-01T02:00:00Z", ends_at: "2026-12-01T04:00:00Z",
    expected_attendance: 40, layout_preference: "theatre", facilities_required: [],
    spaces: [{ id: "space-1", version: 1, label: "Main hall", expected_pax: 40, layout_preference: "theatre", facilities_required: [] }],
    accessibility_needs: null, preliminary_equipment_needs: null, registration_enabled: false,
    registration_capacity: null, registration_opens_at: null, registration_closes_at: null,
    coordinator_id: "coordinator-1", version: 4, amendment: AMENDMENT,
    ...overrides,
  };
}

const mountedApps = [];

async function mountForm(listed, detail) {
  eventsApi.list.mockResolvedValue(listed);
  eventsApi.get.mockResolvedValue(detail);
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "event-new", query: { id: detail.id } });
  const { default: View } = await import("@/views/events/EventRequestView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.querySelector("input").value).toBe(detail.name));
  await nextTick();
  return { el, router };
}

async function mountNewForm() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "event-new" });
  const { default: View } = await import("@/views/events/EventRequestView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.querySelector('input[placeholder="Regional planning workshop"]')).not.toBeNull());
  await nextTick();
  return { el };
}

const labelled = (el, label) =>
  [...el.querySelectorAll("label")].find((node) => node.textContent.trim().startsWith(label));
const controlFor = (el, label) => document.getElementById(labelled(el, label).getAttribute("for"));
const buttonByText = (el, text) => [...el.querySelectorAll("button")].find((node) => node.textContent.trim() === text);

describe("EventRequestView amending a returned request (SCRUM-33)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("opens the returned request with the coordinator's message and fields to review", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());

    expect(eventsApi.get).toHaveBeenCalledWith("returned-1", "access");
    expect(el.textContent).toContain("Amend your request");
    expect(el.querySelector('[data-testid="amendment-banner"]').textContent).toContain("Please confirm the attendance");
  });

  it("highlights every input behind a flagged field and nothing else", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());

    expect(controlFor(el, "Expected attendance").dataset.flagged).toBe("true");
    expect(controlFor(el, "Proposed event date").dataset.flagged).toBe("true");
    expect(controlFor(el, "Proposed start time").dataset.flagged).toBe("true");
    expect(controlFor(el, "Purpose").dataset.flagged).toBeUndefined();
    expect(controlFor(el, "Proposed end time").dataset.flagged).toBeUndefined();
  });

  it("tints a flagged description box instead of leaving it white", async () => {
    const { el } = await mountForm(
      [returnedEvent({ amendment: null })],
      returnedEvent({ amendment: { ...AMENDMENT, flagged_fields: ["description"] } }),
    );

    const description = el.querySelector("#event-description");
    expect(description.dataset.flagged).toBe("true");
    expect(description.classList.contains("bg-bauhaus-yellow/30")).toBe(true);
    expect(description.classList.contains("bg-canvas")).toBe(false);
  });

  it("offers Resubmit and Save changes instead of Submit request and Save draft", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());

    expect(buttonByText(el, "Resubmit")).toBeTruthy();
    expect(buttonByText(el, "Save changes")).toBeTruthy();
    expect(buttonByText(el, "Submit request")).toBeUndefined();
    expect(buttonByText(el, "Save draft")).toBeUndefined();
  });

  it("resubmits the edited request with a note and returns to the dashboard", async () => {
    const { el, router } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());
    eventsApi.resubmit.mockResolvedValue(returnedEvent({ status: "under_review", expected_attendance: 60, amendment: null, version: 6 }));
    eventsApi.updateSpace.mockResolvedValue({ id: "space-1", version: 2 });
    const attendance = controlFor(el, "Expected attendance");
    attendance.value = "60";
    attendance.dispatchEvent(new Event("input"));
    await nextTick();
    const layout = controlFor(el, "Preferred layout");
    layout.value = "classroom";
    layout.dispatchEvent(new Event("change"));
    await nextTick();

    buttonByText(el, "Resubmit").click();
    await nextTick();
    const note = document.querySelector("#resubmit-note");
    note.value = "Attendance is now 60";
    note.dispatchEvent(new Event("input"));
    await nextTick();
    document.querySelector('button[aria-label="Resubmit request"]').click();

    await vi.waitFor(() => expect(eventsApi.resubmit).toHaveBeenCalled());
    const [id, payload, token] = eventsApi.resubmit.mock.calls[0];
    expect(id).toBe("returned-1");
    expect(payload.expected_attendance).toBe(60);
    expect(payload.resubmission_note).toBe("Attendance is now 60");
    expect(token).toBe("access");
    expect(eventsApi.updateSpace).toHaveBeenCalledWith("returned-1", "space-1", expect.objectContaining({
      layout_preference: "classroom",
      version: 1,
    }), "access");
    await nextTick();
    expect(document.querySelector('[aria-label="Leave page"]')).toBeNull();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-organiser"));
  });

  it("keeps the banner and highlights after Save changes", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());
    eventsApi.update.mockResolvedValue(returnedEvent({ purpose: "Brief our partners", version: 5 }));
    const purpose = controlFor(el, "Purpose");
    purpose.value = "Brief our partners";
    purpose.dispatchEvent(new Event("input"));
    await nextTick();

    buttonByText(el, "Save changes").click();

    await vi.waitFor(() => expect(eventsApi.update).toHaveBeenCalled());
    await nextTick();
    expect(el.querySelector('[data-testid="amendment-banner"]')).not.toBeNull();
    expect(controlFor(el, "Expected attendance").dataset.flagged).toBe("true");
  });

  it("still opens and resubmits a returned request that has no amendment on record", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent({ amendment: null }));

    expect(el.textContent).toContain("Amend your request");
    expect(el.querySelector('[data-testid="amendment-banner"]')).toBeNull();
    expect(buttonByText(el, "Resubmit")).toBeTruthy();
  });

  it("opens the request fresh even when the cached list is out of date", async () => {
    // The list still says under review; the event itself has since been returned.
    const { el } = await mountForm([returnedEvent({ status: "under_review", amendment: null })], returnedEvent());

    expect(el.textContent).toContain("Amend your request");
    expect(el.querySelector('[data-testid="amendment-banner"]')).not.toBeNull();
  });

  it("sends a request that can no longer be edited to its detail page, not a blank form", async () => {
    const underReview = returnedEvent({ status: "under_review", amendment: null });
    eventsApi.list.mockResolvedValue([underReview]);
    eventsApi.get.mockResolvedValue(underReview);
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore();
    auth.token = "access";
    auth.refreshToken = "refresh";
    auth.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
    auth.sessionVerified = true;
    const { default: router } = await import("@/router");
    await router.push({ name: "event-new", query: { id: underReview.id } });
    const { default: View } = await import("@/views/events/EventRequestView.vue");
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp(View).use(pinia).use(router);
    app.mount(el);
    mountedApps.push(app);

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-detail"));
    expect(router.currentRoute.value.params.id).toBe(underReview.id);
    expect(eventsApi.create).not.toHaveBeenCalled();
  });

  it("leaves a draft in draft mode", async () => {
    const draft = returnedEvent({ id: "draft-1", status: "draft", amendment: null });
    const { el } = await mountForm([draft], draft);

    expect(el.textContent).toContain("Edit your draft");
    expect(buttonByText(el, "Submit request")).toBeTruthy();
    expect(el.querySelector('[data-testid="amendment-banner"]')).toBeNull();
  });

  it("stages multiple spaces before the first event save", async () => {
    const created = returnedEvent({ id: "draft-2", status: "draft", spaces: [], amendment: null });
    const saved = returnedEvent({
      id: "draft-2",
      status: "draft",
      amendment: null,
      spaces: [
        { id: "space-1", version: 1, label: "Main hall", expected_pax: 40, layout_preference: "theatre", facilities_required: [] },
        { id: "space-2", version: 1, label: "Workshop room", expected_pax: 20, layout_preference: "classroom", facilities_required: [] },
      ],
    });
    eventsApi.create.mockResolvedValue(created);
    eventsApi.get.mockResolvedValue(saved);
    eventsApi.createSpace.mockResolvedValue({});
    const { el } = await mountNewForm();

    controlFor(el, "Event title").value = "Two room event";
    controlFor(el, "Event title").dispatchEvent(new Event("input"));
    for (const [index, [label, pax, layout]] of [["Main hall", "40", "theatre"], ["Workshop room", "20", "classroom"]].entries()) {
      if (index > 0) {
        buttonByText(el, "Add space request").click();
        await nextTick();
      }
      const spaceLabelNode = [...el.querySelectorAll("label")].filter((node) => node.textContent.trim().startsWith("Space label")).at(-1);
      const spaceLabel = document.getElementById(spaceLabelNode.getAttribute("for"));
      spaceLabel.value = label;
      spaceLabel.dispatchEvent(new Event("input"));
      const expectedPaxNode = [...el.querySelectorAll("label")].filter((node) => node.textContent.trim().startsWith("Expected pax")).at(-1);
      const expectedPax = document.getElementById(expectedPaxNode.getAttribute("for"));
      expectedPax.value = pax;
      expectedPax.dispatchEvent(new Event("input"));
      const layoutNode = [...el.querySelectorAll("label")].filter((node) => node.textContent.trim().startsWith("Preferred layout")).at(-1);
      const layoutSelect = document.getElementById(layoutNode.getAttribute("for"));
      layoutSelect.value = layout;
      layoutSelect.dispatchEvent(new Event("change"));
      await nextTick();
    }

    expect(el.textContent).toContain("2 spaces");
    buttonByText(el, "Save draft").click();
    await vi.waitFor(() => expect(eventsApi.createSpace).toHaveBeenCalledTimes(2));
    expect(eventsApi.createSpace.mock.calls.map(([, payload]) => payload.label)).toEqual(["Main hall", "Workshop room"]);
  });

  it("adds and removes unsaved space cards without a separate panel", async () => {
    const { el } = await mountNewForm();
    expect(el.textContent).toContain("1 spaces");
    expect(buttonByText(el, "Remove space")).toBeUndefined();

    buttonByText(el, "Add space request").click();
    await nextTick();
    expect(el.textContent).toContain("2 spaces");
    expect([...el.querySelectorAll("button")].filter((node) => node.textContent.trim() === "Remove space")).toHaveLength(2);

    buttonByText(el, "Remove space").click();
    await nextTick();
    expect(el.textContent).toContain("1 spaces");
    expect(buttonByText(el, "Remove space")).toBeUndefined();
  });

  it("validates space label, pax and layout only when submitting", async () => {
    const { el } = await mountNewForm();
    const setValue = async (label, value, eventName = "input") => {
      const control = controlFor(el, label);
      control.value = value;
      control.dispatchEvent(new Event(eventName));
      await nextTick();
    };
    await setValue("Event title", "Venue requirements test");
    await setValue("Purpose", "Test space validation");
    await setValue("Proposed event date", "2026-12-01");
    await setValue("Proposed start time", "10:00");
    await setValue("Proposed end time", "12:00");

    buttonByText(el, "Submit request").click();
    await nextTick();
    expect(el.textContent).toContain("Enter a space label.");
    expect(el.textContent).toContain("Enter expected pax of at least 1.");
    expect(el.textContent).toContain("Choose a layout.");
    expect(el.textContent).not.toContain("Complete every space request");
    const layoutControl = controlFor(el, "Preferred layout");
    expect(layoutControl.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(layoutControl.getAttribute("aria-describedby")).textContent).toBe("Choose a layout.");
    expect(eventsApi.submit).not.toHaveBeenCalled();

    await setValue("Space label", "Main venue");
    buttonByText(el, "Submit request").click();
    await nextTick();
    expect(el.textContent).not.toContain("Enter a space label.");
    expect(el.textContent).toContain("Enter expected pax of at least 1.");
    expect(el.textContent).toContain("Choose a layout.");

    await setValue("Expected pax", "20");
    buttonByText(el, "Submit request").click();
    await nextTick();
    expect(el.textContent).not.toContain("Enter expected pax of at least 1.");
    expect(el.textContent).toContain("Choose a layout.");

    await setValue("Preferred layout", "classroom", "change");
    buttonByText(el, "Submit request").click();
    await nextTick();
    expect(document.body.textContent).toContain("Submit event request?");
    expect(document.body.textContent).not.toContain("Enter expected attendance of at least 1");
  });

  it("removes a persisted space through the event API", async () => {
    const spaces = [
      { id: "space-1", version: 1, label: "Main venue", expected_pax: 40, layout_preference: "theatre", facilities_required: [] },
      { id: "space-2", version: 1, label: "Workshop room", expected_pax: 20, layout_preference: "classroom", facilities_required: [] },
    ];
    const draft = returnedEvent({ id: "draft-spaces", status: "draft", amendment: null, spaces });
    const refreshed = returnedEvent({ id: "draft-spaces", status: "draft", amendment: null, spaces: [spaces[1]] });
    const { el } = await mountForm([draft], draft);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    eventsApi.get.mockResolvedValue(refreshed);
    eventsApi.removeSpace.mockResolvedValue(undefined);

    buttonByText(el, "Remove space").click();
    await nextTick();
    expect(eventsApi.removeSpace).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    buttonByText(el, "Remove space").click();

    await vi.waitFor(() => expect(eventsApi.removeSpace).toHaveBeenCalledWith("draft-spaces", "space-1", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("1 spaces"));
    expect(eventsApi.get).toHaveBeenCalledTimes(2);
  });

  it("keeps a persisted space and displays an API error when removal fails", async () => {
    const spaces = [
      { id: "space-1", version: 1, label: "Main venue", expected_pax: 40, layout_preference: "theatre", facilities_required: [] },
      { id: "space-2", version: 1, label: "Workshop room", expected_pax: 20, layout_preference: "classroom", facilities_required: [] },
    ];
    const draft = returnedEvent({ id: "draft-remove-fail", status: "draft", amendment: null, spaces });
    const { el } = await mountForm([draft], draft);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    eventsApi.removeSpace.mockRejectedValue(new Error("Space version is out of date."));

    buttonByText(el, "Remove space").click();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')?.textContent).toContain("Space version is out of date."));
    expect(el.textContent).toContain("2 spaces");
    expect(buttonByText(el, "Remove space").disabled).toBe(false);
  });

  it("saves incomplete staged spaces with the draft without sending them separately", async () => {
    const created = returnedEvent({ id: "draft-incomplete", status: "draft", spaces: [], amendment: null });
    eventsApi.create.mockResolvedValue(created);
    eventsApi.get.mockResolvedValue(created);
    const { el } = await mountNewForm();
    controlFor(el, "Event title").value = "Incomplete space draft";
    controlFor(el, "Event title").dispatchEvent(new Event("input"));

    buttonByText(el, "Save draft").click();

    await vi.waitFor(() => expect(eventsApi.create).toHaveBeenCalled());
    await vi.waitFor(() => expect(el.textContent).toContain("1 spaces"));
    expect(eventsApi.createSpace).not.toHaveBeenCalled();
    expect(controlFor(el, "Space label").value).toBe("");
  });

  it("persists all spaces before submitting a new event request", async () => {
    const callOrder = [];
    const draft = returnedEvent({ id: "draft-submit", status: "draft", spaces: [], amendment: null });
    const savedSpace = {
      id: "space-submit",
      version: 1,
      label: "Main venue",
      expected_pax: 30,
      layout_preference: "theatre",
      facilities_required: ["projector"],
    };
    const withSpace = returnedEvent({ id: "draft-submit", status: "draft", spaces: [savedSpace], amendment: null });
    eventsApi.create.mockImplementation(async () => { callOrder.push("create-event"); return draft; });
    eventsApi.createSpace.mockImplementation(async () => { callOrder.push("create-space"); return savedSpace; });
    eventsApi.get.mockImplementation(async () => { callOrder.push("get-event"); return withSpace; });
    eventsApi.submit.mockImplementation(async () => { callOrder.push("submit-event"); return { ...withSpace, status: "under_review" }; });
    const { el } = await mountNewForm();
    const setValue = async (label, value, eventName = "input") => {
      const control = controlFor(el, label);
      control.value = value;
      control.dispatchEvent(new Event(eventName));
      await nextTick();
    };

    await setValue("Event title", "Venue planning workshop");
    await setValue("Purpose", "Plan the venue requirements");
    await setValue("Proposed event date", "2099-12-01");
    await setValue("Proposed start time", "10:00");
    await setValue("Proposed end time", "12:00");
    await setValue("Space label", "Main venue");
    await setValue("Expected pax", "30");
    await setValue("Preferred layout", "theatre", "change");

    buttonByText(el, "Submit request").click();
    await nextTick();
    document.querySelector('[aria-label="Confirm and submit"]').click();

    await vi.waitFor(() => expect(eventsApi.submit).toHaveBeenCalled());
    expect(callOrder).toEqual(["create-event", "create-space", "get-event", "submit-event"]);
    expect(eventsApi.createSpace).toHaveBeenCalledWith("draft-submit", expect.objectContaining({
      label: "Main venue",
      expected_pax: 30,
      layout_preference: "theatre",
    }), "access");
  });

  it("saves and submits edits to existing spaces through the event-level actions", async () => {
    const sequence = [];
    const savedSpace = {
      id: "space-existing",
      event_id: "draft-existing",
      version: 2,
      label: "Updated main hall",
      expected_pax: 40,
      layout_preference: "theatre",
      facilities_required: [],
    };
    const draft = returnedEvent({
      id: "draft-existing",
      status: "draft",
      amendment: null,
      spaces: [{ ...savedSpace, version: 1, label: "Main hall" }],
    });
    const refreshed = returnedEvent({ id: "draft-existing", status: "draft", amendment: null, spaces: [savedSpace] });
    eventsApi.update.mockImplementation(async () => { sequence.push("save-event"); return draft; });
    eventsApi.updateSpace.mockImplementation(async () => { sequence.push("save-space"); return savedSpace; });
    eventsApi.submit.mockImplementation(async () => { sequence.push("submit-event"); return { ...refreshed, status: "under_review" }; });
    const { el } = await mountForm([draft], draft);
    eventsApi.get.mockImplementation(async () => { sequence.push("reload-event"); return refreshed; });

    const spaceLabel = [...el.querySelectorAll("label")]
      .find((node) => node.textContent.trim().startsWith("Space label"));
    const spaceLabelInput = document.getElementById(spaceLabel.getAttribute("for"));
    spaceLabelInput.value = "Updated main hall";
    spaceLabelInput.dispatchEvent(new Event("input"));
    await nextTick();
    buttonByText(el, "Save draft").click();
    await vi.waitFor(() => expect(eventsApi.updateSpace).toHaveBeenCalledTimes(1));

    expect(eventsApi.updateSpace).toHaveBeenLastCalledWith("draft-existing", "space-existing", {
      label: "Updated main hall",
      expected_pax: 40,
      layout_preference: "theatre",
      facilities_required: [],
      version: 1,
    }, "access");
    await vi.waitFor(() => expect(eventsApi.get).toHaveBeenCalledTimes(2));

    buttonByText(el, "Submit request").click();
    await nextTick();
    document.querySelector('[aria-label="Confirm and submit"]').click();
    await vi.waitFor(() => expect(eventsApi.submit).toHaveBeenCalled());

    expect(eventsApi.updateSpace).toHaveBeenCalledTimes(2);
    expect(eventsApi.updateSpace.mock.calls.map(([, , payload]) => payload.version)).toEqual([1, 2]);
    expect(sequence).toEqual([
      "save-event", "save-space", "reload-event",
      "save-event", "save-space", "reload-event", "submit-event",
    ]);
  });
});
