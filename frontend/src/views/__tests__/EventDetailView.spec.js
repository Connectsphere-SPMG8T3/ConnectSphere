import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), history: vi.fn(), listComments: vi.fn(), addComment: vi.fn() },
}));

function eventResponse(overrides = {}) {
  return {
    id: "event-1",
    name: "Annual Conference",
    status: "submitted",
    event_timezone: "Asia/Singapore",
    starts_at: "2026-11-01T02:00:00Z",
    ends_at: "2026-11-01T07:00:00Z",
    expected_attendance: 150,
    facilities_required: [],
    registration_enabled: false,
    coordinator_id: null,
    ...overrides,
  };
}

const mountedApps = [];

async function mountDetail(response, historyResponse = { entries: [] }) {
  eventsApi.history.mockResolvedValue(historyResponse);
  eventsApi.listComments.mockResolvedValue({ comments: [] });
  eventsApi.get.mockResolvedValue(response);
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  authStore.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "event-detail", params: { id: response.id } });
  const { default: EventDetailView } = await import("@/views/events/EventDetailView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(EventDetailView).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return el;
}

describe("EventDetailView status", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("SCRUM-82 shows confirmed arrangements", async () => {
    const el = await mountDetail(eventResponse({status: "confirmed", venue_booking: {venue_name: "Main Hall", status: "approved"}, technical_readiness: "not_required"}));
    expect(el.textContent).toContain("Arrangements"); expect(el.textContent).toContain("Main Hall"); expect(el.textContent).toContain("Not required");
  });
  it.each(["planning", "safety_review"])("SCRUM-82 hides confirmed arrangements in %s", async (status) => {
    const el = await mountDetail(eventResponse({status}));
    expect(el.textContent).not.toContain("Arrangements");
    if (status === "safety_review") expect(el.textContent).toContain("Your event is with the Safety Officer for its operational safety check.");
  });
  it("shows the discussion once the request is submitted (SCRUM-61)", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access"));
    expect(el.textContent).toContain("Discussion");
  });

  it("has no discussion on a draft (SCRUM-61)", async () => {
    const el = await mountDetail(eventResponse({ status: "draft" }));

    expect(el.textContent).not.toContain("Discussion");
    expect(eventsApi.listComments).not.toHaveBeenCalled();
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("shows the same plain-language status label as the dashboard, not the raw status (LC-R3)", async () => {
    const el = await mountDetail(eventResponse({ status: "submitted" }));

    expect(el.textContent).toContain("Awaiting assignment");
    expect(el.textContent).not.toMatch(/\bsubmitted\b/);
  });

  it("never describes a planning event as approved (QA2-8)", async () => {
    const el = await mountDetail(eventResponse({ status: "planning" }));

    expect(el.textContent).toContain("Planning");
    expect(el.textContent).not.toMatch(/\bapproved\b/i);
  });
});

describe("EventDetailView decision and history (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  const rejection = {
    id: "h2", from_status: "under_review", to_status: "rejected", reason: "Venue unavailable on that date",
    at: "2026-09-24T06:05:00Z", actor: { id: "c1", full_name: "Marcus Lim" },
  };

  it("shows the organiser why their request was rejected", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    await vi.waitFor(() => expect(el.querySelector('[data-testid="rejection-notice"]')).not.toBeNull());
    const notice = el.querySelector('[data-testid="rejection-notice"]');
    expect(notice.textContent).toContain("Venue unavailable on that date");
    expect(notice.textContent).toContain("can't be resubmitted");
  });

  it("renders the rejection notice as a solid red block, not a faint accent stripe", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    await vi.waitFor(() => expect(el.querySelector('[data-testid="rejection-notice"]')).not.toBeNull());
    const notice = el.querySelector('[data-testid="rejection-notice"]');
    expect(notice.classList.contains("bg-bauhaus-red")).toBe(true);
  });

  it("offers no resubmit or edit action on a rejected request", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    expect(el.textContent).not.toMatch(/resubmit request|edit request/i);
  });

  it("lists the status history", async () => {
    const el = await mountDetail(eventResponse({ status: "planning" }), {
      entries: [{ id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } }],
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Marcus Lim"));
    expect(el.textContent).toContain("History");
  });

  it("shows no rejection notice for an event that isn't rejected", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    expect(el.querySelector('[data-testid="rejection-notice"]')).toBeNull();
  });
  it("shows the coordinator's amendment request and a way to amend it (SCRUM-33)", async () => {
    const el = await mountDetail(eventResponse({
      status: "returned",
      amendment: { id: "a1", message: "Please confirm the attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" },
    }));

    const banner = el.querySelector('[data-testid="amendment-banner"]');
    expect(banner.textContent).toContain("Please confirm the attendance");
    const { default: router } = await import("@/router");
    [...banner.querySelectorAll("button")].find((node) => node.textContent.trim() === "Amend and resubmit").click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.query.id).toBe("event-1");
  });

  it("shows no amendment banner for a request that isn't returned", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    expect(el.querySelector('[data-testid="amendment-banner"]')).toBeNull();
  });
});

describe("EventDetailView sidebar (D23, D24)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  function registrationCard(el) {
    const heading = [...el.querySelectorAll("h2")].find((h2) => h2.textContent.trim() === "Registration");
    return heading.parentElement;
  }

  it("keeps the registration labels and timezone in ink, since the card's surface is white (D23)", async () => {
    // BauhausCard draws its tone as an edge stripe on a white surface, so white
    // (`text-canvas`) text inside it is invisible.
    const el = await mountDetail(eventResponse({
      registration_enabled: true,
      registration_capacity: 80,
      registration_opens_at: "2026-10-20T09:00:00+08:00",
      registration_closes_at: "2026-10-30T18:00:00+08:00",
    }));
    const card = registrationCard(el);

    for (const label of ["Capacity", "Opens", "Closes"]) expect(card.textContent).toContain(label);
    expect(card.textContent).toContain("Asia/Singapore");
    expect(card.querySelectorAll('[class*="text-canvas"]')).toHaveLength(0);
  });

  it("names the assigned coordinator instead of showing their account ID (D24)", async () => {
    const el = await mountDetail(eventResponse({
      status: "under_review",
      coordinator_id: "c0000000-0000-4000-8000-000000000002",
      coordinator: { id: "c0000000-0000-4000-8000-000000000002", full_name: "Marcus Lim" },
    }));

    expect(el.textContent).toContain("Coordinator: Marcus Lim");
    expect(el.textContent).not.toContain("c0000000-0000-4000-8000-000000000002");
  });

  it("never falls back to the coordinator's ID when their name is missing (D24)", async () => {
    // Only the single-event read carries the name; an edit response doesn't.
    const el = await mountDetail(eventResponse({ coordinator_id: "c0000000-0000-4000-8000-000000000002" }));

    expect(el.textContent).toContain("Coordinator: Assigned");
    expect(el.textContent).not.toContain("c0000000-0000-4000-8000-000000000002");
  });

  it("says a coordinator is still to be assigned when there is none (D24)", async () => {
    const el = await mountDetail(eventResponse({ coordinator_id: null, coordinator: null }));

    expect(el.textContent).toContain("Coordinator: To be assigned");
  });
});
