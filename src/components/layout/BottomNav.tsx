import React from 'react';
import { NavLink } from 'react-router-dom';
import { Home, Sparkles, List, User } from 'lucide-react';

export const BottomNav: React.FC = () => {
  const navItems = [
    { name: 'Home', path: '/', icon: Home },
    { name: 'Ask', path: '/ask', icon: Sparkles },
    { name: 'Flows', path: '/flows', icon: List },
    { name: 'Profile', path: '/profile', icon: User },
  ];

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-surface border-t border-border px-2 py-2 z-50 safe-area-inset">
      <div className="flex items-center justify-around">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => {
                const active = isActive;
                return `flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition-colors min-w-[4rem] ${
                  active
                    ? 'text-primary'
                    : 'text-text-tertiary hover:text-text-secondary'
                }`;
              }}
            >
              {({ isActive }) => (
                <>
                  <Icon className="w-5 h-5" strokeWidth={isActive ? 2.5 : 2} />
                  <span className="text-[10px] font-medium">{item.name}</span>
                </>
              )}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
};
