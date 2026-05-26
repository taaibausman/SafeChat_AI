import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { ShieldAlert, ShieldCheck, ArrowLeft, AlertTriangle } from 'lucide-react';

export default function Results() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await axios.get(`http://localhost:8000/api/analyze/report/${id}`);
        setData(response.data);
      } catch (err: any) {
        setError('Failed to load analysis report.');
      } finally {
        setLoading(false);
      }
    };
    fetchReport();
  }, [id]);

  if (loading) {
    return <div className="p-8 text-center text-slate-400">Loading analysis results...</div>;
  }

  if (error || !data) {
    return <div className="p-8 text-center text-red-500">{error}</div>;
  }

  const analysis = data.analysis_results;
  
  const pieData = [
    { name: 'Safe', value: analysis?.safe_percentage || 0, color: '#10b981' },
    { name: 'Unsafe', value: analysis?.unsafe_percentage || 0, color: '#ef4444' }
  ];

  return (
    <div className="p-8 max-w-6xl mx-auto animate-fade-in-up">
      <Link to="/export-analyzer" className="flex items-center gap-2 text-slate-400 hover:text-white mb-6 transition-colors w-max">
        <ArrowLeft className="w-4 h-4" /> Back to Analyzer
      </Link>

      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Analysis Report</h1>
          <p className="text-slate-400">Chat Name: {data.chat_name}</p>
        </div>
        <div className={`px-6 py-3 rounded-full flex items-center gap-3 font-bold text-lg ${analysis?.unsafe_percentage > 20 ? 'bg-red-900/40 text-red-400 border border-red-800' : 'bg-green-900/40 text-green-400 border border-green-800'}`}>
          {analysis?.unsafe_percentage > 20 ? <ShieldAlert className="w-6 h-6" /> : <ShieldCheck className="w-6 h-6" />}
          {analysis?.unsafe_percentage > 20 ? 'High Risk Detected' : 'Generally Safe'}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
          <h3 className="text-lg font-medium text-slate-300 mb-4">Overall Safety Ratio</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#fff' }}
                  itemStyle={{ color: '#fff' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-6 mt-2">
            <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-green-500"></div><span className="text-sm">Safe ({analysis?.safe_percentage?.toFixed(1)}%)</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-red-500"></div><span className="text-sm">Unsafe ({analysis?.unsafe_percentage?.toFixed(1)}%)</span></div>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg md:col-span-2">
          <h3 className="text-lg font-medium text-slate-300 mb-4">Summary</h3>
          <p className="text-xl text-white mb-6 leading-relaxed">{analysis?.summary}</p>
          
          <h4 className="font-medium text-slate-400 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" /> Dangerous Messages Detected
          </h4>
          <div className="space-y-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
            {data.messages.filter((m: any) => m.risk_score > 50).slice(0, 50).map((msg: any, i: number) => (
              <div key={i} className="bg-slate-800 p-3 rounded-lg border border-red-900/30 border-l-4 border-l-red-500">
                <div className="flex justify-between mb-1">
                  <span className="font-bold text-slate-300 text-sm">{msg.sender}</span>
                  <span className="text-xs text-red-400 font-medium">Risk Score: {msg.risk_score.toFixed(1)}</span>
                </div>
                <p className="text-sm text-slate-100">{msg.message}</p>
                {msg.label && (
                  <span className="inline-block mt-2 px-2 py-0.5 rounded text-xs font-medium bg-red-900/50 text-red-300">
                    {msg.label}
                  </span>
                )}
              </div>
            ))}
            {data.messages.filter((m: any) => m.risk_score > 50).length === 0 && (
              <p className="text-slate-500 italic">No dangerous messages detected.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
