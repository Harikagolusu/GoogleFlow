// Minimal fetch wrapper — the ONLY place that talks to the network.
// React pages never call fetch directly; they go through workflowService,
// which uses these helpers.

const DEFAULT_API_URL = 'http://localhost:8000';

export function getApiUrl(): string {
  const configured = import.meta.env.VITE_API_URL as string | undefined;
  return (configured || DEFAULT_API_URL).replace(/\/+$/, '');
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface HttpOptions {
  headers?: Record<string, string>;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const baseUrl = getApiUrl();
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the LifeFlow backend at ${baseUrl}. Make sure it is running, then try again.`,
      0,
    );
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? (data as { detail?: unknown }).detail
        : null;
    const message =
      typeof detail === 'string' && detail
        ? detail
        : `The backend returned an error (status ${response.status}).`;
    throw new ApiError(message, response.status);
  }

  return data as T;
}

export function apiGet<T>(path: string, options: HttpOptions = {}): Promise<T> {
  return request<T>(path, { method: 'GET', headers: options.headers });
}

export function apiPost<T>(path: string, body: unknown, options: HttpOptions = {}): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
    body: JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body: unknown, options: HttpOptions = {}): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
    body: JSON.stringify(body),
  });
}