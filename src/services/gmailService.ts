// Gmail shim — kept for backward compat. New code should use googleService.
import { googleService, type GmailConnectionStatus, type GmailDisconnectResult, type GmailConnectResult, type GmailRecentResult } from './googleService';

export type { GmailConnectionStatus, GmailDisconnectResult, GmailConnectResult, GmailMessage, GmailRecentResult } from './googleService';

export const gmailService = {
  isUserAuthenticated: googleService.isUserAuthenticated,
  async connectGmail(): Promise<GmailConnectResult> {
    return googleService.connect('gmail');
  },
  async getStatus(): Promise<GmailConnectionStatus> {
    const s = await googleService.getStatus('gmail');
    // Map generic status to Gmail-specific interface
    return s as GmailConnectionStatus;
  },
  async disconnect(): Promise<GmailDisconnectResult> {
    const r = await googleService.disconnect('gmail');
    return r as GmailDisconnectResult;
  },
  async getRecentMessages(limit = 10): Promise<GmailRecentResult> {
    return googleService.getRecentMessages(limit);
  },
};
