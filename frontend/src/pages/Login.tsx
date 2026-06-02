import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Eye, EyeOff, Lock, Mail, Shield } from 'lucide-react';
import { apiClient, getStoredSession, storeSession } from '../lib/api';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [emailOrUsername, setEmailOrUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const nextPath = new URLSearchParams(location.search).get('next') || '/settings';

  useEffect(() => {
    if (getStoredSession()) {
      navigate(nextPath, { replace: true });
    }
  }, [navigate, nextPath]);

  const submitLogin = async () => {
    try {
      setIsSubmitting(true);
      setError('');
      const response = await apiClient.post('/api/auth/login', {
        email_or_username: emailOrUsername.trim(),
        password,
      });
      storeSession(response.data);
      navigate(nextPath, { replace: true });
    } catch (requestError: any) {
      setError(requestError?.response?.data?.detail || 'Login failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_top,rgba(44,76,192,0.22),transparent_38%),linear-gradient(180deg,#050917_0%,#081223_100%)] px-4 py-12 sm:px-6">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.08),transparent_42%)]" aria-hidden="true" />

      <section className="relative w-full max-w-[32rem] rounded-[28px] border border-cyan-400/20 bg-[linear-gradient(180deg,rgba(18,26,48,0.96),rgba(11,18,34,0.96))] px-7 py-8 shadow-[0_24px_90px_rgba(4,10,24,0.75)] backdrop-blur md:px-10 md:py-10">
        <div className="flex items-center justify-center gap-3 text-white">
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/8 p-2.5">
            <Shield className="h-5 w-5 text-cyan-300" />
          </div>
          <span className="text-2xl font-semibold tracking-tight">SafeChat AI</span>
        </div>

        <div className="mt-7 text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-white md:text-[2.2rem]">Sign in to SafeChat AI</h1>
          <p className="mt-2 text-sm text-slate-400">Welcome back</p>
        </div>

        <div className="mt-8 space-y-4">
          <label className="flex min-h-14 items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.04] px-4 transition focus-within:border-cyan-300/50 focus-within:bg-white/[0.06]">
            <Mail className="h-4 w-4 text-slate-500" />
            <input
              value={emailOrUsername}
              onChange={(event) => setEmailOrUsername(event.target.value)}
              placeholder="Email or username"
              className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
            />
          </label>

          <label className="flex min-h-14 items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.04] px-4 transition focus-within:border-cyan-300/50 focus-within:bg-white/[0.06]">
            <Lock className="h-4 w-4 text-slate-500" />
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              className="text-slate-500 transition hover:text-cyan-300"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </label>
        </div>

        <button
          type="button"
          onClick={() => void submitLogin()}
          disabled={isSubmitting}
          className="mt-6 inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-base font-medium text-white transition hover:brightness-110 disabled:opacity-60"
        >
          {isSubmitting ? 'Signing in...' : 'Sign In'}
          <ArrowRight className="h-4 w-4" />
        </button>

        {error && <p className="mt-4 text-center text-sm text-rose-300">{error}</p>}

        <p className="mt-6 text-center text-sm text-slate-400">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="font-medium text-cyan-300 transition hover:text-cyan-200">
            Create account
          </Link>
        </p>
      </section>
    </div>
  );
}
