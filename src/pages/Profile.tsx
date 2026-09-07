import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  LogOut,
  RefreshCw,
  Mail,
  Calendar,
  FolderOpen,
  MapPinned,
  ExternalLink,
  Shield,
} from 'lucide-react';
import { workflowService } from '../services/workflowService';
import { authService } from '../services/authService';
import { useAuthUser } from '../hooks/useAuthUser';
import {
  googleService,
  type ConnectionStatus,
  type GmailMessage,
  type CalendarEvent,
  type DriveFile,
} from '../services/googleService';
import { gmailService } from '../services/gmailService';
import type { Service } from '../types/service';
import { ServiceLogo } from '../components/ServiceLogo';
import { ServiceConnectionCard } from '../components/ServiceConnectionCard';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';

export const Profile: React.FC = () => {
  const { user, signedIn, isAuthEnabled, loading: authLoading } = useAuthUser();
  const [services, setServices] = useState<Service[]>([]);
  const [workflows, setWorkflows] = useState<{ id: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [signingOut, setSigningOut] = useState(false);
  const [gmail, setGmail] = useState<ConnectionStatus | null>(null);
  const [calendar, setCalendar] = useState<ConnectionStatus | null>(null);
  const [drive, setDrive] = useState<ConnectionStatus | null>(null);
  const [mapsStatus, setMapsStatus] = useState<{ enabled: boolean; configured: boolean } | null>(null);
  const [gmailMessages, setGmailMessages] = useState<GmailMessage[]>([]);
  const [gmailMessagesLoading, setGmailMessagesLoading] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [driveLoading, setDriveLoading] = useState(false);
  const [callbackError, setCallbackError] = useState('');

  useEffect(() => {
    if (authLoading) return;
    Promise.all([workflowService.getServices(), workflowService.getWorkflows()]).then(([s, w]) => {
      setServices(s);
      setWorkflows(w);
      setLoading(false);
    });
  }, [authLoading]);

  useEffect(() => {
    if (authLoading || loading) return;
    if (!signedIn) {
      setGmail(null);
      setCalendar(null);
      setDrive(null);
      setMapsStatus(null);
      return;
    }
    let cancelled = false;
    googleService.getStatus('gmail').then((s) => { if (!cancelled) setGmail(s); }).catch(() => { if (!cancelled) setGmail({ connected: false, service: 'gmail', scopes: [] }); });
    googleService.getStatus('calendar').then((s) => { if (!cancelled) setCalendar(s); }).catch(() => { if (!cancelled) setCalendar({ connected: false, service: 'calendar', scopes: [] }); });
    googleService.getStatus('drive').then((s) => { if (!cancelled) setDrive(s); }).catch(() => { if (!cancelled) setDrive({ connected: false, service: 'drive', scopes: [] }); });
    googleService.getMapsStatus().then((s) => { if (!cancelled) setMapsStatus(s); }).catch(() => { if (!cancelled) setMapsStatus({ enabled: false, configured: false }); });
    return () => { cancelled = true; };
  }, [signedIn, loading]);

  useEffect(() => {
    if (!gmail?.connected) { setGmailMessages([]); return; }
    let cancelled = false;
    setGmailMessagesLoading(true);
    gmailService
      .getRecentMessages(10)
      .then((result) => { if (!cancelled) setGmailMessages(result.messages as unknown as GmailMessage[]); })
      .catch(() => { if (!cancelled) setGmailMessages([]); })
      .finally(() => { if (!cancelled) setGmailMessagesLoading(false); });
    return () => { cancelled = true; };
  }, [gmail?.connected]);

  useEffect(() => {
    if (!calendar?.connected) { setCalendarEvents([]); return; }
    let cancelled = false;
    setCalendarLoading(true);
    googleService.getCalendarEvents(10).then((r) => { if (!cancelled) setCalendarEvents(r.events); }).catch(() => { if (!cancelled) setCalendarEvents([]); }).finally(() => { if (!cancelled) setCalendarLoading(false); });
    return () => { cancelled = true; };
  }, [calendar?.connected]);

  useEffect(() => {
    if (!drive?.connected) { setDriveFiles([]); return; }
    let cancelled = false;
    setDriveLoading(true);
    googleService.getDriveFiles(10).then((r) => { if (!cancelled) setDriveFiles(r.files); }).catch(() => { if (!cancelled) setDriveFiles([]); }).finally(() => { if (!cancelled) setDriveLoading(false); });
    return () => { cancelled = true; };
  }, [drive?.connected]);

  const handleRefreshGmailMessages = async () => {
    setGmailMessagesLoading(true);
    try {
      const result = await gmailService.getRecentMessages(10);
      setGmailMessages(result.messages as unknown as GmailMessage[]);
    } catch {
    } finally {
      setGmailMessagesLoading(false);
    }
  };
  const handleRefreshCalendar = async () => {
    setCalendarLoading(true);
    try {
      const r = await googleService.getCalendarEvents(10);
      setCalendarEvents(r.events);
    } catch {}
    finally { setCalendarLoading(false); }
  };
  const handleRefreshDrive = async () => {
    setDriveLoading(true);
    try {
      const r = await googleService.getDriveFiles(10);
      setDriveFiles(r.files);
    } catch {}
    finally { setDriveLoading(false); }
  };

  const callbackHandledRef = useRef(false);
  useEffect(() => {
    if (callbackHandledRef.current) return;
    const params = new URLSearchParams(window.location.search);
    const services = ['gmail', 'calendar', 'drive'];
    let matched: string | null = null;
    let status: string | null = null;
    for (const svc of services) {
      const v = params.get(svc);
      if (v) { matched = svc; status = v; break; }
    }
    if (!status) return;
    callbackHandledRef.current = true;
    if (status === 'connected') {
      if (matched === 'gmail') googleService.getStatus('gmail').then(setGmail).catch(()=>{});
      if (matched === 'calendar') googleService.getStatus('calendar').then(setCalendar).catch(()=>{});
      if (matched === 'drive') googleService.getStatus('drive').then(setDrive).catch(()=>{});
      setTimeout(() => {
        googleService.getStatus('gmail').then(setGmail).catch(()=>{});
        googleService.getStatus('calendar').then(setCalendar).catch(()=>{});
        googleService.getStatus('drive').then(setDrive).catch(()=>{});
      }, 500);
    } else if (status === 'denied') {
      setCallbackError(`${matched} connection was cancelled.`);
    } else if (status === 'failed' || status === 'invalid') {
      setCallbackError(`${matched} connection failed. Please try again.`);
    }
    for (const svc of services) params.delete(svc);
    const search = params.toString();
    const url = window.location.pathname + (search ? `?${search}` : '');
    window.history.replaceState({}, '', url);
  }, []);

  if (loading) {
    return (
      <div className="pt-12 px-4 md:px-6 max-w-4xl mx-auto">
        <div className="flex flex-col items-center mb-12">
          <Skeleton width="5rem" height="5rem" className="rounded-full mb-4" />
          <Skeleton width="12rem" height="2rem" className="mb-2" />
          <Skeleton width="16rem" height="1rem" />
        </div>
      </div>
    );
  }

  const handleSignIn = async () => {
    try { await authService.signInWithGoogle(); } catch {}
  };
  const handleSignOut = async () => {
    setSigningOut(true);
    try { await authService.signOut(); } finally { setSigningOut(false); }
  };

  const displayName = signedIn && user?.displayName ? user.displayName : 'Guest';
  const displayEmail = signedIn && user?.email ? user.email : isAuthEnabled ? 'Sign in to sync your LifeFlows' : 'Demo mode — sign in to save your LifeFlows';
  const initial = displayName.trim().charAt(0).toUpperCase();

  const connectedCount = [gmail, calendar, drive].filter(s => s?.connected).length;
  const isAuthenticated = isAuthEnabled && signedIn;

  return (
    <div className="pt-12 px-4 md:px-6 pb-24 md:pb-20 max-w-4xl mx-auto">
      {/* Header */}
      <header className="text-center mb-10">
        {signedIn && user?.photoURL ? (
          <img
            src={user.photoURL}
            alt={displayName}
            referrerPolicy="no-referrer"
            className="w-20 h-20 rounded-full object-cover border-2 border-border shadow-sm mx-auto mb-4"
          />
        ) : (
          <div className="w-20 h-20 rounded-full bg-background flex items-center justify-center text-3xl font-medium text-text-secondary mx-auto mb-4">
            {initial}
          </div>
        )}
        <h1 className="text-3xl md:text-4xl font-serif text-text-primary mb-1">{displayName}</h1>
        <p className="text-text-secondary">{displayEmail}</p>

        <div className="flex items-center justify-center gap-4 mt-6">
          {isAuthEnabled && !signedIn && (
            <Button variant="primary" onClick={handleSignIn}>
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Continue with Google
            </Button>
          )}
          {signedIn && isAuthEnabled && (
            <Button variant="secondary" onClick={handleSignOut} loading={signingOut} icon={<LogOut className="w-4 h-4" />}>
              Sign out
            </Button>
          )}
        </div>
      </header>

      {/* Stats */}
      {isAuthenticated && workflows.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
          <Card padding="md" className="text-center">
            <p className="text-2xl font-semibold text-text-primary">{workflows.length}</p>
            <p className="text-xs text-text-secondary mt-1">LifeFlows</p>
          </Card>
          <Card padding="md" className="text-center">
            <p className="text-2xl font-semibold text-text-primary">{connectedCount}</p>
            <p className="text-xs text-text-secondary mt-1">Connected</p>
          </Card>
          <Card padding="md" className="text-center">
            <p className="text-2xl font-semibold text-text-primary">{services.length}</p>
            <p className="text-xs text-text-secondary mt-1">Available</p>
          </Card>
          <Card padding="md" className="text-center">
            <p className="text-2xl font-semibold text-success">{connectedCount}/{services.length}</p>
            <p className="text-xs text-text-secondary mt-1">Integration</p>
          </Card>
        </div>
      )}

      {/* Connected Services */}
      <section className="mb-10">
        <h2 className="text-xl font-serif text-text-primary mb-4">Connect Google Apps</h2>
        <p className="text-sm text-text-secondary mb-4">
          Connect your Google apps to let LifeFlow detect important events from your accounts.
        </p>

        <div className="space-y-3">
          <ServiceConnectionCard
            service="gmail"
            displayName="Gmail"
            description="Read-only access to detect events from your inbox"
            icon="✉️"
            status={gmail}
            signedIn={!!signedIn}
            onStatusChange={setGmail}
          />
          <ServiceConnectionCard
            service="calendar"
            displayName="Google Calendar"
            description="Read-only access to upcoming events"
            icon="📅"
            status={calendar}
            signedIn={!!signedIn}
            onStatusChange={setCalendar}
          />
          <ServiceConnectionCard
            service="drive"
            displayName="Google Drive"
            description="Read-only access to recent files (metadata only)"
            icon="📁"
            status={drive}
            signedIn={!!signedIn}
            onStatusChange={setDrive}
          />

          {/* Maps Status */}
          <Card padding="md">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-background flex items-center justify-center">
                  <MapPinned className="w-5 h-5 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">Google Maps</p>
                  <p className="text-xs text-text-secondary">
                    {mapsStatus?.configured
                      ? 'Enabled — location context for LifeFlows'
                      : 'Not configured — set GOOGLE_MAPS_API_KEY'}
                  </p>
                </div>
              </div>
              <Badge variant={mapsStatus?.configured ? 'success' : 'default'}>
                {mapsStatus?.configured ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
          </Card>
        </div>

        {callbackError && (
          <div className="mt-4 p-3 rounded-lg bg-error-light text-error text-sm">
            {callbackError}
          </div>
        )}

        <div className="flex items-start gap-2 mt-4 text-xs text-text-tertiary">
          <Shield className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p>
            LifeFlow uses read-only access where applicable. It can never send, modify, or delete your email, calendar events, or Drive files.
          </p>
        </div>
      </section>

      {/* Recent Activity */}
      {gmail?.connected && (
        <section className="mb-8">
          <Card padding="md">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-text-tertiary" />
                <h3 className="text-base font-medium text-text-primary">Recent Gmail</h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefreshGmailMessages}
                loading={gmailMessagesLoading}
                icon={<RefreshCw className="w-3 h-3" />}
              >
                Refresh
              </Button>
            </div>
            {gmailMessagesLoading && gmailMessages.length === 0 ? (
              <div className="space-y-2">
                {[1, 2, 3].map(i => <Skeleton key={i} height="3rem" className="rounded-lg" />)}
              </div>
            ) : gmailMessages.length === 0 ? (
              <p className="text-sm text-text-secondary text-center py-4">No recent messages found.</p>
            ) : (
              <div className="space-y-2">
                {gmailMessages.slice(0, 5).map((msg) => (
                  <div key={msg.id} className="p-3 rounded-lg border border-border-light hover:bg-background transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-text-primary line-clamp-1">
                          {msg.subject || '(no subject)'}
                        </p>
                        <p className="text-xs text-text-secondary">{msg.sender}</p>
                      </div>
                      <span className="text-xs text-text-tertiary whitespace-nowrap">{msg.date}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </section>
      )}

      {calendar?.connected && (
        <section className="mb-8">
          <Card padding="md">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-text-tertiary" />
                <h3 className="text-base font-medium text-text-primary">Upcoming Events</h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefreshCalendar}
                loading={calendarLoading}
                icon={<RefreshCw className="w-3 h-3" />}
              >
                Refresh
              </Button>
            </div>
            {calendarLoading && calendarEvents.length === 0 ? (
              <div className="space-y-2">
                {[1, 2, 3].map(i => <Skeleton key={i} height="3rem" className="rounded-lg" />)}
              </div>
            ) : calendarEvents.length === 0 ? (
              <p className="text-sm text-text-secondary text-center py-4">No upcoming events in next 14 days.</p>
            ) : (
              <div className="space-y-2">
                {calendarEvents.slice(0, 5).map((ev) => (
                  <div key={ev.id} className="p-3 rounded-lg border border-border-light">
                    <p className="text-sm font-medium text-text-primary">{ev.summary}</p>
                    <p className="text-xs text-text-secondary mt-0.5">
                      {ev.displayStart}
                      {ev.location && ` · ${ev.location}`}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </section>
      )}

      {drive?.connected && (
        <section className="mb-8">
          <Card padding="md">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-4 h-4 text-text-tertiary" />
                <h3 className="text-base font-medium text-text-primary">Recent Drive Files</h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefreshDrive}
                loading={driveLoading}
                icon={<RefreshCw className="w-3 h-3" />}
              >
                Refresh
              </Button>
            </div>
            {driveLoading && driveFiles.length === 0 ? (
              <div className="space-y-2">
                {[1, 2, 3].map(i => <Skeleton key={i} height="3rem" className="rounded-lg" />)}
              </div>
            ) : driveFiles.length === 0 ? (
              <p className="text-sm text-text-secondary text-center py-4">No recent files found.</p>
            ) : (
              <div className="space-y-2">
                {driveFiles.slice(0, 5).map((f) => (
                  <div key={f.id} className="flex items-center gap-3 p-3 rounded-lg border border-border-light">
                    <div className="w-8 h-8 rounded bg-background flex items-center justify-center text-xs">
                      <FolderOpen className="w-4 h-4 text-text-tertiary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary line-clamp-1">{f.name}</p>
                      <p className="text-xs text-text-secondary">
                        {f.mimeType} · {f.modifiedTime}
                      </p>
                    </div>
                    {f.webViewLink && (
                      <a
                        href={f.webViewLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 rounded-lg text-text-tertiary hover:text-text-secondary hover:bg-background transition-colors"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </section>
      )}

      {/* Services Grid */}
      <section className="mb-8">
        <h2 className="text-xl font-serif text-text-primary mb-4">Available Services</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {services.map(service => (
            <Link
              key={service.id}
              to={`/service/${service.name.toLowerCase()}`}
              className="flex items-center gap-3 p-4 rounded-xl border border-border-light bg-surface hover:border-border hover:shadow-sm transition-all"
            >
              <div className="w-10 h-10 rounded-lg bg-background flex items-center justify-center">
                <ServiceLogo name={service.name} className="w-5 h-5" />
              </div>
              <span className="text-sm font-medium text-text-primary">{service.name}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* Sign Out (Mobile) */}
      {signedIn && (
        <Card padding="md" className="md:hidden">
          <Button
            variant="secondary"
            onClick={handleSignOut}
            loading={signingOut}
            icon={<LogOut className="w-4 h-4" />}
            className="w-full text-error"
          >
            Sign out
          </Button>
        </Card>
      )}
    </div>
  );
};

export default Profile;
