import { API_V1 } from "./config";
import type {
  UCProfile,
  SystemStatus,
  TestResult,
  ResultHistoryItem,
} from "./types";

/* ── Generic fetch wrapper ── */
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

/* ── Profiles ── */
export async function getProfiles(): Promise<UCProfile[]> {
  return apiFetch<UCProfile[]>("/profiles");
}

/* ── System status (used for polling active sessions) ── */
export async function getSystemStatus(): Promise<SystemStatus> {
  return apiFetch<SystemStatus>("/system/status");
}

/* ── Results ── */
export async function getResultsHistory(): Promise<ResultHistoryItem[]> {
  return apiFetch<ResultHistoryItem[]>("/results/history");
}

export async function getResultById(testId: string): Promise<TestResult> {
  return apiFetch<TestResult>(`/results/${testId}`);
}

/* ── Session control (used only in debug mode) ── */
export async function initSession(body: {
  uc_id: string;
  obu_ip: string;
  label?: string;
  network_condition?: string;
  params?: Record<string, unknown>;
  requested_duration_s?: number;
}) {
  return apiFetch("/session/init", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function startSession(sessionId: string) {
  return apiFetch("/session/start", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function stopSession(sessionId: string) {
  return apiFetch("/session/stop", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}
