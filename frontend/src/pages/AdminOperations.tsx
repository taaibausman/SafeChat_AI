import { useEffect, useMemo, useState } from 'react';
import { BellRing, RefreshCw, Server, ShieldCheck, Smartphone } from 'lucide-react';
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

function StatusCard({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string | number;
  note: string;
  tone: 'cyan' | 'emerald' | 'amber' | 'rose';
}) {
  const toneMap = {
    cyan: 'from-cyan-500/15 to-blue-500/10 text-cyan-300 border-cyan-500/20',
    emerald: 'from-emerald-500/15 to-teal-500/10 text-emerald-300 border-emerald-500/20',
    amber: 'from-amber-500/15 to-orange-500/10 text-amber-300 border-amber-500/20',
    rose: 'from-rose-500/15 to-fuchsia-500/10 text-rose-300 border-rose-500/20',
  };

  return (
    <div className={`rounded-[24px] border bg-gradient-to-br p-5 ${toneMap[tone]}`}>
      <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
      <p className="mt-2 text-sm text-slate-300">{note}</p>
    </div>
  );
}

function SimplePanel({
  icon,
  eyebrow,
  title,
  children,
}: {
  icon: React.ReactNode;
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
      <div className="flex items-center gap-3">
        <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">{icon}</div>
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">{eyebrow}</p>
          <h2 className="mt-1 text-2xl font-semibold text-white">{title}</h2>
        </div>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
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
      setHealthSummary(null);
      nextErrors.push('Backend health summary is unavailable.');
    }

    if (bridgeResult.status === 'fulfilled') {
      setBridgeOps(bridgeResult.value.data);
    } else {
      setBridgeOps(null);
      nextErrors.push('Bridge status is unavailable.');
    }

    if (liveResult.status === 'fulfilled') {
      setLiveOps(liveResult.value.data);
    } else {
      setLiveOps(null);
      nextErrors.push('Live monitoring summary is unavailable.');
    }

    if (alertResult.status === 'fulfilled') {
      setAlertSummary(alertResult.value.data);
    } else {
      setAlertSummary(null);
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

  const primaryStatus = useMemo(() => {
    if (healthSummary?.status === 'healthy') {
      return { value: 'Healthy', note: 'Bridge and live monitoring look stable.', tone: 'emerald' as const };
    }
    return { value: 'Needs attention', note: 'One or more system checks need review.', tone: 'amber' as const };
  }, [healthSummary]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <section className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(135deg,rgba(10,18,34,0.98),rgba(8,14,26,0.96))] p-5 shadow-[0_30px_120px_rgba(34,211,238,0.08)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-2xl bg-cyan-500/14 p-3 text-cyan-300">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-white">System Health</h1>
              <p className="mt-1 text-sm text-slate-400">
                A simple admin view for the shared WhatsApp bridge, live feed, and alerts.
              </p>
            </div>
          </div>

          <button
            onClick={() => void loadData(true)}
            disabled={isRefreshing}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-4">
          <StatusCard label="Overall" value={primaryStatus.value} note={primaryStatus.note} tone={primaryStatus.tone} />
          <StatusCard
            label="Bridge"
            value={bridgeOps?.current_state.status ?? 'unknown'}
            note={bridgeOps?.bridge_reachable ? 'WhatsApp bridge is reachable.' : 'Bridge is offline or unreachable.'}
            tone={bridgeOps?.bridge_reachable ? 'cyan' : 'amber'}
          />
          <StatusCard
            label="Live Messages"
            value={liveOps?.live_summary.total_live_messages ?? 0}
            note={`${liveOps?.live_summary.total_live_chats ?? 0} chat(s) currently represented in the live feed.`}
            tone="emerald"
          />
          <StatusCard
            label="Open Alerts"
            value={liveOps?.live_summary.open_alerts ?? 0}
            note={`${alertSummary?.total_alerts ?? 0} total alert record(s) in the system.`}
            tone={(liveOps?.live_summary.open_alerts ?? 0) > 0 ? 'rose' : 'emerald'}
          />
        </div>

        <p className="mt-5 text-xs text-slate-400">
          {lastUpdated ? `Last updated ${formatDateTime(lastUpdated)}` : isLoading ? 'Loading system state...' : 'Not refreshed yet'}
        </p>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-3">
        <SimplePanel icon={<Server className="h-5 w-5 text-cyan-300" />} eyebrow="Bridge" title="WhatsApp bridge">
          <div className="space-y-3 text-sm text-slate-300">
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Status: <span className="font-medium text-white">{bridgeOps?.current_state.status ?? 'unknown'}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Reachable: <span className="font-medium text-white">{bridgeOps?.bridge_reachable ? 'Yes' : 'No'}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Connected phone: <span className="font-medium text-white">{bridgeOps?.current_state.connected_phone ?? 'None recorded'}</span>
            </div>
          </div>
        </SimplePanel>

        <SimplePanel icon={<Smartphone className="h-5 w-5 text-cyan-300" />} eyebrow="Live Feed" title="Shared monitoring">
          <div className="space-y-3 text-sm text-slate-300">
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              This is a shared system-wide monitor, not a separate inbox per user.
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Messages: <span className="font-medium text-white">{liveOps?.live_summary.total_live_messages ?? 0}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Flagged messages: <span className="font-medium text-white">{liveOps?.live_summary.flagged_live_messages ?? 0}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Last live message: <span className="font-medium text-white">{formatDateTime(liveOps?.live_summary.last_message_at)}</span>
            </div>
          </div>
        </SimplePanel>

        <SimplePanel icon={<BellRing className="h-5 w-5 text-cyan-300" />} eyebrow="Alerts" title="Alert state">
          <div className="space-y-3 text-sm text-slate-300">
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Open: <span className="font-medium text-white">{liveOps?.live_summary.open_alerts ?? 0}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Acknowledged: <span className="font-medium text-white">{liveOps?.live_summary.acknowledged_alerts ?? 0}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Resolved: <span className="font-medium text-white">{liveOps?.live_summary.resolved_alerts ?? 0}</span>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/55 p-4">
              Latest alert: <span className="font-medium text-white">{formatDateTime(alertSummary?.latest_alert_at)}</span>
            </div>
          </div>
        </SimplePanel>
      </div>
    </div>
  );
}
