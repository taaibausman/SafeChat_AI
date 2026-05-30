import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { io } from 'socket.io-client';
import {
  BellRing,
  History,
  QrCode,
  RadioTower,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Target,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { BRIDGE_SOCKET_URL, WS_BASE_URL, apiClient } from '../lib/api';

type WhatsAppStatus = {
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
  unsafe_percentage: number;
  last_message_at?: string | null;
  latest_message_preview?: string | null;
};

type BridgeHealth = {
  reachable: boolean;
  status?: string | null;
  detail?: string | null;
};

type BridgeOpsSummary = {
  current_state: {
    status: string;
    connected_phone?: string | null;
    bridge_reachable?: boolean;
  };
  recent_event_count: number;
  recent_snapshot_count: number;
  recent_window_hours: number;
  bridge_reachable: boolean;
  attention_required: boolean;
};

type LiveOpsSummary = {
  live_summary: {
    total_live_chats: number;
    total_live_messages: number;
    flagged_live_messages: number;
    open_alerts: number;
  };
  recent_feed_count: number;
  recent_alert_count: number;
  recent_flagged_message_count: number;
  flagged_chat_count: number;
  high_risk_chat_count: number;
  recent_window_hours: number;
  attention_required: boolean;
};

type BackendHealthSummary = {
  bridge_ops: BridgeOpsSummary;
  live_ops: LiveOpsSummary;
  recent_window_hours: number;
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

type BridgeEvent = {
  id: number;
  event_type: string;
  status?: string | null;
  detail?: string | null;
  connected_phone?: string | null;
  bridge_reachable?: boolean | null;
  created_at: string;
};

type BridgeSnapshot = {
  id: number;
  status?: string | null;
  reason?: string | null;
  connected_phone?: string | null;
  bridge_status?: string | null;
  bridge_detail?: string | null;
  bridge_reachable?: boolean | null;
  qr_present: boolean;
  created_at: string;
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

function toApiDate(value: string) {
  if (!value) return undefined;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}

function formatDateTime(value?: string | null) {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unavailable';
  return parsed.toLocaleString();
}

function lastUpdatedLabel(value: string | null) {
  if (!value) return 'Not refreshed yet';
  return `Last updated ${formatDateTime(value)}`;
}

function scoreTone(score?: number | null) {
  if ((score ?? 0) >= 80) return 'border-rose-500/25 bg-rose-500/10 text-rose-300';
  if ((score ?? 0) > 50) return 'border-amber-500/25 bg-amber-500/10 text-amber-300';
  return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300';
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
  return [payload, ...deduped].slice(0, 100);
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

export default function RealtimeMonitor() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [chats, setChats] = useState<LiveChatSummary[]>([]);
  const [alerts, setAlerts] = useState<LiveAlert[]>([]);
  const [bridgeEvents, setBridgeEvents] = useState<BridgeEvent[]>([]);
  const [bridgeSnapshots, setBridgeSnapshots] = useState<BridgeSnapshot[]>([]);
  const [monitoredContacts, setMonitoredContacts] = useState<MonitoredContact[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [bridgeHealth, setBridgeHealth] = useState<BridgeHealth | null>(null);
  const [healthSummary, setHealthSummary] = useState<BackendHealthSummary | null>(null);
  const [chatSearch, setChatSearch] = useState('');
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('');
  const [alertStatusFilter, setAlertStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [isSavingMonitor, setIsSavingMonitor] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [bridgeSocketState, setBridgeSocketState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [monitorName, setMonitorName] = useState('');
  const [monitorKey, setMonitorKey] = useState('');
  const [monitorType, setMonitorType] = useState<'direct' | 'group'>('direct');

  const loadData = async (showSpinner = false) => {
    if (showSpinner) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    const commonDateParams = {
      date_from: toApiDate(dateFrom),
      date_to: toApiDate(dateTo),
    };

    const [statusResult, feedResult, chatResult, healthResult, opsResult, alertResult, eventResult, snapshotResult, monitoredResult] = await Promise.allSettled([
      apiClient.get('/api/whatsapp/status'),
      apiClient.get('/api/whatsapp/live-feed', {
        params: {
          ...commonDateParams,
          chat_id: selectedChatId ?? undefined,
          flagged_only: flaggedOnly || undefined,
          limit: 100,
        },
      }),
      apiClient.get('/api/whatsapp/chats', {
        params: {
          ...commonDateParams,
          flagged_only: flaggedOnly || undefined,
          limit: 100,
        },
      }),
      apiClient.get('/api/whatsapp/bridge-health'),
      apiClient.get('/api/whatsapp/health-summary'),
      apiClient.get('/api/whatsapp/alerts', {
        params: {
          ...commonDateParams,
          chat_id: selectedChatId ?? undefined,
          severity: severityFilter || undefined,
          status: alertStatusFilter || undefined,
          limit: 25,
        },
      }),
      apiClient.get('/api/whatsapp/bridge-events', {
        params: {
          ...commonDateParams,
          limit: 8,
        },
      }),
      apiClient.get('/api/whatsapp/bridge-state-history', {
        params: {
          ...commonDateParams,
          limit: 8,
        },
      }),
      apiClient.get('/api/whatsapp/monitored-contacts'),
    ]);

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
      setBridgeHealth({
        reachable: false,
        detail: 'Bridge health route is unavailable.',
      });
    }

    if (opsResult.status === 'fulfilled') {
      setHealthSummary(opsResult.value.data);
    } else {
      nextErrors.push('Backend health summary could not be loaded.');
    }

    if (alertResult.status === 'fulfilled') {
      setAlerts(alertResult.value.data.alerts ?? []);
    } else {
      setAlerts([]);
      nextErrors.push('Alert history could not be loaded.');
    }

    if (eventResult.status === 'fulfilled') {
      setBridgeEvents(eventResult.value.data.events ?? []);
    } else {
      setBridgeEvents([]);
      nextErrors.push('Bridge event history could not be loaded.');
    }

    if (snapshotResult.status === 'fulfilled') {
      setBridgeSnapshots(snapshotResult.value.data.snapshots ?? []);
    } else {
      setBridgeSnapshots([]);
      nextErrors.push('Bridge state history could not be loaded.');
    }

    if (monitoredResult.status === 'fulfilled') {
      setMonitoredContacts(monitoredResult.value.data.contacts ?? []);
    } else {
      setMonitoredContacts([]);
      nextErrors.push('Monitor selection state could not be loaded.');
    }

    setError(nextErrors.join(' '));
    setLastUpdated(new Date().toISOString());
    setIsLoading(false);
    setIsRefreshing(false);
  };

  useEffect(() => {
    void loadData(false);
    const timer = window.setInterval(() => {
      void loadData(true);
    }, 15000);

    return () => window.clearInterval(timer);
  }, [selectedChatId, flaggedOnly, severityFilter, alertStatusFilter, dateFrom, dateTo]);

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE_URL}/ws/whatsapp`);

    socket.onopen = () => {
      socket.send('subscribe');
    };

    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.type === 'status') {
          setStatus(parsed.payload);
          return;
        }

        if (parsed.type === 'message') {
          const payload = parsed.payload as LiveMessage;
          setMessages((current) => mergeLiveMessage(current, payload, selectedChatId, flaggedOnly));
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
  }, [selectedChatId, flaggedOnly]);

  useEffect(() => {
    const socket = io(BRIDGE_SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      timeout: 5000,
    });

    socket.on('connect', () => {
      setBridgeSocketState('connected');
    });

    socket.on('disconnect', () => {
      setBridgeSocketState('disconnected');
    });

    socket.on('bridge_status', (payload: Partial<WhatsAppStatus>) => {
      setStatus((current) => ({ ...(current ?? { status: 'unknown' }), ...payload }));
    });

    socket.on('monitored_contacts', (payload: { contacts?: MonitoredContact[] }) => {
      setMonitoredContacts(payload.contacts ?? []);
    });

    socket.on('moderation_result', (payload: { live_message?: LiveMessage | null; chat?: LiveChatSummary | null }) => {
      if (payload.chat) {
        setChats((current) => mergeChatSummary(current, payload.chat as LiveChatSummary));
      }
      if (payload.live_message) {
        setMessages((current) =>
          mergeLiveMessage(current, payload.live_message as LiveMessage, selectedChatId, flaggedOnly)
        );
      }
      setLastUpdated(new Date().toISOString());
    });

    socket.on('bridge_error', () => {
      setError((current) => current || 'Bridge socket reported an operational error. Using fallback refresh where needed.');
    });

    socket.on('connect_error', () => {
      setBridgeSocketState('disconnected');
    });

    return () => {
      socket.close();
    };
  }, [selectedChatId, flaggedOnly]);

  const qrImage = status?.qr
    ? `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(status.qr)}`
    : '';

  const connected = status?.status === 'connected' || status?.status === 'ready';
  const selectedChat = useMemo(
    () => chats.find((chat) => chat.id === selectedChatId) ?? null,
    [chats, selectedChatId]
  );
  const monitoredKeySet = useMemo(
    () => new Set(monitoredContacts.map((contact) => contact.chat_key)),
    [monitoredContacts]
  );

  const filteredChats = useMemo(() => {
    const query = chatSearch.trim().toLowerCase();
    return chats.filter((chat) => {
      const matchesSearch =
        !query ||
        chat.chat_name.toLowerCase().includes(query) ||
        (chat.chat_type ?? '').toLowerCase().includes(query);
      const matchesFlagged = !flaggedOnly || chat.flagged_messages > 0;
      return matchesSearch && matchesFlagged;
    });
  }, [chatSearch, chats, flaggedOnly]);

  const filteredMessages = useMemo(
    () => messages.filter((message) => !flaggedOnly || (message.risk_score ?? 0) > 50),
    [flaggedOnly, messages]
  );

  const refreshNow = async () => {
    await loadData(true);
  };

  const saveMonitor = async () => {
    if (!monitorName.trim() || !monitorKey.trim()) {
      setError('Monitor name and chat key are required.');
      return;
    }

    try {
      setIsSavingMonitor(true);
      const response = await apiClient.post('/api/whatsapp/monitored-contacts', {
        contact_name: monitorName.trim(),
        chat_key: monitorKey.trim(),
        chat_type: monitorType,
        is_active: true,
      });
      const created = response.data as MonitoredContact;
      setMonitoredContacts((current) => {
        const next = current.filter((item) => item.id !== created.id);
        return [created, ...next];
      });
      setMonitorName('');
      setMonitorKey('');
      setMonitorType('direct');
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
      setError('Could not update monitored contact state.');
    }
  };

  const deleteMonitor = async (contactId: number) => {
    try {
      await apiClient.delete(`/api/whatsapp/monitored-contacts/${contactId}`);
      setMonitoredContacts((current) => current.filter((item) => item.id !== contactId));
    } catch {
      setError('Could not delete monitored contact.');
    }
  };

  const quickAddMonitor = async (chat: LiveChatSummary) => {
    try {
      const response = await apiClient.post('/api/whatsapp/monitored-contacts', {
        contact_name: chat.chat_name,
        chat_key: chat.external_chat_id || chat.chat_name,
        chat_type: chat.chat_type || 'direct',
        is_active: true,
      });
      const created = response.data as MonitoredContact;
      setMonitoredContacts((current) => {
        const next = current.filter((item) => item.id !== created.id);
        return [created, ...next];
      });
    } catch (saveError: any) {
      setError(saveError?.response?.data?.detail || 'Could not add this chat to the monitored list.');
    }
  };

  const resetFilters = () => {
    setDateFrom('');
    setDateTo('');
    setSeverityFilter('');
    setAlertStatusFilter('');
    setFlaggedOnly(false);
    setSelectedChatId(null);
    setChatSearch('');
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

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <section className="overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(135deg,rgba(18,28,58,0.96),rgba(21,15,39,0.94))] p-6 shadow-[0_30px_120px_rgba(59,130,246,0.15)] md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE MONITOR</p>
            <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">WhatsApp realtime moderation</h1>
            <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">
              Review live feed activity, narrow the window, filter alerts by severity and status, and inspect bridge history without leaving the page.
            </p>
          </div>

          <div className="flex flex-col items-start gap-3 lg:items-end">
            <button
              onClick={refreshNow}
              disabled={isRefreshing}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Refresh now'}
            </button>
            <p className="text-xs text-slate-400">{lastUpdatedLabel(lastUpdated)}</p>
          </div>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <input
            type="datetime-local"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-500/30"
          />
          <input
            type="datetime-local"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-500/30"
          />
          <select
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
            className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-500/30"
          >
            <option value="">All severities</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
          <select
            value={alertStatusFilter}
            onChange={(event) => setAlertStatusFilter(event.target.value)}
            className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-500/30"
          >
            <option value="">All alert statuses</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
          <div className="flex gap-3">
            <button
              onClick={() => setFlaggedOnly((current) => !current)}
              className={`min-h-11 flex-1 rounded-2xl border px-4 py-3 text-sm transition ${flaggedOnly ? 'border-rose-500/25 bg-rose-500/10 text-rose-300' : 'border-white/8 bg-slate-950/60 text-slate-300 hover:bg-slate-950/80'}`}
            >
              {flaggedOnly ? 'Flagged only' : 'All messages'}
            </button>
            <button
              onClick={resetFilters}
              className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-slate-300 transition hover:bg-slate-950/80"
            >
              Clear
            </button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Backend status</p>
          <p className={`mt-3 text-2xl font-semibold ${healthSummary?.status === 'attention' ? 'text-amber-300' : 'text-emerald-300'}`}>
            {healthSummary?.status ?? 'unknown'}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            {healthSummary?.attention_required ? 'One or more operational checks need review.' : 'Bridge and live monitoring look stable.'}
          </p>
        </div>
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Bridge ops</p>
          <p className="mt-3 text-2xl font-semibold text-white">
            {healthSummary?.bridge_ops.current_state.status ?? 'unknown'}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            {healthSummary?.bridge_ops.recent_event_count ?? 0} events | {healthSummary?.bridge_ops.recent_snapshot_count ?? 0} snapshots
          </p>
        </div>
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Live alerts</p>
          <p className="mt-3 text-2xl font-semibold text-white">
            {healthSummary?.live_ops.live_summary.open_alerts ?? 0}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            {healthSummary?.live_ops.recent_alert_count ?? 0} recent alerts | {healthSummary?.live_ops.recent_flagged_message_count ?? 0} flagged messages
          </p>
        </div>
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Risky chats</p>
          <p className="mt-3 text-2xl font-semibold text-white">
            {healthSummary?.live_ops.flagged_chat_count ?? 0}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            {healthSummary?.live_ops.high_risk_chat_count ?? 0} high-risk chats in the recent window
          </p>
        </div>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
        <section className="space-y-6">
          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">CONNECTION</p>
                <h2 className="mt-2 text-2xl font-semibold text-white">Bridge state</h2>
              </div>
              <div className={`inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs ${connected ? 'border border-emerald-500/25 bg-emerald-500/10 text-emerald-300' : 'border border-amber-500/25 bg-amber-500/10 text-amber-300'}`}>
                {connected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
                {connected ? 'Session live' : 'Waiting'}
              </div>
            </div>

            <div className="mt-5 rounded-[22px] border border-white/8 bg-slate-950/60 p-5">
              <p className="text-sm text-slate-400">Current status</p>
              <p className="mt-3 text-2xl font-semibold capitalize text-white">{status?.status ?? 'unknown'}</p>
              {status?.reason && <p className="mt-2 text-sm leading-7 text-slate-400">{status.reason}</p>}
              {(status?.bridge_detail || bridgeHealth?.detail) && (
                <p className="mt-2 text-xs text-slate-500">{status?.bridge_detail || bridgeHealth?.detail}</p>
              )}
              {status?.connected_phone && (
                <p className="mt-2 text-xs text-cyan-300">Connected account: {status.connected_phone}</p>
              )}
              <p className="mt-3 text-xs text-slate-500">{lastUpdatedLabel(lastUpdated)}</p>
            </div>

            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <button
                onClick={restartBridge}
                disabled={isRestarting}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
              >
                <RefreshCw className={`h-4 w-4 ${isRestarting ? 'animate-spin' : ''}`} />
                {isRestarting ? 'Restarting...' : 'Restart bridge'}
              </button>
              <div className="rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-xs text-slate-400">
                Run bridge manually: <code className="text-slate-200">cd whatsapp && npm run dev</code>
              </div>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Bridge socket: {bridgeSocketState === 'connected' ? 'connected' : bridgeSocketState === 'connecting' ? 'connecting' : 'disconnected'}
            </p>
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <QrCode className="h-5 w-5 text-cyan-300" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">AUTHENTICATION</p>
                <h2 className="mt-1 text-2xl font-semibold text-white">QR pairing</h2>
              </div>
            </div>

            <div className="mt-5 flex min-h-[20rem] items-center justify-center rounded-[24px] border border-dashed border-white/10 bg-slate-950/60 p-6 text-center">
              {qrImage ? (
                <img src={qrImage} alt="WhatsApp QR code" className="rounded-[20px] bg-white p-3 shadow-lg" />
              ) : isLoading ? (
                <div className="max-w-sm">
                  <p className="text-lg font-medium text-slate-200">Checking for an active QR code...</p>
                  <p className="mt-3 text-sm leading-7 text-slate-400">
                    The current bridge state will appear here once the first status request completes.
                  </p>
                </div>
              ) : (
                <div className="max-w-sm">
                  <p className="text-lg font-medium text-slate-200">QR code not available</p>
                  <p className="mt-3 text-sm leading-7 text-slate-400">
                    When the bridge enters the <code>qr_required</code> state, the pairing code will appear here.
                  </p>
                </div>
              )}
            </div>

            {status?.qr_updated_at && (
              <p className="mt-3 text-xs text-slate-500">Last QR update: {formatDateTime(status.qr_updated_at)}</p>
            )}
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <Target className="h-5 w-5 text-cyan-300" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">MONITOR SCOPE</p>
                <h2 className="mt-1 text-2xl font-semibold text-white">Contacts and groups to watch</h2>
              </div>
            </div>

            <p className="mt-4 text-sm leading-7 text-slate-400">
              When this list is empty, the bridge forwards all chats. Once active entries exist, only matching direct chats and groups are analyzed.
            </p>

            <div className="mt-5 grid gap-3 md:grid-cols-[1.2fr_1.1fr_0.8fr_auto]">
              <input
                value={monitorName}
                onChange={(event) => setMonitorName(event.target.value)}
                placeholder="Display name"
                className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-500/30"
              />
              <input
                value={monitorKey}
                onChange={(event) => setMonitorKey(event.target.value)}
                placeholder="Chat key or phone number"
                className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-500/30"
              />
              <select
                value={monitorType}
                onChange={(event) => setMonitorType(event.target.value as 'direct' | 'group')}
                className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-500/30"
              >
                <option value="direct">Direct</option>
                <option value="group">Group</option>
              </select>
              <button
                onClick={saveMonitor}
                disabled={isSavingMonitor}
                className="min-h-11 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
              >
                {isSavingMonitor ? 'Saving...' : 'Add monitor'}
              </button>
            </div>

            <div className="mt-5 space-y-3">
              {monitoredContacts.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                  No scoped monitors yet. Add a contact manually or use the quick-add action from a live chat.
                </div>
              ) : (
                monitoredContacts.map((contact) => (
                  <div key={contact.id} className="flex flex-col gap-3 rounded-[22px] border border-white/8 bg-slate-950/55 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-white">{contact.contact_name}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        {(contact.chat_type || 'direct').toUpperCase()} | {contact.chat_key}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleMonitor(contact)}
                        className={`rounded-full border px-3 py-1.5 text-xs ${contact.is_active ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300' : 'border-white/8 bg-white/[0.03] text-slate-400'}`}
                      >
                        {contact.is_active ? 'Active' : 'Paused'}
                      </button>
                      <button
                        onClick={() => deleteMonitor(contact.id)}
                        className="rounded-full border border-white/8 bg-white/[0.03] p-2 text-slate-400 transition hover:text-rose-300"
                        aria-label={`Delete ${contact.contact_name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE CHATS</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Monitored conversations</h2>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row">
              <input
                value={chatSearch}
                onChange={(event) => setChatSearch(event.target.value)}
                placeholder="Search chat name or type"
                className="min-h-11 flex-1 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-500/30"
              />
              <button
                onClick={() => setSelectedChatId(null)}
                className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-slate-300 transition hover:bg-slate-950/80"
              >
                View all
              </button>
            </div>

            <div className="mt-5 space-y-3">
              {isLoading ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                  Loading live chats...
                </div>
              ) : filteredChats.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                  No chats match the current filters. Clear the search or wait for more live activity.
                </div>
              ) : (
                filteredChats.map((chat) => (
                  <button
                    key={chat.id}
                    onClick={() => setSelectedChatId(chat.id)}
                    className={`w-full rounded-[22px] border px-4 py-4 text-left transition ${selectedChatId === chat.id ? 'border-cyan-500/25 bg-cyan-500/10' : 'border-white/8 bg-slate-950/55 hover:bg-slate-950/70'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-white">{chat.chat_name}</p>
                        <p className="mt-1 text-xs text-slate-400">
                          {(chat.chat_type ?? 'chat').toUpperCase()} | {chat.message_count} messages | {chat.flagged_messages} flagged
                        </p>
                        {chat.latest_message_preview && (
                          <p className="mt-1 truncate text-xs text-slate-500">{chat.latest_message_preview}</p>
                        )}
                        {chat.last_message_at && (
                          <p className="mt-1 text-xs text-slate-500">
                            Last activity: {formatDateTime(chat.last_message_at)}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            void quickAddMonitor(chat);
                          }}
                          className={`rounded-full border px-3 py-1.5 text-xs ${monitoredKeySet.has(chat.external_chat_id || chat.chat_name) ? 'border-cyan-500/25 bg-cyan-500/10 text-cyan-300' : 'border-white/8 bg-white/[0.03] text-slate-300'}`}
                        >
                          {monitoredKeySet.has(chat.external_chat_id || chat.chat_name) ? 'Tracked' : 'Track'}
                        </button>
                        <span className={`rounded-full px-3 py-1.5 text-xs ${chat.unsafe_percentage > 20 ? 'border border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                          {chat.unsafe_percentage.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <History className="h-5 w-5 text-cyan-300" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">BRIDGE HISTORY</p>
                <h2 className="mt-1 text-2xl font-semibold text-white">Events and snapshots</h2>
              </div>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
                <p className="text-sm font-medium text-white">Recent events</p>
                <div className="mt-4 space-y-3">
                  {bridgeEvents.length === 0 ? (
                    <p className="text-sm text-slate-400">No bridge events match the current date range.</p>
                  ) : (
                    bridgeEvents.slice(0, 4).map((event) => (
                      <div key={event.id} className="rounded-2xl border border-white/6 bg-white/[0.03] p-3">
                        <p className="text-sm font-medium text-slate-100">{event.event_type}</p>
                        <p className="mt-1 text-xs text-slate-400">
                          {(event.status ?? 'unknown').toUpperCase()} | {formatDateTime(event.created_at)}
                        </p>
                        {event.detail && <p className="mt-2 text-xs leading-6 text-slate-500">{event.detail}</p>}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
                <p className="text-sm font-medium text-white">State snapshots</p>
                <div className="mt-4 space-y-3">
                  {bridgeSnapshots.length === 0 ? (
                    <p className="text-sm text-slate-400">No bridge snapshots match the current date range.</p>
                  ) : (
                    bridgeSnapshots.slice(0, 4).map((snapshot) => (
                      <div key={snapshot.id} className="rounded-2xl border border-white/6 bg-white/[0.03] p-3">
                        <p className="text-sm font-medium text-slate-100">{snapshot.status ?? 'unknown'}</p>
                        <p className="mt-1 text-xs text-slate-400">
                          {(snapshot.bridge_status ?? 'unknown').toUpperCase()} | {formatDateTime(snapshot.created_at)}
                        </p>
                        <p className="mt-2 text-xs leading-6 text-slate-500">
                          {snapshot.reason || snapshot.bridge_detail || 'No extra snapshot detail recorded.'}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE FEED</p>
                <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-white">
                  <RadioTower className="h-5 w-5 text-cyan-300" />
                  {selectedChat ? selectedChat.chat_name : 'Incoming messages'}
                </h2>
              </div>
              <div className="flex items-center gap-3">
                {selectedChat && (
                  <Link
                    to={`/results/${selectedChat.id}`}
                    className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-300 transition hover:bg-cyan-500/15"
                  >
                    Open report
                  </Link>
                )}
                <div className="rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-sm text-slate-300">
                  {filteredMessages.length} recent message(s)
                </div>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {isLoading ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm leading-7 text-slate-400">
                  Loading live feed...
                </div>
              ) : filteredMessages.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm leading-7 text-slate-400">
                  No live messages match the current filters. Adjust the date range, severity filters, or wait for new activity.
                </div>
              ) : (
                filteredMessages.map((message) => (
                  <article key={message.id} className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium text-white">{message.sender_name || message.sender}</p>
                          <span className="rounded-full border border-white/8 bg-white/[0.03] px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                            {message.chat_name}
                          </span>
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] ${message.is_from_me ? 'border-cyan-500/20 bg-cyan-500/10 text-cyan-300' : 'border-white/8 bg-white/[0.03] text-slate-400'}`}>
                            {message.direction ?? (message.is_from_me ? 'outgoing' : 'incoming')}
                          </span>
                        </div>
                        <p className="mt-3 text-sm leading-7 text-slate-300">{message.message}</p>
                        <p className="mt-3 text-xs text-slate-500">
                          {formatDateTime(message.timestamp)} | {message.label ?? 'unclassified'}
                        </p>
                      </div>
                      <span className={`rounded-full border px-3 py-1.5 text-xs ${scoreTone(message.risk_score)}`}>
                        {(message.risk_score ?? 0).toFixed(1)} risk
                      </span>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE ALERTS</p>
                <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-white">
                  <BellRing className="h-5 w-5 text-cyan-300" />
                  Filtered alert queue
                </h2>
              </div>
              <p className="text-xs text-slate-400">
                Severity: {severityFilter || 'All'} | Status: {alertStatusFilter || 'All'}
              </p>
            </div>

            <div className="mt-5 space-y-3">
              {isLoading ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm leading-7 text-slate-400">
                  Loading alert queue...
                </div>
              ) : alerts.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm leading-7 text-slate-400">
                  No alerts match the current severity, status, chat, and date filters.
                </div>
              ) : (
                alerts.map((alert) => (
                  <article key={alert.id} className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium text-white">{alert.chat_name}</p>
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] ${alert.severity === 'High' ? 'border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border-amber-500/20 bg-amber-500/10 text-amber-300'}`}>
                            {alert.severity}
                          </span>
                          <span className="rounded-full border border-white/8 bg-white/[0.03] px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                            {alert.status}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-slate-400">{alert.sender} | {formatDateTime(alert.created_at)}</p>
                        <p className="mt-3 text-sm leading-7 text-slate-300">{alert.message}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {(alert.risk_score ?? 0) > 50 ? (
                          <ShieldAlert className="h-5 w-5 text-rose-300" />
                        ) : (
                          <ShieldCheck className="h-5 w-5 text-emerald-300" />
                        )}
                        <span className={`rounded-full border px-3 py-1.5 text-xs ${scoreTone(alert.risk_score)}`}>
                          {(alert.risk_score ?? 0).toFixed(1)} risk
                        </span>
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
