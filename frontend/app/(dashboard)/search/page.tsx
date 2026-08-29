"use client";
import React, { Suspense } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { GlobalSearchResult } from "@/lib/schemas";
import { fmtClock, fmtDate, statusPalette, titleCase } from "@/lib/utils";

function SearchContent() {
  const sp = useSearchParams();
  const [q, setQ] = useState(sp.get("q") || "");
  const [results, setResults] = useState<GlobalSearchResult | null>(null);
  const [waiting, setWaiting] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!q.trim()) {
      setResults(null);
      setWaiting(false);
      return;
    }
    setWaiting(true);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      api
        .globalSearch(q)
        .then(setResults)
        .catch(() => setResults(null))
        .finally(() => setWaiting(false));
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [q]);

  const meetings = results?.meetings || [];
  const transcripts = results?.transcripts || [];
  const actions = results?.action_items || [];
  const decisions = results?.decisions || [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Search Meetings</h1>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search meetings, transcripts, decisions, action items…"
        className="w-full rounded-xl border border-white/10 bg-slate-800 px-4 py-3 text-sm outline-none focus:border-indigo-500"
      />

      {!q.trim() && (
        <div className="rounded-2xl border border-dashed border-white/10 p-12 text-center text-slate-400">
          <div className="text-3xl mb-2">🔍</div>
          Type above to search across meetings, transcripts, decisions, and action items.
        </div>
      )}

      {q.trim() && waiting && !results && <div className="h-16 rounded-xl skeleton" />}

      {q.trim() && results && results.total_matches === 0 && (
        <div className="rounded-2xl border border-dashed border-white/10 p-12 text-center text-slate-400">
          No matches found for “{q}”.
        </div>
      )}

      {q.trim() && results && results.total_matches > 0 && (
        <>
          <p className="text-sm text-slate-400">
            {results.total_matches} result{results.total_matches === 1 ? "" : "s"} for “{q}”.
          </p>

          {meetings.length > 0 && (
            <Section title={`Meetings (${meetings.length})`}>
              {meetings.map((m) => {
                const p = statusPalette((m.status as string) || "");
                return (
                  <Link
                    key={m.id as string}
                    href={`/meetings/${m.id}`}
                    className="block rounded-xl border border-white/5 bg-slate-800/60 p-4 hover:border-indigo-500/40"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium truncate">{m.title as string}</span>
                      <span className={`rounded-full border px-2.5 py-1 text-xs ${p.chip} ${p.text}`}>
                        {titleCase((m.status as string) || "")}
                      </span>
                    </div>
                    {m.meeting_date ? (
                      <p className="text-xs text-slate-500 mt-1">{fmtDate(m.meeting_date as string)}</p>
                    ) : null}
                  </Link>
                );
              })}
            </Section>
          )}

          {transcripts.length > 0 && (
            <Section title={`Transcript matches (${transcripts.length})`}>
              {transcripts.map((t) => (
                <Link
                  key={t.id as string}
                  href={`/meetings/${t.meeting_id}`}
                  className="block rounded-xl border border-white/5 bg-slate-800/60 p-4 hover:border-indigo-500/40"
                >
                  <p className="text-sm text-slate-200 line-clamp-2">{t.text as string}</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {t.speaker_label ? `${String(t.speaker_label)} · ` : ""}
                    {t.start_time_seconds != null ? `at ${fmtClock(t.start_time_seconds as number)} · ` : ""}
                    open meeting →
                  </p>
                </Link>
              ))}
            </Section>
          )}

          {decisions.length > 0 && (
            <Section title={`Decisions (${decisions.length})`}>
              {decisions.map((d) => (
                <Link
                  key={d.id as string}
                  href={`/meetings/${d.meeting_id}`}
                  className="block rounded-xl border border-white/5 bg-slate-800/60 p-4 hover:border-indigo-500/40"
                >
                  <p className="text-sm text-slate-200">{d.decision_text as string}</p>
                  {d.timestamp_seconds != null ? (
                    <p className="text-xs text-slate-500 mt-1">at {fmtClock(d.timestamp_seconds as number)}</p>
                  ) : null}
                </Link>
              ))}
            </Section>
          )}

          {actions.length > 0 && (
            <Section title={`Action items (${actions.length})`}>
              {actions.map((a) => (
                <Link
                  key={a.id as string}
                  href={`/meetings/${a.meeting_id}`}
                  className="block rounded-xl border border-white/5 bg-slate-800/60 p-4 hover:border-indigo-500/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-slate-200 truncate">{a.task_description as string}</span>
                    {a.assigned_to ? <span className="text-xs text-slate-400">{String(a.assigned_to)}</span> : null}
                  </div>
                </Link>
              ))}
            </Section>
          )}
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-slate-900/60 p-5">
      <h2 className="font-semibold mb-3">{title}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="h-20 rounded-xl skeleton p-6">Loading search...</div>}>
      <SearchContent />
    </Suspense>
  );
}
