import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, RefreshCw } from 'lucide-react';
import { apiClient } from '../lib/api';

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

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: 'cyan' | 'rose' | 'emerald';
}) {
  const toneMap = {
    cyan: 'from-cyan-500/15 to-blue-500/10 text-cyan-300 border-cyan-500/20',
    rose: 'from-rose-500/15 to-fuchsia-500/10 text-rose-300 border-rose-500/20',
    emerald: 'from-emerald-500/15 to-teal-500/10 text-emerald-300 border-emerald-500/20',
  };

  return (
    <div className={`rounded-[22px] border bg-gradient-to-br p-5 ${toneMap[tone]}`}>
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold md:text-4xl">{value}</p>
    </div>
  );
}

export default function ReportsPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
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
    try {
      const response = await apiClient.get('/api/analyze/dashboard-summary');
      setSummary(response.data);
      setLastUpdated(new Date().toISOString());
    } catch {
      setSummary(null);
      setError('Reports are unavailable right now.');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    void loadSummary(false);
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6 sm:py-5 lg:px-8">
      <section className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(135deg,rgba(10,18,34,0.98),rgba(8,14,26,0.96))] p-4 shadow-[0_30px_120px_rgba(34,211,238,0.08)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-2xl bg-cyan-500/14 p-3 text-cyan-300">
              <FileText className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-white">Reports</h1>
              <p className="mt-1 text-sm text-slate-400">Review saved analyses and open full result pages.</p>
            </div>
          </div>
          <div className="flex flex-col items-start gap-3 lg:items-end">
            <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
              <p className="text-xs text-slate-400">Records</p>
              <p className="text-sm font-medium text-white">{summary?.recent_chats?.length ?? 0} recent report(s)</p>
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

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <StatCard label="Chats analyzed" value={summary?.total_chats ?? 0} tone="cyan" />
          <StatCard label="Flagged messages" value={summary?.flagged_messages ?? 0} tone="rose" />
          <StatCard label="Safe ratio" value={`${summary?.safe_ratio?.toFixed(1) ?? '100.0'}%`} tone="emerald" />
        </div>
        <p className="mt-5 text-xs text-slate-400">
          {lastUpdated ? `Last updated ${new Date(lastUpdated).toLocaleString()}` : 'Not refreshed yet'}
        </p>
      </section>

      {error && (
        <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] backdrop-blur md:p-5">
        <h2 className="text-xl font-semibold text-white md:text-2xl">Recent reports</h2>
        <div className="mt-4 max-h-[34rem] space-y-3 overflow-auto pr-1">
          {isLoading ? (
            <div className="rounded-[20px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-slate-400">
              Loading reports...
            </div>
          ) : summary?.recent_chats?.length ? (
            summary.recent_chats.map((chat) => (
              <Link
                key={chat.id}
                to={`/results/${chat.id}`}
                className="flex flex-col gap-3 rounded-[20px] border border-white/6 bg-slate-950/70 px-4 py-3 transition hover:border-cyan-500/30 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="font-medium text-white">{chat.chat_name}</p>
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
              </Link>
            ))
          ) : (
            <div className="rounded-[20px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-slate-400">
              No reports yet. Run an analysis from Analyze Chat first.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
