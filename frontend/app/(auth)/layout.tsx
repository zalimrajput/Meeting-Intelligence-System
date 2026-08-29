import React from "react";
import Link from "next/link";
import { LogoMark } from "@/lib/logo";
import { ThemeToggle } from "@/components/ThemeToggle";

export { LogoMark };

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#0b1120] text-slate-100 relative">
      <div className="absolute top-4 right-4 z-20">
        <ThemeToggle />
      </div>
      {/* Brand panel */}
      <div className="flex flex-col justify-between p-8 lg:p-12 relative overflow-hidden">
        <Link href="/" className="flex items-center gap-2 text-xl font-bold">
          <LogoMark className="h-8 w-8" />
          <span>
            Meeting<span className="text-indigo-400">Mind</span>
          </span>
        </Link>
        <div className="hidden lg:block space-y-4">
          <h2 className="text-3xl font-semibold leading-tight">
            Turn meeting recordings into{" "}
            <span className="text-indigo-300">actionable intelligence.</span>
          </h2>
          <p className="text-slate-400 max-w-md">
            Upload audio or video, and get a structured report: transcript, decisions, action
            items, deadlines, and unresolved issues — extracted automatically by AI.
          </p>
          <div className="flex flex-wrap gap-2">
            {["Transcript + speaker ID", "Decisions", "Action items", "Deadlines", "Ask AI"].map((f) => (
              <span
                key={f}
                className="rounded-full border border-indigo-400/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-200"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
        <p className="text-xs text-slate-500">© 2026 MeetingMind · AI Meeting Intelligence</p>
      </div>
      {/* Form panel */}
      <div className="flex items-center justify-center p-6">{children}</div>
    </div>
  );
}
