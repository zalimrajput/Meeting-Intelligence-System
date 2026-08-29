/* Demo data used when USE_MOCKS === true (no backend server running). */
import {
  Meeting,
  TranscriptSegment,
  ActionItem,
  Decision,
  KeyPoint,
  Issue,
  AllInsights,
  ChatMessage,
  DashboardStats,
  UpcomingDeadline,
  RecentDecision,
  RecentMeeting,
  GlobalSearchResult,
  User,
} from "./schemas";

export const MOCK_USER: User = {
  id: "u_demo",
  full_name: "Alex Carter",
  email: "alex@meetingmind.app",
  role: "USER",
  is_active: true,
  created_at: "2026-08-01T10:00:00Z",
};

const NOW = Date.now();
function daysAgo(n: number, h = 9): string {
  return new Date(NOW - n * 86400000).toISOString();
}
function daysAhead(n: number): string {
  return new Date(NOW + n * 86400000).toISOString().slice(0, 10);
}

export const MOCK_MEETINGS: Meeting[] = [
  {
    id: "m1",
    owner_id: "u_demo",
    title: "Q3 Product Launch Planning",
    meeting_date: daysAgo(1),
    duration_seconds: 42 * 60 + 15,
    status: "ready",
    summary_short: "Team aligned on September launch, budget set at $120k, and backend owner confirmed.",
    summary_detailed:
      "The team finalized the Q3 product launch date as September 1. The marketing budget was settled at $120,000 with paid ads as the primary channel. Ali finished the backend API by Friday, and Sara owns the homepage redesign. An internal risk around third-party email deliverability was raised and needs a follow-up.",
    sentiment: "positive",
    sentiment_score: 0.72,
    failure_reason: null,
    created_at: daysAgo(1),
    updated_at: daysAgo(1),
  },
  {
    id: "m2",
    owner_id: "u_demo",
    title: "Weekly Marketing Sync",
    meeting_date: daysAgo(3),
    duration_seconds: 25 * 60,
    status: "ready",
    summary_short: "Reviewed ad spend and agreed to reallocate budget to SEO.",
    summary_detailed:
      "The weekly sync reviewed ad spend against target CAC. The team decided to shift 20% of the small-platform budget toward SEO after strong early results.",
    sentiment: "neutral",
    sentiment_score: 0.1,
    failure_reason: null,
    created_at: daysAgo(3),
    updated_at: daysAgo(3),
  },
  {
    id: "m3",
    owner_id: "u_demo",
    title: "Design Review — Homepage Redesign",
    meeting_date: daysAgo(6),
    duration_seconds: 38 * 60 + 50,
    status: "complete",
    summary_short: "Approved homepage layout; accessibility copy still pending review.",
    summary_detailed: "",
    sentiment: "mixed",
    sentiment_score: 0.05,
    failure_reason: null,
    created_at: daysAgo(6),
    updated_at: daysAgo(6),
  },
];

export const MOCK_TRANSCRIPT: TranscriptSegment[] = [
  { id: "s1", meeting_id: "m1", speaker_id: "sp1", speaker_label: "Sara", segment_index: 0, start_time_seconds: 0, end_time_seconds: 14, text: "Good morning team. We should lock the launch date today and confirm the budget.", confidence: 0.96, created_at: daysAgo(1) },
  { id: "s2", meeting_id: "m1", speaker_id: "sp2", speaker_label: "Ali", segment_index: 1, start_time_seconds: 14, end_time_seconds: 29, text: "We should target September 1 for the launch. The backend will be ready by Friday.", confidence: 0.93, created_at: daysAgo(1) },
  { id: "s3", meeting_id: "m1", speaker_id: "sp1", speaker_label: "Sara", segment_index: 2, start_time_seconds: 30, end_time_seconds: 46, text: "So the product launch date is decided as September 1. I will complete the homepage by Friday.", confidence: 0.95, created_at: daysAgo(1) },
  { id: "s4", meeting_id: "m1", speaker_id: "sp3", speaker_label: "Maya", segment_index: 3, start_time_seconds: 46, end_time_seconds: 62, text: "For the marketing budget, we finalized the allocation at one hundred twenty thousand dollars.", confidence: 0.9, created_at: daysAgo(1) },
  { id: "s5", meeting_id: "m1", speaker_id: "sp2", speaker_label: "Ali", segment_index: 4, start_time_seconds: 63, end_time_seconds: 79, text: "Ali will finish the backend work by Friday, and we have an unresolved issue around email deliverability to follow up on.", confidence: 0.91, created_at: daysAgo(1) },
];

export const MOCK_KEY_POINTS: KeyPoint[] = [
  { id: "k1", meeting_id: "m1", point_text: "Launch date set for September 1.", timestamp_seconds: 20 },
  { id: "k2", meeting_id: "m1", point_text: "Marketing budget finalized at $120,000.", timestamp_seconds: 46 },
  { id: "k3", meeting_id: "m1", point_text: "Homepage redesign targets this Friday.", timestamp_seconds: 30 },
];

export const MOCK_ACTIONS: ActionItem[] = [
  { id: "a1", meeting_id: "m1", task_description: "Finish backend API by Friday", assigned_to: "Ali", deadline_raw_text: "Friday", deadline_date: daysAhead(2), status: "in_progress", timestamp_seconds: 63 },
  { id: "a2", meeting_id: "m1", task_description: "Complete homepage redesign", assigned_to: "Sara", deadline_raw_text: "Friday", deadline_date: daysAhead(2), status: "pending", timestamp_seconds: 39 },
  { id: "a3", meeting_id: "m1", task_description: "Prepare launch assets for September 1", assigned_to: "Maya", deadline_raw_text: "September 1", deadline_date: daysAhead(8), status: "pending", timestamp_seconds: 20 },
  { id: "a4", meeting_id: "m1", task_description: "Follow up on email deliverability", assigned_to: "Alex", deadline_raw_text: "Next Monday", deadline_date: daysAhead(4), status: "overdue", timestamp_seconds: 79 },
];

export const MOCK_DECISIONS: Decision[] = [
  { id: "d1", meeting_id: "m1", decision_text: "Product launch date is September 1.", decided_by: "group", timestamp_seconds: 20 },
  { id: "d2", meeting_id: "m1", decision_text: "Marketing budget finalized at $120,000.", decided_by: "group", timestamp_seconds: 46 },
  { id: "d3", meeting_id: "m1", decision_text: "Homepage delivered by Friday.", decided_by: "Sara", timestamp_seconds: 39 },
];

export const MOCK_ISSUES: Issue[] = [
  { id: "i1", meeting_id: "m1", issue_text: "Third-party email deliverability risk unresolved.", timestamp_seconds: 79 },
  { id: "i2", meeting_id: "m1", issue_text: "Pricing page accessibility copy still pending review.", timestamp_seconds: 82 },
];

export const MOCK_INSIGHTS: AllInsights = {
  summary_short: MOCK_MEETINGS[0]!.summary_short,
  summary_detailed: MOCK_MEETINGS[0]!.summary_detailed,
  sentiment: "positive",
  sentiment_score: 0.72,
  key_points: MOCK_KEY_POINTS,
  action_items: MOCK_ACTIONS,
  decisions: MOCK_DECISIONS,
  unresolved_issues: MOCK_ISSUES,
};

export const MOCK_CHAT: ChatMessage[] = [
  {
    id: "c1",
    meeting_id: "m1",
    user_id: "u_demo",
    question: "What did we decide about the marketing budget?",
    answer:
      "The marketing budget was finalized at $120,000. (See the 46-second mark of the meeting.)",
    referenced_timestamp_seconds: 46,
    created_at: daysAgo(1),
  },
];

export const MOCK_DASHBOARD_STATS: DashboardStats = {
  total_meetings: 12,
  total_duration_seconds: 6 * 3600 + 25 * 60,
  total_duration_minutes: 385,
  total_hours_formatted: "6.4 hrs",
  total_decisions: 18,
  action_items: { total: 9, pending: 4, in_progress: 2, completed: 2, overdue: 1 },
  sentiment: { positive: 5, neutral: 6, negative: 0, mixed: 1 },
};

export const MOCK_DEADLINES: UpcomingDeadline[] = [
  { id: "dl1", meeting_id: "m1", meeting_title: "Q3 Product Launch Planning", description: "Finish backend API", raw_text: "Friday", resolved_date: daysAhead(2), timestamp_seconds: 63, created_at: daysAgo(1) },
  { id: "dl2", meeting_id: "m1", meeting_title: "Q3 Product Launch Planning", description: "Complete homepage redesign", raw_text: "Friday", resolved_date: daysAhead(2), timestamp_seconds: 39, created_at: daysAgo(1) },
  { id: "dl3", meeting_id: "m1", meeting_title: "Q3 Product Launch Planning", description: "Follow up on deliverability", raw_text: "Next Monday", resolved_date: daysAhead(4), timestamp_seconds: 79, created_at: daysAgo(1) },
];

export const MOCK_RECENT_DECISIONS: RecentDecision[] = MOCK_DECISIONS.map((d) => ({
  id: d.id,
  meeting_id: d.meeting_id || "m1",
  meeting_title: "Q3 Product Launch Planning",
  decision_text: d.decision_text,
  decided_by: d.decided_by,
  timestamp_seconds: d.timestamp_seconds,
  created_at: daysAgo(1),
}));

export const MOCK_RECENT_MEETINGS: RecentMeeting[] = MOCK_MEETINGS.map((m) => ({
  id: m.id,
  title: m.title,
  meeting_date: m.meeting_date,
  duration_seconds: m.duration_seconds || 0,
  status: m.status,
  summary_short: m.summary_short,
  sentiment: m.sentiment,
  sentiment_score: m.sentiment_score,
  action_items_count: m.id === "m1" ? 4 : 2,
  decisions_count: m.id === "m1" ? 3 : 1,
  created_at: m.created_at,
}));

export function mockSearch(q: string): GlobalSearchResult {
  const needle = q.toLowerCase();
  const meetings = MOCK_MEETINGS.filter((m) => m.title.toLowerCase().includes(needle)).map((m) => ({
    id: m.id,
    title: m.title,
    status: m.status,
    meeting_date: m.meeting_date,
  }));
  const transcripts = MOCK_TRANSCRIPT.filter((s) => s.text.toLowerCase().includes(needle)).map((s) => ({
    id: s.id,
    meeting_id: s.meeting_id,
    text: s.text,
    start_time_seconds: s.start_time_seconds,
    speaker_label: s.speaker_label,
  }));
  const action_items = MOCK_ACTIONS.filter((a) => (a.task_description + " " + (a.assigned_to || "")).toLowerCase().includes(needle)).map((a) => ({
    id: a.id,
    meeting_id: a.meeting_id,
    task_description: a.task_description,
    assigned_to: a.assigned_to,
    status: a.status,
  }));
  const decisions = MOCK_DECISIONS.filter((d) => d.decision_text.toLowerCase().includes(needle)).map((d) => ({
    id: d.id,
    meeting_id: d.meeting_id,
    decision_text: d.decision_text,
    timestamp_seconds: d.timestamp_seconds,
  }));
  return { query: q, total_matches: meetings.length + transcripts.length + action_items.length + decisions.length, meetings, transcripts, action_items, decisions };
}

