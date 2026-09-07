// Generic Google service OAuth + data service.
// Reuses http.ts/authService pattern from gmailService. Supports gmail, calendar, drive.
// Maps is API-key based (no OAuth) — use mapsService for geocode/directions.

import { apiGet, apiPost } from './http';
import { authService } from './authService';

export type OAuthService = 'gmail' | 'calendar' | 'drive';

export interface ConnectionStatus {
  connected: boolean;
  service: string;
  scopes: string[];
  connected_at?: string;
  last_sync_at?: string | null;
  enabled?: boolean;
  configured?: boolean;
}

export interface DisconnectResult {
  disconnected: boolean;
  service: string;
  was_connected: boolean;
}

export interface ConnectResult {
  authorization_url: string;
  state: string;
}

// Aliases for backward compat
export type GmailConnectionStatus = ConnectionStatus;
export type GmailDisconnectResult = DisconnectResult;
export type GmailConnectResult = ConnectResult;
export type GmailRecentResult = { messages: GmailMessage[]; count: number; limit: number };

export interface GmailMessage {
  id: string;
  threadId: string;
  sender: string;
  subject: string;
  date: string;
  snippet: string;
  labels: string[];
}

export interface CalendarEvent {
  id: string;
  summary: string;
  description: string;
  location: string;
  start: string;
  end: string;
  displayStart: string;
  attendees: string[];
  htmlLink: string;
  status: string;
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime: string;
  owner: string;
  webViewLink: string;
  iconLink: string;
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await authService.waitForToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const googleService = {
  isUserAuthenticated(): boolean {
    return authService.isAvailable() && Boolean(authService.getCurrentUser());
  },

  async connect(service: OAuthService): Promise<ConnectResult> {
    const headers = await authHeaders();
    return apiPost<ConnectResult>(`/api/auth/${service}/connect`, {}, { headers });
  },

  async getStatus(service: OAuthService): Promise<ConnectionStatus> {
    const headers = await authHeaders();
    return apiGet<ConnectionStatus>(`/api/auth/${service}/status`, { headers });
  },

  async disconnect(service: OAuthService): Promise<DisconnectResult> {
    const headers = await authHeaders();
    return apiPost<DisconnectResult>(`/api/auth/${service}/disconnect`, {}, { headers });
  },

  async getAllStatus(): Promise<Record<string, ConnectionStatus>> {
    const headers = await authHeaders();
    return apiGet<Record<string, ConnectionStatus>>('/api/services/status', { headers });
  },

  async getRecentMessages(limit = 10): Promise<{ messages: GmailMessage[]; count: number; limit: number }> {
    const headers = await authHeaders();
    return apiGet(`/api/gmail/recent?limit=${limit}`, { headers });
  },

  async getCalendarEvents(limit = 10, days = 14): Promise<{ events: CalendarEvent[]; count: number; limit: number }> {
    const headers = await authHeaders();
    return apiGet(`/api/calendar/events?limit=${limit}&days=${days}`, { headers });
  },

  async getDriveFiles(limit = 10): Promise<{ files: DriveFile[]; count: number; limit: number }> {
    const headers = await authHeaders();
    return apiGet(`/api/drive/recent?limit=${limit}`, { headers });
  },

  async getMapsStatus(): Promise<{ enabled: boolean; configured: boolean; service: string }> {
    const headers = await authHeaders();
    return apiGet('/api/maps/status', { headers });
  },

  async geocode(address: string): Promise<{ formatted_address: string; lat: number; lng: number; place_id: string }> {
    const headers = await authHeaders();
    return apiPost('/api/maps/geocode', { address }, { headers });
  },

  async getDirections(origin: string, destination: string, mode = 'driving'): Promise<{ distance_text: string; distance_meters: number; duration_text: string; duration_seconds: number }> {
    const headers = await authHeaders();
    return apiPost('/api/maps/directions', { origin, destination, mode }, { headers });
  },
};

// Backward-compat shim for old imports: re-export with gmailService name will be in gmailService.ts
