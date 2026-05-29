import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Image as ImageIcon, ScanLine, Shield, View } from 'lucide-react';
import { apiClient } from '../lib/api';

export default function ImageAnalyzer() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (!selectedFile.type.startsWith('image/')) {
        setError('Please upload a valid image file (JPG, PNG, WEBP).');
        return;
      }
      setFile(selectedFile);
      setPreviewUrl(URL.createObjectURL(selectedFile));
      setError('');
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await apiClient.post(`/api/image/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 60000,
      });
      navigate(`/results/${response.data.chat_id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred during OCR analysis.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <section className="overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(135deg,rgba(18,28,58,0.96),rgba(21,15,39,0.94))] p-6 shadow-[0_30px_120px_rgba(59,130,246,0.15)] md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs uppercase tracking-[0.22em] text-cyan-400">IMAGE ANALYZER</p>
            <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">Screenshot OCR review</h1>
            <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">
              Upload a chat screenshot and extract the text for the same moderation pipeline used by export analysis.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:w-[30rem]">
            {[
              ['Input', 'Chat image'],
              ['Output', 'OCR + report'],
              ['Formats', 'JPG, PNG, WEBP'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-white/8 bg-white/[0.04] p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
                <p className="mt-2 text-sm font-medium text-white">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <div
            className="cursor-pointer rounded-[24px] border-2 border-dashed border-white/10 bg-slate-950/55 p-8 text-center transition hover:border-cyan-500/35 hover:bg-slate-950/70 sm:p-12"
            onClick={() => document.getElementById('image-upload')?.click()}
          >
            <div className="mx-auto inline-flex rounded-3xl border border-cyan-500/20 bg-cyan-500/10 p-4">
              <ScanLine className="h-10 w-10 text-cyan-300" />
            </div>
            <h3 className="mt-6 text-2xl font-semibold text-white">Drop screenshot or click to upload</h3>
            <p className="mt-3 text-sm leading-7 text-slate-400">
              Use this when you only have a screenshot. The OCR extractor will pull text first, then forward it to the moderation engine.
            </p>
            <div className="mt-5 inline-flex rounded-full border border-white/8 bg-white/[0.03] px-4 py-2 text-xs text-slate-300">
              Best for screenshots and shared chat images
            </div>
            <input type="file" id="image-upload" className="hidden" accept="image/*" onChange={handleFileChange} />
          </div>

          {previewUrl && (
            <div className="mt-5 rounded-[22px] border border-white/8 bg-slate-950/65 p-4">
              <div className="mb-4 flex items-center gap-3">
                <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                  <View className="h-5 w-5 text-cyan-300" />
                </div>
                <div>
                  <p className="font-medium text-white">Preview ready</p>
                  <p className="text-xs text-slate-400">{file?.name}</p>
                </div>
              </div>

              <div className="overflow-hidden rounded-[20px] border border-white/8 bg-slate-950">
                <img src={previewUrl} alt="Preview" className="aspect-[4/5] w-full object-cover md:aspect-[16/10]" />
              </div>

              <button
                onClick={handleUpload}
                disabled={isUploading}
                className="mt-4 inline-flex min-h-12 w-full items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ImageIcon className="h-5 w-5" />
                {isUploading ? 'Running OCR and analysis...' : 'Run OCR analysis'}
              </button>
            </div>
          )}

          {error && (
            <div className="mt-5 rounded-[22px] border border-rose-500/20 bg-rose-500/8 p-4 text-rose-300">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                <p className="text-sm">{error}</p>
              </div>
            </div>
          )}
        </section>

        <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">PIPELINE</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">How screenshot analysis works</h2>

          <div className="mt-6 space-y-4">
            {[
              {
                icon: ScanLine,
                title: 'Extract visible text',
                text: 'OCR reads the screenshot and reconstructs the chat content before moderation begins.',
              },
              {
                icon: Shield,
                title: 'Run the same safety checks',
                text: 'Extracted text is scored using the same moderation workflow as uploaded exports.',
              },
              {
                icon: ImageIcon,
                title: 'Open a full report',
                text: 'The result is routed into the report view so you can inspect flagged lines and review context.',
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
