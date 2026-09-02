// Minimal React binding for authService — the only auth hook in the app.
// Usage: const { user, loading, signedIn, isAuthEnabled } = useAuthUser();

import { useEffect, useState } from 'react';
import type { User } from 'firebase/auth';
import { authService, type AuthState } from '../services/authService';

export interface AuthUserState {
  user: User | null;
  /** True while Firebase Auth is resolving the initial session. */
  loading: boolean;
  signedIn: boolean;
  /** Firebase configured via env vars (false = local demo mode). */
  isAuthEnabled: boolean;
}

export function useAuthUser(): AuthUserState {
  const [state, setState] = useState<AuthState>(() => authService.getAuthState());

  useEffect(() => authService.onChange(next => setState(next)), []);

  return {
    user: state.user,
    loading: state.available && !state.resolved,
    signedIn: Boolean(state.user),
    isAuthEnabled: state.available,
  };
}