import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Mail, RefreshCw, Calendar, HardDrive } from 'lucide-react';
import { workflowService } from '../services/workflowService';
import { gmailService, type GmailMessage, type GmailConnectionStatus } from '../services/gmailService';
import { googleService, type CalendarEvent, type DriveFile, type ConnectionStatus } from '../services/googleService';
import { authService } from '../services/authService';
import type { Service } from '../types/service';
import { ServiceLogo } from '../components/ServiceLogo';

export const ServiceDetail: React.FC = () => {
  const { name } = useParams<{ name: string }>();
  const [service, setService] = useState<Service | null>(null);
  const [loading, setLoading] = useState(true);

  const isGmail = name === 'gmail';
  const isCalendar = name === 'calendar' || name === 'google calendar';
  const isDrive = name === 'drive' || name === 'google drive';
  const isMaps = name === 'maps' || name === 'google maps';

  const [gmailStatus, setGmailStatus] = useState<GmailConnectionStatus | null>(null);
  const [gmailMessages, setGmailMessages] = useState<GmailMessage[]>([]);
  const [gmailLoading, setGmailLoading] = useState(false);
  const [gmailError, setGmailError] = useState('');

  const [genericStatus, setGenericStatus] = useState<ConnectionStatus | null>(null);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [genericLoading, setGenericLoading] = useState(false);
  const [genericError, setGenericError] = useState('');
  const [mapsEnabled, setMapsEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    if (name) {
      workflowService.getServiceByName(name).then(data => {
        setService(data || null);
        setLoading(false);
      });
    }
  }, [name]);

  // Gmail fetch (kept separate for backward compat)
  useEffect(() => {
    if (!isGmail || loading) return;
    let cancelled = false;
    gmailService
      .getStatus()
      .then((status) => {
        if (cancelled) return;
        setGmailStatus(status);
        if (status.connected) {
          setGmailLoading(true);
          return gmailService.getRecentMessages(10);
        }
        return null;
      })
      .then((result) => {
        if (cancelled || !result) return;
        setGmailMessages(result.messages);
      })
      .catch(() => {
        if (!cancelled) {
          setGmailStatus({ connected: false, service: 'gmail', scopes: [] });
          setGmailError('Could not load Gmail data.');
        }
      })
      .finally(() => { if (!cancelled) setGmailLoading(false); });
    return () => { cancelled = true; };
  }, [isGmail, loading]);

  // Calendar / Drive fetch
  useEffect(() => {
    if (loading) return;
    if (isCalendar) {
      let cancelled = false;
      googleService.getStatus('calendar').then((s) => {
        if (cancelled) return;
        setGenericStatus(s);
        if (s.connected) {
          setGenericLoading(true);
          return googleService.getCalendarEvents(10);
        }
        return null;
      }).then((r) => { if (!cancelled && r) setCalendarEvents(r.events); })
        .catch(() => { if (!cancelled) setGenericError('Could not load Calendar data.'); })
        .finally(() => { if (!cancelled) setGenericLoading(false); });
      return () => { cancelled = true; };
    }
    if (isDrive) {
      let cancelled = false;
      googleService.getStatus('drive').then((s) => {
        if (cancelled) return;
        setGenericStatus(s);
        if (s.connected) {
          setGenericLoading(true);
          return googleService.getDriveFiles(10);
        }
        return null;
      }).then((r) => { if (!cancelled && r) setDriveFiles(r.files); })
        .catch(() => { if (!cancelled) setGenericError('Could not load Drive data.'); })
        .finally(() => { if (!cancelled) setGenericLoading(false); });
      return () => { cancelled = true; };
    }
    if (isMaps) {
      googleService.getMapsStatus().then((s) => setMapsEnabled(s.configured)).catch(() => setMapsEnabled(false));
    }
  }, [isCalendar, isDrive, isMaps, loading]);

  const handleRefreshMessages = async () => {
    setGmailLoading(true); setGmailError('');
    try { const result = await gmailService.getRecentMessages(10); setGmailMessages(result.messages); } catch (err) { setGmailError(err instanceof Error ? err.message : 'Failed to refresh emails.'); } finally { setGmailLoading(false); }
  };
  const handleRefreshGeneric = async () => {
    setGenericLoading(true); setGenericError('');
    try {
      if (isCalendar) { const r = await googleService.getCalendarEvents(10); setCalendarEvents(r.events); }
      if (isDrive) { const r = await googleService.getDriveFiles(10); setDriveFiles(r.files); }
    } catch (err) { setGenericError(err instanceof Error ? err.message : 'Failed to refresh.'); }
    finally { setGenericLoading(false); }
  };
  const handleConnectGeneric = async (svc: 'gmail'|'calendar'|'drive') => {
    if (!authService.isAvailable() || !authService.getCurrentUser()) {
      if (svc==='gmail') setGmailError('Sign in with Google first to connect.');
      else setGenericError('Sign in with Google first to connect.');
      return;
    }
    try { const result = await googleService.connect(svc); window.location.href = result.authorization_url; } catch (err) { const msg = err instanceof Error ? err.message : 'Failed to start connection.'; if (svc==='gmail') setGmailError(msg); else setGenericError(msg); }
  };
  const handleConnectGmail = () => handleConnectGeneric('gmail');

  if (loading) return <div className="p-8 text-center text-gray-500 mt-20">Loading...</div>;
  if (!service) return <div className="p-8 text-center text-gray-500 mt-20">Service not found.</div>;

  const displayEmails = isGmail && gmailMessages.length > 0
    ? gmailMessages.map((msg) => ({ subject: msg.subject || '(no subject)', from: msg.sender, time: msg.date, snippet: msg.snippet, isReal: true }))
    : (service.relatedEmails || []).map((e) => ({ ...e, isReal: false }));

  const showGmailConnected = isGmail && gmailStatus?.connected;
  const showGmailNotConnected = isGmail && gmailStatus && !gmailStatus.connected;

  return (
    <div className="pt-12 px-6 max-w-3xl mx-auto">
      <Link to="/" className="flex items-center gap-2 text-gray-400 hover:text-gray-900 mb-12 transition-colors font-medium text-sm">
        <ArrowLeft className="w-4 h-4" /><span>Back</span>
      </Link>

      <header className="mb-12">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-14 h-14 rounded-[1.25rem] bg-[#F4F4F5] flex items-center justify-center text-gray-700">
            <ServiceLogo name={service.name} className="w-9 h-9" />
          </div>
          <h1 className="text-4xl md:text-5xl font-serif text-gray-900">{service.name}</h1>
        </div>
        <p className="text-xl text-gray-500">{service.description}</p>
      </header>

      {showGmailNotConnected && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-2xl font-serif text-gray-900 mb-4">Connect your Gmail</h3>
          <p className="text-sm text-gray-500 mb-6">Connect your Gmail account to see recent emails right here. LifeFlow uses read-only access — it can never send or modify your email.</p>
          <button onClick={handleConnectGmail} className="text-sm font-medium text-google-blue hover:underline transition-colors">Connect Gmail</button>
          {gmailError && <p className="mt-3 text-sm text-red-500">{gmailError}</p>}
        </div>
      )}

      {showGmailConnected && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-2xl font-serif text-gray-900">Recent Emails</h3>
            <button onClick={handleRefreshMessages} disabled={gmailLoading} className="flex items-center gap-2 text-sm font-medium text-google-blue hover:underline disabled:opacity-50 transition-colors">
              <RefreshCw className={`w-4 h-4 ${gmailLoading ? 'animate-spin' : ''}`} /> {gmailLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {gmailLoading && gmailMessages.length === 0 ? <p className="text-sm text-gray-500">Loading recent emails…</p> : gmailMessages.length === 0 ? <p className="text-sm text-gray-500">No recent messages found in your inbox.</p> : (
            <div className="space-y-3">
              {gmailMessages.map((msg) => (
                <div key={msg.id} className="flex items-start gap-4 p-4 rounded-2xl bg-[#F8FAFC] border border-gray-100 hover:shadow-sm transition-shadow">
                  <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center text-red-500 flex-shrink-0"><Mail className="w-5 h-5" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 truncate">{msg.subject || '(no subject)'}</p>
                    <p className="text-sm text-gray-500 truncate">{msg.sender} · {msg.date}</p>
                    {msg.snippet && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{msg.snippet}</p>}
                  </div>
                </div>
              ))}
            </div>
          )}
          {gmailError && <p className="mt-3 text-sm text-red-500">{gmailError}</p>}
        </div>
      )}

      {/* Calendar connect / events */}
      {isCalendar && genericStatus && !genericStatus.connected && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-2xl font-serif text-gray-900 mb-4">Connect your Calendar</h3>
          <p className="text-sm text-gray-500 mb-6">Let LifeFlow see your upcoming events to generate timely LifeFlows. Read-only.</p>
          <button onClick={() => handleConnectGeneric('calendar')} className="text-sm font-medium text-google-blue hover:underline transition-colors">Connect Calendar</button>
          {genericError && <p className="mt-3 text-sm text-red-500">{genericError}</p>}
        </div>
      )}
      {isCalendar && genericStatus?.connected && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-2xl font-serif text-gray-900">Upcoming Events</h3>
            <button onClick={handleRefreshGeneric} disabled={genericLoading} className="flex items-center gap-2 text-sm font-medium text-google-blue hover:underline disabled:opacity-50 transition-colors">
              <RefreshCw className={`w-4 h-4 ${genericLoading ? 'animate-spin' : ''}`} /> {genericLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {genericLoading && calendarEvents.length === 0 ? <p className="text-sm text-gray-500">Loading events…</p> : calendarEvents.length === 0 ? <p className="text-sm text-gray-500">No upcoming events in next 14 days.</p> : (
            <div className="space-y-3">
              {calendarEvents.map((ev) => (
                <div key={ev.id} className="flex items-start gap-4 p-4 rounded-2xl bg-[#F8FAFC] border border-gray-100">
                  <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center text-blue-500 flex-shrink-0"><Calendar className="w-5 h-5" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 truncate">{ev.summary}</p>
                    <p className="text-sm text-gray-500 truncate">{ev.displayStart} {ev.location ? `· ${ev.location}` : ''}</p>
                    {ev.description && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{ev.description}</p>}
                  </div>
                </div>
              ))}
            </div>
          )}
          {genericError && <p className="mt-3 text-sm text-red-500">{genericError}</p>}
        </div>
      )}

      {/* Drive connect / files */}
      {isDrive && genericStatus && !genericStatus.connected && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-2xl font-serif text-gray-900 mb-4">Connect your Drive</h3>
          <p className="text-sm text-gray-500 mb-6">Let LifeFlow see recent file metadata to help with document checklists. Metadata only, no file content.</p>
          <button onClick={() => handleConnectGeneric('drive')} className="text-sm font-medium text-google-blue hover:underline transition-colors">Connect Drive</button>
          {genericError && <p className="mt-3 text-sm text-red-500">{genericError}</p>}
        </div>
      )}
      {isDrive && genericStatus?.connected && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-2xl font-serif text-gray-900">Recent Files</h3>
            <button onClick={handleRefreshGeneric} disabled={genericLoading} className="flex items-center gap-2 text-sm font-medium text-google-blue hover:underline disabled:opacity-50 transition-colors">
              <RefreshCw className={`w-4 h-4 ${genericLoading ? 'animate-spin' : ''}`} /> {genericLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {genericLoading && driveFiles.length === 0 ? <p className="text-sm text-gray-500">Loading files…</p> : driveFiles.length === 0 ? <p className="text-sm text-gray-500">No recent files found.</p> : (
            <div className="space-y-3">
              {driveFiles.map((f) => (
                <div key={f.id} className="flex items-start gap-4 p-4 rounded-2xl bg-[#F8FAFC] border border-gray-100">
                  <div className="w-10 h-10 rounded-full bg-yellow-50 flex items-center justify-center text-yellow-600 flex-shrink-0"><HardDrive className="w-5 h-5" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 truncate">{f.name}</p>
                    <p className="text-sm text-gray-500 truncate">{f.mimeType} · {f.modifiedTime}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          {genericError && <p className="mt-3 text-sm text-red-500">{genericError}</p>}
        </div>
      )}

      {/* Maps info */}
      {isMaps && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-2xl font-serif text-gray-900 mb-4">Google Maps</h3>
          <p className="text-sm text-gray-500 mb-4">Maps provides location and travel context for LifeFlows (geocoding, directions). It uses a server API key — no OAuth connect needed.</p>
          <div className="text-sm"><span className="font-medium">Status:</span> <span className={mapsEnabled ? 'text-green-600' : 'text-gray-500'}>{mapsEnabled === null ? 'Checking…' : mapsEnabled ? 'Enabled (GOOGLE_MAPS_API_KEY set)' : 'Not configured'}</span></div>
          <p className="text-xs text-gray-400 mt-3">LifeFlows with a location will show a “View on Maps” link and travel-time hints when Maps is enabled.</p>
        </div>
      )}

      {(!isGmail || !gmailStatus) && !isCalendar && !isDrive && !isMaps && displayEmails.length > 0 && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-2xl font-serif text-gray-900 mb-6">We found related items</h3>
          <div className="space-y-4">
            {displayEmails.map((email, i) => (
              <div key={i} className="flex items-start gap-4 p-4 rounded-2xl bg-[#F8FAFC] border border-gray-100">
                <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center text-red-500 flex-shrink-0"><Mail className="w-5 h-5" /></div>
                <div><p className="font-medium text-gray-900">{email.subject}</p><p className="text-sm text-gray-500">{email.from} · {email.time}</p></div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">Connected to</h3>
        <Link to="/flows" className="mt-4 inline-flex items-center gap-2 text-google-blue font-medium hover:text-blue-700 transition-colors text-sm">View all LifeFlows →</Link>
      </div>
    </div>
  );
};
