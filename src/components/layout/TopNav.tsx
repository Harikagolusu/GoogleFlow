import React from 'react';
import { NavLink } from 'react-router-dom';
import { Sparkles } from 'lucide-react';

export const TopNav: React.FC = () => {
  const navItems = [
    { name: 'Dashboard', path: '/' },
    { name: 'Ask', path: '/ask' },
    { name: 'LifeFlows', path: '/flows' },
    { name: 'Profile', path: '/profile' },
  ];

  return (
    <header className="w-full max-w-6xl mx-auto px-4 md:px-6 py-4 md:py-6 flex items-center justify-between">
      <NavLink to="/" className="flex items-center gap-2.5 group">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center shadow-sm group-hover:shadow transition-shadow">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
        <span className="text-lg font-semibold tracking-tight text-text-primary">LifeFlow</span>
      </NavLink>

      <nav className="hidden md:flex items-center gap-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-surface text-text-primary shadow-sm'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface/50'
              }`
            }
          >
            {item.name}
          </NavLink>
        ))}
      </nav>

      <NavLink
        to="/profile"
        className="md:hidden w-9 h-9 rounded-full bg-surface border border-border flex items-center justify-center text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      </NavLink>
    </header>
  );
};
