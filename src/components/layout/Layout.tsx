import React from 'react';
import { TopNav } from './TopNav';
import { BottomNav } from './BottomNav';

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="min-h-screen bg-[#F4F4F5] flex flex-col relative overflow-hidden">
      <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-blue-100 rounded-full blur-[120px] opacity-40 -translate-x-1/2 -translate-y-1/2 pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-red-50 rounded-full blur-[150px] opacity-40 translate-x-1/3 translate-y-1/3 pointer-events-none" />

      <TopNav />
      <main className="flex-1 w-full max-w-5xl mx-auto pb-24 md:pb-20 relative z-10">
        {children}
      </main>
      <BottomNav />
    </div>
  );
};
