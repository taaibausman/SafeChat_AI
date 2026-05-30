import { useEffect, useState } from 'react';
import { Activity, BellRing, RefreshCw, Server, Workflow } from 'lucide-react';
import { apiClient } from '../lib/api';

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
    bridge_status: string;
    bridge_reachable: boolean;
    connected_phone?: string | null;
    total_live_chats: number;
    total_live_messages: number;
    flagged_live_messages: number;
    total_alerts: number;
    open_alerts: number;
    acknowledged_alerts: number;
    resolved_alerts: number;
    safe_ratio: number;
    last_message_at?: string | null;
  };
  recent_feed_count: number;
  recent_alert_count: number;
  recent_flagged_message_count: number;
  flagged_chat_count: number;
  high_risk_chat_count: number;
  recent_window_hours: number;
  attention_required: boolean;
};

type AlertSummary = {
  total_alerts: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  latest_alert_at?: string | null;
};

type BackendHealthSummary = {
  bridge_ops: BridgeOpsSummary;
  live_ops: LiveOpsSummary;
  recent_window_hours: number;
  attention_required: boolean;
  status: 'healthy' | 'attention';
};

function formatDateTime(value?: string | null) {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unavailable';
  return parsed.toLocaleString();
}

function formatCounts(entries: Record<string, number>) {
  const items = Object.entries(entries);
  if (!items.length) return 'No data';
  return items.map(([key, value]) => `${key}: ${value}`).join(' | ');
}

export default function AdminOperations() {
  const [healthSummary, setHealthSummary] = useState<BackendHealthSummary | null>(null);
  const [bridgeOps, setBridgeOps] = useState<BridgeOpsSummary | null>(null);
  const [liveOps, setLiveOps] = useState<LiveOpsSummary | null>(null);
  const [alertSummary, setAlertSummary] = useState<AlertSummary | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadData = async (showSpinner = false) => {
    if (showSpinner) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    const [healthResult, bridgeResult, liveResult, alertResult] = await Promise.allSettled([
      apiClient.get('/api/whatsapp/health-summary'),
      apiClient.get('/api/whatsapp/bridge-ops-summary'),
      apiClient.get('/api/whatsapp/ops-summary'),
      apiClient.get('/api/whatsapp/alerts/summary'),
    ]);

    const nextErrors: string[] = [];

    if (healthResult.status === 'fulfilled') {
      setHealthSummary(healthResult.value.data);
    } else {
      nextErrors.push('Backend health summary is unavailable.');
    }

    if (bridgeResult.status === 'fulfilled') {
      setBridgeOps(bridgeResult.value.data);
    } else {
      nextErrors.push('Bridge ops summary is unavailable.');
    }

    if (liveResult.status === 'fulfilled') {
      setLiveOps(liveResult.value.data);
    } else {
      nextErrors.push('Live ops summary is unavailable.');
    }

    if (alertResult.status === 'fulfilled') {
      setAlertSummary(alertResult.value.data);
    } else {
      nextErrors.push('Alert summary is unavailable.');
    }

    setError(nextErrors.join(' '));
    setLastUpdated(new Date().toISOString());
    setIsLoading(false);
    setIsRefreshing(false);
  };

  useEffect(() => {
    void loadData(false);
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <section className="overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(135deg,rgba(16,26,48,0.96),rgba(17,35,48,0.92))] p-6 shadow-[0_30px_120px_rgba(34,211,238,0.12)] md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">ADMIN OPS</p>
            <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">Backend and bridge operations</h1>
            <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">
              Single place to review backend health, bridge activity, live monitoring posture, and alert summary counts.
            </p>
          </div>

          <div className="flex flex-col items-start gap-3 lg:items-end">
            <button
              onClick={() => void loadData(true)}
              disabled={isRefreshing}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Refresh now'}
            </button>
            <p className="text-xs text-slate-400">
              {lastUpdated ? `Last updated ${formatDateTime(lastUpdated)}` : 'Not refreshed yet'}
            </p>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Backend health</p>
          <p className={`mt-3 text-2xl font-semibold ${healthSummary?.status === 'attention' ? 'text-amber-300' : 'text-emerald-300'}`}>
            {healthSummary?.status ?? 'unknown'}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            Recent window: {healthSummary?.recent_window_hours ?? 24} hours
          </p>
        </div>
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Bridge ops</p>
          <p className="mt-3 text-2xl font-semibold text-white">{bridgeOps?.current_state.status ?? 'unknown'}</p>
          <p className="mt-2 text-xs text-slate-400">
            {bridgeOps?.recent_event_count ?? 0} events | {bridgeOps?.recent_snapshot_count ?? 0} snapshots
          </p>
        </div>
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Live ops</p>
          <p className="mt-3 text-2xl font-semibold text-white">{liveOps?.live_summary.total_live_chats ?? 0}</p>
          <p className="mt-2 text-xs text-slate-400">
            live chats | {liveOps?.live_summary.total_live_messages ?? 0} live messages
          </p>
        </div>
        <div className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.3)]">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Alert summary</p>
          <p className="mt-3 text-2xl font-semibold text-white">{alertSummary?.total_alerts ?? 0}</p>
          <p className="mt-2 text-xs text-slate-400">
            total alerts across the live moderation backend
          </p>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <Server className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">BACKEND HEALTH</p>
              <h2 className="mt-1 text-2xl font-semibold text-white">Overall status</h2>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Status</p>
              <p className={`mt-2 text-2xl font-semibold ${healthSummary?.status === 'attention' ? 'text-amber-300' : 'text-emerald-300'}`}>
                {healthSummary?.status ?? (isLoading ? 'loading' : 'unknown')}
              </p>
              <p className="mt-2 text-sm text-slate-400">
                {healthSummary?.attention_required ? 'One or more checks require attention.' : 'All tracked checks are stable.'}
              </p>
            </div>
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Last refresh</p>
              <p className="mt-2 text-sm text-white">{formatDateTime(lastUpdated)}</p>
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <Workflow className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">BRIDGE OPS</p>
              <h2 className="mt-1 text-2xl font-semibold text-white">Session and bridge state</h2>
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Current state</p>
              <p className="mt-2 text-xl font-semibold text-white">{bridgeOps?.current_state.status ?? 'unknown'}</p>
              <p className="mt-2 text-sm text-slate-400">
                {bridgeOps?.bridge_reachable ? 'Bridge reachable' : 'Bridge offline or unreachable'}
              </p>
            </div>
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Connected account</p>
              <p className="mt-2 text-sm text-white">{bridgeOps?.current_state.connected_phone ?? 'None recorded'}</p>
              <p className="mt-2 text-sm text-slate-400">
                Window: {bridgeOps?.recent_window_hours ?? 24} hours
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <Activity className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">LIVE OPS</p>
              <h2 className="mt-1 text-2xl font-semibold text-white">Live moderation flow</h2>
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Volume</p>
              <p className="mt-2 text-sm text-white">
                {liveOps?.live_summary.total_live_messages ?? 0} messages | {liveOps?.recent_feed_count ?? 0} in recent window
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Last live message: {formatDateTime(liveOps?.live_summary.last_message_at)}
              </p>
            </div>
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Risk posture</p>
              <p className="mt-2 text-sm text-white">
                {liveOps?.flagged_chat_count ?? 0} flagged chats | {liveOps?.high_risk_chat_count ?? 0} high-risk chats
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Safe ratio: {liveOps?.live_summary.safe_ratio?.toFixed(1) ?? '0.0'}%
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <BellRing className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">ALERT SUMMARY</p>
              <h2 className="mt-1 text-2xl font-semibold text-white">Severity and status mix</h2>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">By severity</p>
              <p className="mt-2 text-sm text-white">{formatCounts(alertSummary?.by_severity ?? {})}</p>
            </div>
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">By status</p>
              <p className="mt-2 text-sm text-white">{formatCounts(alertSummary?.by_status ?? {})}</p>
            </div>
            <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <p className="text-sm text-slate-400">Latest alert</p>
              <p className="mt-2 text-sm text-white">{formatDateTime(alertSummary?.latest_alert_at)}</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
