export type BackendStatus = "ok" | "unavailable";

export interface BackendStatusResponse {
  status: BackendStatus;
}

export const BACKEND_STATUS_PATH = "/api/backend-health";
