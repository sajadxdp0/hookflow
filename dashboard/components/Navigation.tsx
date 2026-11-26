"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/", label: "Overview" },
  { href: "/endpoints", label: "Endpoints" },
  { href: "/deliveries", label: "Deliveries" },
  { href: "/dlq", label: "Dead letters" },
  { href: "/keys", label: "API keys" },
  { href: "/metrics", label: "Metrics" },
];

export function Navigation({ environment }: { environment: string }) {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-white/8 bg-[#080b12]/90 backdrop-blur-xl">
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between gap-4">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-3 rounded-lg"
            aria-label="HookFlow overview"
          >
            <Image src="/logo.svg" alt="" width={36} height={36} priority />
            <span className="text-base font-semibold tracking-tight text-white">
              HookFlow
            </span>
            <span className="hidden rounded-md border border-white/10 bg-white/4 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 md:inline">
              Console
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 text-xs text-slate-500 sm:flex">
              <span className="size-1.5 rounded-full bg-teal-400" aria-hidden="true" />
              Tenant operations
            </span>
            <span className="rounded-md border border-white/10 bg-white/4 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-400">
              {environment}
            </span>
          </div>
        </div>
        <nav
          aria-label="Primary navigation"
          className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
        >
          {nav.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-teal-400/10 text-teal-200"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
