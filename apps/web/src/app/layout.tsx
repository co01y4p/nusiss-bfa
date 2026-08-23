import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Facilities AI Assistant",
  description: "Report, track, and triage facility incidents",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link className="brand" href="/report">
            Facilities AI Assistant
          </Link>
          <nav aria-label="Primary navigation">
            <Link href="/report">Report</Link>
            <Link href="/assistant">Assistant</Link>
            <Link href="/knowledge">Knowledge (RAG)</Link>
            <Link href="/track">Track</Link>
            <Link href="/manager">Manager</Link>
          </nav>
        </header>
        <main>{children}</main>
        <footer>Bounded multi-agent capstone harness</footer>
      </body>
    </html>
  );
}
