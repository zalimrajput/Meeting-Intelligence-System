/* MeetingMind — Backend schema types (mirrors FastAPI Pydantic schemas exactly). */

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  meta?: Record<string, unknown> | null;
}

export interface ApiErrorBody {
  success: false;
  error: { code: string; message: string; details?: Record<string, unknown> };
}

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/* ---------- Auth ---------- */
export interface User {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthData {
  user: User;
  tokens: Tokens;
}

/* ---------- Meetings ---------- */
export type MeetingStatus = "uploading" | "processing" | "ready" | "complete" | "failed";

export interface Meeting {
  id: string;
  owner_id: string;
  title: string;
  meeting_date: string | null;
  duration_seconds: number | null;
  status: MeetingStatus | string;
  summary_short: string | null;
  summary_detailed: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingFile {
  id: string;
  meeting_id: string;
  file_type: string;
  original_filename: string;
  storage_path: string;
  format: string;
  size_bytes: number;
  checksum: string;
  uploaded_at: string;
}

export interface ProcessingJob {
  id: string;
  meeting_id: string;
  stage: string;
  status: "queued" | "running" | "completed" | "failed";
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface MeetingUploadResult {
  meeting: Meeting;
  file: MeetingFile;
  job: ProcessingJob;
}

export interface MeetingStatusResult {
  meeting_id: string;
  status: string;
  failure_reason: string | null;
  jobs: ProcessingJob[];
}

/* ---------- Transcript ---------- */
export interface TranscriptSegment {
  id: string;
  meeting_id: string;
  speaker_id: string | null;
  speaker_label: string | null;
  segment_index: number;
  start_time_seconds: number;
  end_time_seconds: number;
  text: string;
  confidence: number | null;
  created_at: string;
}

/* ---------- Insights ---------- */
export type ActionStatus = "pending" | "in_progress" | "completed" | "overdue";

export interface KeyPoint {
  id: string;
  meeting_id?: string;
  point_text: string;
  timestamp_seconds: number | null;
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  task_description: string;
  assigned_to: string | null;
  deadline_raw_text: string | null;
  deadline_date: string | null;
  status: ActionStatus | string;
  timestamp_seconds: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface Decision {
  id: string;
  meeting_id?: string;
  decision_text: string;
  decided_by: string | null;
  timestamp_seconds: number | null;
}

export interface Issue {
  id: string;
  meeting_id?: string;
  issue_text: string;
  timestamp_seconds: number | null;
}

export interface AllInsights {
  summary_short: string | null;
  summary_detailed: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  key_points: KeyPoint[];
  action_items: ActionItem[];
  decisions: Decision[];
  unresolved_issues: Issue[];
}

/* ---------- Chat / Q&A ---------- */
export interface ChatMessage {
  id: string;
  meeting_id: string;
  user_id: string;
  question: string;
  answer: string;
  referenced_timestamp_seconds: number | null;
  created_at: string;
}

/* ---------- Dashboard ---------- */
export interface ActionStats {
  total: number;
  pending: number;
  in_progress: number;
  completed: number;
  overdue: number;
}

export interface SentimentBreakdown {
  positive: number;
  neutral: number;
  negative: number;
  mixed: number;
}

export interface DashboardStats {
  total_meetings: number;
  total_duration_seconds: number;
  total_duration_minutes: number;
  total_hours_formatted: string;
  total_decisions: number;
  action_items: ActionStats;
  sentiment: SentimentBreakdown;
}

export interface UpcomingDeadline {
  id: string;
  meeting_id: string;
  meeting_title: string;
  description: string;
  raw_text: string | null;
  resolved_date: string | null;
  timestamp_seconds: number | null;
  created_at: string;
}

export interface RecentDecision {
  id: string;
  meeting_id: string;
  meeting_title: string;
  decision_text: string;
  decided_by: string | null;
  timestamp_seconds: number | null;
  created_at: string;
}

export interface RecentMeeting {
  id: string;
  title: string;
  meeting_date: string | null;
  duration_seconds: number;
  status: string;
  summary_short: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  action_items_count: number;
  decisions_count: number;
  created_at: string;
}

export interface GlobalSearchResult {
  query: string;
  total_matches: number;
  meetings: Array<Record<string, unknown>>;
  transcripts: Array<Record<string, unknown>>;
  action_items: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
}

/* ---------- Misc ---------- */
export interface PagedMeetings {
  items: Meeting[];
  total: number;
  page: number;
  limit: number;
}
