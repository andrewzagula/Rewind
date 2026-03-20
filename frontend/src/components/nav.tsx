"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/strategies", label: "Strategies" },
  { href: "/runs", label: "Runs" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="border-b border-zinc-800 bg-zinc-900">
      <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight text-zinc-100">
          Rewind
        </Link>
        <div className="flex gap-6">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm transition-colors ${
                pathname.startsWith(link.href)
                  ? "text-white font-medium"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
