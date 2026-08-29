"use client";
import React from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Meeting } from "@/lib/schemas";
import { fmtMinutes, fmtDate, timeAgo, statusPalette, titleCase } from "@/lib/utils";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .listMeetings()
      .then(setMeetings)
      .catch((e) => setErr((e as Error).message));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Meetings</h1>
          <p className="text-sm text-slate-400">All your processed meeting reports.</p>
        </div>
        <Link href="/upload" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">
          + Upload
        </Link>
      </div>

      {err && <p className="rounded-lg bg-rose-500/10 border border-rose-500/30 p-3 text-sm text-rose-200">Error: {err}</p>}

      {meetings === null ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 rounded-xl skeleton" />
          ))}
        </div>
      ) : meetings.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 p-10 text-center text-slate-400">
          No meetings yet — upload an audio or video recording to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {meetings.map((m) => {
            const p = statusPalette(m.status);
            return (
              <Link key={m.id} href={`/meetings/${m.id}`} className="flex items-center gap-3 rounded-xl border border-white/5 bg-slate-800/60 p-4 hover:border-indigo-500/40">
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">{m.title}</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {fmtMinutes(m.duration_seconds)} · {timeAgo(m.created_at)} · {m.meeting_date ? new Date(m.meeting_date).toLocaleDateString() : "Date not set"}
                  </p>
                </div>
                <span className={`rounded-full border px-2.5 py-1 text-xs ${p.chip} ${p.text}`}>
                  <span className={`mr-1 inline-block h-2 w-2 rounded-full ${p.dot}`} />
                  {titleCase(m.status)}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
