import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'Aviation Ops Copilot',
  description:
    'A tool-using LLM agent for aviation operations questions — flight history, ' +
    'live weather, NOTAMs, and FAA procedures, with an inspectable tool trace.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">{children}</body>
    </html>
  );
}
