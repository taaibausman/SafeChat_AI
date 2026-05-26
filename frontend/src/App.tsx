import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { Shield, MessageSquare, Image, Smartphone, LogOut } from 'lucide-react';
import ExportAnalyzer from './pages/ExportAnalyzer';
import Results from './pages/Results';
import ImageAnalyzer from './pages/ImageAnalyzer';

function Dashboard() {
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6 text-white">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg glow">
          <h2 className="text-xl font-semibold mb-2">Total Chats Analyzed</h2>
          <p className="text-4xl font-bold text-primary">124</p>
        </div>
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg glow">
          <h2 className="text-xl font-semibold mb-2 text-red-400">Threats Detected</h2>
          <p className="text-4xl font-bold text-red-500">12</p>
        </div>
        <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg glow">
          <h2 className="text-xl font-semibold mb-2 text-green-400">Safe Ratio</h2>
          <p className="text-4xl font-bold text-green-500">90%</p>
        </div>
      </div>
    </div>
  );
}

function Sidebar() {
  return (
    <div className="w-64 bg-slate-900 border-r border-slate-800 h-screen flex flex-col">
      <div className="p-6 flex items-center gap-3 border-b border-slate-800">
        <Shield className="w-8 h-8 text-primary" />
        <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-primary">SafeChat AI</span>
      </div>
      
      <nav className="flex-1 p-4 space-y-2">
        <Link to="/" className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-all">
          <Shield className="w-5 h-5" /> Dashboard
        </Link>
        <Link to="/export-analyzer" className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-all">
          <MessageSquare className="w-5 h-5" /> Chat Exports
        </Link>
        <Link to="/image-analyzer" className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-all">
          <Image className="w-5 h-5" /> Image OCR
        </Link>
        <Link to="/realtime-monitor" className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-all">
          <Smartphone className="w-5 h-5" /> Real-time Monitor
        </Link>
      </nav>
      
      <div className="p-4 border-t border-slate-800">
        <button className="flex items-center gap-3 p-3 w-full rounded-lg hover:bg-red-900/30 text-slate-400 hover:text-red-400 transition-all">
          <LogOut className="w-5 h-5" /> Logout
        </button>
      </div>
    </div>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-slate-950 overflow-hidden text-slate-100">
      <Sidebar />
      <div className="flex-1 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/export-analyzer" element={<ExportAnalyzer />} />
          <Route path="/results/:id" element={<Results />} />
          <Route path="/image-analyzer" element={<ImageAnalyzer />} />
          <Route path="/realtime-monitor" element={<div className="p-8">Real-time Monitor (Phase 3)</div>} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
