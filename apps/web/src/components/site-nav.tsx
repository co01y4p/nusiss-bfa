"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/assistant", label: "Assistant" },
  { href: "/knowledge", label: "Knowledge (RAG)" },
  { href: "/track", label: "Track" },
  { href: "/prompts", label: "Prompts" },
  { href: "/manager", label: "Manager" },
];

export default function SiteNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary navigation">
      {LINKS.map((link) => {
        const active =
          pathname === link.href || pathname?.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={active ? "active" : undefined}
            aria-current={active ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
