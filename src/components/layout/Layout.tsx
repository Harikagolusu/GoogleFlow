import React from 'react';
import { TopNav } from './TopNav';
import { BottomNav } from './BottomNav';

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="min-h-screen bg-background flex flex-col relative">
      {/* Subtle background gradient */}
      <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-gradient-to-br from-primary/5 to-transparent rounded-full blur-3xl -translate-x-1/3 -translate-y-1/3 pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-gradient-to-tl from-primary/5 to-transparent rounded-full blur-3xl translate-x-1/4 translate-y-1/4 pointer-events-none" />

      <TopNav />
      <main className="flex-1 w-full max-w-6xl mx-auto pb-24 md:pb-20 relative z-10">
        {children}
      </main>
      <BottomNav />
    </div>
  );
};
