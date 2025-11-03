import './globals.css';
import React from 'react';

export const metadata = {
  title: 'Valuation App',
  description: 'EV calculator with gated expected valuation'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-green-700 text-white">
        <div className="container">
          <header className="flex flex-col items-center gap-1 text-center space-y-1 mb-8">
            <h1 className="text-2xl font-bold">Jordon Voytek Capital Partners</h1>
            <h2 className="text-2xl font-semibold">Valuation Engine</h2>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
