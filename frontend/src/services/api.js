const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
    throw new ApiError(message, response.status);
  }

  return payload;
}

export const authApi = {
  login(email, password) {
    return request("/auth/login", { method: "POST", body: { email, password } });
  },
  refresh(refreshToken) {
    return request("/auth/refresh", { method: "POST", body: { refresh_token: refreshToken } });
  },
  me(token) {
    return request("/auth/me", { token });
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
};

export const eventsApi = {
  // Not implemented by the backend yet — the `events` module is still an empty
  // stub package, so this answers 404 until that story lands (SCRUM-72).
  coordinatorDashboard(token) {
    return request("/events/dashboard/coordinator", { token });
  },
};

export { ApiError };
