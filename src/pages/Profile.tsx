import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Lock, Palette, LogOut } from 'lucide-react';
import { workflowService } from '../services/workflowService';
import { authService } from '../services/authService';
import { useAuthUser } from '../hooks/useAuthUser';
import type { Service } from '../types/service';
import { ServiceLogo, GoogleGMark } from '../components/ServiceLogo';

export const Profile: React.FC = () => {
  const { user, signedIn, isAuthEnabled } = useAuthUser();
  const [services, setServices] = useState<Service[]>([]);
  const [workflows, setWorkflows] = useState<{ id: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    Promise.all([workflowService.getServices(), workflowService.getWorkflows()]).then(([s, w]) => {
      setServices(s);
      setWorkflows(w);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="p-8 text-center text-gray-500 mt-20">Loading...</div>;
  }

  const handleSignIn = async () => {
    try {
      await authService.signInWithGoogle();
    } catch {
      // Popup closed by the user — nothing to do.
    }
  };

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await authService.signOut();
    } finally {
      setSigningOut(false);
    }
  };

  const displayName =
    signedIn && user?.displayName ? user.displayName : 'Harika';
  const displayEmail =
    signedIn && user?.email
      ? user.email
      : isAuthEnabled
        ? 'Sign in with Google to sync your LifeFlows'
        : 'harika@gmail.com';
  const initial = displayName.trim().charAt(0).toUpperCase();

  return (
    <div className="pt-12 px-6 max-w-3xl mx-auto">
      <header className="mb-12 text-center">
        {signedIn && user?.photoURL ? (
          <img
            src={user.photoURL}
            alt={displayName}
            referrerPolicy="no-referrer"
            className="w-20 h-20 rounded-full object-cover border border-gray-200 shadow-sm mx-auto mb-4"
          />
        ) : (
          <div className="w-20 h-20 rounded-full bg-gray-200 flex items-center justify-center text-3xl text-gray-500 font-medium mx-auto mb-4">
            {initial}
          </div>
        )}
        <h1 className="text-4xl md:text-5xl font-serif text-gray-900 mb-2">{displayName}</h1>
        <p className="text-lg text-gray-500">{displayEmail}</p>
        {isAuthEnabled && !signedIn && (
          <button
            onClick={handleSignIn}
            className="mt-6 inline-flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 rounded-full px-6 py-3 text-sm font-medium text-gray-700 shadow-sm transition-colors"
          >
            <GoogleGMark className="w-5 h-5" />
            Continue with Google
          </button>
        )}
      </header>

      <div className="flex justify-center gap-8 mb-12">
        <div className="text-center">
          <div className="text-3xl font-serif text-gray-900">{workflows.length}</div>
          <div className="text-sm text-gray-500">Active LifeFlows</div>
        </div>
        <div className="text-center">
          <div className="text-3xl font-serif text-gray-900">{services.length}</div>
          <div className="text-sm text-gray-500">Connected services</div>
        </div>
      </div>

      <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
        <h3 className="text-2xl font-serif text-gray-900 mb-6">Connected services</h3>
        <div className="grid grid-cols-3 gap-4">
          {services.map(service => (
            <Link
              key={service.id}
              to={`/service/${service.name.toLowerCase()}`}
              className="flex flex-col items-center gap-2 p-4 rounded-2xl hover:bg-[#F8FAFC] transition-colors"
            >
              <div className="w-12 h-12 rounded-2xl bg-[#F4F4F5] flex items-center justify-center text-gray-600">
                <ServiceLogo name={service.name} className="w-6 h-6" />
              </div>
              <span className="text-sm font-medium text-gray-700">{service.name}</span>
            </Link>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <h3 className="text-2xl font-serif text-gray-900 mb-6">Preferences</h3>
        <div className="space-y-1">
          <button className="w-full flex items-center justify-between py-3 text-gray-700 hover:text-gray-900 transition-colors">
            <span className="flex items-center gap-3">
              <Bell className="w-5 h-5 text-gray-400" />
              Notifications
            </span>
          </button>
          <button className="w-full flex items-center justify-between py-3 text-gray-700 hover:text-gray-900 transition-colors">
            <span className="flex items-center gap-3">
              <Lock className="w-5 h-5 text-gray-400" />
              Privacy & data
            </span>
          </button>
          <button className="w-full flex items-center justify-between py-3 text-gray-700 hover:text-gray-900 transition-colors">
            <span className="flex items-center gap-3">
              <Palette className="w-5 h-5 text-gray-400" />
              Appearance
            </span>
          </button>
          {isAuthEnabled && !signedIn ? (
            <button
              onClick={handleSignIn}
              className="w-full flex items-center justify-between py-3 text-gray-700 hover:text-gray-900 transition-colors"
            >
              <span className="flex items-center gap-3">
                <GoogleGMark className="w-5 h-5" />
                Sign in with Google
              </span>
            </button>
          ) : (
            <button
              onClick={handleSignOut}
              disabled={signingOut}
              className="w-full flex items-center justify-between py-3 text-red-500 hover:text-red-600 transition-colors disabled:opacity-60"
            >
              <span className="flex items-center gap-3">
                <LogOut className="w-5 h-5" />
                {signingOut ? 'Signing out…' : 'Sign out'}
              </span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
