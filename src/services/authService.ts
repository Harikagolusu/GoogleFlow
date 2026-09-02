// Firebase Authentication service — the ONLY place that talks to Firebase Auth.
//
// Pages use the useAuthUser() hook (React binding) or call these methods via
// workflowService for tokens. When Firebase is not configured (local dev),
// the app runs in demo mode: no auth UI, mock workflows keep working.

import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from 'firebase/auth';
import { firebaseAuth, isFirebaseConfigured } from '../config/firebase';

export interface AuthState {
  /** Firebase is configured via env vars. */
  available: boolean;
  /** Signed-in user, if any. */
  user: User | null;
  /** True once Firebase Auth has resolved the initial session. */
  resolved: boolean;
}

type AuthListener = (state: AuthState) => void;

let currentUser: User | null = null;
// Demo mode (Firebase unconfigured) is resolved immediately with no user.
let authResolved = !isFirebaseConfigured();
let initialized = false;
const listeners = new Set<AuthListener>();

function notify(): void {
  const state = getAuthState();
  listeners.forEach(listener => listener(state));
}

function init(): void {
  if (!firebaseAuth || initialized) return;
  initialized = true;
  onAuthStateChanged(firebaseAuth, user => {
    currentUser = user;
    authResolved = true;
    notify();
  });
}

function getAuthState(): AuthState {
  return { available: isFirebaseConfigured(), user: currentUser, resolved: authResolved };
}

export const authService = {
  /** True when Firebase Auth is configured via env vars. */
  isAvailable: (): boolean => isFirebaseConfigured(),

  /** Current signed-in user or null. */
  getCurrentUser: (): User | null => currentUser,

  getAuthState,

  /**
   * Subscribe to auth changes. Emits the current state immediately, then on
   * every change. Returns an unsubscribe function.
   */
  onChange(listener: AuthListener): () => void {
    init();
    listeners.add(listener);
    listener(getAuthState());
    return () => {
      listeners.delete(listener);
    };
  },

  /** Opens the Google Sign-In popup and returns the signed-in user. */
  async signInWithGoogle(): Promise<User> {
    if (!firebaseAuth) {
      throw new Error('Firebase is not configured. Add your VITE_FIREBASE_* env vars first.');
    }
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    const credential = await signInWithPopup(firebaseAuth, provider);
    return credential.user;
  },

  /** Signs the user out. */
  async signOut(): Promise<void> {
    if (!firebaseAuth) return;
    await firebaseSignOut(firebaseAuth);
  },

  /**
   * Fresh Firebase ID token for the signed-in user (used as the backend
   * Authorization bearer token), or null when signed out / demo mode.
   */
  async getIdToken(): Promise<string | null> {
    if (!firebaseAuth || !currentUser) return null;
    try {
      return await currentUser.getIdToken();
    } catch {
      return null;
    }
  },
};