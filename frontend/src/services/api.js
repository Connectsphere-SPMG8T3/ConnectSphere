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
