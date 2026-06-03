import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Download, FileText, Shield, Upload } from 'lucide-react';
import { apiClient, getStoredSession, storeGuestReport } from '../lib/api';

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
      const hasSession = !!getStoredSession();
      const response = await apiClient.post(hasSession ? '/api/analyze/upload' : '/api/analyze/guest-upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      });
      if (hasSession) {
        setResults(response.data);
      } else {
        storeGuestReport(response.data.report);
        setResults({
          message: response.data.message,
          chat_id: 'guest',
        });
      }
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
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6 sm:py-5 lg:px-8">
      <section className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(135deg,rgba(18,28,58,0.96),rgba(21,15,39,0.94))] p-4 shadow-[0_30px_120px_rgba(59,130,246,0.12)] md:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">ANALYZE CHAT</p>
            <h1 className="text-3xl font-semibold tracking-tight text-white md:text-[2.6rem]">WhatsApp export review</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400 md:text-base">
              Upload a WhatsApp `.txt` export to generate a moderation report.
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-3 lg:w-[19rem]">
            {[
              { label: 'Input', value: '.txt export', icon: Download },
              { label: 'Output', value: 'Risk report', icon: FileText },
              { label: 'Mode', value: 'Offline', icon: Shield },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label} className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-cyan-500/10 p-2 text-cyan-300">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-500">{label}</p>
                    <p className="mt-1 text-sm font-medium text-white">{value}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
          <div
            className="cursor-pointer rounded-[24px] border-2 border-dashed border-blue-500/40 bg-[linear-gradient(180deg,rgba(8,16,35,0.96),rgba(11,18,34,0.88))] p-6 text-center transition hover:border-cyan-500/45 hover:bg-slate-950/70 sm:p-8"
            onClick={() => document.getElementById('file-upload')?.click()}
          >
            <div className="mx-auto inline-flex rounded-[22px] border border-cyan-500/20 bg-cyan-500/10 p-4">
              <Upload className="h-8 w-8 text-cyan-300" />
            </div>
            <h3 className="mt-4 text-xl font-semibold text-white">Drop export or click to upload</h3>
            <p className="mt-2 text-sm text-slate-400">
              Supported format: `.txt`
            </p>
            <input type="file" id="file-upload" className="hidden" accept=".txt" onChange={handleFileChange} />
          </div>

          {file && (
            <div className="mt-4 rounded-[22px] border border-white/8 bg-slate-950/65 p-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
                  className="inline-flex min-h-11 items-center justify-center rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isUploading ? 'Analyzing export...' : 'Run analysis'}
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-[22px] border border-rose-500/20 bg-rose-500/8 p-3 text-rose-300">
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
            <div className="mt-4 rounded-[22px] border border-emerald-500/20 bg-emerald-500/8 p-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-300" />
                <div className="min-w-0 flex-1">
                  <h4 className="text-lg font-semibold text-white">Analysis complete</h4>
                  <p className="mt-2 text-sm text-slate-300">{results.message}</p>
                  <div className="mt-3 rounded-2xl border border-white/8 bg-slate-950/55 p-3 font-mono text-sm text-emerald-300">
                    {results.chat_id === 'guest' ? 'Guest analysis only' : `Chat ID: ${results.chat_id}`}
                  </div>
                  <button
                    onClick={() => navigate(`/results/${results.chat_id}`)}
                    className="mt-3 inline-flex min-h-10 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-white/[0.08]"
                  >
                    Open full report
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-4 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-5">
          <h2 className="text-2xl font-semibold text-white">What happens after upload</h2>
          <div className="mt-4 space-y-3">
            {[
              {
                title: 'Parse export',
                text: 'Extract messages and timestamps.',
              },
              {
                title: 'Score content',
                text: 'Detect risky or harmful language.',
              },
              {
                title: 'View report',
                text: 'Review flagged messages and summary.',
              },
            ].map(({ title, text }, index) => (
              <div key={title} className="flex items-start gap-3 rounded-[20px] border border-white/8 bg-slate-950/55 p-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-cyan-500/25 bg-cyan-500/10 text-sm font-semibold text-cyan-300">
                  {index + 1}
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">{title}</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-400">{text}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
