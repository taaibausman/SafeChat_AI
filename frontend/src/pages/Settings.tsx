import { useEffect, useState } from 'react';
import {
  CalendarDays,
  ChevronRight,
  KeyRound,
  Lock,
  LogOut,
  Mail,
  RefreshCw,
  Shield,
  ShieldCheck,
  User,
  UserCog,
  Users,
  X,
} from 'lucide-react';
import { apiClient, getStoredSession, storeSession, type AuthSession } from '../lib/api';

type UserRecord = {
  id: number;
  username?: string | null;
  email: string;
  role: string;
  is_active: boolean;
  name?: string | null;
  created_at: string;
};

function formatDateTime(value?: string | null) {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unavailable';
  return parsed.toLocaleString();
}

function SectionCard({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[28px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)] md:p-6">
      <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold text-white">{title}</h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function SettingsInfoRow({
  icon,
  label,
  value,
  onChange,
  readOnly = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs text-slate-400">{label}</span>
      <div className="flex min-h-12 items-center gap-3 rounded-2xl border border-white/8 bg-slate-950/55 px-4 text-sm text-white">
        <span className="text-cyan-300">{icon}</span>
        <input
          value={value}
          readOnly={readOnly}
          onChange={(event) => onChange?.(event.target.value)}
          className="w-full bg-transparent text-sm text-white outline-none"
        />
      </div>
    </label>
  );
}

function PrivacyItem({
  icon,
  title,
  text,
  interactive = false,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
  interactive?: boolean;
}) {
  return (
    <div className="flex items-center gap-4 rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
      <div className="rounded-2xl bg-cyan-500/12 p-3 text-cyan-300">{icon}</div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white">{title}</p>
        <p className="mt-1 text-xs leading-6 text-slate-400">{text}</p>
      </div>
      {interactive ? <ChevronRight className="h-4 w-4 text-slate-500" /> : null}
    </div>
  );
}

export default function SettingsPage() {
  const [session, setSession] = useState<AuthSession | null>(() => getStoredSession());
  const [authMessage, setAuthMessage] = useState('');
  const [profileName, setProfileName] = useState('');
  const [profileUsername, setProfileUsername] = useState('');
  const [profileEmail, setProfileEmail] = useState('');
  const [profileError, setProfileError] = useState('');
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [userError, setUserError] = useState('');
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [lastUserRefresh, setLastUserRefresh] = useState<string | null>(null);

  const isAdmin = session?.user.role === 'admin';

  const syncSession = (next: AuthSession | null) => {
    setSession(next);
    storeSession(next);
  };

  useEffect(() => {
    if (!session) return;
    setProfileName(session.user.name || '');
    setProfileUsername(session.user.username || '');
    setProfileEmail(session.user.email || '');
  }, [session]);

  const loadUsers = async (search = userSearch) => {
    if (!isAdmin) return;
    try {
      setIsLoadingUsers(true);
      setUserError('');
      const response = await apiClient.get('/api/users', {
        params: {
          search: search || undefined,
          limit: 100,
        },
      });
      setUsers(response.data.users ?? []);
      setLastUserRefresh(new Date().toISOString());
    } catch (error: any) {
      setUsers([]);
      setUserError(error?.response?.data?.detail || 'Could not load admin user records.');
    } finally {
      setIsLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      void loadUsers(userSearch);
    } else {
      setUsers([]);
      setUserError('');
      setLastUserRefresh(null);
    }
  }, [isAdmin]);

  const logout = () => {
    syncSession(null);
    setUsers([]);
    setAuthMessage('Signed out.');
  };

  const saveProfile = async () => {
    if (!session) return;
    try {
      setIsSavingProfile(true);
      setProfileError('');
      setAuthMessage('');
      const response = await apiClient.patch('/api/users/me', {
        name: profileName.trim() || null,
        username: profileUsername.trim() || null,
        email: profileEmail.trim(),
      });
      const nextSession: AuthSession = {
        ...session,
        user: {
          ...session.user,
          ...response.data,
        },
      };
      syncSession(nextSession);
      setAuthMessage('Profile updated.');
    } catch (error: any) {
      setProfileError(error?.response?.data?.detail || 'Could not update your profile.');
    } finally {
      setIsSavingProfile(false);
    }
  };

  const closePasswordModal = () => {
    setIsPasswordModalOpen(false);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordError('');
    setPasswordMessage('');
  };

  const updatePassword = async () => {
    if (!session) return;
    if (!currentPassword.trim()) {
      setPasswordError('Enter your current password.');
      return;
    }
    if (newPassword.trim().length < 6) {
      setPasswordError('New password must be at least 6 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('New password and confirmation do not match.');
      return;
    }

    try {
      setIsUpdatingPassword(true);
      setPasswordError('');
      setPasswordMessage('');
      await apiClient.patch('/api/users/me', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordMessage('Password updated.');
      window.setTimeout(() => {
        closePasswordModal();
      }, 900);
    } catch (error: any) {
      setPasswordError(error?.response?.data?.detail || 'Could not update your password.');
    } finally {
      setIsUpdatingPassword(false);
    }
  };

  const renderProfileCard = (label: string) => (
    <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Display Name</p>
          <p className="mt-2 text-base font-medium text-white">{session?.user.name || 'Not set'}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Username</p>
          <p className="mt-2 text-base font-medium text-white">{session?.user.username || 'Not set'}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Email</p>
          <p className="mt-2 text-base font-medium text-white">{session?.user.email}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Created</p>
          <p className="mt-2 text-base font-medium text-white">{formatDateTime(session?.user.created_at)}</p>
        </div>
      </div>
    </div>
  );

  const renderPasswordModal = () => {
    if (!isPasswordModalOpen) return null;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
        <div className="w-full max-w-md rounded-[28px] border border-white/8 bg-slate-900 p-6 shadow-[0_30px_120px_rgba(15,23,42,0.5)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-cyan-400">SECURITY</p>
              <h3 className="mt-2 text-2xl font-semibold text-white">Change password</h3>
            </div>
            <button
              type="button"
              onClick={closePasswordModal}
              className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04] text-slate-300 transition hover:bg-white/[0.08]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-5 grid gap-3">
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              placeholder="Current password"
              className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
            />
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder="New password"
              className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
            />
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Confirm new password"
              className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
            />
          </div>

          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={() => void updatePassword()}
              disabled={isUpdatingPassword}
              className="inline-flex min-h-11 flex-1 items-center justify-center rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-60"
            >
              {isUpdatingPassword ? 'Updating...' : 'Update password'}
            </button>
            <button
              type="button"
              onClick={closePasswordModal}
              className="inline-flex min-h-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04] px-5 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08]"
            >
              Cancel
            </button>
          </div>

          {passwordError && <p className="mt-4 text-sm text-rose-300">{passwordError}</p>}
          {passwordMessage && <p className="mt-4 text-sm text-emerald-300">{passwordMessage}</p>}
        </div>
      </div>
    );
  };

  const updateUser = async (userId: number, payload: Partial<UserRecord>) => {
    try {
      setUserError('');
      const response = await apiClient.patch(`/api/users/${userId}`, payload);
      const updated = response.data as UserRecord;
      setUsers((current) => current.map((user) => (user.id === updated.id ? updated : user)));
      setLastUserRefresh(new Date().toISOString());
    } catch (error: any) {
      setUserError(error?.response?.data?.detail || 'Could not update the selected user.');
    }
  };

  const renderUserSettings = () => (
    <div className="grid gap-6 xl:grid-cols-[0.98fr_1fr]">
      <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)]">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl bg-cyan-500/12 p-3 text-cyan-300">
            <UserCog className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-white">Profile &amp; Account</h2>
          </div>
        </div>

        <div className="mt-5 space-y-4">
          <SettingsInfoRow icon={<User className="h-4 w-4" />} label="Name" value={profileName} onChange={setProfileName} />
          <SettingsInfoRow icon={<User className="h-4 w-4" />} label="Username" value={profileUsername} onChange={setProfileUsername} />
          <SettingsInfoRow icon={<Mail className="h-4 w-4" />} label="Email" value={profileEmail} onChange={setProfileEmail} />

          <div className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
            <div className="flex items-center gap-3 text-cyan-300">
              <CalendarDays className="h-4 w-4" />
              <div>
                <p className="text-xs text-slate-400">Created</p>
                <p className="mt-1 text-sm text-white">{formatDateTime(session?.user.created_at)}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => void saveProfile()}
            disabled={isSavingProfile}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-60"
          >
            {isSavingProfile ? 'Saving...' : 'Save Profile'}
          </button>
          <button
            type="button"
            onClick={() => setIsPasswordModalOpen(true)}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-5 py-3 text-sm font-medium text-cyan-300 transition hover:bg-cyan-500/15"
          >
            <KeyRound className="h-4 w-4" />
            Change Password
          </button>
        </div>

        <button
          type="button"
          onClick={logout}
          className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-5 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08]"
        >
          <LogOut className="h-4 w-4 text-rose-300" />
          Sign Out
        </button>

        {profileError && <p className="mt-4 text-sm text-rose-300">{profileError}</p>}
        {authMessage && <p className="mt-4 text-sm text-emerald-300">{authMessage}</p>}
      </section>

      <section className="rounded-[24px] border border-white/8 bg-slate-900/78 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.35)]">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl bg-cyan-500/12 p-3 text-cyan-300">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <h2 className="text-2xl font-semibold text-white">Privacy</h2>
        </div>

        <div className="mt-5 space-y-4">
          <PrivacyItem
            icon={<Lock className="h-4 w-4" />}
            title="Your information is private."
            text="No admin tools or sensitive access."
          />
          <PrivacyItem
            icon={<Shield className="h-4 w-4" />}
            title="Local processing"
            text="Chat content stays in this project environment."
            interactive
          />
          <PrivacyItem
            icon={<ShieldCheck className="h-4 w-4" />}
            title="Protected routes"
            text="Moderation routes require an authenticated session."
            interactive
          />
        </div>
      </section>
    </div>
  );

  const renderAdminSettings = () => (
    <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      <div className="space-y-6">
        <SectionCard eyebrow="ADMIN SESSION" title="Admin account controls">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <UserCog className="h-5 w-5 text-cyan-300" />
            </div>
            <p className="text-sm leading-7 text-slate-400">
              Admin sessions can review their own account details and access user-management controls on the right.
            </p>
          </div>

          {renderProfileCard('Administrator account')}

          <div className="mt-5 grid gap-3">
            <input value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder="Display name" className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500" />
            <input value={profileUsername} onChange={(event) => setProfileUsername(event.target.value)} placeholder="Username" className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500" />
            <input value={profileEmail} onChange={(event) => setProfileEmail(event.target.value)} placeholder="Email" className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500" />
          </div>

          <div className="mt-5 space-y-4">
            <button
              type="button"
              onClick={() => void saveProfile()}
              disabled={isSavingProfile}
              className="inline-flex min-h-11 items-center justify-center rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-60"
            >
              {isSavingProfile ? 'Saving...' : 'Save profile'}
            </button>
            <button
              type="button"
              onClick={() => setIsPasswordModalOpen(true)}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-5 py-3 text-sm font-medium text-cyan-300 transition hover:bg-cyan-500/15"
            >
              <KeyRound className="h-4 w-4" />
              Change password
            </button>
            <button
              type="button"
              onClick={logout}
              className="inline-flex min-h-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.04] px-5 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08]"
            >
              Sign out
            </button>
          </div>

          {profileError && <p className="mt-4 text-sm text-rose-300">{profileError}</p>}
          {authMessage && <p className="mt-4 text-sm text-emerald-300">{authMessage}</p>}
        </SectionCard>

        <SectionCard eyebrow="ADMIN POLICY" title="Access status">
          <div className="grid gap-4 md:grid-cols-2">
            {[
              ['Role-protected routes', 'User management and moderation overrides are limited to authenticated admin sessions.'],
              ['Admin scope', 'Use this page to manage accounts and review access-sensitive operations.'],
              ['Last sync', lastUserRefresh ? formatDateTime(lastUserRefresh) : 'No user refresh has been run yet.'],
              ['Records loaded', `${users.length} user record(s) currently loaded in this session.`],
            ].map(([title, text]) => (
              <div key={title} className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
                <p className="font-medium text-white">{title}</p>
                <p className="mt-2 text-sm leading-7 text-slate-400">{text}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard eyebrow="ADMIN USERS" title="User management">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
              <Users className="h-5 w-5 text-cyan-300" />
            </div>
            <p className="text-sm leading-7 text-slate-400">
              Search, update roles, and enable or disable accounts from the live user directory.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void loadUsers()}
              disabled={isLoadingUsers}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${isLoadingUsers ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <p className="text-xs text-slate-400">
              {lastUserRefresh ? `Last updated ${formatDateTime(lastUserRefresh)}` : 'Not refreshed yet'}
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input
            value={userSearch}
            onChange={(event) => setUserSearch(event.target.value)}
            placeholder="Search by email, username, or name"
            className="min-h-11 flex-1 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            type="button"
            onClick={() => void loadUsers(userSearch)}
            className="min-h-11 rounded-2xl border border-white/8 bg-slate-950/60 px-4 py-3 text-sm text-slate-300 transition hover:bg-slate-950/80"
          >
            Apply search
          </button>
        </div>

        <div className="mt-5 space-y-3">
          {users.map((user) => (
            <div key={user.id} className="rounded-[22px] border border-white/8 bg-slate-950/55 p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <p className="truncate font-medium text-white">{user.name || user.username || user.email}</p>
                  <p className="mt-1 text-sm text-slate-400">{user.email}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Role: {user.role} | Status: {user.is_active ? 'active' : 'disabled'} | Created: {formatDateTime(user.created_at)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void updateUser(user.id, { role: user.role === 'admin' ? 'user' : 'admin' })}
                    className={`rounded-full border px-3 py-1.5 text-xs ${user.role === 'admin' ? 'border-cyan-500/25 bg-cyan-500/10 text-cyan-300' : 'border-white/8 bg-white/[0.03] text-slate-300'}`}
                  >
                    {user.role === 'admin' ? 'Demote to user' : 'Promote to admin'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void updateUser(user.id, { is_active: !user.is_active })}
                    className={`rounded-full border px-3 py-1.5 text-xs ${user.is_active ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/25 bg-amber-500/10 text-amber-300'}`}
                  >
                    {user.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                </div>
              </div>
            </div>
          ))}
          {!isLoadingUsers && users.length === 0 && (
            <div className="rounded-[22px] border border-dashed border-white/10 bg-slate-950/50 p-5 text-sm text-slate-400">
              No users matched the current admin filter.
            </div>
          )}
        </div>

        {userError && <p className="mt-4 text-sm text-rose-300">{userError}</p>}
      </SectionCard>
    </div>
  );

  if (!session) {
    return null;
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      {renderPasswordModal()}
      <section className="overflow-hidden rounded-[24px] border border-white/8 bg-[linear-gradient(135deg,rgba(10,18,34,0.98),rgba(8,14,26,0.96))] p-5 shadow-[0_30px_120px_rgba(34,211,238,0.08)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-2xl bg-cyan-500/14 p-3 text-cyan-300">
              <UserCog className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-white">
                {isAdmin ? 'Admin Settings' : 'User Settings'}
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                {isAdmin ? 'Manage administrator access and user controls.' : 'Manage your profile and privacy.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600/25 text-sm font-semibold text-cyan-200">
              {(session.user.name || session.user.username || session.user.email).slice(0, 2).toUpperCase()}
            </div>
            <div>
              <p className="text-xs text-slate-400">Signed in as</p>
              <p className="text-sm font-medium text-white">{session.user.email}</p>
            </div>
          </div>
        </div>
      </section>

      {isAdmin ? renderAdminSettings() : renderUserSettings()}
    </div>
  );
}
