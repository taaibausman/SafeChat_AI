import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { io } from 'socket.io-client';
import {
  AlertTriangle,
  BellRing,
  MessageSquare,
  QrCode,
  RadioTower,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Smartphone,
  Trash2,
  Users,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { BRIDGE_SOCKET_URL, WS_BASE_URL, apiClient, getStoredSession, storeSession, type AuthSession } from '../lib/api';

type WhatsAppStatus = {
  bridge_session_key?: string | null;
  single_account_mode?: boolean;
  status: string;
  reason?: string | null;
  qr?: string | null;
  qr_updated_at?: string | null;
  connected_phone?: string | null;
  bridge_reachable?: boolean;
  bridge_status?: string | null;
  bridge_detail?: string | null;
  last_event_at?: string | null;
};

type LiveMessage = {
  id: number;
  chat_id: number;
  chat_name: string;
  sender: string;
  sender_id?: string | null;
  sender_name?: string | null;
  message: string;
  external_message_id?: string | null;
  source?: string | null;
  direction?: string | null;
  is_from_me?: boolean;
  timestamp?: string | null;
  risk_score?: number | null;
  label?: string | null;
};

type LiveChatSummary = {
  id: number;
  chat_name: string;
  platform: string;
  external_chat_id?: string | null;
  chat_type?: string | null;
  is_live: boolean;
  message_count: number;
  flagged_messages: number;
  open_alert_count: number;
  unsafe_percentage: number;
  last_message_at?: string | null;
  latest_message_preview?: string | null;
};

type BridgeHealth = {
  reachable: boolean;
  status?: string | null;
  detail?: string | null;
};

type BackendHealthSummary = {
  live_ops: {
    live_summary: {
      total_live_chats: number;
      total_live_messages: number;
      flagged_live_messages: number;
      open_alerts: number;
    };
  };
  attention_required: boolean;
  status: 'healthy' | 'attention';
};

type LiveAlert = {
  id: number;
  message_id: number;
  chat_id: number;
  chat_name: string;
  alert_type: string;
  severity: string;
  status: string;
  notes?: string | null;
  created_at: string;
  sender: string;
  message: string;
  risk_score?: number | null;
  label?: string | null;
  timestamp?: string | null;
};

type MonitoredContact = {
  id: number;
  user_id?: number | null;
  contact_name: string;
  phone_number?: string | null;
  chat_key: string;
  chat_type: string;
  is_active: boolean;
  created_at?: string | null;
};

type ChatDirectoryItem = {
  chat_key: string;
  chat_type: string;
  display_name: string;
  phone_number?: string | null;
  source: string;
  recent_message_count: number;
  last_activity_at?: string | null;
  is_monitored: boolean;
};

function formatDateTime(value?: string | null) {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unavailable';
  return parsed.toLocaleString();
}

function formatBridgeStatus(status?: string | null) {
  const normalized = String(status || '').trim().toLowerCase();
  switch (normalized) {
    case 'connected':
    case 'ready':
      return 'Connected';
    case 'qr_required':
      return 'Waiting for QR';
    case 'starting':
      return 'Starting';
    case 'connecting':
      return 'Connecting';
    case 'restarting':
      return 'Refreshing';
    case 'disconnected':
      return 'Disconnected';
    case 'idle':
      return 'Not connected';
    default:
      return status ? status.replace(/_/g, ' ') : 'Waiting';
  }
}

function scoreTone(score?: number | null) {
  if ((score ?? 0) >= 80) return 'border-rose-500/25 bg-rose-500/10 text-rose-300';
  if ((score ?? 0) > 50) return 'border-amber-500/25 bg-amber-500/10 text-amber-300';
  return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300';
}

function messageCardTone(score?: number | null) {
  if ((score ?? 0) >= 80) return 'border-rose-500/20 bg-rose-500/[0.07]';
  if ((score ?? 0) > 50) return 'border-amber-500/20 bg-amber-500/[0.06]';
  return 'border-white/8 bg-slate-950/55';
}

function mergeLiveMessage(current: LiveMessage[], payload: LiveMessage, selectedChatId: number | null, flaggedOnly: boolean) {
  const matchesChat = selectedChatId === null || payload.chat_id === selectedChatId;
  const matchesFlagged = !flaggedOnly || (payload.risk_score ?? 0) > 50;
  if (!matchesChat || !matchesFlagged) {
    return current;
  }

  const deduped = current.filter(
    (item) =>
      item.id !== payload.id &&
      (!payload.external_message_id || item.external_message_id !== payload.external_message_id)
  );
  return [payload, ...deduped].slice(0, 80);
}

function mergeChatSummary(current: LiveChatSummary[], payload: LiveChatSummary) {
  const next = current.some((item) => item.id === payload.id)
    ? current.map((item) => (item.id === payload.id ? payload : item))
    : [payload, ...current];
  return next.sort((a, b) => {
    const aTime = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
    const bTime = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
    return bTime - aTime;
  });
}

function isUnauthorizedResult(result: PromiseSettledResult<unknown>) {
  return result.status === 'rejected' && (result.reason as any)?.response?.status === 401;
}

function SimpleStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{hint}</p>
    </div>
  );
}

export default function RealtimeMonitor() {
  const session = getStoredSession() as AuthSession | null;
  const location = useLocation();
  const navigate = useNavigate();

  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [chats, setChats] = useState<LiveChatSummary[]>([]);
  const [alerts, setAlerts] = useState<LiveAlert[]>([]);
  const [monitoredContacts, setMonitoredContacts] = useState<MonitoredContact[]>([]);
  const [directoryItems, setDirectoryItems] = useState<ChatDirectoryItem[]>([]);
  const [bridgeHealth, setBridgeHealth] = useState<BridgeHealth | null>(null);
  const [healthSummary, setHealthSummary] = useState<BackendHealthSummary | null>(null);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [chatSearch, setChatSearch] = useState('');
  const [directorySearch, setDirectorySearch] = useState('');
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isDirectoryLoading, setIsDirectoryLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [isSavingMonitor, setIsSavingMonitor] = useState(false);
  const [hasAutoStartedBridge, setHasAutoStartedBridge] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [bridgeSocketState, setBridgeSocketState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');

  const singleAccountMode = Boolean(status?.single_account_mode);
  const bridgeSessionKey = singleAccountMode
    ? (status?.bridge_session_key ?? 'safechat-demo')
    : (session ? `user-${session.user.id}` : null);

  const loadData = async (showSpinner = false) => {
    if (showSpinner) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    if (!showSpinner || directoryItems.length === 0) {
      setIsDirectoryLoading(true);
    }

    const [statusResult, feedResult, chatResult, healthResult, opsResult, alertResult, monitoredResult, directoryResult] = await Promise.allSettled([
      apiClient.get('/api/whatsapp/status'),
      apiClient.get('/api/whatsapp/live-feed', {
        params: {
          chat_id: selectedChatId ?? undefined,
          flagged_only: flaggedOnly || undefined,
          limit: 100,
        },
      }),
      apiClient.get('/api/whatsapp/chats', {
        params: {
          flagged_only: flaggedOnly || undefined,
          limit: 100,
        },
      }),
      apiClient.get('/api/whatsapp/bridge-health'),
      apiClient.get('/api/whatsapp/health-summary'),
      apiClient.get('/api/whatsapp/alerts', {
        params: {
          chat_id: selectedChatId ?? undefined,
          limit: 15,
        },
      }),
      apiClient.get('/api/whatsapp/monitored-contacts'),
      apiClient.get('/api/whatsapp/chat-directory', {
        params: {
          search: directorySearch || undefined,
          limit: 100,
        },
      }),
    ]);

    const authFailed = [
      statusResult,
      feedResult,
      chatResult,
      healthResult,
      opsResult,
      alertResult,
      monitoredResult,
      directoryResult,
    ].some(isUnauthorizedResult);

    if (authFailed) {
      setStatus(null);
      setMessages([]);
      setChats([]);
      setAlerts([]);
      setMonitoredContacts([]);
      setDirectoryItems([]);
      setBridgeHealth(null);
      setHealthSummary(null);
      setError('Your session expired. Please log in again.');
      setIsLoading(false);
      setIsRefreshing(false);
      setIsDirectoryLoading(false);
      storeSession(null);
      navigate('/login', { replace: true });
      return;
    }

    const nextErrors: string[] = [];

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value.data);
    } else {
      nextErrors.push('WhatsApp status is unavailable.');
    }

    if (feedResult.status === 'fulfilled') {
      setMessages(feedResult.value.data.messages ?? []);
    } else {
      setMessages([]);
      nextErrors.push('Live feed could not be loaded.');
    }

    if (chatResult.status === 'fulfilled') {
      setChats(chatResult.value.data.chats ?? []);
    } else {
      setChats([]);
      nextErrors.push('Chat list is unavailable.');
    }

    if (healthResult.status === 'fulfilled') {
      setBridgeHealth(healthResult.value.data);
    } else {
      setBridgeHealth({ reachable: false, detail: 'Bridge health route is unavailable.' });
    }

    if (opsResult.status === 'fulfilled') {
      setHealthSummary(opsResult.value.data);
    } else {
      setHealthSummary(null);
      nextErrors.push('Backend health summary could not be loaded.');
    }

    if (alertResult.status === 'fulfilled') {
      setAlerts(alertResult.value.data.alerts ?? []);
    } else {
      setAlerts([]);
      nextErrors.push('Alert list could not be loaded.');
    }

    if (monitoredResult.status === 'fulfilled') {
      setMonitoredContacts(monitoredResult.value.data.contacts ?? []);
    } else {
      setMonitoredContacts([]);
      nextErrors.push('Monitor list could not be loaded.');
    }

    if (directoryResult.status === 'fulfilled') {
      setDirectoryItems(directoryResult.value.data.items ?? []);
    } else {
      nextErrors.push('Connected WhatsApp chats could not be loaded.');
    }

    setError(nextErrors.join(' '));
    setLastUpdated(new Date().toISOString());
    setIsLoading(false);
    setIsRefreshing(false);
    setIsDirectoryLoading(false);
  };

  useEffect(() => {
    void loadData(false);
    const timer = window.setInterval(() => {
      void loadData(true);
    }, 15000);

    return () => window.clearInterval(timer);
  }, [directorySearch, flaggedOnly, selectedChatId]);

  useEffect(() => {
    if (location.pathname !== '/live') {
      navigate('/live', { replace: true });
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    const token = getStoredSession()?.access_token;
    if (!token) {
      return undefined;
    }

    const socket = new WebSocket(`${WS_BASE_URL}/ws/whatsapp?token=${encodeURIComponent(token)}`);
    socket.onopen = () => socket.send('subscribe');
    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.type === 'status') {
          setStatus(parsed.payload);
          return;
        }
        if (parsed.type === 'message') {
          setMessages((current) => mergeLiveMessage(current, parsed.payload as LiveMessage, selectedChatId, flaggedOnly));
          return;
        }
        if (parsed.type === 'chat_updated') {
          const payload = parsed.payload as { chat: LiveChatSummary };
          setChats((current) => mergeChatSummary(current, payload.chat));
        }
      } catch {
        setError('Received an invalid realtime event.');
      }
    };
    socket.onerror = () => {
      setError((current) => current || 'Realtime connection failed. Falling back to periodic refresh.');
    };

    return () => socket.close();
  }, [flaggedOnly, selectedChatId]);

  useEffect(() => {
    const socket = io(BRIDGE_SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      timeout: 5000,
    });

    socket.on('connect', () => setBridgeSocketState('connected'));
    socket.on('disconnect', () => setBridgeSocketState('disconnected'));
    socket.on('connect_error', () => setBridgeSocketState('disconnected'));

    socket.on('bridge_status', (payload: Partial<WhatsAppStatus> & { session_key?: string | null; bridge_session_key?: string | null }) => {
      const payloadSessionKey = payload.bridge_session_key || payload.session_key || null;
      if (!singleAccountMode && payloadSessionKey && bridgeSessionKey && payloadSessionKey !== bridgeSessionKey) {
        return;
      }
      setStatus((current) => ({ ...(current ?? { status: 'unknown' }), ...payload }));
    });

    socket.on('bridge_error', (payload: { session_key?: string | null } | undefined) => {
      if (!singleAccountMode && payload?.session_key && bridgeSessionKey && payload.session_key !== bridgeSessionKey) {
        return;
      }
      setError((current) => current || 'Bridge socket reported an operational error.');
    });

    socket.on('monitored_contacts', (payload: { session_key?: string | null; contacts?: MonitoredContact[] } | undefined) => {
      if (!singleAccountMode && payload?.session_key && bridgeSessionKey && payload.session_key !== bridgeSessionKey) {
        return;
      }
      if (Array.isArray(payload?.contacts)) {
        setMonitoredContacts(payload.contacts);
      }
    });

    return () => {
      socket.close();
    };
  }, [bridgeSessionKey, singleAccountMode]);

  const connected = status?.status === 'connected' || status?.status === 'ready';
  const statusLabel = formatBridgeStatus(status?.status);
  const qrImage = status?.qr
    ? `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(status.qr)}`
    : '';

  const filteredChats = useMemo(() => {
    const query = chatSearch.trim().toLowerCase();
    return chats.filter((chat) => {
      const matchesSearch = !query || chat.chat_name.toLowerCase().includes(query);
      const matchesFlagged = !flaggedOnly || chat.flagged_messages > 0;
      return matchesSearch && matchesFlagged;
    });
  }, [chatSearch, chats, flaggedOnly]);

  const visibleMessages = useMemo(() => {
    const query = chatSearch.trim().toLowerCase();
    return messages
      .filter((message) => !flaggedOnly || (message.risk_score ?? 0) > 50)
      .filter((message) => {
        if (!query) return true;
        return (
          message.chat_name.toLowerCase().includes(query) ||
          message.sender.toLowerCase().includes(query) ||
          message.message.toLowerCase().includes(query)
        );
      });
  }, [chatSearch, flaggedOnly, messages]);

  const openAlerts = alerts.filter((alert) => alert.status === 'open');
  const showDirectoryLoadingState = isDirectoryLoading && directoryItems.length === 0;
  const monitoredKeys = useMemo(
    () => new Set(monitoredContacts.map((contact) => `${contact.chat_type}:${contact.chat_key}`)),
    [monitoredContacts]
  );

  const saveMonitor = async (item: ChatDirectoryItem) => {
    try {
      setIsSavingMonitor(true);
      const response = await apiClient.post('/api/whatsapp/monitored-contacts', {
        contact_name: item.display_name.trim(),
        chat_key: item.chat_key.trim(),
        chat_type: item.chat_type,
        is_active: true,
      });
      const created = response.data as MonitoredContact;
      setMonitoredContacts((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setDirectoryItems((current) =>
        current.map((entry) =>
          entry.chat_key === item.chat_key && entry.chat_type === item.chat_type
            ? { ...entry, is_monitored: true }
            : entry
        )
      );
      setError('');
    } catch (saveError: any) {
      setError(saveError?.response?.data?.detail || 'Could not save the monitored contact.');
    } finally {
      setIsSavingMonitor(false);
    }
  };

  const toggleMonitor = async (contact: MonitoredContact) => {
    try {
      const response = await apiClient.patch(`/api/whatsapp/monitored-contacts/${contact.id}`, {
        is_active: !contact.is_active,
      });
      const updated = response.data as MonitoredContact;
      setMonitoredContacts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      setError('Could not update monitor state.');
    }
  };

  const deleteMonitor = async (contactId: number) => {
    try {
      const removed = monitoredContacts.find((item) => item.id === contactId);
      await apiClient.delete(`/api/whatsapp/monitored-contacts/${contactId}`);
      setMonitoredContacts((current) => current.filter((item) => item.id !== contactId));
      if (removed) {
        setDirectoryItems((current) =>
          current.map((entry) =>
            entry.chat_key === removed.chat_key && entry.chat_type === removed.chat_type
              ? { ...entry, is_monitored: false }
              : entry
          )
        );
      }
    } catch {
      setError('Could not delete monitor.');
    }
  };

  const restartBridge = async () => {
    try {
      setIsRestarting(true);
      await apiClient.post('/api/whatsapp/bridge-restart');
      await loadData(true);
    } catch {
      setError('Could not restart the WhatsApp bridge.');
    } finally {
      window.setTimeout(() => setIsRestarting(false), 1500);
    }
  };

  useEffect(() => {
    if (!session || hasAutoStartedBridge || isRestarting || isLoading) {
      return;
    }

    const normalized = String(status?.status || '').toLowerCase();
    if (connected || normalized === 'starting' || normalized === 'connecting' || normalized === 'restarting' || normalized === 'qr_required') {
      return;
    }

    setHasAutoStartedBridge(true);
    void restartBridge();
  }, [connected, hasAutoStartedBridge, isLoading, isRestarting, session, status?.status]);

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6 sm:py-5 lg:px-8">
      <section className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(135deg,rgba(10,18,34,0.98),rgba(8,14,26,0.96))] p-4 shadow-[0_30px_120px_rgba(34,211,238,0.08)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-2xl bg-cyan-500/14 p-3 text-cyan-300">
              <Smartphone className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-white">WhatsApp Live Monitor</h1>
              <p className="mt-1 text-sm text-slate-400">
                {singleAccountMode
                  ? 'One shared demo account.'
                  : 'Realtime message review.'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void loadData(true)}
              disabled={isRefreshing}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </button>
            <button
              type="button"
              onClick={restartBridge}
              disabled={isRestarting}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-4 py-3 text-sm font-medium text-slate-950 transition hover:brightness-110 disabled:opacity-60"
            >
              <Wifi className="h-4 w-4" />
              {isRestarting ? 'Connecting...' : (connected ? 'Reconnect WhatsApp' : 'Connect WhatsApp')}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <SimpleStat
            label="Bridge"
            value={statusLabel}
            hint={bridgeSocketState === 'connected' ? 'Socket connected' : 'Socket reconnecting'}
          />
          <SimpleStat
            label="Chats"
            value={healthSummary?.live_ops.live_summary.total_live_chats ?? chats.length}
            hint={selectedChatId ? 'One chat selected' : 'All visible chats'}
          />
          <SimpleStat
            label="Messages"
            value={healthSummary?.live_ops.live_summary.total_live_messages ?? messages.length}
            hint="Incoming messages analyzed"
          />
          <SimpleStat
            label="Open alerts"
            value={healthSummary?.live_ops.live_summary.open_alerts ?? openAlerts.length}
            hint={healthSummary?.status === 'attention' ? 'Needs review' : 'No urgent issue'}
          />
        </div>

        <div className="mt-4 rounded-[20px] border border-white/8 bg-slate-950/45 p-3 text-sm leading-6 text-slate-300">
          {singleAccountMode
            ? 'Scan once, then receive messages.'
            : 'Each workspace uses its own bridge.'}
        </div>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <section className="space-y-4">
          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                {connected ? <Wifi className="h-5 w-5 text-emerald-300" /> : <WifiOff className="h-5 w-5 text-amber-300" />}
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">Connection</p>
                <h2 className="mt-1 text-2xl font-semibold text-white">{statusLabel}</h2>
              </div>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[22px] border border-white/8 bg-slate-950/60 p-3">
                <p className="text-sm text-slate-400">Current state</p>
                <p className="mt-2 text-base text-white">{status?.reason || bridgeHealth?.detail || 'Waiting for update.'}</p>
                <p className="mt-3 text-xs text-slate-500">
                  {lastUpdated ? `Last updated ${formatDateTime(lastUpdated)}` : 'Not refreshed yet'}
                </p>
              </div>
              <div className="rounded-[22px] border border-white/8 bg-slate-950/60 p-3">
                <p className="text-sm text-slate-400">Connected account</p>
                <p className="mt-2 text-base text-white">{status?.connected_phone || 'Not paired yet'}</p>
                <p className="mt-3 text-xs text-slate-500">
                  {bridgeHealth?.reachable ? 'Bridge reachable' : 'Bridge unavailable'}
                </p>
              </div>
            </div>

            <div className="mt-4 rounded-[24px] border border-dashed border-white/10 bg-slate-950/60 p-4 text-center">
              <div className="mb-3 flex items-center justify-center gap-2 text-cyan-300">
                <QrCode className="h-5 w-5" />
                <span className="text-sm font-medium">QR Pairing</span>
              </div>
              {qrImage ? (
                <img src={qrImage} alt="WhatsApp QR code" className="mx-auto w-full max-w-[12rem] rounded-[20px] bg-white p-3 shadow-lg" />
              ) : (
                <div className="mx-auto max-w-sm">
                  <p className="text-lg font-medium text-slate-200">QR code not available</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">
                    Click connect and wait for QR.
                  </p>
                </div>
              )}
              {status?.qr_updated_at && (
                <p className="mt-3 text-xs text-slate-500">Last QR update: {formatDateTime(status.qr_updated_at)}</p>
              )}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <Users className="h-5 w-5 text-cyan-300" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">Chat selection</p>
                <h2 className="mt-1 text-2xl font-semibold text-white">Choose groups and chats</h2>
              </div>
            </div>

            <p className="mt-3 text-sm leading-6 text-slate-400">
              After QR pairing, choose only the chats you want SafeChat to analyze. Messages outside this selected list are ignored.
            </p>

            <div className="mt-4">
              <input
                value={directorySearch}
                onChange={(event) => setDirectorySearch(event.target.value)}
                placeholder="Search groups, frequent chats, or a contact number"
                className="min-h-11 w-full rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-500/30"
              />
            </div>

            <div className="mt-4 max-h-[24rem] space-y-3 overflow-auto pr-1">
              {showDirectoryLoadingState ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                  Loading connected chats...
                </div>
              ) : directoryItems.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                  {connected ? 'No connected chats found yet. Open WhatsApp and let recent chats sync.' : 'Connect WhatsApp with the QR code first to load groups and chats.'}
                </div>
              ) : (
                directoryItems.map((item) => {
                  const selected = monitoredKeys.has(`${item.chat_type}:${item.chat_key}`);
                  return (
                  <div key={`${item.chat_type}:${item.chat_key}`} className="flex flex-col gap-3 rounded-[22px] border border-white/8 bg-slate-950/55 p-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-medium text-white">{item.display_name}</p>
                        <span className="rounded-full border border-white/8 bg-white/[0.03] px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                          {item.chat_type === 'group' ? 'Group' : 'Chat'}
                        </span>
                        <span className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-300">
                          {item.source}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{item.phone_number || item.chat_key}</p>
                      <p className="mt-2 text-xs text-slate-500">
                        {item.recent_message_count > 0 ? `${item.recent_message_count} recent messages` : 'Available to monitor'}
                        {item.last_activity_at ? ` | Last activity ${formatDateTime(item.last_activity_at)}` : ''}
                      </p>
                    </div>
                    <button
                      onClick={() => void saveMonitor(item)}
                      disabled={selected || isSavingMonitor}
                      className={`min-h-11 rounded-2xl border px-4 py-3 text-sm font-medium transition ${
                        selected
                          ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                          : 'border-white/8 bg-white/[0.04] text-white hover:bg-white/[0.08]'
                      } disabled:opacity-70`}
                    >
                      {selected ? 'Selected' : (isSavingMonitor ? 'Adding...' : 'Analyze this chat')}
                    </button>
                  </div>
                )})
              )}
            </div>

            <div className="mt-4 rounded-[22px] border border-white/8 bg-slate-950/45 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-white">Selected chats</p>
                  <p className="mt-1 text-xs text-slate-500">Only these chats are analyzed live.</p>
                </div>
                <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1 text-xs text-slate-300">
                  {monitoredContacts.length}
                </span>
              </div>

              <div className="mt-3 max-h-[16rem] space-y-3 overflow-auto pr-1">
                {monitoredContacts.length === 0 ? (
                  <div className="rounded-[18px] border border-dashed border-white/10 bg-slate-950/50 p-4 text-sm text-slate-400">
                    No chats selected yet.
                  </div>
                ) : (
                  monitoredContacts.slice(0, 8).map((contact) => (
                    <div key={contact.id} className="flex flex-col gap-3 rounded-[18px] border border-white/8 bg-slate-950/55 p-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-white">{contact.contact_name}</p>
                        <p className="mt-1 text-xs text-slate-400">{(contact.chat_type || 'direct').toUpperCase()} | {contact.chat_key}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button onClick={() => void toggleMonitor(contact)} className={`rounded-full border px-3 py-1.5 text-xs ${contact.is_active ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300' : 'border-white/8 bg-white/[0.03] text-slate-400'}`}>
                          {contact.is_active ? 'Active' : 'Paused'}
                        </button>
                        <button onClick={() => void deleteMonitor(contact.id)} className="rounded-full border border-white/8 bg-white/[0.03] p-2 text-slate-400 transition hover:text-rose-300" aria-label={`Delete ${contact.contact_name}`}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">Live feed</p>
                <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-white">
                  <RadioTower className="h-5 w-5 text-cyan-300" />
                  Incoming messages
                </h2>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  value={chatSearch}
                  onChange={(event) => setChatSearch(event.target.value)}
                  placeholder="Search"
                  className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-500/30"
                />
                <button
                  type="button"
                  onClick={() => setFlaggedOnly((current) => !current)}
                  className={`min-h-11 rounded-2xl border px-4 py-3 text-sm transition ${flaggedOnly ? 'border-amber-500/25 bg-amber-500/10 text-amber-300' : 'border-white/8 bg-slate-950/60 text-slate-300'}`}
                >
                  {flaggedOnly ? 'Flagged only' : 'All messages'}
                </button>
              </div>
            </div>

            <div className="mt-4 max-h-[30rem] space-y-3 overflow-auto pr-1">
              {isLoading ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm text-slate-400">
                  Loading live messages...
                </div>
              ) : visibleMessages.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm text-slate-400">
                  No messages found.
                </div>
              ) : (
                visibleMessages.slice(0, 18).map((message) => (
                  <article key={message.id} className={`rounded-[22px] border p-3 ${messageCardTone(message.risk_score)}`}>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium text-white">{message.chat_name}</p>
                          <span className="rounded-full border border-white/8 bg-white/[0.03] px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                            {message.sender}
                          </span>
                          {message.is_from_me && (
                            <span className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-300">
                              Sent by me
                            </span>
                          )}
                        </div>
                        <p className="mt-2 text-sm leading-6 text-slate-200">{message.message}</p>
                        <p className="mt-2 text-xs text-slate-500">{formatDateTime(message.timestamp)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {(message.risk_score ?? 0) > 50 ? (
                          <ShieldAlert className="h-5 w-5 text-rose-300" />
                        ) : (
                          <ShieldCheck className="h-5 w-5 text-emerald-300" />
                        )}
                        <span className={`rounded-full border px-3 py-1.5 text-xs ${scoreTone(message.risk_score)}`}>
                          {message.label || 'Safe'} | {(message.risk_score ?? 0).toFixed(1)}
                        </span>
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                  <MessageSquare className="h-5 w-5 text-cyan-300" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">Chats</p>
                  <h2 className="mt-1 text-2xl font-semibold text-white">Recent conversations</h2>
                </div>
              </div>

              <div className="mt-4 max-h-[22rem] space-y-3 overflow-auto pr-1">
                {filteredChats.length === 0 ? (
                  <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                    No chats yet.
                  </div>
                ) : (
                  filteredChats.slice(0, 8).map((chat) => (
                    <button
                      key={chat.id}
                      type="button"
                      onClick={() => setSelectedChatId((current) => (current === chat.id ? null : chat.id))}
                      className={`w-full rounded-[22px] border px-4 py-3 text-left transition ${selectedChatId === chat.id ? 'border-cyan-500/25 bg-cyan-500/10' : 'border-white/8 bg-slate-950/55 hover:bg-slate-950/70'}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-white">{chat.chat_name}</p>
                          <p className="mt-1 text-xs text-slate-400">
                            {(chat.chat_type ?? 'chat').toUpperCase()} | {chat.message_count} messages | {chat.flagged_messages} flagged
                          </p>
                          {chat.latest_message_preview && (
                            <p className="mt-2 truncate text-xs text-slate-500">{chat.latest_message_preview}</p>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-2">
                          <span className={`rounded-full px-3 py-1.5 text-xs ${chat.unsafe_percentage > 20 ? 'border border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                            {chat.unsafe_percentage.toFixed(1)}%
                          </span>
                          <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">
                            {chat.open_alert_count} open alerts
                          </span>
                        </div>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                  <BellRing className="h-5 w-5 text-cyan-300" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">Alerts</p>
                  <h2 className="mt-1 text-2xl font-semibold text-white">Open moderation alerts</h2>
                </div>
              </div>

              <div className="mt-4 max-h-[22rem] space-y-3 overflow-auto pr-1">
                {openAlerts.length === 0 ? (
                  <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                    No open alerts.
                  </div>
                ) : (
                  openAlerts.slice(0, 8).map((alert) => (
                    <article key={alert.id} className="rounded-[22px] border border-white/8 bg-slate-950/55 p-3">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-white">{alert.chat_name}</p>
                            <span className={`rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] ${alert.severity === 'High' ? 'border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border-amber-500/20 bg-amber-500/10 text-amber-300'}`}>
                              {alert.severity}
                            </span>
                          </div>
                          <p className="mt-2 text-xs text-slate-400">{alert.sender} | {formatDateTime(alert.created_at)}</p>
                          <p className="mt-2 text-sm leading-6 text-slate-300">{alert.message}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="h-5 w-5 text-rose-300" />
                          <span className={`rounded-full border px-3 py-1.5 text-xs ${scoreTone(alert.risk_score)}`}>
                            {(alert.risk_score ?? 0).toFixed(1)}
                          </span>
                        </div>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
