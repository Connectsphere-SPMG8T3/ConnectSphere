const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

class ApiError extends Error {
  // `detail` is the response's raw `detail`, so a form can place a 422's
  // per-field errors (`detail[].loc`) under the fields they name.
  constructor(message, status, detail = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
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
    throw new ApiError(message, response.status, detail ?? null);
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
};

export const venueBookingsApi = {
  // SCRUM-19: a tentative hold over the event's own period. The body carries no
  // times; the API reads them from the event.
  request(payload, token) {
    return request("/venue-bookings", { method: "POST", body: payload, token });
  },
};

export const eventsApi = {
  coordinatorDashboard(token) {
    return request("/events/dashboard/coordinator", { token });
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
  // SCRUM-34/52: the assigned coordinator's decisions, and the history they leave.
  approve(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/approve`, { method: "POST", token });
  },
  reject(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/reject`, { method: "POST", body: { reason }, token });
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

export const equipmentApi = {
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
};

export function checkEquipmentAvailability(payload, token) {
  return equipmentApi.checkEquipmentAvailability(payload, token);
}

export { ApiError };
