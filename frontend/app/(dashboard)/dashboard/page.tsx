"use client";
import React from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  DashboardStats,
  RecentMeeting,
  UpcomingDeadline,
  RecentDecision,
} from "@/lib/schemas";
import {
  fmtMinutes,
  fmtDate,
  timeAgo,
  statusPalette,
  titleCase,
  relativeDeadline,
} from "@/lib/utils";

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recent, setRecent] = useState<RecentMeeting[] | null>(null);
  const [deadlines, setDeadlines] = useState<UpcomingDeadline[] | null>(null);
  const [decisions, setDecisions] = useState<RecentDecision[] | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.dashboardStats().then(setStats).catch(() => setStats(null));
    api.recentMeetings(6).then(setRecent).catch(() => setRecent(null));
    api.upcomingDeadlines(6).then(setDeadlines).catch(() => setDeadlines(null));
    api.recentDecisions(6).then(setDecisions).catch(() => setDecisions(null));
  }, []);

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) router.push(`/search?q=${encodeURIComponent(query.trim())}`);
  }

  const firstName = (user?.full_name || "There").split(" ")[0]!;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Welcome back, {firstName} 👋</h1>
        <p className="text-slate-400 text-sm">Your meeting intelligence at a glance.</p>
        <form onSubmit={submitSearch} className="mt-3 flex">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search across meetings, decisions, and action items…"
            className="flex-1 rounded-lg border border-white/10 bg-slate-800 px-4 py-2.5 text-sm outline-none focus:border-indigo-500 placeholder-slate-500"
          />
          <button className="ml-2 rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white">
            Search
          </button>
        </form>
      </header>

      {/* Stat cards */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Total Meetings" value={stats ? String(stats.total_meetings) : "—"} icon="📁" />
        <StatCard
          title="Time Analyzed"
          value={stats?.total_hours_formatted || "—"}
          icon="⏱"
          sub={stats ? `${stats.total_duration_minutes} min` : ""}
        />
        <StatCard
          title="Action Items"
          value={stats ? String(stats.action_items.total) : "—"}
          icon="✅"
          sub={stats ? `${stats.action_items.pending} pending · ${stats.action_items.overdue} overdue` : ""}
        />
        <StatCard
          title="Sentiment (Positive)"
          value={stats ? String(stats.sentiment.positive) : "—"}
          icon="😊"
          sub={stats ? `${stats.sentiment.neutral} neutral · ${stats.sentiment.mixed} mixed` : ""}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent meetings */}
        <section className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Recent Meetings</h2>
            <Link href="/meetings" className="text-sm text-indigo-400">
              View all →
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {recent === null ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-16 rounded-lg skeleton" />
              ))
            ) : recent.length === 0 ? (
              <EmptyState text="No meetings yet. Upload your first recording." />
            ) : (
              recent.map((m) => <MeetingsRow key={m.id} m={m} />)
            )}
          </div>
        </section>

        {/* Deadlines */}
        <section className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
          <h2 className="font-semibold mb-4">Upcoming Deadlines</h2>
          <div className="space-y-3">
            {deadlines === null ? (
              <div className="h-16 rounded-lg skeleton" />
            ) : deadlines.length === 0 ? (
              <EmptyState text="No upcoming deadlines." />
            ) : (
              deadlines.map((d) => (
                <div key={d.id} className="rounded-lg border border-white/5 bg-slate-800/60 p-3">
                  <Link href={`/meetings/${d.meeting_id}`} className="text-sm text-indigo-300 line-clamp-1">
                    {d.meeting_title}
                  </Link>
                  <p className="text-xs text-slate-300 mt-1">{d.description}</p>
                  <p className="text-xs mt-1 text-amber-300">
                    {d.raw_text ? `"${d.raw_text}"` : fmtDate(d.resolved_date)} ·{" "}
                    <span className={relativeDeadline(d.resolved_date).overdue ? "text-rose-300" : "text-emerald-300"}>
                      {relativeDeadline(d.resolved_date).label || "—"}
                    </span>
                  </p>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* Recent decisions */}
      <section className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
        <h2 className="font-semibold mb-4">Recent Decisions</h2>
        <div className="space-y-3">
          {decisions === null ? (
            <div className="h-20 rounded-lg skeleton" />
          ) : decisions.length === 0 ? (
            <EmptyState text="No decisions extracted yet." />
          ) : (
            decisions.map((d) => (
              <div key={d.id} className="flex gap-3 items-start rounded-lg bg-slate-800/60 border border-white/5 p-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-400" />
                <div className="flex-1">
                  <p className="text-sm text-slate-100">{sentenceCase(d.decision_text)}</p>
                  <p className="text-xs text-slate-400 mt-1">
                    Decided by {d.decided_by || "group"} · {timeAgo(d.created_at)} ·{" "}
                    <Link className="text-indigo-400" href={`/meetings/${d.meeting_id}`}>
                      open meeting →
                    </Link>
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function StatCard({
  title,
  label,
  value,
  icon,
  sub,
}: {
  title?: string;
  label?: string;
  value: string;
  icon: string;
  sub?: string;
}) {
  const displayLabel = title || label || "";
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
      <div className="text-xl">{icon}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
      <div className="text-xs text-slate-400">{displayLabel}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

function MeetingsRow({ m }: { m: RecentMeeting }) {
  const p = statusPalette(m.status);
  return (
    <Link
      href={`/meetings/${m.id}`}
      className="block rounded-xl border border-white/5 bg-slate-800/60 p-4 hover:border-indigo-500/40 transition"
    >
      <div className="flex items-center gap-3 justify-between">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-slate-100 truncate">{m.title}</p>
          <p className="text-xs text-slate-500 mt-1">
            {fmtDate(m.meeting_date)} · {fmtMinutes(m.duration_seconds)} · {timeAgo(m.created_at)}
          </p>
          <p className="text-xs text-slate-400 mt-1 line-clamp-2">{m.summary_short || "No summary yet."}</p>
        </div>
        <div className="text-right shrink-0">
          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs border ${p.chip} ${p.text}`}>
            <span className={`h-2 w-2 rounded-full ${p.dot}`} />
            {titleCase(m.status)}
          </span>
          <div className="mt-2 text-[11px] text-slate-500">
            {m.action_items_count ?? 0} ✓ · {m.decisions_count ?? 0} 🎯
          </div>
        </div>
      </div>
    </Link>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

function sentenceCase(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}
