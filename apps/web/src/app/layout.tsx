import type { Metadata } from "next";
import Link from "next/link";

import SiteNav from "@/components/site-nav";

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
          <Link className="brand" href="/assistant">
            Facilities AI Assistant
          </Link>
          <SiteNav />
        </header>
        <main>{children}</main>
        <footer>Bounded multi-agent capstone harness</footer>
      </body>
    </html>
  );
}
