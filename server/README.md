# 🎙️ MeetingMind Backend — Production API & AI Intelligence Platform

MeetingMind is an enterprise AI meeting intelligence engine built on **FastAPI (async Python 3.11+)**, **PostgreSQL (Supabase)**, **DeepGram Nova-3**, and **Google Gemini 2.5 Flash**.

---

## 🚀 Quick Start Guide

### 1. Local Environment Setup

#### Prerequisites:
- Python 3.11 or newer
- FFmpeg (for video-to-audio extraction)

```bash
# Navigate to server directory
cd server

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in DATABASE_URL, DEEPGRAM_API_KEY, and GEMINI_API_KEY
```

#### Run the API Server:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

---

### 2. Docker Compose Deployment (Recommended)

To run the complete production multi-container stack (API, Redis broker, background worker):

```bash
docker-compose up --build -d
```

---

## 📖 API Documentation

Once the server is running, explore the interactive documentation:
- **Interactive Swagger UI**: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)
- **Alternative ReDoc UI**: [http://127.0.0.1:8001/redoc](http://127.0.0.1:8001/redoc)
- **OpenAPI JSON Schema**: [http://127.0.0.1:8001/openapi.json](http://127.0.0.1:8001/openapi.json)
- **Health Check**: `GET /api/v1/health`

---

## 🧪 Testing Suites

### 1. White-Box Tests (Internal Unit & Cryptographic Logic)
```bash
python run_whitebox_tests.py
```
Validates BCrypt password hashing, JWT cryptographic signature verification & expiration, timestamp boundary formats (`format_seconds`), magic-byte inspection, and exception envelopes.

### 2. Black-Box Tests (External Integration & Multi-Tenant Security)
```bash
python run_blackbox_tests.py
```
Validates HTTP endpoints, standard `{ success, data, meta, error }` envelopes, media streaming (`HTTP 206 Partial Content`), and multi-tenant security boundaries (403 Forbidden).

### 3. Full Repository Test Suite
```bash
pytest -v
```

---

## 🤝 Frontend Integration Guide (Next.js)

### Base URL:
`http://localhost:8001/api/v1`

### Authentication:
All protected routes require standard Bearer token in the `Authorization` header:
```http
Authorization: Bearer <access_token>
```

### Standard Response Envelope:
All JSON responses strictly follow:
```json
{
  "success": true,
  "data": { ... },
  "meta": { ... }
}
```

Error responses:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

---

## 📑 Key Endpoints for Frontend Teammate

| Feature | Method | Endpoint | Description |
| :--- | :---: | :--- | :--- |
| **Register** | `POST` | `/auth/register` | Register new user |
| **Login** | `POST` | `/auth/login` | Login and receive tokens |
| **Current User** | `GET` | `/users/me` | Fetch user profile |
| **Upload Audio** | `POST` | `/meetings` | Multipart file upload (`file`, `title`) |
| **List Meetings** | `GET` | `/meetings` | Paginated meeting list |
| **Meeting Details**| `GET` | `/meetings/{id}` | Summary, sentiment, keypoints, actions, decisions |
| **Stream Media** | `GET` | `/meetings/{id}/media` | HTTP Range 206 audio streaming for scrub bar |
| **Transcripts** | `GET` | `/meetings/{id}/transcript` | Diarized segments (`?search=query` filter) |
| **Action Items** | `PATCH`| `/meetings/{id}/actions/{action_id}` | Update status (`pending`, `completed`), deadline, task |
| **Create Action** | `POST` | `/meetings/{id}/actions` | Manually add an action item |
| **Delete Action** | `DELETE`| `/meetings/{id}/actions/{action_id}` | Remove action item |
| **Meeting Q&A** | `POST` | `/meetings/{id}/chat` | Ask questions over transcript with citations |
| **SSE Stream Q&A**| `POST` | `/meetings/{id}/chat/stream` | Server-Sent Events stream for AI typing effect |
| **Dashboard Stats**| `GET` | `/dashboard/stats` | Aggregated counts, duration, and sentiment |
| **Deadlines** | `GET` | `/dashboard/deadlines` | Upcoming deadlines widget |
| **Decisions** | `GET` | `/dashboard/decisions` | Recent decisions widget |
| **Global Search** | `GET` | `/search?q={query}` | Search across titles, transcripts, actions, decisions |
| **Export Report** | `GET` | `/meetings/{id}/export?format=markdown\|json\|email\|text` | Download formatted meeting report |
