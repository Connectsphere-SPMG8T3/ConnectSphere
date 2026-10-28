const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

class ApiError extends Error {
  // `detail` is the response's raw `detail`, so a form can place a 422's
  // per-field errors (`detail[].loc`) under the fields they name. `conflict`
  // is what a refused booking request names as in the way (SCRUM-21).
  constructor(message, status, detail = null, conflict = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.conflict = conflict;
  }
}

async function request(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail;
    const message = Array.isArray(detail)
      ? detail.map((entry) => entry.msg).join(", ")
      : detail || "An unexpected error occurred. Please try again.";
    throw new ApiError(message, response.status, detail ?? null, payload?.conflict ?? null);
  }

  return payload;
}

export const authApi = {
  signup(details) {
    return request("/auth/signup", { method: "POST", body: details });
  },
  login(email, password) {
    return request("/auth/login", { method: "POST", body: { email, password } });
  },
  refresh(refreshToken) {
    return request("/auth/refresh", { method: "POST", body: { refresh_token: refreshToken } });
  },
  me(token) {
    return request("/auth/me", { token });
  },
  updateProfile(token, changes) {
    return request("/auth/me", { method: "PATCH", body: changes, token });
  },
  setActiveRole(token, role) {
    return request("/auth/active-role", { method: "POST", body: { role }, token });
  },
  logout(token) {
    return request("/auth/logout", { method: "POST", token });
  },
};

// Repeats array values as `key=a&key=b`, which FastAPI reads as a list.
function toQueryString(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((entry) => query.append(key, entry));
    else query.append(key, value);
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export const venuesApi = {
  search(params, token) {
    return request(`/venues${toQueryString(params)}`, { token });
  },
  get(venueId, token) {
    return request(`/venues/${encodeURIComponent(venueId)}`, { token });
  },
  // The venue-staff work queue across every venue (SCRUM-70).
  venueStaffDashboard(token) {
    return request("/venues/dashboard/venue-staff", { token });
  },
  // SCRUM-63: `saved: false` means a warning came back instead of being written.
  update(venueId, payload, token) {
    return request(`/venues/${encodeURIComponent(venueId)}`, { method: "PATCH", body: payload, token });
  },
  history(venueId, token) {
    return request(`/venues/${encodeURIComponent(venueId)}/history`, { token });
  },
  // SCRUM-64: `saved: false` means `affected` came back instead of being written.
  deactivate(venueId, payload, token) {
    return request(`/venues/${encodeURIComponent(venueId)}/deactivate`, { method: "POST", body: payload, token });
  },
  reactivate(venueId, payload, token) {
    return request(`/venues/${encodeURIComponent(venueId)}/reactivate`, { method: "POST", body: payload, token });
  },
  // SCRUM-51: `saved: false` means `affected` came back instead of being written.
  createBlock(venueId, payload, token) {
    return request(`/venues/${encodeURIComponent(venueId)}/blocks`, { method: "POST", body: payload, token });
  },
};

export const venueBookingsApi = {
  sendForReReview(bookingId, note, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}/send-for-re-review`, { method: "POST", body: { note }, token });
  },
  markRevised(bookingId, note, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}/mark-revised`, { method: "POST", body: { note }, token });
  },
  // SCRUM-19: a tentative hold over the event's own period. The body carries no
  // times; the API reads them from the event.
  request(payload, token) {
    return request("/venue-bookings", { method: "POST", body: payload, token });
  },
  // CR-99 AC2: venue staff change or extend a hold's expiry.
  changeExpiry(bookingId, payload, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}/expiry`, { method: "PATCH", body: payload, token });
  },
  // SCRUM-38: one request as venue staff decide it, and the assigned coordinator reads it.
  get(bookingId, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}`, { token });
  },
  // SCRUM-38: `payload` is `{ reason, suggestion }`; 409 means it is no longer a live hold.
  reject(bookingId, payload, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}/reject`, { method: "POST", body: payload, token });
  },
  // SCRUM-36: no body; 409 means it is no longer a live hold, a block now
  // overlaps it, or the venue is inactive.
  approve(bookingId, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}/approve`, { method: "POST", token });
  },
  // CR-95 AC9: venue staff restore an affected booking; 409 says why the venue isn't free yet.
  restore(bookingId, token) {
    return request(`/venue-bookings/${encodeURIComponent(bookingId)}/restore`, { method: "POST", token });
  },
};

// SCRUM-113: the notification bell. Every call is scoped by the API to the caller
// and the role their session is acting as.
export const notificationsApi = {
  // The 10-second poll (ADR-0004): `{count, latest_at}`.
  unreadCount(token) {
    return request("/notifications/unread-count", { token });
  },
  // `before` is the previous page's `next_before`.
  list({ limit, before } = {}, token) {
    return request(`/notifications${toQueryString({ limit, before })}`, { token });
  },
  markRead(notificationId, token) {
    return request(`/notifications/${encodeURIComponent(notificationId)}/read`, { method: "POST", token });
  },
  markAllRead(token) {
    return request("/notifications/read-all", { method: "POST", token });
  },
};

export const eventsApi = {
  safetyQueue(token) {
    return request("/events/safety-queue", { token });
  },
  safetyHistory(token) {
    return request("/events/safety-history", { token });
  },
  safetyReview(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/safety-review`, { token });
  },
  safetyDecisions(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/safety-decisions`, { token });
  },
  safetyApprove(eventId, body, token) {
    return request(`/events/${encodeURIComponent(eventId)}/safety-approve`, { method: "POST", body, token });
  },
  safetyRequestChanges(eventId, body, token) {
    return request(`/events/${encodeURIComponent(eventId)}/safety-request-changes`, { method: "POST", body, token });
  },
  safetyReject(eventId, body, token) {
    return request(`/events/${encodeURIComponent(eventId)}/safety-reject`, { method: "POST", body, token });
  },
  coordinatorDashboard(token) {
    return request("/events/dashboard/coordinator", { token });
  },
  // CR-101: the Event Coordinator Lead's view and reassign action.
  leadDashboard(token) {
    return request("/events/dashboard/lead", { token });
  },
  // SCRUM-12: a Lead assigns a coordinator to a queued (submitted) event.
  assign(eventId, coordinatorId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/assign`, {
      method: "POST",
      body: { coordinator_id: coordinatorId },
      token,
    });
  },
  // `expectedVersion` is the event version the Lead was looking at: a screen that is behind is refused.
  reassign(eventId, coordinatorId, expectedVersion, token) {
    return request(`/events/${encodeURIComponent(eventId)}/reassign`, {
      method: "POST",
      body: { coordinator_id: coordinatorId, expected_version: expectedVersion },
      token,
    });
  },
  list(token) {
    return request("/events", { token });
  },
  get(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}`, { token });
  },
  create(payload, token) {
    return request("/events", { method: "POST", body: payload, token });
  },
  clone(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/clone`, { method: "POST", token });
  },
  update(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}`, { method: "PATCH", body: payload, token });
  },
  remove(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}`, { method: "DELETE", token });
  },
  submit(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/submit`, { method: "POST", body: payload, token });
  },
  createSpace(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/spaces`, { method: "POST", body: payload, token });
  },
  updateSpace(eventId, spaceId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/spaces/${encodeURIComponent(spaceId)}`, { method: "PATCH", body: payload, token });
  },
  removeSpace(eventId, spaceId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/spaces/${encodeURIComponent(spaceId)}`, { method: "DELETE", token });
  },
  // SCRUM-34/52: the assigned coordinator's decisions, and the history they leave.
  sendForSafetyCheck(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/send-for-safety-check`, { method: "POST", token });
  },
  approve(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/approve`, { method: "POST", token });
  },
  // CR-97 AC9: the assigned coordinator's primary venue.
  setPrimarySpace(eventId, spaceId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/spaces/${encodeURIComponent(spaceId)}/primary`, { method: "PUT", token });
  },
  clearPrimarySpace(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/spaces/primary`, { method: "DELETE", token });
  },
  reject(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/reject`, { method: "POST", body: { reason }, token });
  },
  // Story 84: the owner asks to cancel; 409 says why the event can't take a request.
  requestCancellation(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/cancellation-request`, { method: "POST", body: { reason }, token });
  },
  // Story 32: `body` is {reason, version, event, spaces}, only the changed fields.
  requestChange(eventId, body, token) {
    return request(`/events/${encodeURIComponent(eventId)}/change-request`, { method: "POST", body, token });
  },
  // Story 115: the assigned coordinator decides the request, or cancels directly.
  approveCancellation(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/cancellation-request/approve`, { method: "POST", token });
  },
  rejectCancellation(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/cancellation-request/reject`, { method: "POST", body: { reason }, token });
  },
  changeImpact(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/change-request/impact`, { token });
  },
  approveChange(eventId, version, token) {
    return request(`/events/${encodeURIComponent(eventId)}/change-request/approve`, { method: "POST", body: { version }, token });
  },
  rejectChange(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/change-request/reject`, { method: "POST", body: { reason }, token });
  },
  cancelEvent(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/cancel`, { method: "POST", body: { reason }, token });
  },
  // SCRUM-33: the coordinator returns a request; the organiser resubmits it.
  returnForAmendment(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/return`, { method: "POST", body: payload, token });
  },
  resubmit(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/resubmit`, { method: "POST", body: payload, token });
  },
  history(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/history`, { token });
  },
  // SCRUM-61: the organiser–coordinator discussion thread.
  listComments(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/comments`, { token });
  },
  addComment(eventId, body, token) {
    return request(`/events/${encodeURIComponent(eventId)}/comments`, { method: "POST", body: { body }, token });
  },
};

export const registrationsApi = {
  directory() {
    return request("/public/events");
  },
  myRegistrations(token) {
    return request("/registrations/me", { token });
  },
  event(eventId) {
    return request(`/public/events/${encodeURIComponent(eventId)}`);
  },
  register(eventId, token) {
    return request(`/public/events/${encodeURIComponent(eventId)}/registrations`, {
      method: "POST",
      token,
    });
  },
};

export const equipmentApi = {
  sendLineForReReview(lineId, note, token) {
    return request(`/equipment/requests/${encodeURIComponent(lineId)}/send-for-re-review`, { method: "POST", body: { note }, token });
  },
  checkEquipmentAvailability(payload, token) {
    return request("/equipment/availability/check", {
      method: "POST",
      body: payload,
      token,
    });
  },
  inventory(startAt, endAt, token) {
    const params = new URLSearchParams();
    if (startAt) params.set("start_at", startAt);
    if (endAt) params.set("end_at", endAt);
    const query = params.toString();
    return request(`/equipment/inventory${query ? `?${query}` : ""}`, { token });
  },
  maintenance(token) {
    return request("/equipment/maintenance", { token });
  },
  // SCRUM-45 equipment request lines.
  catalogue(token) {
    return request("/equipment/catalogue", { token });
  },
  submitRequest(payload, token) {
    return request("/equipment/requests", { method: "POST", body: payload, token });
  },
  eventRequests(eventId, token) {
    return request(`/equipment/requests/event/${encodeURIComponent(eventId)}`, { token });
  },
  // SCRUM-44: the assigned coordinator changes or removes a line, naming the
  // status they saw, and reads the event's equipment history.
  updateLine(lineId, payload, token) {
    return request(`/equipment/requests/${encodeURIComponent(lineId)}`, { method: "PATCH", body: payload, token });
  },
  removeLine(lineId, expectedStatus, token) {
    const query = new URLSearchParams({ expected_status: expectedStatus });
    return request(`/equipment/requests/${encodeURIComponent(lineId)}?${query}`, { method: "DELETE", token });
  },
  eventHistory(eventId, token) {
    return request(`/equipment/requests/event/${encodeURIComponent(eventId)}/history`, { token });
  },
  // Every line on every open event, any status (SCRUM-24 requests page).
  requestList(token) {
    return request("/equipment/requests", { token });
  },
  // SCRUM-24 equipment reservation (tech support only).
  technicalView(eventId, token) {
    return request(`/equipment/events/${encodeURIComponent(eventId)}/technical`, { token });
  },
  reserveLine(lineId, token) {
    return request(`/equipment/requests/${encodeURIComponent(lineId)}/reserve`, { method: "POST", token });
  },
  markNotAvailable(lineId, reason, token) {
    return request(`/equipment/requests/${encodeURIComponent(lineId)}/not-available`, {
      method: "POST", body: { reason }, token,
    });
  },
  setLineNote(lineId, note, token) {
    return request(`/equipment/requests/${encodeURIComponent(lineId)}/notes`, { method: "PUT", body: { note }, token });
  },
  setExitConfirmation(eventId, confirmed, token) {
    return request(`/equipment/events/${encodeURIComponent(eventId)}/exit-confirmation`, {
      method: "PUT", body: { confirmed }, token,
    });
  },
};

export { ApiError };
