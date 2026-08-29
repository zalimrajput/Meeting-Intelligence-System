# 🎙️ MeetingMind — Next.js Frontend

A production-style **Next.js 14 (App Router) + TypeScript + Tailwind** frontend for the
**MeetingMind AI Meeting Intelligence System**. It plugs into the FastAPI backend that already
ships with this platform, mirroring its real API contract exactly.

## Page Flow

```
Login ── Signup
        └── Dashboard (Recent Meetings · Processing Status · Action Items · Decisions · Deadlines)
              ├── Upload Meeting (Audio / Video)
              ├── Meeting Details (Overview · Transcript · AI Insights · Ask AI)
              └── Search Meetings
```

## Run it

```bash
npm install
cp .env.example .env.local        # set NEXT_PUBLIC_API_BASE_URL if your backend is up
npm run dev                       # http://localhost:3000
```

## Two modes

`lib/api.ts` exposes a `USE_MOCKS` flag:

- **Mock mode (default, no backend)** — `USE_MOCKS` is `true` unless you set
  `NEXT_PUBLIC_API_BASE_URL`. The UI runs on seeded demo data (`lib/mocks.ts`) so you can
  click through every page: login, dashboard, upload, meeting detail, ask AI, search — object
  through `lib/mocks.ts` replace `lib/api.ts` calls and everything works offline.
- **Live mode (backend connected)** — set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1`
  in `.env.local`. All `api.login`, `api.listMeetings`, `api.getInsights`, `api.askQuestion`,
  `api.globalSearch`, media streaming, and export calls hit the real FastAPI routes.

> Flip `USE_MOCKS` in `lib/api.ts` (or unset/set the env var) to switch.

## Backend contract implemented

The client types (`lib/schemas.ts`) mirror the FastAPI Pydantic schemas 1:1, and `lib/api.ts`
handles the `{ success, data, meta }` envelope, Bearer auth, HTTP Range media, action-item
PATCH, SSE Q&A streaming, and export downloads.

Endpoints referenced:

- `POST /auth/register` · `POST /auth/login` · `GET /users/me`
- `GET /meetings` · `POST /meetings` (multipart) · `GET /meetings/{id}` ·
  `GET /meetings/{id}/status` · `DELETE /meetings/{id}` · `GET /meetings/{id}/media`
- `GET /meetings/{id}/transcript` · `GET /meetings/{id}/insights` ·
  `GET|POST|PATCH|DELETE /meetings/{id}/actions`
- `POST /meetings/{id}/chat[ /stream]` · `GET /meetings/{id}/chat`
- `GET /dashboard/stats|deadlines|decisions|recent-meetings` · `GET /search`
- `GET /meetings/{id}/export`

## Layout

```
app/
  (auth)/login, (auth)/signup      auth pages on a split brand layout
  (dashboard)/ layout + pages       sidebar shell → dashboard, upload, meetings, [id], search
lib/
  schemas.ts  Pydantic-mirror types
  api.ts      typed client (auth / envelope / SSE / mocks fallback)
  mocks.ts    realistic demo data
  utils.ts    fmtClock, relative deadlines, status palettes
  auth-context.tsx   token + user provider
  logo.tsx    shared SVG logo mark
```
