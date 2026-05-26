import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, CheckCircle, AlertTriangle } from 'lucide-react';
import axios from 'axios';

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
      const response = await axios.post('http://localhost:8000/api/analyze/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      setResults(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred during analysis.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-3xl font-bold mb-2 text-white">WhatsApp Export Analyzer</h1>
      <p className="text-slate-400 mb-8">Upload your exported WhatsApp chat (.txt) for AI safety analysis.</p>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 mb-8 shadow-xl">
        <div 
          className="border-2 border-dashed border-slate-700 rounded-xl p-12 flex flex-col items-center justify-center text-center hover:border-primary/50 transition-colors cursor-pointer bg-slate-800/50"
          onClick={() => document.getElementById('file-upload')?.click()}
        >
          <Upload className="w-12 h-12 text-slate-400 mb-4" />
          <h3 className="text-xl font-semibold mb-2">Drag & Drop or Click to Upload</h3>
          <p className="text-slate-400 text-sm">Supported formats: .txt</p>
          <input 
            type="file" 
            id="file-upload" 
            className="hidden" 
            accept=".txt" 
            onChange={handleFileChange}
          />
        </div>

        {file && (
          <div className="mt-6 p-4 bg-slate-800 rounded-lg flex items-center justify-between border border-slate-700">
            <div className="flex items-center gap-3">
              <FileText className="text-primary w-6 h-6" />
              <div>
                <p className="font-medium">{file.name}</p>
                <p className="text-xs text-slate-400">{(file.size / 1024).toFixed(2)} KB</p>
              </div>
            </div>
            <button 
              onClick={handleUpload}
              disabled={isUploading}
              className="bg-primary hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {isUploading ? 'Analyzing...' : 'Analyze Chat'}
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 p-4 bg-red-900/20 border border-red-900 rounded-lg flex items-start gap-3 text-red-400">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <p>{error}</p>
          </div>
        )}
      </div>

      {results && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-xl animate-fade-in-up">
          <div className="flex items-center gap-3 mb-6">
            <CheckCircle className="text-green-500 w-8 h-8" />
            <h2 className="text-2xl font-bold">Analysis Complete</h2>
          </div>
          <p className="text-slate-300 mb-4">{results.message}</p>
          <div className="p-4 bg-slate-800 rounded-lg border border-slate-700 font-mono text-sm text-green-400">
            Chat ID generated: {results.chat_id}
          </div>
          <button 
            onClick={() => navigate(`/results/${results.chat_id}`)}
            className="mt-6 bg-slate-800 hover:bg-slate-700 text-white px-6 py-2 rounded-lg font-medium transition-colors border border-slate-700">
            View Full Report
          </button>
        </div>
      )}
    </div>
  );
}
