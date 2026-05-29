import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import {
  QrCode,
  RadioTower,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { API_BASE_URL, WS_BASE_URL, apiClient } from '../lib/api';

type WhatsAppStatus = {
  status: string;
  reason?: string | null;
  qr?: string | null;
  qr_updated_at?: string | null;
};

type LiveMessage = {
  id: number;
  chat_id: number;
  chat_name: string;
  sender: string;
  message: string;
  timestamp?: string | null;
  risk_score?: number | null;
  label?: string | null;
};

type LiveChatSummary = {
  id: number;
  chat_name: string;
  platform: string;
  message_count: number;
  flagged_messages: number;
  unsafe_percentage: number;
  last_message_at?: string | null;
};

type BridgeHealth = {
  reachable: boolean;
  status?: string | null;
  detail?: string | null;
};

export default function RealtimeMonitor() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [chats, setChats] = useState<LiveChatSummary[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [bridgeHealth, setBridgeHealth] = useState<BridgeHealth | null>(null);
  const [error, setError] = useState('');
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      const [statusResult, feedResult, chatResult, healthResult] = await Promise.allSettled([
        axios.get(`${API_BASE_URL}/api/whatsapp/status`),
        axios.get(`${API_BASE_URL}/api/whatsapp/live-feed`, {
          params: selectedChatId ? { chat_id: selectedChatId } : undefined,
        }),
        axios.get(`${API_BASE_URL}/api/whatsapp/chats`),
        axios.get(`${API_BASE_URL}/api/whatsapp/bridge-health`),
      ]);

      if (!active) return;

      const nextError: string[] = [];

      if (statusResult.status === 'fulfilled') {
        setStatus(statusResult.value.data);
      } else {
        nextError.push('WhatsApp status is unavailable.');
      }

      if (feedResult.status === 'fulfilled') {
        setMessages(feedResult.value.data.messages ?? []);
      } else {
        nextError.push('Live feed could not be loaded.');
      }

      if (chatResult.status === 'fulfilled') {
        setChats(chatResult.value.data.chats ?? []);
      } else {
        setChats([]);
        nextError.push('Chat list unavailable. Restart the backend to enable chat-level WhatsApp routes.');
      }

      if (healthResult.status === 'fulfilled') {
        setBridgeHealth(healthResult.value.data);
      } else {
        setBridgeHealth({
          reachable: false,
          detail: 'Bridge health route unavailable. Restart the backend to enable bridge controls.',
        });
      }

      setError(nextError.join(' '));
    };

    load();
    const timer = window.setInterval(load, 5000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selectedChatId]);

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
          setChats((current) => {
            const existing = current.find((item) => item.id === payload.chat_id);
            if (!existing) {
              return current;
            }
            return current.map((item) =>
              item.id === payload.chat_id
                ? {
                    ...item,
                    message_count: item.message_count + 1,
                    flagged_messages: item.flagged_messages + ((payload.risk_score ?? 0) > 50 ? 1 : 0),
                    unsafe_percentage:
                      ((item.flagged_messages + ((payload.risk_score ?? 0) > 50 ? 1 : 0)) / (item.message_count + 1)) * 100,
                    last_message_at: payload.timestamp ?? item.last_message_at,
                  }
                : item
            );
          });
          setMessages((current) => {
            if (selectedChatId !== null && payload.chat_id !== selectedChatId) {
              return current;
            }
            return [payload, ...current].slice(0, 50);
          });
        }
      } catch {
        setError('Received an invalid realtime event.');
      }
    };

    socket.onerror = () => {
      setError((current) => current || 'Realtime connection failed. Falling back to periodic refresh.');
    };

    return () => {
      socket.close();
    };
  }, [selectedChatId]);

  const qrImage = status?.qr
    ? `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(status.qr)}`
    : '';

  const connected = status?.status === 'connected' || status?.status === 'ready';
  const selectedChat = useMemo(
    () => chats.find((chat) => chat.id === selectedChatId) ?? null,
    [chats, selectedChatId]
  );

  const restartBridge = async () => {
    try {
      setIsRestarting(true);
      await apiClient.post('/api/whatsapp/bridge-restart');
    } catch {
      setError('Could not restart the WhatsApp bridge.');
    } finally {
      setTimeout(() => setIsRestarting(false), 1500);
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
              Connect the bridge, authenticate the session, filter by live chat, and review incoming WhatsApp messages with risk scoring.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:w-[34rem]">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Session</p>
              <p className={`mt-2 text-sm font-medium ${connected ? 'text-emerald-300' : 'text-amber-300'}`}>
                {status?.status ?? 'unknown'}
              </p>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Bridge health</p>
              <p className={`mt-2 text-sm font-medium ${bridgeHealth?.reachable ? 'text-emerald-300' : 'text-rose-300'}`}>
                {bridgeHealth?.reachable ? (bridgeHealth.status ?? 'reachable') : 'offline'}
              </p>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Live chats</p>
              <p className="mt-2 text-sm font-medium text-white">{chats.length}</p>
            </div>
          </div>
        </div>
      </section>

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
              {bridgeHealth?.detail && <p className="mt-2 text-xs text-slate-500">{bridgeHealth.detail}</p>}
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

            {error && (
              <div className="mt-4 rounded-[22px] border border-rose-500/20 bg-rose-500/8 p-4 text-sm text-rose-300">
                {error}
              </div>
            )}
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
              ) : (
                <div className="max-w-sm">
                  <p className="text-lg font-medium text-slate-200">QR code not available yet</p>
                  <p className="mt-3 text-sm leading-7 text-slate-400">
                    When the bridge enters `qr_required` state, the pairing code will appear here.
                  </p>
                </div>
              )}
            </div>

            {status?.qr_updated_at && (
              <p className="mt-3 text-xs text-slate-500">Last QR update: {new Date(status.qr_updated_at).toLocaleString()}</p>
            )}
          </div>

          <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE CHATS</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Monitored conversations</h2>
            <div className="mt-5 space-y-3">
              <button
                onClick={() => setSelectedChatId(null)}
                className={`w-full rounded-[22px] border px-4 py-4 text-left transition ${selectedChatId === null ? 'border-cyan-500/25 bg-cyan-500/10' : 'border-white/8 bg-slate-950/55 hover:bg-slate-950/70'}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-white">All live chats</p>
                    <p className="mt-1 text-xs text-slate-400">Aggregate feed across all WhatsApp live conversations</p>
                  </div>
                  <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">
                    {messages.length} visible
                  </span>
                </div>
              </button>

              {chats.map((chat) => (
                <button
                  key={chat.id}
                  onClick={() => setSelectedChatId(chat.id)}
                  className={`w-full rounded-[22px] border px-4 py-4 text-left transition ${selectedChatId === chat.id ? 'border-cyan-500/25 bg-cyan-500/10' : 'border-white/8 bg-slate-950/55 hover:bg-slate-950/70'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-white">{chat.chat_name}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        {chat.message_count} messages • {chat.flagged_messages} flagged
                      </p>
                      {chat.last_message_at && (
                        <p className="mt-1 text-xs text-slate-500">
                          Last activity: {new Date(chat.last_message_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <span className={`rounded-full px-3 py-1.5 text-xs ${chat.unsafe_percentage > 20 ? 'border border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                      {chat.unsafe_percentage.toFixed(1)}%
                    </span>
                  </div>
                </button>
              ))}

              {chats.length === 0 && (
                <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
                  No live WhatsApp chats stored yet. Connect the bridge and wait for incoming messages.
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE FEED</p>
              <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-white">
                <RadioTower className="h-5 w-5 text-cyan-300" />
                {selectedChat ? selectedChat.chat_name : 'Incoming messages'}
              </h2>
            </div>
            <div className="rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-sm text-slate-300">
              {messages.length} recent message(s)
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {messages.length === 0 ? (
              <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-6 text-sm leading-7 text-slate-400">
                No live messages yet. After the bridge connects, send a test WhatsApp message to populate this feed.
              </div>
            ) : (
              messages.map((message) => (
                <div key={message.id} className="rounded-[22px] border border-white/6 bg-slate-950/60 p-4 transition hover:border-white/10">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <Link to={`/results/${message.chat_id}`} className="font-semibold text-white transition hover:text-cyan-300">
                        {message.chat_name}
                      </Link>
                      <p className="mt-1 text-sm text-slate-400">{message.sender}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs sm:justify-end">
                      <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 font-medium ${(message.risk_score ?? 0) > 50 ? 'border border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                        {(message.risk_score ?? 0) > 50 ? <ShieldAlert className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                        {message.label ?? 'Safe'} {(message.risk_score ?? 0).toFixed(1)}
                      </span>
                      {message.timestamp && (
                        <span className="text-slate-500">{new Date(message.timestamp).toLocaleString()}</span>
                      )}
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-slate-100">{message.message}</p>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
