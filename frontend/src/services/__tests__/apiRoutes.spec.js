import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authApi, equipmentApi, eventsApi, venueBookingsApi, venuesApi } from "@/services/api";

// Every other spec mocks this module, so a wrong path or method here would only
// show up in a live run. Each row is one wrapper and the request it must send.
const BASE = "http://localhost:8000/api/v1";
const T = "token";
const BODY = { a: 1 };

const ROUTES = [
  ["authApi.signup", () => authApi.signup(BODY), "POST", "/auth/signup", BODY, false],
  ["authApi.login", () => authApi.login("e", "p"), "POST", "/auth/login", { email: "e", password: "p" }, false],
  ["authApi.refresh", () => authApi.refresh("r"), "POST", "/auth/refresh", { refresh_token: "r" }, false],
  ["authApi.me", () => authApi.me(T), "GET", "/auth/me"],
  ["authApi.setActiveRole", () => authApi.setActiveRole(T, "attendee"), "POST", "/auth/active-role", { role: "attendee" }],
  ["authApi.logout", () => authApi.logout(T), "POST", "/auth/logout"],

  ["venuesApi.search", () => venuesApi.search({ capacity: 5 }, T), "GET", "/venues?capacity=5"],
  ["venuesApi.get", () => venuesApi.get("v/1", T), "GET", "/venues/v%2F1"],
  ["venuesApi.venueStaffDashboard", () => venuesApi.venueStaffDashboard(T), "GET", "/venues/dashboard/venue-staff"],
  ["venuesApi.update", () => venuesApi.update("v1", BODY, T), "PATCH", "/venues/v1", BODY],
  ["venuesApi.history", () => venuesApi.history("v1", T), "GET", "/venues/v1/history"],
  ["venuesApi.deactivate", () => venuesApi.deactivate("v1", BODY, T), "POST", "/venues/v1/deactivate", BODY],
  ["venuesApi.reactivate", () => venuesApi.reactivate("v1", BODY, T), "POST", "/venues/v1/reactivate", BODY],
  ["venuesApi.createBlock", () => venuesApi.createBlock("v1", BODY, T), "POST", "/venues/v1/blocks", BODY],
  ["venueBookingsApi.setPreparation", () => venueBookingsApi.setPreparation("b1", BODY, T), "PUT",
    "/venue-bookings/b1/preparation", BODY],

  ["eventsApi.coordinatorDashboard", () => eventsApi.coordinatorDashboard(T), "GET", "/events/dashboard/coordinator"],
  ["eventsApi.get", () => eventsApi.get("e1", T), "GET", "/events/e1"],
  ["eventsApi.create", () => eventsApi.create(BODY, T), "POST", "/events", BODY],
  ["eventsApi.update", () => eventsApi.update("e1", BODY, T), "PATCH", "/events/e1", BODY],
  ["eventsApi.remove", () => eventsApi.remove("e1", T), "DELETE", "/events/e1"],
  ["eventsApi.submit", () => eventsApi.submit("e1", BODY, T), "POST", "/events/e1/submit", BODY],
  ["eventsApi.approve", () => eventsApi.approve("e1", T), "POST", "/events/e1/approve"],
  ["eventsApi.setPrimarySpace", () => eventsApi.setPrimarySpace("e1", "s1", T), "PUT", "/events/e1/spaces/s1/primary"],
  ["eventsApi.clearPrimarySpace", () => eventsApi.clearPrimarySpace("e1", T), "DELETE", "/events/e1/spaces/primary"],
  ["eventsApi.reject", () => eventsApi.reject("e1", "Why", T), "POST", "/events/e1/reject", { reason: "Why" }],
  ["eventsApi.requestCancellation", () => eventsApi.requestCancellation("e1", "Why", T), "POST",
    "/events/e1/cancellation-request", { reason: "Why" }],
  ["eventsApi.returnForAmendment", () => eventsApi.returnForAmendment("e1", BODY, T), "POST", "/events/e1/return", BODY],
  ["eventsApi.resubmit", () => eventsApi.resubmit("e1", BODY, T), "POST", "/events/e1/resubmit", BODY],
  ["eventsApi.history", () => eventsApi.history("e1", T), "GET", "/events/e1/history"],
  ["eventsApi.listComments", () => eventsApi.listComments("e1", T), "GET", "/events/e1/comments"],
  ["eventsApi.addComment", () => eventsApi.addComment("e1", "Hi", T), "POST", "/events/e1/comments", { body: "Hi" }],

  ["equipmentApi.checkEquipmentAvailability", () => equipmentApi.checkEquipmentAvailability(BODY, T), "POST",
    "/equipment/availability/check", BODY],
  ["equipmentApi.inventory with a window", () => equipmentApi.inventory("s", "e", T), "GET",
    "/equipment/inventory?start_at=s&end_at=e"],
  ["equipmentApi.inventory without one", () => equipmentApi.inventory(null, null, T), "GET", "/equipment/inventory"],
  ["equipmentApi.maintenance", () => equipmentApi.maintenance(T), "GET", "/equipment/maintenance"],
  ["equipmentApi.submitRequest", () => equipmentApi.submitRequest(BODY, T), "POST", "/equipment/requests", BODY],
  ["equipmentApi.requestList", () => equipmentApi.requestList(T), "GET", "/equipment/requests"],
  ["equipmentApi.technicalView", () => equipmentApi.technicalView("e1", T), "GET", "/equipment/events/e1/technical"],
  ["equipmentApi.reserveLine", () => equipmentApi.reserveLine("l1", T), "POST", "/equipment/requests/l1/reserve"],
  ["equipmentApi.markNotAvailable", () => equipmentApi.markNotAvailable("l1", "Why", T), "POST",
    "/equipment/requests/l1/not-available", { reason: "Why" }],
  ["equipmentApi.setLineNote", () => equipmentApi.setLineNote("l1", "Note", T), "PUT", "/equipment/requests/l1/notes",
    { note: "Note" }],
  ["equipmentApi.setExitConfirmation", () => equipmentApi.setExitConfirmation("e1", true, T), "PUT",
    "/equipment/events/e1/exit-confirmation", { confirmed: true }],
  ["equipmentApi.setTechnicalPreparation", () => equipmentApi.setTechnicalPreparation("e1", BODY, T), "PUT",
    "/equipment/events/e1/preparation", BODY],
];

describe("API routes", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it.each(ROUTES)("%s sends the right request", async (_name, call, method, path, body, authenticated = true) => {
    await call();

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}${path}`);
    expect(options.method).toBe(method);
    expect(options.body).toBe(body ? JSON.stringify(body) : undefined);
    expect(options.headers.Authorization).toBe(authenticated ? `Bearer ${T}` : undefined);
  });
});
