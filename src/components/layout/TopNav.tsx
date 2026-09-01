import React from 'react';
import { NavLink } from 'react-router-dom';

export const TopNav: React.FC = () => {
  const navItems = [
    { name: 'Home', path: '/' },
    { name: 'Ask LifeFlow', path: '/ask' },
    { name: 'My LifeFlows', path: '/flows' },
    { name: 'Profile', path: '/profile' },
  ];

  return (
    <header className="w-full max-w-5xl mx-auto px-6 py-6 flex items-center justify-between">
      <NavLink to="/" className="flex items-center gap-3">
        <div className="w-6 h-6 rounded-full bg-google-blue"></div>
        <span className="text-xl font-medium tracking-tight text-gray-900">LifeFlow</span>
      </NavLink>

      <nav className="hidden md:flex items-center gap-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `px-5 py-2.5 rounded-full text-sm font-medium transition-all ${
                isActive
                  ? 'bg-gray-200/60 text-gray-900'
                  : 'text-gray-500 hover:text-gray-900'
              }`
            }
          >
            {item.name}
          </NavLink>
        ))}
      </nav>

      <NavLink to="/profile" className="md:hidden w-9 h-9 rounded-full bg-gray-200 flex items-center justify-center text-sm font-medium text-gray-600">
        H
      </NavLink>
    </header>
  );
};
