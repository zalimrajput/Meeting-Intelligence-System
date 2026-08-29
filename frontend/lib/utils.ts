/* Shared formatting/helper utilities. */

export function fmtClock(totalSeconds: number): string {
  if (!isFinite(totalSeconds) || totalSeconds < 0) return "00:00";
  const s = Math.floor(totalSeconds % 60);
  const m = Math.floor((totalSeconds / 60) % 60);
  const h = Math.floor(totalSeconds / 3600);
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function fmtMinutes(totalSeconds: number | null | undefined): string {
  if (!totalSeconds) return "—";
  const m = Math.round(totalSeconds / 60);
  if (m < 60) return `${m} min`;
  const h = (m / 60).toFixed(1);
  return `${h} hr`;
}

export function fmtBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return fmtDate(iso);
}

/** Relative "in X days" for a deadline date. Negative => "X days overdue". */
export function relativeDeadline(dateIso: string | null): { label: string; overdue: boolean } {
  if (!dateIso) return { label: "", overdue: false };
  const target = new Date(`${dateIso}T00:00:00`).getTime();
  if (isNaN(target)) return { label: fmtDate(dateIso), overdue: false };
  const days = Math.round((target - Date.now()) / 86400000);
  if (days < 0) return { label: `${Math.abs(days)}d overdue`, overdue: true };
  if (days === 0) return { label: "today", overdue: false };
  if (days === 1) return { label: "tomorrow", overdue: false };
  return { label: `in ${days} days`, overdue: false };
}

export function statusPalette(status: string): { dot: string; text: string; chip: string } {
  switch (status) {
    case "ready":
    case "complete":
    case "completed":
      return { dot: "bg-emerald-400", text: "text-emerald-300", chip: "bg-emerald-500/15 border-emerald-500/30" };
    case "processing":
    case "uploading":
    case "in_progress":
      return { dot: "bg-amber-400 animate-pulse-soft", text: "text-amber-300", chip: "bg-amber-500/15 border-amber-500/30" };
    case "queued":
      return { dot: "bg-sky-400", text: "text-sky-300", chip: "bg-sky-500/15 border-sky-500/30" };
    case "failed":
    case "overdue":
      return { dot: "bg-rose-400", text: "text-rose-300", chip: "bg-rose-500/15 border-rose-500/30" };
    default:
      return { dot: "bg-slate-400", text: "text-slate-300", chip: "bg-slate-500/15 border-slate-500/30" };
  }
}

export function titleCase(status: string): string {
  if (!status) return "";
  return status.replace(/[_|-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export const SPEAKER_COLORS = [
  "bg-indigo-500",
  "bg-violet-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-sky-500",
  "bg-rose-500",
  "bg-teal-500",
  "bg-fuchsia-500",
];

export function speakerColor(label: string | null): string {
  if (!label) return SPEAKER_COLORS[0];
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) % 997;
  return SPEAKER_COLORS[hash % SPEAKER_COLORS.length];
}
