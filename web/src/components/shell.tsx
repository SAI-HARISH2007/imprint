"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Config } from "@/lib/api";
import { short } from "@/lib/format";

const NAV = [
  { href: "/register", label: "Register" },
  { href: "/verify", label: "Check" },
  { href: "/receipt", label: "Receipts" },
  { href: "/me", label: "My work" },
  { href: "/stress", label: "Stress test" },
  { href: "/evidence", label: "Evidence" },
];

export function Header() {
  const path = usePathname();
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <Link href="/" className="display text-2xl leading-none tracking-tight">
          Imprint
        </Link>
        <nav className="flex flex-wrap items-center justify-end gap-0.5 text-sm sm:gap-1">
          {NAV.map((n) => {
            const on = path === n.href || path.startsWith(n.href + "/");
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`whitespace-nowrap rounded-full px-2.5 py-1.5 transition-colors sm:px-3 ${
                  on ? "bg-ink text-paper" : "text-ink2 hover:bg-paper2 hover:text-ink"
                }`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    // The image service scales to zero when idle and takes about 30 s to come back. The first call from
    // any page wakes it; if that call is slow, say so instead of leaving the first drop unexplained.
    const timer = setTimeout(() => setSlow(true), 2000);
    api
      .config()
      .then(setCfg)
      .catch(() => {})
      .finally(() => {
        clearTimeout(timer);
        setSlow(false);
      });
    return () => clearTimeout(timer);
  }, []);
  return (
    <footer className="border-t border-line">
      {slow && (
        <div className="bg-warnbg text-warn">
          <div className="mx-auto flex w-full max-w-5xl items-center gap-2 px-5 py-2 text-xs sm:px-8">
            <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-warn" />
            Starting the image service. It sleeps when idle and takes about 30 seconds to wake; after that every
            step is quick.
          </div>
        </div>
      )}
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-2 px-5 py-6 text-xs text-ink2 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>
          Built for Monad Metropolis. Runs on Monad testnet only. It records who registered an image and when, not
          who made it.
        </p>
        {cfg && (
          <a className="mono underline-offset-2 hover:underline" href={cfg.registry_url} target="_blank" rel="noreferrer">
            Registry {short(cfg.registry, 6, 4)} · chain {cfg.chain_id}
          </a>
        )}
      </div>
    </footer>
  );
}
