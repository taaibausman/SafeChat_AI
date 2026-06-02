import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { LayoutDashboard, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { apiClient, getStoredSession } from '../lib/api';

type DashboardSummary = {
  total_chats: number;
  total_messages: number;
  flagged_messages: number;
  safe_ratio: number;
  recent_chats: Array<{
    id: number;
    chat_name: string;
    platform: string;
    created_at: string;
    unsafe_percentage: number | null;
    flagged_messages: number;
  }>;
};

type BackendHealthSummary = {
  bridge_ops: {
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
  live_ops: {
    live_summary: {
      total_live_chats: number;
      total_live_messages: number;
      flagged_live_messages: number;
      open_alerts: number;
    };
    recent_feed_count: number;
    recent_alert_count: number;
    flagged_chat_count: number;
    high_risk_chat_count: number;
    recent_window_hours: number;
    attention_required: boolean;
  };
  recent_window_hours: number;
  attention_required: boolean;
  status: 'healthy' | 'attention';
};

type UserRecord = {
  id: number;
  username?: string | null;
  email: string;
  role: string;
  is_active: boolean;
  name?: string | null;
  created_at: string;
};

type UserListResponse = {
  total: number;
  limit: number;
  offset: number;
  users: UserRecord[];
};

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: 'cyan' | 'rose' | 'emerald' | 'amber';
}) {
  const toneMap = {
    cyan: 'from-cyan-500/15 to-blue-500/10 text-cyan-300 border-cyan-500/20',
    rose: 'from-rose-500/15 to-fuchsia-500/10 text-rose-300 border-rose-500/20',
    emerald: 'from-emerald-500/15 to-teal-500/10 text-emerald-300 border-emerald-500/20',
    amber: 'from-amber-500/15 to-orange-500/10 text-amber-300 border-amber-500/20',
  };

  return (
    <div className={`rounded-[22px] border bg-gradient-to-br p-5 ${toneMap[tone]}`}>
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold md:text-4xl">{value}</p>
    </div>
  );
}

export default function DashboardPage() {
  const session = getStoredSession();
  const isAdmin = session?.user.role === 'admin';
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [healthSummary, setHealthSummary] = useState<BackendHealthSummary | null>(null);
  const [userSummary, setUserSummary] = useState<UserListResponse | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadSummary = async (showSpinner = false) => {
    if (showSpinner) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setError('');

    const requests = [
      apiClient.get('/api/analyze/dashboard-summary'),
      apiClient.get('/api/whatsapp/health-summary'),
      ...(isAdmin ? [apiClient.get('/api/users', { params: { limit: 100 } })] : []),
    ];

    const results = await Promise.allSettled(requests);
    const [dashboardResult, healthResult, usersResult] = results;

    const nextErrors: string[] = [];
    if (dashboardResult.status === 'fulfilled') {
      setSummary(dashboardResult.value.data);
    } else {
      setSummary(null);
      nextErrors.push('Dashboard summary could not be loaded.');
    }

    if (healthResult.status === 'fulfilled') {
      setHealthSummary(healthResult.value.data);
    } else {
      setHealthSummary(null);
      nextErrors.push('Backend health summary is unavailable.');
    }

    if (isAdmin) {
      if (usersResult?.status === 'fulfilled') {
        setUserSummary(usersResult.value.data as UserListResponse);
      } else {
        setUserSummary(null);
        nextErrors.push('Admin user summary is unavailable.');
      }
    } else {
      setUserSummary(null);
    }

    setError(nextErrors.join(' '));
    setLastUpdated(new Date().toISOString());
    setIsLoading(false);
    setIsRefreshing(false);
  };

  useEffect(() => {
    void loadSummary(false);
  }, [isAdmin]);

  const adminStats = useMemo(() => {
    const users = userSummary?.users ?? [];
    return {
      totalUsers: userSummary?.total ?? 0,
      adminUsers: users.filter((user) => user.role === 'admin').length,
      activeUsers: users.filter((user) => user.is_active).length,
      inactiveUsers: users.filter((user) => !user.is_active).length,
    };
  }, [userSummary]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <section className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(135deg,rgba(10,18,34,0.98),rgba(8,14,26,0.96))] p-5 shadow-[0_30px_120px_rgba(34,211,238,0.08)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-2xl bg-cyan-500/14 p-3 text-cyan-300">
              <LayoutDashboard className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-white">{isAdmin ? 'Admin Dashboard' : 'Dashboard'}</h1>
              <p className="mt-1 text-sm text-slate-400">
                {isAdmin ? 'User accounts, access state, and backend operations.' : 'Live workspace summary and moderation coverage.'}
              </p>
            </div>
          </div>

          <div className="flex flex-col items-start gap-3 lg:items-end">
            <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
              <div className={`h-2.5 w-2.5 rounded-full ${healthSummary?.attention_required ? 'bg-amber-300' : 'bg-emerald-300'}`} />
              <div>
                <p className="text-xs text-slate-400">System status</p>
                <p className="text-sm font-medium text-white">{healthSummary?.status ?? 'unknown'}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void loadSummary(true)}
              disabled={isRefreshing}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Refresh now'}
            </button>
          </div>
        </div>

        {isAdmin ? (
          <div className="mt-6 grid gap-4 md:grid-cols-4">
            <StatCard label="Total users" value={adminStats.totalUsers} tone="cyan" />
            <StatCard label="Admin accounts" value={adminStats.adminUsers} tone="amber" />
            <StatCard label="Active users" value={adminStats.activeUsers} tone="emerald" />
            <StatCard label="Disabled users" value={adminStats.inactiveUsers} tone="rose" />
          </div>
        ) : (
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <StatCard label="Total chats analyzed" value={summary?.total_chats ?? 0} tone="cyan" />
            <StatCard label="Flagged messages" value={summary?.flagged_messages ?? 0} tone="rose" />
            <StatCard label="Safe ratio" value={`${summary?.safe_ratio?.toFixed(1) ?? '100.0'}%`} tone="emerald" />
          </div>
        )}
        <p className="mt-5 text-xs text-slate-400">
          {lastUpdated ? `Last updated ${new Date(lastUpdated).toLocaleString()}` : 'Not refreshed yet'}
        </p>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] backdrop-blur md:p-6">
          <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">{isAdmin ? 'USERS' : 'QUEUE'}</p>
          <h2 className="text-xl font-semibold text-white md:text-2xl">{isAdmin ? 'Recent user accounts' : 'Recent analyses'}</h2>
          <div className="mt-5 space-y-3">
            {isLoading ? (
              <div className="rounded-[20px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-slate-400">
                Loading {isAdmin ? 'user records' : 'recent analyses'}...
              </div>
            ) : isAdmin ? (
              userSummary?.users?.length ? (
                userSummary.users.slice(0, 8).map((user) => (
                  <div key={user.id} className="rounded-[20px] border border-white/6 bg-slate-950/60 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-100">{user.name || user.username || user.email}</p>
                        <p className="mt-1 text-sm text-slate-400">
                          {user.email} · {new Date(user.created_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        <span className={`rounded-full px-3 py-1.5 text-xs ${user.role === 'admin' ? 'border border-cyan-500/25 bg-cyan-500/10 text-cyan-300' : 'border border-white/8 bg-white/[0.03] text-slate-300'}`}>
                          {user.role}
                        </span>
                        <span className={`rounded-full px-3 py-1.5 text-xs ${user.is_active ? 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300' : 'border border-rose-500/20 bg-rose-500/10 text-rose-300'}`}>
                          {user.is_active ? 'active' : 'disabled'}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[20px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-slate-400">
                  No user records available.
                </div>
              )
            ) : summary?.recent_chats?.length ? (
              summary.recent_chats.map((chat) => (
                <Link
                  key={chat.id}
                  to={`/results/${chat.id}`}
                  className="block rounded-[20px] border border-white/6 bg-slate-950/60 p-4 transition hover:border-cyan-500/30 hover:bg-slate-950"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="font-medium text-slate-100">{chat.chat_name}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {chat.platform} · {new Date(chat.created_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-6 text-sm">
                      <div>
                        <p className="text-slate-500">Flagged</p>
                        <p className="font-medium text-rose-400">{chat.flagged_messages}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Unsafe</p>
                        <p className="font-medium text-amber-400">{chat.unsafe_percentage?.toFixed(1) ?? '0.0'}%</p>
                      </div>
                    </div>
                  </div>
                </Link>
              ))
            ) : (
              <div className="rounded-[20px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-slate-400">
                No analyses yet. Upload a chat export to populate the dashboard.
              </div>
            )}
          </div>
          {isAdmin && (
            <div className="mt-5">
              <Link
                to="/settings"
                className="inline-flex items-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08]"
              >
                <Users className="h-4 w-4" />
                Open user management
              </Link>
            </div>
          )}
        </section>

        <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] backdrop-blur md:p-6">
          <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">{isAdmin ? 'OPERATIONS' : 'STATUS'}</p>
          <h2 className="text-xl font-semibold text-white md:text-2xl">{isAdmin ? 'Admin overview' : 'Coverage'}</h2>
          <div className="mt-5 space-y-4">
            <div className="rounded-[20px] border border-white/6 bg-slate-950/60 p-5">
              <p className="text-sm text-slate-400">{isAdmin ? 'Moderation records' : 'Total messages analyzed'}</p>
              <p className="mt-3 text-3xl font-semibold text-white">{summary?.total_messages ?? 0}</p>
            </div>
            {isAdmin && (
              <div className="rounded-[20px] border border-white/6 bg-slate-950/60 p-5">
                <div className="flex items-center gap-3">
                  <ShieldCheck className="h-5 w-5 text-cyan-300" />
                  <div>
                    <p className="text-sm text-slate-400">Account role mix</p>
                    <p className="mt-1 text-sm text-slate-300">
                      {adminStats.adminUsers} admin · {Math.max(adminStats.totalUsers - adminStats.adminUsers, 0)} standard users
                    </p>
                  </div>
                </div>
              </div>
            )}
            <div className="rounded-[20px] border border-white/6 bg-slate-950/60 p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-400">Backend health</p>
                  <p className={`mt-3 text-2xl font-semibold ${healthSummary?.status === 'attention' ? 'text-amber-300' : 'text-emerald-300'}`}>
                    {healthSummary?.status ?? 'unknown'}
                  </p>
                </div>
                <span className={`rounded-full px-3 py-1.5 text-xs ${healthSummary?.attention_required ? 'border border-amber-500/20 bg-amber-500/10 text-amber-300' : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                  {healthSummary?.attention_required ? 'Needs review' : 'Stable'}
                </span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Bridge ops</p>
                  <p className="mt-2 text-sm text-white">
                    {healthSummary?.bridge_ops.current_state.status ?? 'unknown'}
                    {healthSummary?.bridge_ops.bridge_reachable ? ' · reachable' : ' · offline'}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    {healthSummary?.bridge_ops.recent_event_count ?? 0} events · {healthSummary?.bridge_ops.recent_snapshot_count ?? 0} snapshots
                  </p>
                </div>
                <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Live ops</p>
                  <p className="mt-2 text-sm text-white">
                    {healthSummary?.live_ops.live_summary.total_live_chats ?? 0} chats · {healthSummary?.live_ops.live_summary.total_live_messages ?? 0} messages
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    {healthSummary?.live_ops.live_summary.flagged_live_messages ?? 0} flagged · {healthSummary?.live_ops.live_summary.open_alerts ?? 0} open alerts
                  </p>
                </div>
              </div>
              {healthSummary?.bridge_ops.current_state.connected_phone && (
                <p className="mt-4 text-xs text-cyan-300">Connected account: {healthSummary.bridge_ops.current_state.connected_phone}</p>
              )}
            </div>
            <div className="rounded-[20px] border border-white/6 bg-slate-950/60 p-5">
              <p className="text-sm text-slate-400">{isAdmin ? 'Operational window' : 'Operational window'}</p>
              <p className="mt-3 text-sm leading-7 text-slate-300">
                {healthSummary
                  ? `Recent live activity is summarized across the last ${healthSummary.recent_window_hours} hour(s).`
                  : 'Recent live activity will appear here after the backend health summary loads.'}
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
