/* MeetingMind API client.
 *
 * USE_MOCKS === true  → returns demo data so the UI runs without a backend.
 * USE_MOCKS === false → calls the real FastAPI backend at NEXT_PUBLIC_API_BASE_URL.
 */
import {
  ApiEnvelope,
  ApiError,
  AuthData,
  Meeting,
  MeetingStatusResult,
  MeetingUploadResult,
  TranscriptSegment,
  AllInsights,
  ActionItem,
  ActionStatus,
  DashboardStats,
  UpcomingDeadline,
  RecentDecision,
  RecentMeeting,
  GlobalSearchResult,
  ChatMessage,
  User,
} from "./schemas";
import {
  MOCK_USER,
  MOCK_MEETINGS,
  MOCK_TRANSCRIPT,
  MOCK_INSIGHTS,
  MOCK_ACTIONS,
  MOCK_CHAT,
  MOCK_DASHBOARD_STATS,
  MOCK_DEADLINES,
  MOCK_RECENT_DECISIONS,
  MOCK_RECENT_MEETINGS,
  mockSearch,
} from "./mocks";

// Toggle mock mode: default to true only if NEXT_PUBLIC_USE_MOCKS is explicitly "true"
// or if no NEXT_PUBLIC_API_BASE_URL is provided in development.
export const USE_MOCKS =
  process.env.NEXT_PUBLIC_USE_MOCKS === "true" ||
  (process.env.NEXT_PUBLIC_USE_MOCKS !== "false" &&
    !process.env.NEXT_PUBLIC_API_BASE_URL);

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000/api/v1";

// ---- token persistence ----
export const TOKEN_KEYS = { access: "mm_access", refresh: "mm_refresh" };

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEYS.access);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEYS.refresh);
}

export function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEYS.access, access);
  window.localStorage.setItem(TOKEN_KEYS.refresh, refresh);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEYS.access);
  window.localStorage.removeItem(TOKEN_KEYS.refresh);
}

export function mediaUrl(meetingId: string): string {
  if (USE_MOCKS) return "";
  const token = getToken();
  return `${BASE}/meetings/${meetingId}/media${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

export function exportUrl(meetingId: string, format: string): string {
  if (USE_MOCKS) return "";
  const token = getToken();
  return `${BASE}/meetings/${meetingId}/export?format=${format}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function onRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      clearTokens();
      return null;
    }

    const json = await res.json();
    const newAccess = json.data?.access_token;
    const newRefresh = json.data?.refresh_token;

    if (newAccess && newRefresh) {
      setTokens(newAccess, newRefresh);
      return newAccess;
    }
    return null;
  } catch {
    clearTokens();
    return null;
  }
}

/* ---------- Real HTTP core (used only when USE_MOCKS === false) ---------- */
interface CustomRequestInit extends RequestInit {
  _retry?: boolean;
}

async function request<T>(path: string, init: CustomRequestInit = {}): Promise<T> {
  if (USE_MOCKS) throw new Error("request() should not be called in mock mode");

  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((init.headers as Record<string, string>) || {}),
  };

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  // Handle 401 Unauthorized with token refresh rotation
  if (res.status === 401 && !init._retry && getRefreshToken()) {
    if (!isRefreshing) {
      isRefreshing = true;
      const newToken = await refreshAccessToken();
      isRefreshing = false;
      if (newToken) {
        onRefreshed(newToken);
        return request<T>(path, { ...init, _retry: true });
      }
    } else {
      return new Promise<T>((resolve, reject) => {
        refreshSubscribers.push((newToken: string) => {
          request<T>(path, {
            ...init,
            _retry: true,
            headers: {
              ...(init.headers as Record<string, string>),
              Authorization: `Bearer ${newToken}`,
            },
          })
            .then(resolve)
            .catch(reject);
        });
      });
    }
  }

  let body: ApiEnvelope<T> | null = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON */
  }

  if (!res.ok) {
    const err = (body as { error?: { code: string; message: string; details?: Record<string, unknown> } })?.error;
    throw new ApiError(
      res.status,
      err?.code || "HTTP_ERROR",
      err?.message || `Request failed (${res.status})`,
      err?.details
    );
  }

  return body?.data as T;
}

/* ---------- typed public API ---------- */
export const api = {
  USE_MOCKS,

  // Auth
  async register(name: string, email: string, password: string): Promise<AuthData> {
    if (USE_MOCKS) {
      await delay(500);
      return {
        user: { ...MOCK_USER, full_name: name, email },
        tokens: {
          access_token: "mock_access",
          refresh_token: "mock_refresh",
          token_type: "bearer",
          expires_in: 900,
        },
      };
    }
    return request<AuthData>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ full_name: name, email, password }),
    });
  },

  async login(email: string, password: string): Promise<AuthData> {
    if (USE_MOCKS) {
      await delay(500);
      if (!email || !password) throw new Error("Email and password are required");
      const name = email.split("@")[0]!.replace(/[._-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      return {
        user: { ...MOCK_USER, full_name: name, email },
        tokens: {
          access_token: "mock_access",
          refresh_token: "mock_refresh",
          token_type: "bearer",
          expires_in: 900,
        },
      };
    }
    return request<AuthData>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async me(): Promise<User> {
    if (USE_MOCKS) return MOCK_USER;
    return request<User>("/users/me");
  },

  // Meetings
  async listMeetings(page = 1, limit = 20): Promise<Meeting[]> {
    if (USE_MOCKS) return MOCK_MEETINGS;
    const res = await request<Meeting[] | { items: Meeting[] }>(`/meetings?page=${page}&limit=${limit}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray((res as { items: Meeting[] }).items)) return (res as { items: Meeting[] }).items;
    return [];
  },

  async getMeeting(id: string): Promise<Meeting> {
    if (USE_MOCKS) return MOCK_MEETINGS.find((m) => m.id === id) || MOCK_MEETINGS[0]!;
    return request<Meeting>(`/meetings/${id}`);
  },

  async getMeetingStatus(id: string): Promise<MeetingStatusResult> {
    if (USE_MOCKS) {
      return {
        meeting_id: id,
        status: "ready",
        failure_reason: null,
        jobs: [
          {
            id: "j1",
            meeting_id: id,
            stage: "transcription",
            status: "completed",
            error_message: null,
            started_at: null,
            completed_at: null,
            created_at: "",
          },
        ],
      };
    }
    return request<MeetingStatusResult>(`/meetings/${id}/status`);
  },

  async uploadMeeting(file: File, title?: string, meetingDate?: string): Promise<MeetingUploadResult> {
    if (USE_MOCKS) {
      await delay(1500);
      const fileType = file.type.includes("video") ? "video" : "audio";
      const meeting = MOCK_MEETINGS[0]!;
      return {
        meeting,
        file: {
          id: "f1",
          meeting_id: meeting.id,
          file_type: fileType,
          original_filename: file.name,
          storage_path: "",
          format: file.name.split(".").pop() || "",
          size_bytes: file.size,
          checksum: "",
          uploaded_at: new Date().toISOString(),
        },
        job: {
          id: "j1",
          meeting_id: meeting.id,
          stage: "transcription",
          status: "queued",
          error_message: null,
          started_at: null,
          completed_at: null,
          created_at: new Date().toISOString(),
        },
      };
    }

    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    if (meetingDate) form.append("meeting_date", meetingDate);

    const token = getToken();
    const res = await fetch(`${BASE}/meetings`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });

    const body = await res.json();
    if (!res.ok) {
      throw new ApiError(
        res.status,
        body?.error?.code || "HTTP_ERROR",
        body?.error?.message || "Upload failed",
        body?.error?.details
      );
    }
    return body.data as MeetingUploadResult;
  },

  async deleteMeeting(id: string): Promise<void> {
    if (!USE_MOCKS) {
      await request(`/meetings/${id}`, { method: "DELETE" });
    }
  },

  // Transcript
  async getTranscript(meetingId: string, search?: string): Promise<TranscriptSegment[]> {
    if (USE_MOCKS) {
      const q = search?.toLowerCase();
      return q ? MOCK_TRANSCRIPT.filter((s) => s.text.toLowerCase().includes(q)) : MOCK_TRANSCRIPT;
    }
    return request<TranscriptSegment[]>(
      `/meetings/${meetingId}/transcript${search ? `?search=${encodeURIComponent(search)}` : ""}`
    );
  },

  // Insights
  async getInsights(meetingId: string): Promise<AllInsights> {
    if (USE_MOCKS) return MOCK_INSIGHTS;
    return request<AllInsights>(`/meetings/${meetingId}/insights`);
  },

  async listActions(meetingId: string): Promise<ActionItem[]> {
    if (USE_MOCKS) return MOCK_ACTIONS;
    return request<ActionItem[]>(`/meetings/${meetingId}/actions`);
  },

  async updateAction(
    meetingId: string,
    actionId: string,
    patch: { status?: ActionStatus; task_description?: string; deadline_date?: string }
  ): Promise<ActionItem> {
    if (USE_MOCKS) return MOCK_ACTIONS.find((a) => a.id === actionId)!;
    return request<ActionItem>(`/meetings/${meetingId}/actions/${actionId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  // Chat / Q&A
  async getChatHistory(meetingId: string): Promise<ChatMessage[]> {
    if (USE_MOCKS) return MOCK_CHAT;
    return request<ChatMessage[]>(`/meetings/${meetingId}/chat`);
  },

  async askQuestion(meetingId: string, question: string): Promise<ChatMessage> {
    if (USE_MOCKS) {
      await delay(800);
      return {
        id: "c2",
        meeting_id: meetingId,
        user_id: "u_demo",
        question,
        answer: `Here is the answer about "${question}". Reference: the marketing budget discussion is around the 46-second mark [00:46].`,
        referenced_timestamp_seconds: 46,
        created_at: new Date().toISOString(),
      };
    }
    const res = await request<ChatMessage>(`/meetings/${meetingId}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    return {
      id: res.id,
      meeting_id: res.meeting_id || meetingId,
      user_id: res.user_id || "",
      question: res.question || question,
      answer: res.answer || "",
      referenced_timestamp_seconds: res.referenced_timestamp_seconds ?? null,
      created_at: res.created_at || new Date().toISOString(),
    };
  },

  async askStream(
    meetingId: string,
    question: string,
    onToken: (token: string) => void
  ): Promise<ChatMessage> {
    if (USE_MOCKS) {
      const full = `Here is my answer about "${question}".`;
      for (const chunk of full.split(/(?<= )/)) {
        onToken(chunk);
        await delay(60);
      }
      return {
        id: "c3",
        meeting_id: meetingId,
        user_id: "u_demo",
        question,
        answer: full,
        referenced_timestamp_seconds: null,
        created_at: new Date().toISOString(),
      };
    }

    const token = getToken();
    const res = await fetch(`${BASE}/meetings/${meetingId}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question }),
    });

    const reader = res.body?.getReader();
    const decoder = new TextDecoder();
    let answer = "";

    while (reader) {
      const { value, done } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          try {
            const { token: t, referenced_timestamp_seconds } = JSON.parse(line.slice(6));
            if (typeof t === "string" && t.length) {
              answer += t;
              onToken(t);
            } else if (referenced_timestamp_seconds != null) {
              return {
                id: "c4",
                meeting_id: meetingId,
                user_id: "u_demo",
                question,
                answer,
                referenced_timestamp_seconds,
                created_at: new Date().toISOString(),
              };
            }
          } catch {
            /* skip malformed JSON chunk */
          }
        }
      }
    }

    return {
      id: "c4",
      meeting_id: meetingId,
      user_id: "u_demo",
      question,
      answer,
      referenced_timestamp_seconds: null,
      created_at: new Date().toISOString(),
    };
  },

  // Dashboard
  async dashboardStats(): Promise<DashboardStats> {
    if (USE_MOCKS) return MOCK_DASHBOARD_STATS;
    return request<DashboardStats>("/dashboard/stats");
  },

  async recentMeetings(limit = 10): Promise<RecentMeeting[]> {
    if (USE_MOCKS) return MOCK_RECENT_MEETINGS;
    return request<RecentMeeting[]>(`/dashboard/recent-meetings?limit=${limit}`);
  },

  async upcomingDeadlines(limit = 10): Promise<UpcomingDeadline[]> {
    if (USE_MOCKS) return MOCK_DEADLINES;
    return request<UpcomingDeadline[]>(`/dashboard/deadlines?limit=${limit}`);
  },

  async recentDecisions(limit = 10): Promise<RecentDecision[]> {
    if (USE_MOCKS) return MOCK_RECENT_DECISIONS;
    return request<RecentDecision[]>(`/dashboard/decisions?limit=${limit}`);
  },

  // Search
  async globalSearch(q: string, limit = 20): Promise<GlobalSearchResult> {
    if (USE_MOCKS) return mockSearch(q);
    return request<GlobalSearchResult>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  },
};
