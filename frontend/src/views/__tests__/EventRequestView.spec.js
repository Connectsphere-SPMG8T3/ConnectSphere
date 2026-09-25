import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), resubmit: vi.fn() },
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

const labelled = (el, label) =>
  [...el.querySelectorAll("label")].find((node) => node.textContent.trim().startsWith(label));
const controlFor = (el, label) => document.getElementById(labelled(el, label).getAttribute("for"));
const buttonByText = (el, text) => [...el.querySelectorAll("button")].find((node) => node.textContent.trim() === text);

describe("EventRequestView amending a returned request (SCRUM-33)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
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
    const attendance = controlFor(el, "Expected attendance");
    attendance.value = "60";
    attendance.dispatchEvent(new Event("input"));
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
});
