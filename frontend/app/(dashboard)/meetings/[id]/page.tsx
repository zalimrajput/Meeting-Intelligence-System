"use client";
import React from "react";
import { useEffect, useRef, useState, FormEvent } from "react";
import { useParams } from "next/navigation";
import { api, mediaUrl, exportUrl } from "@/lib/api";
import {
  Meeting,
  TranscriptSegment,
  AllInsights,
  ActionItem,
  ChatMessage,
  ActionStatus,
} from "@/lib/schemas";
import {
  fmtClock,
  fmtMinutes,
  fmtDate,
  statusPalette,
  titleCase,
  relativeDeadline,
  speakerColor,
} from "@/lib/utils";

type Tab = "overview" | "transcript" | "insights" | "ask";
type InsightTab = "points" | "decisions" | "actions" | "deadlines" | "issues";

const SUGGESTIONS = [
  "What did we decide about the marketing budget?",
  "Who owns the backend work and when is it due?",
  "What risks were raised?",
  "Summarize the action items.",
];

/* ---------------- Error Boundary ---------------- */
interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallbackTitle?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-rose-200">
          <h3 className="font-semibold text-rose-100">
            {this.props.fallbackTitle || "Something went wrong in this section"}
          </h3>
          <p className="mt-2 text-sm text-rose-300">
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500 transition-colors"
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const meetingId = params.id;

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [insights, setInsights] = useState<AllInsights | null>(null);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [insightTab, setInsightTab] = useState<InsightTab>("points");
  const [statusMsg, setStatusMsg] = useState("");
  const [currentStatus, setCurrentStatus] = useState("uploaded");
  const [failed, setFailed] = useState("");
  const [txSearch, setTxSearch] = useState("");
  const [seekTo, setSeekTo] = useState<number | null>(null);

  function seek(t: number) {
    setSeekTo(t);
  }

  useEffect(() => {
    let isCancelled = false;

    const loadMeetingData = async () => {
      try {
        let m = await api.getMeeting(meetingId);
        if (isCancelled) return;

        const isProcessingState = (st: string) =>
          ["uploaded", "uploading", "transcribing", "analyzing", "processing", "queued"].includes(
            (st || "").toLowerCase()
          );

        if (isProcessingState(m.status)) {
          setCurrentStatus(m.status);
          const stageDescriptions: Record<string, string> = {
            uploaded: "Recording uploaded. Queued for AI transcription...",
            queued: "Queued in background processing worker...",
            transcribing: "Transcribing audio and diarizing speakers (DeepGram Nova-3)...",
            analyzing: "Extracting intelligence, summary, decisions & action items (Gemini)...",
            processing: "AI processing in progress...",
          };

          setStatusMsg(stageDescriptions[m.status.toLowerCase()] || "Processing meeting recording...");

          // Poll until completed or failed
          for (let i = 0; i < 60; i++) {
            await new Promise((r) => setTimeout(r, 2500));
            if (isCancelled) return;

            try {
              const st = await api.getMeetingStatus(meetingId);
              if (isCancelled) return;

              setCurrentStatus(st.status);

              if (st.status === "failed") {
                setStatusMsg("");
                setFailed(st.failure_reason || "AI processing pipeline encountered an error.");
                return;
              }

              if (["completed", "complete", "ready"].includes((st.status || "").toLowerCase())) {
                m = await api.getMeeting(meetingId);
                break;
              } else {
                setStatusMsg(
                  stageDescriptions[(st.status || "").toLowerCase()] || `Processing meeting (${st.status})...`
                );
              }
            } catch {
              // Ignore transient polling hiccups
            }
          }
          setStatusMsg("");
        }

        if (isCancelled) return;
        setMeeting(m);

        try {
          const [tx, ins, acts] = await Promise.all([
            api.getTranscript(meetingId).catch(() => []),
            api.getInsights(meetingId).catch(() => null),
            api.listActions(meetingId).catch(() => []),
          ]);
          if (!isCancelled) {
            setTranscript(tx);
            setInsights(ins);
            setActions(acts);
          }
        } catch (err) {
          console.debug("Error loading auxiliary meeting data:", err);
        }
      } catch (e) {
        if (!isCancelled) {
          setFailed((e as Error).message);
        }
      }
    };

    loadMeetingData();

    return () => {
      isCancelled = true;
    };
  }, [meetingId]);

  if (failed) {
    return (
      <div className="rounded-2xl bg-rose-500/10 border border-rose-500/30 p-6 text-rose-200">
        <h2 className="text-lg font-semibold text-rose-100">Failed to load meeting</h2>
        <p className="mt-1 text-sm text-rose-300">{failed}</p>
      </div>
    );
  }

  const processing =
    !meeting ||
    ["uploaded", "uploading", "transcribing", "analyzing", "processing", "queued"].includes(
      (meeting.status || "").toLowerCase()
    );

  return (
    <div className="space-y-6">
      {processing ? (
        <ProcessingPanel
          message={statusMsg || "Processing meeting recording..."}
          status={currentStatus}
        />
      ) : (
        <header className="rounded-2xl border border-white/10 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold">{meeting!.title}</h1>
              <p className="text-sm text-slate-400 mt-1">
                {fmtDate(meeting!.meeting_date)} · {fmtMinutes(meeting!.duration_seconds ?? 0)} · ID{" "}
                <span className="font-mono text-xs text-slate-500">{meeting!.id}</span>
              </p>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={meeting!.status} />
              <SentimentBadge sentiment={meeting!.sentiment} score={meeting!.sentiment_score} />
              <ExportMenu meeting={meeting!} />
            </div>
          </div>
          <AudioPlayer src={mediaUrl(meetingId)} seekTo={seekTo} />
        </header>
      )}

      {!processing && <Tabs active={tab} onChange={setTab} />}

      {!processing && (
        <ErrorBoundary fallbackTitle="Could not render this section">
          {tab === "overview" && <OverviewTab meeting={meeting!} insights={insights} />}
          {tab === "transcript" && (
            <TranscriptTab
              segments={transcript}
              search={txSearch}
              setSearch={setTxSearch}
              onSeek={seek}
            />
          )}
          {tab === "insights" && (
            <InsightsTab
              insights={insights}
              actions={actions}
              active={insightTab}
              onSubTab={setInsightTab}
              onToggleAction={(a, st) =>
                api
                  .updateAction(meetingId, a.id, { status: st })
                  .then(() =>
                    setActions((prev) => prev.map((x) => (x.id === a.id ? { ...x, status: st } : x)))
                  )
              }
              onSeek={seek}
            />
          )}
          {tab === "ask" && <AskTab meetingId={meetingId} onSeek={seek} />}
        </ErrorBoundary>
      )}
    </div>
  );
}

/* ---------------- Processing + badges ---------------- */

function ProcessingPanel({ message, status }: { message: string; status?: string }) {
  const steps = [
    { key: "uploaded", label: "Recording Uploaded" },
    { key: "transcribing", label: "Speech-to-Text & Diarization (DeepGram)" },
    { key: "analyzing", label: "Intelligence & Insights Extraction (Gemini)" },
    { key: "completed", label: "Ready & Completed" },
  ];

  const currentIdx =
    status === "analyzing" ? 2 : status === "transcribing" ? 1 : status === "completed" ? 3 : 0;

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-6 shadow-xl">
      <div className="flex items-center gap-3">
        <span className="inline-block h-3.5 w-3.5 rounded-full bg-indigo-500 animate-pulse" />
        <p className="font-semibold text-slate-100">{message}</p>
      </div>
      <div className="mt-5 space-y-3">
        {steps.map((step, i) => {
          const isDone = i < currentIdx;
          const isCurrent = i === currentIdx;
          return (
            <div key={step.key} className="flex items-center gap-3 py-1">
              <span
                className={`h-5 w-5 rounded-full flex items-center justify-center text-[11px] font-bold ${
                  isDone
                    ? "bg-emerald-500 text-white"
                    : isCurrent
                    ? "bg-indigo-500 text-white animate-pulse"
                    : "bg-slate-800 text-slate-500 border border-white/5"
                }`}
              >
                {isDone ? "✓" : i + 1}
              </span>
              <span
                className={`text-sm ${
                  isDone
                    ? "text-emerald-300 font-medium"
                    : isCurrent
                    ? "text-indigo-200 font-medium"
                    : "text-slate-500"
                }`}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-slate-400">
        Live status updates automatically as your meeting progresses through the AI pipeline.
      </p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const p = statusPalette(status);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${p.chip} ${p.text}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${p.dot}`} />
      {titleCase(status)}
    </span>
  );
}

function SentimentBadge({ sentiment, score }: { sentiment: string | null; score: number | null }) {
  if (!sentiment) return null;
  const icon =
    sentiment === "positive"
      ? "😊"
      : sentiment === "negative"
      ? "😞"
      : sentiment === "mixed"
      ? "🤷"
      : "😐";
  return (
    <span className="inline-flex rounded-full border border-white/10 bg-slate-800/60 px-2.5 py-1 text-xs text-slate-200">
      {icon} {titleCase(sentiment)}
      {score != null ? ` · ${(score * 100).toFixed(0)}%` : ""}
    </span>
  );
}

function ExportMenu({ meeting }: { meeting: Meeting }) {
  const formats: Array<[string, string]> = [
    ["markdown", "Markdown (.md)"],
    ["json", "JSON (.json)"],
    ["email", "Email Digest (.txt)"],
    ["text", "Plain Text (.txt)"],
  ];
  return (
    <div className="relative group">
      <button className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5 transition-colors">
        ⬇ Export
      </button>
      <div className="absolute right-0 top-full mt-1 hidden group-hover:flex flex-col rounded-lg border border-white/10 bg-slate-900/95 p-1 min-w-40 shadow-xl z-20">
        {formats.map(([f, label]) => (
          <a
            key={f}
            href={exportUrl(meeting.id, f)}
            download
            className="px-3 py-2 text-xs text-slate-300 hover:bg-indigo-500/20 hover:text-white rounded transition-colors"
          >
            {label}
          </a>
        ))}
      </div>
    </div>
  );
}

function AudioPlayer({ src, seekTo }: { src: string; seekTo: number | null }) {
  const ref = useRef<HTMLAudioElement | null>(null);
  useEffect(() => {
    if (seekTo != null && ref.current && isFinite(seekTo)) {
      ref.current.currentTime = seekTo;
      ref.current.play().catch(() => {});
    }
  }, [seekTo]);

  if (!src) {
    return (
      <p className="mt-3 text-xs text-slate-500">
        🔊 Media playback appears here once backend media stream is connected.
      </p>
    );
  }
  return <audio ref={ref} controls src={src} preload="metadata" className="mt-3 w-full rounded-lg" />;
}

function Tabs({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  const list: Array<[Tab, string]> = [
    ["overview", "Overview"],
    ["transcript", "Transcript"],
    ["insights", "AI Insights"],
    ["ask", "Ask AI"],
  ];
  return (
    <div className="flex flex-wrap gap-2 rounded-lg border border-white/10 bg-slate-800/60 p-1">
      {list.map(([id, label]) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
            active === id
              ? "bg-indigo-600 text-white shadow"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/* ---------------- Overview ---------------- */

function OverviewTab({ meeting, insights }: { meeting: Meeting; insights: AllInsights | null }) {
  const summary =
    insights?.summary_detailed ||
    insights?.summary_short ||
    meeting.summary_detailed ||
    meeting.summary_short ||
    "No summary generated yet.";
  const meta: Array<[string, string]> = [
    ["Duration", fmtMinutes(meeting.duration_seconds ?? 0)],
    ["Date", fmtDate(meeting.meeting_date)],
    ["Created", fmtDate(meeting.created_at)],
  ];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-white/10 bg-slate-900/60 p-6">
        <h2 className="font-semibold text-lg mb-3">Executive Summary</h2>
        <p className="text-sm leading-6 text-slate-200 whitespace-pre-wrap">{summary}</p>
      </section>
      <section className="rounded-2xl border border-white/10 bg-slate-900/60 p-6">
        <h2 className="font-semibold text-lg mb-3">Meeting Details</h2>
        <dl className="space-y-3">
          {meta.map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-white/5 pb-2">
              <dt className="text-xs text-slate-400">{k}</dt>
              <dd className="text-sm text-slate-100 font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

/* ---------------- Transcript ---------------- */

function TranscriptTab({
  segments,
  search,
  setSearch,
  onSeek,
}: {
  segments: TranscriptSegment[];
  search: string;
  setSearch: (s: string) => void;
  onSeek: (t: number) => void;
}) {
  const q = search.trim().toLowerCase();
  const filtered = q ? segments.filter((s) => s.text.toLowerCase().includes(q)) : segments;

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-lg">Transcript ({segments.length} segments)</h2>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search transcript…"
          className="w-64 rounded-lg border border-white/10 bg-slate-800 px-3 py-1.5 text-sm outline-none focus:border-indigo-500 text-slate-100"
        />
      </div>
      {filtered.length === 0 ? (
        <p className="text-sm text-slate-500 py-8 text-center">
          {segments.length === 0 ? "No transcript segments recorded." : "No lines match your search query."}
        </p>
      ) : (
        <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
          {filtered.map((s) => (
            <div key={s.id} className="rounded-lg bg-slate-800/50 border border-white/5 p-3 hover:border-indigo-500/30 transition-colors">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium text-white ${speakerColor(s.speaker_label)}`}>
                  {s.speaker_label || `Speaker ${s.speaker_id || "?"}`}
                </span>
                <button
                  onClick={() => onSeek(s.start_time_seconds)}
                  className="text-[11px] text-indigo-300 hover:text-indigo-200 underline font-mono cursor-pointer"
                >
                  ▶ {fmtClock(s.start_time_seconds)}
                </button>
                {s.confidence != null && (
                  <span className="text-[11px] text-slate-500">{Math.round(s.confidence * 100)}% conf</span>
                )}
              </div>
              <p className="mt-1.5 text-sm text-slate-200 leading-relaxed">{highlight(s.text, q)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function highlight(text: string, q: string) {
  if (!q) return text;
  const idx = text.toLowerCase().indexOf(q);
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded bg-amber-400/30 text-amber-100 px-0.5 font-medium">{text.slice(idx, idx + q.length)}</mark>
      {text.slice(idx + q.length)}
    </>
  );
}

/* ---------------- Insights ---------------- */

function InsightsTab({
  insights,
  actions,
  active,
  onSubTab,
  onToggleAction,
  onSeek,
}: {
  insights: AllInsights | null;
  actions: ActionItem[];
  active: InsightTab;
  onSubTab: (t: InsightTab) => void;
  onToggleAction: (a: ActionItem, s: ActionStatus) => void;
  onSeek: (t: number) => void;
}) {
  const subs: Array<[InsightTab, string]> = [
    ["points", "Key Points"],
    ["decisions", "Decisions"],
    ["actions", "Action Items"],
    ["deadlines", "Deadlines"],
    ["issues", "Unresolved Issues"],
  ];
  return (
    <div>
      <div className="flex flex-wrap gap-2 rounded-lg border border-white/10 bg-slate-800/60 p-1 mb-4">
        {subs.map(([id, label]) => (
          <button
            key={id}
            onClick={() => onSubTab(id)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              active === id
                ? "bg-indigo-600 text-white font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {active === "points" && (
        <ListCard title={`Key Points (${insights?.key_points?.length || 0})`}>
          {insights?.key_points && insights.key_points.length ? (
            insights.key_points.map((k, i) => (
              <Row key={k.id} index={String(i + 1)} title={k.point_text} onSeek={onSeek} ts={k.timestamp_seconds}>
                <span className="text-xs text-indigo-300">Key point</span>
              </Row>
            ))
          ) : (
            <EmptyNote />
          )}
        </ListCard>
      )}

      {active === "decisions" && (
        <ListCard title={`Decisions (${insights?.decisions?.length || 0})`}>
          {insights?.decisions && insights.decisions.length ? (
            insights.decisions.map((d, i) => (
              <Row key={d.id} index={String(i + 1)} title={d.decision_text} onSeek={onSeek} ts={d.timestamp_seconds}>
                <span className="text-xs text-slate-400">Decided by {d.decided_by || "group"}</span>
              </Row>
            ))
          ) : (
            <EmptyNote />
          )}
        </ListCard>
      )}

      {active === "actions" && (
        <ListCard title={`Action Items (${actions.length})`}>
          {actions.length ? (
            actions.map((a) => (
              <div key={a.id} className="rounded-xl border border-white/5 bg-slate-800/50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium text-sm text-slate-100">{a.task_description}</p>
                  <StatusBadge status={a.status} />
                </div>
                <div className="mt-2 flex flex-wrap gap-2 items-center">
                  <span className="rounded-full bg-indigo-500/10 px-2.5 py-1 text-xs text-indigo-200">
                    👤 {a.assigned_to || "Unassigned"}
                  </span>
                  {a.deadline_raw_text || a.deadline_date ? (
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        relativeDeadline(a.deadline_date).overdue
                          ? "bg-rose-500/10 border-rose-500/30 text-rose-200"
                          : "bg-amber-500/10 border-amber-500/30 text-amber-200"
                      }`}
                    >
                      ⏰ {a.deadline_raw_text || a.deadline_date}
                      {a.deadline_date ? ` (${relativeDeadline(a.deadline_date).label})` : ""}
                    </span>
                  ) : null}
                  {a.timestamp_seconds != null && (
                    <button
                      onClick={() => onSeek(a.timestamp_seconds!)}
                      className="text-[11px] text-indigo-300 hover:text-indigo-200 underline font-mono cursor-pointer"
                    >
                      ▶ {fmtClock(a.timestamp_seconds)}
                    </button>
                  )}
                  <ToggleStatus status={a.status} onToggle={(s) => onToggleAction(a, s)} />
                </div>
              </div>
            ))
          ) : (
            <EmptyNote />
          )}
        </ListCard>
      )}

      {active === "deadlines" && <DeadlinesTab actions={actions} onSeek={onSeek} />}
      {active === "issues" && (
        <ListCard title={`Unresolved Issues (${insights?.unresolved_issues?.length || 0})`}>
          {insights?.unresolved_issues && insights.unresolved_issues.length ? (
            insights.unresolved_issues.map((iss, i) => (
              <Row key={iss.id} index={String(i + 1)} title={iss.issue_text} onSeek={onSeek} ts={iss.timestamp_seconds}>
                <span className="text-xs text-amber-300">Follow-up required</span>
              </Row>
            ))
          ) : (
            <EmptyNote />
          )}
        </ListCard>
      )}
    </div>
  );
}

function ListCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 shadow-lg">
      <h2 className="font-semibold text-lg mb-4 text-slate-100">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Row({
  index,
  title,
  ts,
  onSeek,
  children,
}: {
  index: string;
  title: string;
  ts: number | null;
  onSeek: (t: number) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-slate-800/50 p-4 flex gap-3 items-start hover:border-indigo-500/20 transition-colors">
      <span className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs text-indigo-200 font-mono">
        {index}
      </span>
      <div className="flex-1">
        <p className="text-sm text-slate-100 leading-relaxed">{title}</p>
        <div className="mt-1.5 flex items-center gap-3">
          {children}
          {ts != null && (
            <button
              onClick={() => onSeek(ts)}
              className="text-[11px] text-indigo-300 hover:text-indigo-200 underline font-mono cursor-pointer"
            >
              ▶ {fmtClock(ts)}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function DeadlinesTab({ actions, onSeek }: { actions: ActionItem[]; onSeek: (t: number) => void }) {
  const items = actions
    .filter((a) => a.deadline_date || a.deadline_raw_text)
    .slice()
    .sort((a, b) => (a.deadline_date || "9999").localeCompare(b.deadline_date || "9999"));
  return (
    <ListCard title={`Deadlines (${items.length})`}>
      {items.length ? (
        items.map((a) => {
          const d = relativeDeadline(a.deadline_date);
          return (
            <div key={a.id} className="rounded-xl border border-white/5 bg-slate-800/50 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-slate-100">{a.task_description}</p>
                <span
                  className={`rounded-full border px-2.5 py-1 text-xs ${
                    d.overdue
                      ? "bg-rose-500/10 border-rose-500/30 text-rose-200"
                      : "bg-amber-500/10 border-amber-500/30 text-amber-200"
                  }`}
                >
                  {a.deadline_date || a.deadline_raw_text} · {d.label || "—"}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="text-xs text-slate-400">Assigned to {a.assigned_to || "—"}</span>
                {a.timestamp_seconds != null && (
                  <button
                    onClick={() => onSeek(a.timestamp_seconds!)}
                    className="text-[11px] text-indigo-300 underline font-mono cursor-pointer"
                  >
                    ▶ {fmtClock(a.timestamp_seconds)}
                  </button>
                )}
              </div>
            </div>
          );
        })
      ) : (
        <EmptyNote />
      )}
    </ListCard>
  );
}

function EmptyNote() {
  return <p className="text-sm text-slate-500 py-6 text-center">Nothing recorded in this section yet.</p>;
}

function ToggleStatus({ status, onToggle }: { status: string; onToggle: (s: ActionStatus) => void }) {
  const label =
    status === "pending"
      ? "Mark in progress"
      : status === "in_progress"
      ? "Mark complete"
      : "Reopen";
  const next: ActionStatus =
    status === "pending"
      ? "in_progress"
      : status === "in_progress"
      ? "completed"
      : "pending";
  return (
    <button
      onClick={() => onToggle(next)}
      className="rounded-lg border border-white/10 bg-slate-800 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-white/5 transition-colors cursor-pointer"
    >
      {label}
    </button>
  );
}

/* ---------------- Ask AI ---------------- */

interface DisplayMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestampSeconds?: number | null;
  isError?: boolean;
  createdAt?: string;
}

function AskTab({ meetingId, onSeek }: { meetingId: string; onSeek: (t: number) => void }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api
      .getChatHistory(meetingId)
      .then((history) => {
        const displayList: DisplayMessage[] = [];
        for (const item of history) {
          if (item.question) {
            displayList.push({
              id: `q-${item.id}`,
              sender: "user",
              text: item.question,
              createdAt: item.created_at,
            });
          }
          if (item.answer) {
            displayList.push({
              id: `a-${item.id}`,
              sender: "ai",
              text: item.answer,
              timestampSeconds: item.referenced_timestamp_seconds,
              createdAt: item.created_at,
            });
          }
        }
        setMessages(displayList);
      })
      .catch((err) => {
        console.debug("Could not load chat history:", err);
      });
  }, [meetingId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const question = q.trim();
    if (!question || busy) return;

    // Optimistic user message rendering
    const userMsg: DisplayMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: question,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setQ("");
    setBusy(true);

    try {
      const aiMsg = await api.askQuestion(meetingId, question);

      const normalizedMsg: DisplayMessage = {
        id: aiMsg.id || `ai-${Date.now()}`,
        sender: "ai",
        text: aiMsg.answer || "No response received from AI.",
        timestampSeconds: aiMsg.referenced_timestamp_seconds ?? null,
        createdAt: aiMsg.created_at || new Date().toISOString(),
      };
      setMessages((prev) => [...prev, normalizedMsg]);
    } catch (err) {
      const errorMsg: DisplayMessage = {
        id: `err-${Date.now()}`,
        sender: "ai",
        text: "⚠️ " + ((err as Error).message || "Failed to receive response from AI. Please try again."),
        isError: true,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="rounded-2xl border border-white/10 bg-slate-900/60 p-6 flex flex-col gap-3 shadow-xl"
      style={{ minHeight: 450 }}
    >
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-lg text-slate-100">Ask AI about this meeting</h2>
          <p className="text-xs text-slate-400">
            Powered by Google Gemini 2.5 Flash with full transcript grounding & timestamp citations.
          </p>
        </div>
      </div>

      {messages.length === 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setQ(s)}
              className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-xs text-indigo-200 hover:bg-indigo-500/20 transition-colors cursor-pointer"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-3 pr-1 max-h-[480px]">
        {messages.map((m) => {
          const isUser = m.sender === "user";
          return (
            <div
              key={m.id}
              className={`flex flex-col ${
                isUser
                  ? "items-end"
                  : "items-start"
              }`}
            >
              <div
                className={`px-4 py-3 rounded-2xl max-w-[85%] text-sm ${
                  isUser
                    ? "bg-indigo-600 text-white rounded-br-sm shadow-md"
                    : m.isError
                    ? "bg-rose-950/60 border border-rose-500/30 text-rose-200 rounded-bl-sm"
                    : "bg-slate-800 border border-white/5 text-slate-100 rounded-bl-sm shadow-md"
                }`}
              >
                {isUser ? (
                  <p className="whitespace-pre-wrap">{m.text}</p>
                ) : (
                  <div>
                    <div className="whitespace-pre-wrap leading-relaxed">
                      {renderAnswer(m.text, onSeek)}
                    </div>
                    {m.timestampSeconds != null && (
                      <button
                        onClick={() => onSeek(m.timestampSeconds!)}
                        className="mt-2.5 inline-flex items-center gap-1 text-xs text-indigo-300 hover:text-indigo-100 bg-indigo-500/20 border border-indigo-500/30 px-2.5 py-1 rounded-md font-mono cursor-pointer transition-colors"
                      >
                        ▶ Jump to {fmtClock(m.timestampSeconds)}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {busy && (
          <div className="flex items-start">
            <div className="bg-slate-800 border border-white/5 rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-slate-300 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping" />
              <span>AI is thinking & searching transcript…</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={submit} className="flex gap-2 mt-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask anything about decisions, action items, or discussion points…"
          className="flex-1 rounded-lg border border-white/10 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500 transition-colors"
        />
        <button
          disabled={busy || !q.trim()}
          className="rounded-lg bg-indigo-600 px-5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
        >
          Send
        </button>
      </form>
    </div>
  );
}

/** Renders any "MM:SS" or "[MM:SS]" token inside the answer as a clickable seek chip. */
function renderAnswer(answer: string, onSeek: (t: number) => void) {
  const parts = answer.split(/(\[?\d{1,2}:\d{2}\]?)/g);
  return parts.map((part, i) => {
    const cleanMatch = part.match(/\[?(\d{1,2}):(\d{2})\]?/);
    if (cleanMatch) {
      const minutes = parseInt(cleanMatch[1], 10);
      const seconds = parseInt(cleanMatch[2], 10);
      const totalSeconds = minutes * 60 + seconds;
      return (
        <button
          key={i}
          onClick={() => onSeek(totalSeconds)}
          title={`Seek to ${cleanMatch[1]}:${cleanMatch[2]}`}
          className="inline-flex items-center gap-1 rounded bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 px-1.5 mx-0.5 font-mono text-xs cursor-pointer transition-colors"
        >
          ▶ {cleanMatch[1]}:{cleanMatch[2]}
        </button>
      );
    }
    return <span key={i}>{part}</span>;
  });
}
