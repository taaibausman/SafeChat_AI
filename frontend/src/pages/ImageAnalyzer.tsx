import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, Image as ImageIcon, AlertTriangle, ScanLine } from 'lucide-react';
import axios from 'axios';

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
        setError('Please upload a valid image file (JPG, PNG).');
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
      const response = await axios.post('http://localhost:8000/api/image/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      // Navigate straight to the results dashboard
      navigate(`/results/${response.data.chat_id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred during OCR analysis.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto animate-fade-in-up">
      <h1 className="text-3xl font-bold mb-2 text-white">Image OCR Analyzer</h1>
      <p className="text-slate-400 mb-8">Upload a screenshot of a chat to extract and analyze the text for safety.</p>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 mb-8 shadow-xl">
        <div 
          className="border-2 border-dashed border-slate-700 rounded-xl p-12 flex flex-col items-center justify-center text-center hover:border-primary/50 transition-colors cursor-pointer bg-slate-800/50"
          onClick={() => document.getElementById('image-upload')?.click()}
        >
          <ScanLine className="w-12 h-12 text-slate-400 mb-4" />
          <h3 className="text-xl font-semibold mb-2">Drag & Drop or Click to Upload Image</h3>
          <p className="text-slate-400 text-sm">Supported formats: JPG, PNG, WEBP</p>
          <input 
            type="file" 
            id="image-upload" 
            className="hidden" 
            accept="image/*" 
            onChange={handleFileChange}
          />
        </div>

        {previewUrl && (
          <div className="mt-8 flex flex-col items-center">
            <h4 className="text-slate-300 mb-4 font-medium self-start">Image Preview:</h4>
            <div className="relative rounded-lg overflow-hidden border border-slate-700 max-w-md w-full mb-6">
              <img src={previewUrl} alt="Preview" className="w-full h-auto object-cover" />
            </div>
            
            <button 
              onClick={handleUpload}
              disabled={isUploading}
              className="bg-primary hover:bg-blue-600 text-white px-8 py-3 rounded-lg font-bold transition-colors disabled:opacity-50 flex items-center gap-3 w-full justify-center text-lg"
            >
              {isUploading ? (
                <>Scanning & Analyzing...</>
              ) : (
                <><ImageIcon className="w-5 h-5" /> Run AI Analysis</>
              )}
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
    </div>
  );
}
