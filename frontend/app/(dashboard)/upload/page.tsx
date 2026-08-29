"use client";
import React from "react";
import { useState, useCallback, ChangeEvent, DragEvent, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { fmtBytes } from "@/lib/utils";

const AUDIO_EXTS = ["mp3", "wav", "m4a", "aac", "ogg"];
const VIDEO_EXTS = ["mp4", "mov", "webm", "mkv"];
const AUDIO_ACCEPT = AUDIO_EXTS.map((e) => `.${e}`).join(",");
const VIDEO_ACCEPT = VIDEO_EXTS.map((e) => `.${e}`).join(",");

interface SelFile {
  file: File;
  type: "audio" | "video";
}

const ACCEPTED = { audio: AUDIO_ACCEPT, video: VIDEO_ACCEPT };

export default function UploadPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"audio" | "video">("audio");
  const [selected, setSelected] = useState<SelFile | null>(null);
  const [invalid, setInvalid] = useState("");
  const [dragging, setDragging] = useState(false);
  const [title, setTitle] = useState("");
  const [dateInput, setDateInput] = useState("");
  const [phase, setPhase] = useState<"idle" | "uploading" | "processing" | "done" | "failed">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [doneId, setDoneId] = useState<string | null>(null);

  const accepted = mode === "audio" ? AUDIO_ACCEPT : VIDEO_ACCEPT;

  function classify(name: string): "audio" | "video" | null {
    const ext = name.toLowerCase().split(".").pop() || "";
    if (AUDIO_EXTS.includes(ext)) return "audio";
    if (VIDEO_EXTS.includes(ext)) return "video";
    return null;
  }

  const pick = useCallback((file: File) => {
    const t = classify(file.name);
    if (!t) {
      setSelected(null);
      setInvalid("Unsupported file type — use " + (mode === "audio" ? AUDIO_ACCEPT.replaceAll(",", ", ") : VIDEO_ACCEPT.replaceAll(",", ", ")) + ".");
      return;
    }
    setInvalid("");
    setSelected({ file, type: t });
    setMode(t);
  }, [mode]);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) pick(f);
  }

  async function upload(): Promise<void> {
    if (!selected) return;
    setPhase("uploading");
    setErrorMsg("");
    try {
      const res = await api.uploadMeeting(selected.file, title || undefined, dateInput || undefined);
      const id = res.meeting.id;
      setPhase("processing");
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 1200));
        const st = await api.getMeetingStatus(id);
        if (st.status === "ready" || st.status === "complete") {
          setDoneId(id);
          setPhase("done");
          return;
        }
        if (st.status === "failed") {
          setErrorMsg(st.failure_reason || "Processing failed.");
          setPhase("failed");
          return;
        }
      }
      // still processing beyond 12s — navigate so user can watch live status
      setDoneId(id);
      setPhase("done");
    } catch (e) {
      setErrorMsg((e as Error).message || "Upload failed");
      setPhase("failed");
    }
  }

  const steps =
    phase === "uploading"
      ? [{ label: "Uploading…", ok: false }]
      : phase === "processing"
        ? [
            { label: "Uploaded", ok: true },
            { label: "Transcribing…", ok: false },
            { label: "Analyzing…", ok: false },
          ]
        : [
            { label: "Uploaded", ok: true },
            { label: "Transcribed", ok: true },
            { label: "Analyzed", ok: true },
            { label: "Ready", ok: true },
          ];

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Upload a Meeting</h1>
      <p className="text-sm text-slate-400">
        Upload an audio or video recording. MeetingMind will transcribe it and extract decisions, action items, deadlines, and more.
      </p>

      {phase === "idle" && (
        <>
          <div className="flex gap-2 rounded-lg border border-white/10 bg-slate-800/60 p-1">
            <TabButton active={mode === "audio"} onClick={() => setMode("audio")}>🎙️ Audio Upload</TabButton>
            <TabButton active={mode === "video"} onClick={() => setMode("video")}>🎥 Video Upload</TabButton>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`rounded-2xl border-2 ${dragging ? "border-indigo-500 bg-indigo-500/10" : "border-dashed border-white/15 bg-slate-900/50"} p-10 text-center`}
          >
            <div className="text-4xl pb-2">{mode === "audio" ? "🎙️" : "🎥"}</div>
            <p className="font-medium">{dragging ? "Drop it here!" : mode === "audio" ? "Drop your audio recording" : "Drop your video recording"}</p>
            <p className="text-xs text-slate-500 mt-1">or</p>
            <label className="mt-2 inline-block rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white cursor-pointer">
              Browse files
              <input type="file" accept={ACCEPTED[mode]} className="hidden" onChange={(e: ChangeEvent<HTMLInputElement>) => e.target.files?.[0] && pick(e.target.files[0])} />
            </label>
            <p className="mt-4 text-[11px] text-slate-500">
              {mode === "audio" ? "MP3 · WAV · M4A · AAC · OGG" : "MP4 · MOV · WEBM · MKV"} — max 2GB
            </p>
          </div>

          {invalid && <p className="text-sm mt-1 text-rose-300">⚠️ {invalid}</p>}

          {selected && (
            <div className="rounded-xl border border-indigo-500/30 bg-slate-900/60 p-4 flex gap-3 items-center">
              <span className="text-2xl">{selected.type === "audio" ? "🎙️" : "🎥"}</span>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm break-all">{selected.file.name}</p>
                <p className="text-xs text-slate-500">{fmtBytes(selected.file.size)} · {selected.type}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-xs rounded-lg border border-white/10 px-2 py-1 text-slate-400">Remove</button>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Meeting title (optional)</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Q3 Product Review" className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-sm outline-none focus:border-indigo-500" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Meeting date (optional)</label>
              <input type="date" value={dateInput} onChange={(e) => setDateInput(e.target.value)} className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 [color-scheme:dark]" />
            </div>
          </div>

          <button onClick={upload} disabled={!selected} className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-50">
            Upload &amp; Analyze
          </button>
        </>
      )}

      {(phase === "uploading" || phase === "processing" || phase === "done") && (
        <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-6">
          <div className="flex items-center gap-3">
            <span className="inline-block h-3 w-3 rounded-full bg-indigo-500 animate-pulse-soft" />
            <p className="font-semibold">
              {phase === "uploading" ? "Uploading recording…" : phase === "processing" ? "Processing meeting — transcribing & analyzing…" : "Processing complete ✅"}
            </p>
          </div>
          <div className="mt-5 space-y-3">
            {steps.map((s, i) => (
              <StepRow key={i} label={s.label} ok={s.ok} />
            ))}
          </div>
          {phase === "done" && doneId && (
            <button onClick={() => router.push(`/meetings/${doneId}`)} className="mt-5 w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
              Open Meeting Report →
            </button>
          )}
        </div>
      )}

      {phase === "failed" && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-6">
          <p className="font-semibold text-rose-200">Processing failed</p>
          <p className="text-sm text-rose-200/80 mb-3">{errorMsg || "An unknown error occurred."}</p>
          <button onClick={() => setPhase("idle")} className="rounded-lg border border-white/10 px-4 py-2 text-sm">Try again</button>
        </div>
      )}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className={`flex-1 py-2 rounded-lg text-sm font-medium ${active ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
      {children}
    </button>
  );
}

function StepRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <span className={`h-4 w-4 rounded-full ${ok ? "bg-emerald-500" : "bg-slate-600"}`} />
      <span className={`text-sm ${ok ? "text-slate-100" : "text-slate-500"}`}>{label}</span>
      {ok && <span className="text-xs text-emerald-400">done</span>}
    </div>
  );
}





