import axios from 'axios';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const WS_BASE_URL = API_BASE_URL.startsWith('https://')
  ? API_BASE_URL.replace('https://', 'wss://')
  : API_BASE_URL.replace('http://', 'ws://');

// Shared axios client with sensible timeout and JSON settings
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000, // 10s
  headers: { 'Accept': 'application/json' }
});
