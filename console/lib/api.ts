export type Principal = { subject: string; tenant: string; role: "admin" | "editor" | "viewer" };

export type Artifact = { id: string; name: string; version: number; family: string;
  source: string; revision: string; digest: string; digest_verified: boolean; created_at: string };
export type Dataset = { id: string; name: string; version: number; uri: string;
  digest: string; train_count: number; heldout_count: number; created_at: string };
export type Deployment = { id: string; name: string; artifact_id: string; engine: string;
  replicas: number; gpu: number; generation: number; intent: string;
  observed_phase: string; runtime_verified: boolean;
  canary_spec?: { source: string; revision: string; digest: string; weight: number } | null;
  canary_status?: { phase: string; readyReplicas?: number } | null; };
export type TrainJob = { id: string; name: string; method: string; artifact_id: string;
  dataset_id: string; observed_phase: string; parameters: Record<string, unknown>;
  parent_job_id?: string | null; attempt?: number; intent?: string;
  runtime_verified?: boolean; cancel_requested?: boolean;
  workflow_uid?: string; progress?: string; started_at?: string;
  finished_at?: string; message?: string };
export type AuditEvent = { id: string; at: string; actor: string; action: string;
  object_kind: string; object_id: string };
export type Approval = { id: string; artifact_id: string; evaluation_id: string; approver: string; reason: string; created_at: string };
export type Evaluation = { id: string; artifact_id: string; dataset_id: string;
  verified: boolean; passed: boolean; metrics: Record<string, number> };
export type Overview = { runtime_connected: boolean; platform_state: string; models: number;
  datasets: number; deployments: number; training_jobs: number; audit_events: number };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

export async function apiRequest<T>(path: string, body?: unknown, method: "GET" | "POST" | "PATCH" | "DELETE" = "GET"): Promise<T> {
  const response = await fetch("/api/control/" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  let data: unknown;
  try { data = await response.json(); } catch { data = { detail: "Invalid control API response" }; }
  if (!response.ok) {
    const message = typeof data === "object" && data !== null && "detail" in data
      ? String((data as { detail: unknown }).detail) : "Request failed";
    throw new ApiError(response.status, message);
  }
  return data as T;
}

export function fmtDate(value?: string): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function shortId(value: string): string { return value?.slice(0, 10) || "—"; }
