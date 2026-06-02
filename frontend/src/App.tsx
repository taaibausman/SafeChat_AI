import { BrowserRouter as Router, Link, Route, Routes, useLocation } from 'react-router-dom';
import { Suspense, lazy, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Building2,
  Eye,
  FileText,
  GraduationCap,
  Lock,
  LogOut,
  Menu,
  MessageSquare,
  Radio,
  Shield,
  Smartphone,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import { AUTH_CHANGED_EVENT, getStoredSession, storeSession, type AuthSession } from './lib/api';

const ExportAnalyzer = lazy(() => import('./pages/ExportAnalyzer'));
const DashboardPage = lazy(() => import('./pages/Dashboard'));
const ReportsPage = lazy(() => import('./pages/Reports'));
const Results = lazy(() => import('./pages/Results'));
const ImageAnalyzer = lazy(() => import('./pages/ImageAnalyzer'));
const RealtimeMonitor = lazy(() => import('./pages/RealtimeMonitor'));
const AdminOperations = lazy(() => import('./pages/AdminOperations'));
const SettingsPage = lazy(() => import('./pages/Settings'));
const LoginPage = lazy(() => import('./pages/Login'));
const RegisterPage = lazy(() => import('./pages/Register'));

const USER_NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: Shield },
  { to: '/analyze', label: 'Analyze Chat', icon: MessageSquare },
  { to: '/image-analyzer', label: 'Analyze Image', icon: Eye },
  { to: '/report', label: 'Report', icon: FileText },
  { to: '/live', label: 'My Live Monitor', icon: Smartphone },
  { to: '/settings', label: 'Settings', icon: Lock },
];

const ADMIN_NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: Shield },
  { to: '/live', label: 'Live Monitoring', icon: Smartphone },
  { to: '/admin-ops', label: 'System Health', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Lock },
];

function getWorkspaceNav(session: AuthSession | null) {
  if ((session?.user.role ?? 'user') === 'admin') {
    return ADMIN_NAV;
  }
  return USER_NAV;
}

function useAuthSessionState() {
  const [session, setSession] = useState<AuthSession | null>(() => getStoredSession());

  useEffect(() => {
    const syncSession = () => {
      setSession(getStoredSession());
    };

    const handleStorage = (event: StorageEvent) => {
      if (!event.key || event.key === 'safechat_auth') {
        syncSession();
      }
    };

    window.addEventListener('storage', handleStorage);
    window.addEventListener(AUTH_CHANGED_EVENT, syncSession as EventListener);
    window.addEventListener('focus', syncSession);

    return () => {
      window.removeEventListener('storage', handleStorage);
      window.removeEventListener(AUTH_CHANGED_EVENT, syncSession as EventListener);
      window.removeEventListener('focus', syncSession);
    };
  }, []);

  return session;
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: 'cyan' | 'rose' | 'emerald' | 'amber';
}) {
  const toneMap = {
    cyan: 'from-cyan-500/15 to-blue-500/10 text-cyan-300 border-cyan-500/20',
    rose: 'from-rose-500/15 to-fuchsia-500/10 text-rose-300 border-rose-500/20',
    emerald: 'from-emerald-500/15 to-teal-500/10 text-emerald-300 border-emerald-500/20',
    amber: 'from-amber-500/15 to-orange-500/10 text-amber-300 border-amber-500/20',
  };

  return (
    <div className={`rounded-[22px] border bg-gradient-to-br p-5 ${toneMap[tone]}`}>
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold md:text-4xl">{value}</p>
    </div>
  );
}

function Sidebar({ onNavigate, session }: { onNavigate?: () => void; session: AuthSession | null }) {
  const location = useLocation();
  const navItems = getWorkspaceNav(session);

  return (
    <div className="flex h-full w-full flex-col border-r border-white/8 bg-slate-950/85 backdrop-blur">
      <div className="flex items-center gap-3 border-b border-white/6 px-5 py-5">
        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-2.5">
          <Shield className="h-5 w-5 text-cyan-300" />
        </div>
        <div>
          <p className="text-lg font-semibold text-white">SafeChat AI</p>
          <p className="text-xs text-slate-500">Moderation workspace</p>
        </div>
      </div>

      <nav className="flex-1 space-y-2 px-4 py-5">
        {navItems.map(({ to, label, icon: Icon }) => {
          const active = location.pathname === to;
          return (
            <Link
              key={to}
              to={to}
              onClick={onNavigate}
              className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition ${
                active
                  ? 'border border-cyan-500/25 bg-cyan-500/10 text-white shadow-[0_0_30px_rgba(56,189,248,0.12)]'
                  : 'border border-transparent text-slate-400 hover:border-white/6 hover:bg-white/[0.03] hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-white/6 p-4">
        <Link
          to="/"
          onClick={onNavigate}
          className="mb-2 flex items-center gap-3 rounded-2xl px-4 py-3 text-sm text-slate-400 transition hover:bg-white/[0.03] hover:text-white"
        >
          <ArrowUpRight className="h-4 w-4" />
          Landing Page
        </Link>
        <button
          type="button"
          onClick={() => {
            storeSession(null);
            window.location.assign('/settings');
          }}
          className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-sm text-slate-500 transition hover:bg-rose-500/10 hover:text-rose-300"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </div>
  );
}

function AppTopBar({ onMenu, session }: { onMenu: () => void; session: AuthSession | null }) {
  const location = useLocation();
  const current = getWorkspaceNav(session).find((item) => item.to === location.pathname);

  return (
    <div className="sticky top-0 z-30 border-b border-white/6 bg-slate-950/75 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onMenu}
            className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-slate-200 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-400">Workspace</p>
            <h1 className="text-lg font-semibold text-white">{current?.label ?? 'SafeChat AI'}</h1>
          </div>
        </div>

        <div className="hidden items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300 sm:flex">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          AI engine online
        </div>
      </div>
    </div>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const session = useAuthSessionState();

  return (
    <div className="min-h-screen bg-[#060915] text-slate-100">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(76,29,149,0.28),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(8,145,178,0.16),transparent_22%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:36px_36px] opacity-[0.05]" />

      <div className="relative flex min-h-screen">
        <aside className="hidden w-72 shrink-0 lg:block">
          <div className="sticky top-0 h-screen p-4">
            <Sidebar session={session} />
          </div>
        </aside>

        {mobileMenuOpen && (
          <div className="fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm lg:hidden" onClick={() => setMobileMenuOpen(false)}>
            <div className="h-full w-[86vw] max-w-sm p-4" onClick={(event) => event.stopPropagation()}>
              <div className="mb-3 flex justify-end">
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-slate-200"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="h-[calc(100%-56px)]">
                <Sidebar session={session} onNavigate={() => setMobileMenuOpen(false)} />
              </div>
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <AppTopBar session={session} onMenu={() => setMobileMenuOpen(true)} />
          <main className="flex-1 pb-24 lg:pb-8">{children}</main>
        </div>
      </div>
    </div>
  );
}

function LandingPage() {
  const features = [
    {
      icon: Shield,
      title: 'Threat detection',
      text: 'Flag toxic, coercive and abusive messages from exports or live streams before they escalate.',
      accent: 'from-cyan-500/18 to-blue-500/10',
      bullets: ['Threat language', 'Harassment patterns', 'Escalation cues'],
    },
    {
      icon: Eye,
      title: 'Actionable review',
      text: 'Give analysts and educators a clear moderation surface for scanning, triage and follow-up.',
      accent: 'from-violet-500/18 to-fuchsia-500/10',
      bullets: ['Fast triage', 'Context-aware review', 'Linked reports'],
    },
    {
      icon: Smartphone,
      title: 'Realtime monitoring',
      text: 'Connect the WhatsApp bridge and watch new messages flow into the moderation feed as they arrive.',
      accent: 'from-emerald-500/18 to-cyan-500/10',
      bullets: ['Live stream', 'Instant labels', 'Session status'],
    },
  ];

  const workflow = [
    {
      step: '01',
      title: 'Bring in the conversation',
      text: 'Upload exported chats or connect the live bridge to start a moderation session with minimal setup.',
    },
    {
      step: '02',
      title: 'Classify risk fast',
      text: 'Each message is scored for unsafe language patterns so high-risk content surfaces quickly.',
    },
    {
      step: '03',
      title: 'Review and respond',
      text: 'Move from summary cards into reports and live feeds to investigate senders, context and severity.',
    },
  ];

  const audiences = [
    {
      icon: GraduationCap,
      title: 'For educators',
      text: 'Monitor class and student spaces with an interface built for fast scanning, incident review and escalation awareness.',
      stat: 'Classroom-safe review',
    },
    {
      icon: Shield,
      title: 'For parents',
      text: 'Get earlier visibility into harmful conversations without wading through raw logs or noisy dashboards.',
      stat: 'Earlier risk visibility',
    },
    {
      icon: Building2,
      title: 'For teams',
      text: 'Use structured summaries and live monitoring to support trust, safety and internal moderation workflows.',
      stat: 'Operational moderation',
    },
  ];

  return (
    <div className="min-h-screen bg-[#060915] text-slate-100">
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(91,33,182,0.34),transparent_36%),radial-gradient(circle_at_bottom_right,rgba(34,211,238,0.14),transparent_28%)]" />
        <div className="absolute left-1/2 top-16 h-[34rem] w-[34rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.32),rgba(76,29,149,0.08)_48%,transparent_72%)] blur-3xl md:h-[44rem] md:w-[44rem]" />

        <div className="relative mx-auto max-w-7xl px-4 pb-16 pt-5 sm:px-6 lg:px-8">
          <header className="flex items-center justify-between gap-4 rounded-full border border-white/8 bg-slate-950/45 px-4 py-3 backdrop-blur sm:px-6">
            <Link to="/" className="flex items-center gap-3">
              <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-2.5">
                <Shield className="h-5 w-5 text-cyan-300" />
              </div>
              <span className="text-lg font-semibold tracking-tight text-white sm:text-[1.35rem]">
                SafeChat <span className="text-indigo-400">AI</span>
              </span>
            </Link>

            <nav className="hidden items-center gap-8 text-sm text-slate-400 lg:flex">
              <a href="#features" className="transition hover:text-white">Features</a>
              <a href="#how-it-works" className="transition hover:text-white">How it works</a>
              <a href="#for-you" className="transition hover:text-white">For you</a>
            </nav>

            <div className="flex items-center gap-2">
              <Link
                to="/login"
                className="rounded-full border border-white/10 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-white/20 hover:bg-white/[0.04] sm:px-5"
              >
                Login
              </Link>
              <Link
                to="/register"
                className="rounded-full border border-cyan-500/35 px-4 py-2.5 text-sm font-medium text-white transition hover:border-cyan-400 hover:bg-cyan-500/10 sm:px-5"
              >
                Register
              </Link>
            </div>
          </header>

          <main className="mx-auto max-w-6xl pt-16 text-center sm:pt-20 lg:pt-24">
            <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-violet-500/20 bg-violet-950/40 px-4 py-2 text-sm text-slate-300 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
              <Sparkles className="h-3.5 w-3.5 text-violet-400" />
              Powered by Hugging Face toxicity models
            </div>

            <h1 className="mx-auto mt-8 max-w-5xl text-4xl font-semibold leading-[0.95] tracking-tight text-white sm:text-6xl lg:text-[5.4rem]">
              Keeping digital
              <br />
              conversations <span className="bg-gradient-to-r from-cyan-300 via-blue-300 to-indigo-400 bg-clip-text text-transparent">safe.</span>
            </h1>

            <p className="mx-auto mt-6 max-w-3xl text-base leading-8 text-slate-400 sm:text-lg md:text-xl">
              SafeChat AI scans chats for toxicity, threats and harmful content in real time so parents, educators and teams can spot risk before it spreads.
            </p>

            <div className="mt-9 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
              <Link
                to="/analyze"
                className="inline-flex min-h-14 items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-6 py-4 text-base font-medium text-slate-950 shadow-[0_18px_60px_rgba(56,189,248,0.25)] transition hover:brightness-110"
              >
                <Upload className="h-4 w-4" />
                Analyze chat
              </Link>
              <Link
                to="/live"
                className="inline-flex min-h-14 items-center justify-center gap-3 rounded-2xl border border-violet-500/30 bg-slate-950/70 px-6 py-4 text-base font-medium text-slate-200 transition hover:border-violet-400 hover:bg-violet-500/10"
              >
                <Radio className="h-4 w-4" />
                Start live monitoring
              </Link>
            </div>

            <section className="mx-auto mt-14 max-w-5xl rounded-[30px] border border-violet-500/18 bg-slate-900/72 p-4 text-left shadow-[0_30px_120px_rgba(59,130,246,0.15)] backdrop-blur sm:p-6 md:mt-20 md:p-8">
              <div className="flex items-center justify-between text-sm text-slate-400">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  Live analysis
                </div>
                <span>Risk score</span>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-3">
                <StatCard label="Safe" value="1,284" tone="emerald" />
                <StatCard label="Unsafe" value="92" tone="rose" />
                <StatCard label="Risk level" value="Moderate" tone="amber" />
              </div>

              <div className="mt-5 space-y-3">
                {[
                  { initial: 'A', sender: 'Alex', text: 'Hey, all good for the meeting?', label: 'Safe', tone: 'emerald' },
                  { initial: 'U', sender: 'Unknown', text: "You're going to regret this...", label: 'Threat', tone: 'rose' },
                  { initial: 'P', sender: 'Priya', text: 'Thanks for the help yesterday!', label: 'Safe', tone: 'emerald' },
                ].map((item) => (
                  <div key={`${item.sender}-${item.text}`} className="flex items-center gap-4 rounded-2xl border border-white/6 bg-[#131933]/86 px-4 py-4">
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${item.tone === 'rose' ? 'bg-fuchsia-500 text-white' : 'bg-violet-500 text-white'}`}>
                      {item.initial}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-slate-400">{item.sender}</p>
                      <p className="truncate text-base text-slate-100 sm:text-lg">{item.text}</p>
                    </div>
                    <span className={`rounded-full px-3 py-1.5 text-xs sm:px-4 sm:text-sm ${item.tone === 'rose' ? 'border border-rose-500/30 bg-rose-500/10 text-rose-400' : 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-400'}`}>
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </main>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
        <section id="features" className="border-t border-white/5 py-16 md:py-20">
          <div className="mb-8 flex flex-col gap-4 md:mb-10 md:flex-row md:items-end md:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">Features</p>
              <h2 className="mt-3 text-3xl font-semibold text-white md:text-4xl">A moderation interface that stays readable under pressure.</h2>
            </div>
            <p className="max-w-xl text-sm leading-7 text-slate-400 md:text-base">
              Each surface is tuned for signal density, rapid scanning and direct movement into the next action.
            </p>
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr_0.85fr]">
            {features.map(({ icon: Icon, title, text, accent, bullets }, index) => (
              <div
                key={title}
                className={`group relative overflow-hidden rounded-[28px] border border-white/8 bg-slate-900/70 p-6 transition duration-300 hover:-translate-y-1 hover:border-cyan-500/20 hover:bg-slate-900/85 ${index === 0 ? 'xl:min-h-[22rem]' : ''}`}
              >
                <div className={`absolute inset-0 bg-gradient-to-br ${accent} opacity-80`} />
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.08),transparent_28%)]" />
                <div className="relative flex h-full flex-col">
                  <div className="inline-flex w-fit rounded-2xl border border-white/10 bg-slate-950/40 p-3 shadow-[0_12px_30px_rgba(15,23,42,0.2)]">
                    <Icon className="h-5 w-5 text-white" />
                  </div>
                  <h3 className="mt-10 text-2xl font-semibold text-white">{title}</h3>
                  <p className="mt-3 text-sm leading-7 text-slate-200/88 md:text-base">{text}</p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {bullets.map((item) => (
                      <span key={item} className="rounded-full border border-white/10 bg-slate-950/35 px-3 py-1.5 text-xs text-slate-200">
                        {item}
                      </span>
                    ))}
                  </div>
                  <div className="mt-auto pt-8 text-sm text-white/90">
                    <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/35 px-3 py-2 transition group-hover:border-white/20">
                      Explore capability
                      <ArrowRight className="h-4 w-4" />
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="py-10 md:py-14">
          <div className="overflow-hidden rounded-[30px] border border-white/8 bg-[linear-gradient(180deg,rgba(15,23,42,0.78),rgba(10,15,30,0.92))]">
            <div className="grid gap-0 lg:grid-cols-[0.95fr_1.05fr]">
              <div className="border-b border-white/6 p-6 md:p-8 lg:border-b-0 lg:border-r">
                <p className="text-xs uppercase tracking-[0.22em] text-violet-400">How it works</p>
                <h2 className="mt-4 text-3xl font-semibold text-white md:text-4xl">From incoming chat to review-ready signal.</h2>
                <p className="mt-4 max-w-xl text-sm leading-7 text-slate-400 md:text-base">
                  The flow stays simple on purpose: ingest, score, then review. That keeps the interface fast for repeated operational use.
                </p>

                <div className="mt-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                  {[
                    ['Realtime', 'Live bridge support'],
                    ['Scored', 'Risk-based labels'],
                    ['Traceable', 'Report-linked output'],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
                      <p className="mt-2 text-sm font-medium text-white">{value}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-px bg-white/6 md:grid-cols-3 lg:grid-cols-1">
                {workflow.map(({ step, title, text }) => (
                  <div key={step} className="bg-slate-950/45 p-6 transition hover:bg-slate-950/60 md:p-7">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-violet-400">{step}</span>
                      <div className="ml-4 h-px flex-1 bg-gradient-to-r from-violet-500/30 to-transparent" />
                    </div>
                    <h3 className="mt-5 text-xl font-semibold text-white">{title}</h3>
                    <p className="mt-3 text-sm leading-7 text-slate-400">{text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="for-you" className="py-10 md:py-14">
          <div className="mb-8 max-w-2xl">
            <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">For you</p>
            <h2 className="mt-3 text-3xl font-semibold text-white md:text-4xl">Different users, one disciplined workflow.</h2>
            <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">
              The UI stays compact and purposeful whether the operator is a parent, an educator or a trust-and-safety team.
            </p>
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            {audiences.map(({ icon: Icon, title, text, stat }) => (
              <div key={title} className="group rounded-[28px] border border-white/8 bg-slate-900/72 p-6 transition duration-300 hover:-translate-y-1 hover:border-cyan-500/20">
                <div className="flex items-start justify-between gap-4">
                  <div className="inline-flex rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                    <Icon className="h-5 w-5 text-cyan-300" />
                  </div>
                  <span className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">
                    {stat}
                  </span>
                </div>
                <h3 className="mt-8 text-2xl font-semibold text-white">{title}</h3>
                <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">{text}</p>
                <div className="mt-8 rounded-2xl border border-white/8 bg-slate-950/55 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Best fit</p>
                  <p className="mt-2 text-sm text-white">
                    {title === 'For educators' && 'Student safety review, class-group moderation, escalation awareness.'}
                    {title === 'For parents' && 'Household oversight, earlier warning signs, simpler review without raw exports.'}
                    {title === 'For teams' && 'Trust-and-safety operations, flagged queues, live message monitoring.'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function RouteFallback() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="rounded-[28px] border border-white/8 bg-slate-900/70 p-8 text-center shadow-[0_24px_80px_rgba(15,23,42,0.35)]">
        <p className="text-sm text-slate-400">Loading workspace...</p>
      </div>
    </div>
  );
}

function AppShell({ children }: { children: React.ReactNode }) {
  return <Layout>{children}</Layout>;
}

function AccessGate({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-10rem)] max-w-3xl items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
      <section className="w-full max-w-xl rounded-[28px] border border-white/8 bg-slate-900/85 p-6 text-center shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-8">
        <div className="mx-auto inline-flex rounded-3xl border border-cyan-500/20 bg-cyan-500/10 p-4">
          <AlertTriangle className="h-8 w-8 text-cyan-300" />
        </div>
        <p className="mt-5 text-xs uppercase tracking-[0.22em] text-cyan-400">PROTECTED PAGE</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">{title}</h2>
        <p className="mt-4 text-sm leading-7 text-slate-400 md:text-base">{message}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            to="/login"
            className="inline-flex min-h-11 items-center justify-center rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="inline-flex min-h-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04] px-5 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08]"
          >
            Register
          </Link>
        </div>
      </section>
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const session = getStoredSession();

  if (!session) {
    return (
      <AccessGate
        title="Login required"
        message="To use this feature or access this page, login first or register first."
      />
    );
  }

  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const session = getStoredSession();

  if (!session) {
    return (
      <AccessGate
        title="Login required"
        message="To use this feature or access this page, login first or register first."
      />
    );
  }

  if (session.user.role !== 'admin') {
    return (
      <AccessGate
        title="Admin access required"
        message="This page is available only for administrator accounts."
      />
    );
  }

  return <>{children}</>;
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<AppShell><RequireAuth><Suspense fallback={<RouteFallback />}><DashboardPage /></Suspense></RequireAuth></AppShell>} />
        <Route path="/analyze" element={<AppShell><Suspense fallback={<RouteFallback />}><ExportAnalyzer /></Suspense></AppShell>} />
        <Route path="/report" element={<AppShell><RequireAuth><Suspense fallback={<RouteFallback />}><ReportsPage /></Suspense></RequireAuth></AppShell>} />
        <Route path="/live/*" element={<AppShell><RequireAuth><Suspense fallback={<RouteFallback />}><RealtimeMonitor /></Suspense></RequireAuth></AppShell>} />
        <Route path="/admin-ops" element={<AppShell><RequireAdmin><Suspense fallback={<RouteFallback />}><AdminOperations /></Suspense></RequireAdmin></AppShell>} />
        <Route path="/settings" element={<AppShell><RequireAuth><Suspense fallback={<RouteFallback />}><SettingsPage /></Suspense></RequireAuth></AppShell>} />
        <Route path="/login" element={<Suspense fallback={<RouteFallback />}><LoginPage /></Suspense>} />
        <Route path="/register" element={<Suspense fallback={<RouteFallback />}><RegisterPage /></Suspense>} />
        <Route path="/export-analyzer" element={<AppShell><Suspense fallback={<RouteFallback />}><ExportAnalyzer /></Suspense></AppShell>} />
        <Route path="/results/:id" element={<AppShell><Suspense fallback={<RouteFallback />}><Results /></Suspense></AppShell>} />
        <Route path="/image-analyzer" element={<AppShell><RequireAuth><Suspense fallback={<RouteFallback />}><ImageAnalyzer /></Suspense></RequireAuth></AppShell>} />
        <Route path="/realtime-monitor/*" element={<AppShell><RequireAuth><Suspense fallback={<RouteFallback />}><RealtimeMonitor /></Suspense></RequireAuth></AppShell>} />
      </Routes>
    </Router>
  );
}

export default App;
