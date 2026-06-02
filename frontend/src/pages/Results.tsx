import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import {
  AlertTriangle,
  ArrowLeft,
  Clock3,
  Download,
  MessageSquareWarning,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { apiClient, getGuestReport } from '../lib/api';

type ReportMessage = {
  sender: string;
  message: string;
  timestamp?: string | null;
  risk_score?: number | null;
  label?: string | null;
};

type ReportData = {
  id: number;
  chat_name: string;
  analysis_results?: {
    overall_score: number;
    safe_percentage: number;
    unsafe_percentage: number;
    summary: string;
  } | null;
  messages: ReportMessage[];
};

export default function Results() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchReport = async () => {
      if (id === 'guest') {
        const guestReport = getGuestReport();
        if (guestReport) {
          setData(guestReport as ReportData);
        } else {
          setError('Guest report is unavailable. Run the guest analysis again.');
        }
        setLoading(false);
        return;
      }
      try {
        const response = await apiClient.get(`/api/analyze/report/${id}`);
        setData(response.data);
      } catch (err: any) {
        if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
          setError('Request timed out while fetching the report. Try again.');
        } else if (err.response) {
          setError(err.response.data?.detail || `Server error: ${err.response.status}`);
        } else {
          setError('Failed to load analysis report.');
        }
      } finally {
        setLoading(false);
      }
    };
    void fetchReport();
  }, [id]);

  const derived = useMemo(() => {
    if (!data) return null;
    const analysis = data.analysis_results;
    const flaggedMessages = data.messages.filter((m) => (m.risk_score ?? 0) > 50);
    const highRisk = (analysis?.unsafe_percentage ?? 0) > 20;
    const pieData = [
      { name: 'Safe', value: analysis?.safe_percentage || 0, color: '#10b981' },
      { name: 'Unsafe', value: analysis?.unsafe_percentage || 0, color: '#ef4444' },
    ];
    return { analysis, flaggedMessages, highRisk, pieData };
  }, [data]);

  const downloadReport = () => {
    if (!data || !derived) return;
    const { analysis, flaggedMessages } = derived;
    const lines = [
      'SafeChat AI Report',
      `Chat: ${data.chat_name}`,
      `Summary: ${analysis?.summary ?? 'No summary available.'}`,
      `Overall score: ${(analysis?.overall_score ?? 0).toFixed(1)}`,
      `Safe percentage: ${(analysis?.safe_percentage ?? 0).toFixed(1)}%`,
      `Unsafe percentage: ${(analysis?.unsafe_percentage ?? 0).toFixed(1)}%`,
      `Messages analyzed: ${data.messages.length}`,
      `Flagged messages: ${flaggedMessages.length}`,
      '',
      'Flagged message details:',
      ...flaggedMessages.map((msg, index) => {
        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString() : 'Unavailable';
        return `${index + 1}. [${timestamp}] ${msg.sender}: ${msg.message} | Risk ${(msg.risk_score ?? 0).toFixed(1)} | ${msg.label ?? 'Unclassified'}`;
      }),
    ].join('\n');

    const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${(data.chat_name || 'safechat-report').replace(/[^a-z0-9-_]+/gi, '_')}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-[28px] border border-white/8 bg-slate-900/70 p-8 text-center text-slate-400 shadow-[0_24px_80px_rgba(15,23,42,0.35)]">
          Loading analysis results...
        </div>
      </div>
    );
  }

  if (error || !data || !derived) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-[28px] border border-rose-500/20 bg-rose-500/8 p-8 text-center shadow-[0_24px_80px_rgba(15,23,42,0.35)]">
          <p className="text-rose-300">{error || 'Report data is unavailable.'}</p>
          <div className="mt-4">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  const { analysis, flaggedMessages, highRisk, pieData } = derived;

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/analyze"
          className="inline-flex items-center gap-2 rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-sm text-slate-300 transition hover:bg-white/[0.06] hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to analyzer
        </Link>
        <button
          type="button"
          onClick={downloadReport}
          className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-300 transition hover:bg-cyan-500/15"
        >
          <Download className="h-4 w-4" />
          Download safety report
        </button>
      </div>

      <section className="overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(135deg,rgba(18,28,58,0.96),rgba(21,15,39,0.94))] p-6 shadow-[0_30px_120px_rgba(59,130,246,0.15)] md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">ANALYSIS REPORT</p>
            <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">{data.chat_name}</h1>
            <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">{analysis?.summary}</p>
          </div>

          <div className={`inline-flex items-center gap-3 rounded-full border px-5 py-3 text-sm font-semibold ${highRisk ? 'border-rose-500/25 bg-rose-500/10 text-rose-300' : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'}`}>
            {highRisk ? <ShieldAlert className="h-5 w-5" /> : <ShieldCheck className="h-5 w-5" />}
            {highRisk ? 'High risk detected' : 'Generally safe'}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.88fr_1.12fr]">
        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">OVERVIEW</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Safety ratio</h2>

          <div className="mt-6 h-60">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={72} outerRadius={92} paddingAngle={4} dataKey="value">
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '16px', color: '#fff' }}
                  itemStyle={{ color: '#fff' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <div className="flex items-center gap-2 text-sm text-slate-300">
              <div className="h-3 w-3 rounded-full bg-emerald-500" />
              Safe ({analysis?.safe_percentage?.toFixed(1)}%)
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-300">
              <div className="h-3 w-3 rounded-full bg-rose-500" />
              Unsafe ({analysis?.unsafe_percentage?.toFixed(1)}%)
            </div>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="rounded-[20px] border border-white/8 bg-slate-950/60 p-4">
              <p className="text-sm text-slate-400">Messages analyzed</p>
              <p className="mt-3 text-2xl font-semibold text-white">{data.messages.length}</p>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/60 p-4">
              <p className="text-sm text-slate-400">Flagged messages</p>
              <p className="mt-3 text-2xl font-semibold text-rose-400">{flaggedMessages.length}</p>
            </div>
            <div className="rounded-[20px] border border-white/8 bg-slate-950/60 p-4">
              <p className="text-sm text-slate-400">Average score</p>
              <p className="mt-3 text-2xl font-semibold text-white">{analysis?.overall_score?.toFixed(1) ?? '0.0'}</p>
            </div>
          </div>
        </section>

        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <AlertTriangle className="h-5 w-5 text-amber-300" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">FLAGGED CONTENT</p>
              <h2 className="mt-1 text-2xl font-semibold text-white">Dangerous messages</h2>
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {flaggedMessages.slice(0, 24).map((msg, i) => (
              <div key={i} className="rounded-[22px] border border-rose-500/18 bg-rose-500/[0.05] p-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="font-semibold text-slate-100">{msg.sender}</p>
                    {msg.timestamp && (
                      <div className="mt-1 flex items-center gap-1 text-xs text-slate-400">
                        <Clock3 className="h-3.5 w-3.5" />
                        <span>{new Date(msg.timestamp).toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 font-medium text-rose-300">
                      Risk {(msg.risk_score ?? 0).toFixed(1)}
                    </span>
                    {msg.label && (
                      <span className="rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 font-medium text-slate-200">
                        {msg.label}
                      </span>
                    )}
                  </div>
                </div>
                <p className="mt-3 text-sm leading-7 text-slate-100">{msg.message}</p>
              </div>
            ))}
            {flaggedMessages.length === 0 && (
              <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-slate-400">
                No dangerous messages detected.
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <MessageSquareWarning className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">MESSAGE LOG</p>
              <h2 className="mt-1 text-2xl font-semibold text-white">Dense moderation review</h2>
            </div>
          </div>
          <div className="rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-sm text-slate-300">
            Showing {Math.min(data.messages.length, 100)} of {data.messages.length}
          </div>
        </div>

        <div className="mt-5 overflow-hidden rounded-[22px] border border-white/8 bg-slate-950/55">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-white/8 bg-white/[0.03] text-xs uppercase tracking-[0.16em] text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Sender</th>
                  <th className="px-4 py-3 font-medium">Timestamp</th>
                  <th className="px-4 py-3 font-medium">Message</th>
                  <th className="px-4 py-3 font-medium">Label</th>
                  <th className="px-4 py-3 font-medium text-right">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/6">
                {data.messages.slice(0, 100).map((msg, i) => (
                  <tr key={i} className="align-top transition hover:bg-white/[0.025]">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-200">{msg.sender}</div>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      {msg.timestamp ? new Date(msg.timestamp).toLocaleString() : '-'}
                    </td>
                    <td className="max-w-[28rem] px-4 py-3 text-slate-100">
                      <div className="line-clamp-3 leading-6">{msg.message}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-3 py-1.5 text-xs font-medium ${(msg.risk_score ?? 0) > 50 ? 'border border-rose-500/20 bg-rose-500/10 text-rose-300' : 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                        {msg.label ?? 'Safe'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-medium text-slate-300">
                      {(msg.risk_score ?? 0).toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
