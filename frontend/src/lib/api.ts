import axios from 'axios';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const WS_BASE_URL = API_BASE_URL.startsWith('https://')
  ? API_BASE_URL.replace('https://', 'wss://')
  : API_BASE_URL.replace('http://', 'ws://');

export const BRIDGE_SOCKET_URL =
  import.meta.env.VITE_WHATSAPP_BRIDGE_SOCKET_URL ?? 'http://127.0.0.1:3011';

const AUTH_STORAGE_KEY = 'safechat_auth';
const GUEST_REPORT_STORAGE_KEY = 'safechat_guest_report';
export const AUTH_CHANGED_EVENT = 'safechat-auth-changed';

export type AuthSession = {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    username?: string | null;
    email: string;
    role: string;
    is_active: boolean;
    name?: string | null;
    created_at: string;
  };
};

export function getStoredSession(): AuthSession | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function storeSession(session: AuthSession | null) {
  if (typeof window === 'undefined') return;
  if (session) {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  } else {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT, { detail: session }));
}

export function getGuestReport() {
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(GUEST_REPORT_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    window.sessionStorage.removeItem(GUEST_REPORT_STORAGE_KEY);
    return null;
  }
}

export function storeGuestReport(report: unknown | null) {
  if (typeof window === 'undefined') return;
  if (report) {
    window.sessionStorage.setItem(GUEST_REPORT_STORAGE_KEY, JSON.stringify(report));
  } else {
    window.sessionStorage.removeItem(GUEST_REPORT_STORAGE_KEY);
  }
}

// Shared axios client with sensible timeout and JSON settings
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000, // 10s
  headers: { 'Accept': 'application/json' }
});

apiClient.interceptors.request.use((config) => {
  const session = getStoredSession();
  if (session?.access_token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
});
