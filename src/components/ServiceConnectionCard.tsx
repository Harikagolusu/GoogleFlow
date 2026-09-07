import React, { useState } from 'react';
import { Loader2, CheckCircle2, XCircle, ExternalLink } from 'lucide-react';
import { googleService, type OAuthService, type ConnectionStatus } from '../services/googleService';
import { Button } from './ui/Button';
import { Badge } from './ui/Badge';

interface Props {
  service: OAuthService;
  displayName: string;
  description: string;
  icon: string;
  status: ConnectionStatus | null;
  signedIn: boolean;
  onStatusChange: (status: ConnectionStatus | null) => void;
  compact?: boolean;
}

export const ServiceConnectionCard: React.FC<Props> = ({
  service,
  displayName,
  description,
  icon,
  status,
  signedIn,
  onStatusChange,
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const connected = !!status?.connected;

  const handleConnect = async () => {
    if (!googleService.isUserAuthenticated()) {
      setError('Sign in with Google first to connect.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await googleService.connect(service);
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start connection.');
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    setBusy(true);
    setError('');
    try {
      await googleService.disconnect(service);
      onStatusChange({ connected: false, service, scopes: [] });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center justify-between p-4 rounded-xl border border-border-light bg-surface">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-background flex items-center justify-center text-lg">
          {icon}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-text-primary">{displayName}</p>
            {connected && (
              <Badge variant="success" size="sm">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                Connected
              </Badge>
            )}
          </div>
          <p className="text-xs text-text-secondary">
            {connected ? 'Read-only access granted' : signedIn ? description : 'Sign in first to connect'}
          </p>
          {error && (
            <p className="text-xs text-error mt-1 flex items-center gap-1">
              <XCircle className="w-3 h-3" />
              {error}
            </p>
          )}
        </div>
      </div>
      {connected ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleDisconnect}
          disabled={busy}
          className="text-error hover:bg-error-light"
        >
          {busy ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Disconnecting...
            </>
          ) : (
            'Disconnect'
          )}
        </Button>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleConnect}
          disabled={!signedIn || busy}
          className="text-primary hover:bg-primary-light"
        >
          {busy ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Connecting...
            </>
          ) : (
            <>
              Connect
              <ExternalLink className="w-3 h-3" />
            </>
          )}
        </Button>
      )}
    </div>
  );
};
