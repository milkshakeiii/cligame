import type { AuthResponse, ViewResponse, CommandResponse } from "./types";

const BASE = "";

async function request<T>(
  path: string,
  opts: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? JSON.stringify(body));
  }
  return res.json();
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const api = {
  register(username: string, password: string) {
    return request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  login(username: string, password: string) {
    return request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  getView(token: string, shipId?: number, sinceTick?: number) {
    const params = new URLSearchParams();
    if (shipId != null) params.set("ship_id", String(shipId));
    if (sinceTick != null) params.set("since_tick", String(sinceTick));
    const qs = params.toString();
    return request<ViewResponse>(
      `/api/view${qs ? `?${qs}` : ""}`,
      {},
      token,
    );
  },

  sendCommand(
    token: string,
    type: string,
    shipId: number | null,
    payload: Record<string, unknown> = {},
  ) {
    return request<CommandResponse>(
      "/api/commands",
      {
        method: "POST",
        body: JSON.stringify({ type, ship_id: shipId, payload }),
      },
      token,
    );
  },
};
