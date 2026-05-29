import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, FileText, MessageSquareText, Shield, Upload } from 'lucide-react';
import { apiClient } from '../lib/api';

export default function ExportAnalyzer() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError('');
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    if (!file.name.endsWith('.txt')) {
      setError('Please upload a valid .txt WhatsApp export file.');
      return;
    }

    setIsUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await apiClient.post(`/api/analyze/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      });
      setResults(response.data);
    } catch (err: any) {
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError('Analysis is taking longer than expected. Wait for model warmup, then retry.');
      } else {
        setError(err.response?.data?.detail || err.message || 'An error occurred during analysis.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <section className="overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(135deg,rgba(18,28,58,0.96),rgba(21,15,39,0.94))] p-6 shadow-[0_30px_120px_rgba(59,130,246,0.15)] md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">ANALYZE CHAT</p>
            <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">WhatsApp export review</h1>
            <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">
              Upload a WhatsApp `.txt` export and generate a structured moderation report with risk scores, flagged messages, and summary insights.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:w-[29rem]">
            {[
              ['Input', '.txt export'],
              ['Output', 'Risk report'],
              ['Mode', 'Offline scan'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-white/8 bg-white/[0.04] p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
                <p className="mt-2 text-sm font-medium text-white">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div
            className="cursor-pointer rounded-[24px] border-2 border-dashed border-white/10 bg-slate-950/55 p-8 text-center transition hover:border-cyan-500/35 hover:bg-slate-950/70 sm:p-12"
            onClick={() => document.getElementById('file-upload')?.click()}
          >
            <div className="mx-auto inline-flex rounded-3xl border border-cyan-500/20 bg-cyan-500/10 p-4">
              <Upload className="h-10 w-10 text-cyan-300" />
            </div>
            <h3 className="mt-6 text-2xl font-semibold text-white">Drop export or click to upload</h3>
            <p className="mt-3 text-sm leading-7 text-slate-400">
              Use the raw WhatsApp text export. The analyzer will extract messages, score them, and generate a linked report.
            </p>
            <div className="mt-5 inline-flex rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-xs text-slate-300">
              Supported format: `.txt`
            </div>
            <input type="file" id="file-upload" className="hidden" accept=".txt" onChange={handleFileChange} />
          </div>

          {file && (
            <div className="mt-5 rounded-[22px] border border-white/8 bg-slate-950/65 p-4">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                    <FileText className="h-5 w-5 text-cyan-300" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-white">{file.name}</p>
                    <p className="text-xs text-slate-400">{(file.size / 1024).toFixed(2)} KB</p>
                  </div>
                </div>
                <button
                  onClick={handleUpload}
                  disabled={isUploading}
                  className="inline-flex min-h-12 items-center justify-center rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isUploading ? 'Analyzing export…' : 'Run analysis'}
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-5 rounded-[22px] border border-rose-500/20 bg-rose-500/8 p-4 text-rose-300">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                <div>
                  <p className="text-sm">{error}</p>
                  <button
                    onClick={handleUpload}
                    className="mt-3 rounded-xl border border-rose-400/20 bg-rose-500/10 px-4 py-2 text-sm text-white transition hover:bg-rose-500/20"
                  >
                    Retry
                  </button>
                </div>
              </div>
            </div>
          )}

          {results && (
            <div className="mt-5 rounded-[22px] border border-emerald-500/20 bg-emerald-500/8 p-5">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-300" />
                <div className="min-w-0 flex-1">
                  <h4 className="text-lg font-semibold text-white">Analysis complete</h4>
                  <p className="mt-2 text-sm text-slate-300">{results.message}</p>
                  <div className="mt-4 rounded-2xl border border-white/8 bg-slate-950/55 p-4 font-mono text-sm text-emerald-300">
                    Chat ID: {results.chat_id}
                  </div>
                  <button
                    onClick={() => navigate(`/results/${results.chat_id}`)}
                    className="mt-4 inline-flex min-h-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04] px-5 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08]"
                  >
                    Open full report
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">WORKFLOW</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">What happens after upload</h2>
          <div className="mt-6 space-y-4">
            {[
              {
                icon: MessageSquareText,
                title: 'Parse the export',
                text: 'The system extracts timestamps, senders, and message content from the chat file.',
              },
              {
                icon: Shield,
                title: 'Score harmful content',
                text: 'Each message is evaluated for unsafe language patterns and aggregated into a report summary.',
              },
              {
                icon: CheckCircle2,
                title: 'Review the result',
                text: 'Open the report page to inspect overall safety ratios, flagged messages, and recent conversation context.',
              },
            ].map(({ icon: Icon, title, text }, index) => (
              <div key={title} className="flex gap-4 rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
                <div className="flex flex-col items-center">
                  <div className="inline-flex rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                    <Icon className="h-5 w-5 text-cyan-300" />
                  </div>
                  {index < 2 && <div className="mt-3 h-full w-px bg-gradient-to-b from-cyan-500/35 to-transparent" />}
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">{title}</h3>
                  <p className="mt-2 text-sm leading-7 text-slate-400">{text}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
