"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { initials } from "@/lib/utils";
import { LogoMark } from "@/lib/logo";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: <DashboardIcon /> },
  { href: "/upload", label: "Upload Meeting", icon: <UploadIcon /> },
  { href: "/meetings", label: "Meetings", icon: <MeetingsIcon /> },
  { href: "/search", label: "Search", icon: <SearchIcon /> },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0b1120] text-slate-100">
        <div className="flex items-center gap-3">
          <span className="h-4 w-4 rounded-full bg-indigo-500 animate-pulse-soft" />
          <span className="text-sm text-slate-400">Loading MeetingMind workspace…</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const sidebar = (
    <div className="flex flex-col gap-1">
      {NAV.map((n) => {
        const active = pathname === n.href || (n.href !== "/dashboard" && pathname.startsWith(n.href));
        return (
          <Link
            key={n.href}
            href={n.href}
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
              active
                ? "bg-indigo-600/15 text-indigo-500 font-semibold"
                : "text-slate-300 hover:bg-slate-800/40"
            }`}
          >
            <span className={active ? "text-indigo-500" : "text-slate-400"}>{n.icon}</span>
            {n.label}
          </Link>
        );
      })}
    </div>
  );

  return (
    <div className="flex min-h-screen bg-[#0b1120] text-slate-100">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 flex-col border-r border-white/5 bg-slate-950/70 p-4">
        <Link href="/dashboard" className="flex items-center gap-2 px-2">
          <LogoMark className="h-9 w-9" />
          <span className="text-lg font-bold">
            Meeting<span className="text-indigo-400">Mind</span>
          </span>
        </Link>
        <div className="mt-6">{sidebar}</div>
        <div className="mt-auto flex flex-col gap-2 border-t border-white/5 pt-4">
          <ThemeToggle showLabel className="w-full justify-start px-3 py-2 text-sm" />
          <button
            onClick={logout}
            className="w-full text-left rounded-lg px-3 py-2 text-sm text-rose-400 hover:bg-rose-500/10 transition"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 bg-slate-950/95 lg:hidden">
          <div className="p-4 flex items-center justify-between border-b border-white/10">
            <span className="font-bold text-lg">MeetingMind</span>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg border border-white/10 px-3 py-1.5 text-sm"
              >
                Close
              </button>
            </div>
          </div>
          <div className="px-4 pt-4">{sidebar}</div>
          <div className="mt-auto p-4 border-t border-white/10">
            <button
              onClick={logout}
              className="w-full text-left rounded-lg px-3 py-2 text-sm text-rose-400 hover:bg-rose-500/10"
            >
              Sign out
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 border-b border-white/5 bg-slate-950/60 backdrop-blur-md flex items-center justify-between px-6 py-3">
          <button
            onClick={() => setOpen(true)}
            className="lg:hidden rounded-lg border border-white/10 px-2 py-1 text-slate-300"
          >
            ☰
          </button>
          <div className="hidden lg:block text-xs font-medium text-slate-400">
            Workspace / AI Meeting Intelligence
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link
              href="/upload"
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 transition"
            >
              + Upload
            </Link>
            <UserChip name={user?.full_name || "User"} onClick={logout} />
          </div>
        </header>
        <main className="p-6 lg:p-8 max-w-7xl mx-auto w-full">{children}</main>
      </div>
    </div>
  );
}

function UserChip({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded-full bg-indigo-500/15 px-3 py-1.5 text-sm text-indigo-100 hover:bg-indigo-500/25 transition"
      title="Click to sign out"
    >
      <span className="rounded-full bg-indigo-500/25 px-2 py-0.5 text-xs text-white">{initials(name)}</span>
      {name}
    </button>
  );
}

/* ---- inline SVG icons ---- */
function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-5 w-5">
      <rect x="3" y="4" width="18" height="3" rx="1" />
      <rect x="3" y="10" width="7" height="10" rx="1" />
      <rect x="12" y="10" width="9" height="10" rx="1" />
    </svg>
  );
}
function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
      <path d="M7 4h10M4 12h16M6 17h12" />
      <path d="M12 6l4 2" strokeWidth="2" />
    </svg>
  );
}
function MeetingsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
      <circle cx="12" cy="7" r="5" />
      <rect x="5" y="14" width="14" height="8" rx="2" />
    </svg>
  );
}
function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
      <circle cx="10" cy="10" r="6" />
      <path d="M21 10a3 3 0 1" />
    </svg>
  );
}
