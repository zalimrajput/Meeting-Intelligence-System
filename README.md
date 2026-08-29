# MeetingMind - AI Meeting Intelligence Platform

An AI-powered meeting intelligence platform that automatically transcribes, analyzes, and extracts insights from meeting recordings using Deepgram (speech-to-text) and Gemini (AI analysis).

---

## 🚀 Quick Start — Command Reference

### Option A: With Docker (Recommended)

| # | Step | Command |
|---|------|---------|
| 1 | Clone repository | `git clone https://github.com/zalimrajput/Meeting-Intelligence-System.git` |
| 2 | Enter project folder | `cd Meeting-Intelligence-System/server` |
| 3 | Create env file | `cp .env.example .env` |
| 4 | Edit `.env` with your API keys | `DEEPGRAM_API_KEY`, `GEMINI_API_KEY` |
| 5 | **Start everything (first time)** | `docker compose up --build -d` |
| 6 | Wait ~30 seconds, then verify | `docker compose ps` |
| 7 | Start frontend | `cd ../frontend && npm install && npm run dev` |
| 8 | Open in browser | `http://localhost:3000` |

> **Subsequent starts:** `docker compose up -d` (no `--build` needed)

---

### Option B: Without Docker (Manual Setup)

| # | Step | Command |
|---|------|---------|
| 1 | Clone repository | `git clone https://github.com/zalimrajput/Meeting-Intelligence-System.git` |
| 2 | Enter server folder | `cd Meeting-Intelligence-System/server` |
| 3 | Create virtual environment | `python -m venv venv` |
| 4 | Activate venv | `source venv/bin/activate` *(Windows: `venv\Scripts\activate`)* |
| 5 | Install Python dependencies | `pip install -r requirements.txt` |
| 6 | Create env file | `cp .env.example .env` |
| 7 | Edit `.env` — set `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/meetingmind` |
| 8 | Edit `.env` — set `REDIS_URL` | `redis://localhost:6379` |
| 9 | Edit `.env` — set API keys | `DEEPGRAM_API_KEY`, `GEMINI_API_KEY` |
| 10 | Run database migrations | `alembic upgrade head` |
| 11 | Start API server *(terminal 1)* | `uvicorn app.main:app --reload --port 8000` |
| 12 | Start worker *(terminal 2)* | `python run_worker.py` |
| 13 | Enter frontend folder | `cd ../frontend` |
| 14 | Install Node.js dependencies | `npm install` |
| 15 | Start frontend dev server | `npm run dev` |
| 16 | Open in browser | `http://localhost:3000` |

---

## 🐳 All Docker Commands

| Command | Description |
|---------|-------------|
| `docker compose up --build -d` | **First time** — build images + start all services |
| `docker compose up -d` | Start services (images already built) |
| `docker compose down` | Stop all services |
| `docker compose ps` | Check status of running containers |
| `docker compose logs -f api` | View API logs (real-time) |
| `docker compose logs -f worker` | View worker logs |
| `docker compose build --no-cache` | Rebuild images from scratch |
| `docker compose exec api alembic upgrade head` | Run database migrations manually |

---

## 🗄️ Database Commands

| Command | Description |
|---------|-------------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Rollback one migration |
| `alembic downgrade base` | Rollback all migrations (reset DB) |
| `alembic current` | Show current migration version |
| `alembic history` | View migration history |
| `alembic revision --autogenerate -m "msg"` | Generate new migration |

> **Docker users:** prefix with `docker compose exec api` — e.g. `docker compose exec api alembic upgrade head`

---

## 🔐 Environment Variables

Create `server/.env` from `server/.env.example`:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `DEEPGRAM_API_KEY` | ✅ | Deepgram API key for speech-to-text |
| `GEMINI_API_KEY` | ✅ | Google Gemini API key for AI analysis |
| `JWT_SECRET` | ✅ | Secret key for JWT tokens (min 32 chars) |
| `STORAGE_DRIVER` | ❌ | `s3` or `local` (default: `s3`) |

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Next.js 15    │────▶│   FastAPI Server  │────▶│   PostgreSQL    │
│   Frontend      │     │   (API + Worker)  │     │   Database      │
│   :3000         │     │   :8000           │     │   :5432         │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │       │
                              ▼       ▼
                        ┌──────┐   ┌────────┐
                        │Redis │   │ S3/Local│
                        │Queue │   │Storage  │
                        └──────┘   └────────┘
```

---

## 📚 API Documentation

Once the server is running:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `Failed to fetch` on login | Backend not running — run `docker compose up -d` |
| `relation does not exist` | Run migrations: `alembic upgrade head` |
| `email-validator not installed` | Rebuild: `docker compose build --no-cache` |
| Frontend shows "Alex" instead of you | Create `frontend/.env.local` with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` and `NEXT_PUBLIC_USE_MOCKS=false` |
| Docker build timeout | Run `docker compose build --no-cache` |
| Port 5432/6379 already in use | Stop local PostgreSQL/Redis, or change ports in `docker-compose.yml` |

---

## 📁 Project Structure

```
Meeting-Intelligence-System/
├── frontend/              # Next.js 15 frontend
│   ├── app/              # App router (auth, dashboard pages)
│   ├── components/       # Reusable UI components
│   └── lib/              # API client, auth context, utils
│
├── server/               # FastAPI backend
│   ├── app/core/         # Config, database, security
│   ├── app/modules/      # Feature modules (auth, meetings, QA)
│   ├── app/services/     # Deepgram, Gemini, queue services
│   ├── alembic/          # Database migrations
│   ├── tests/            # Test suite
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── requirements.txt
│
└── README.md
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
