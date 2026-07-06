# Claims Auditor API

FastAPI backend for **ClaimsAuditor AI** — an enterprise health-insurance claims auditing platform. It ingests policy documents, indexes them for semantic search, audits claim forms against policy rules using Gemini, and streams live progress to the dashboard over WebSockets.

## What it does

| Capability | Description |
|------------|-------------|
| **Policy ingestion** | Upload EOC/policy PDFs or DOCX; Docling extracts layout-aware Markdown; chunks are embedded and stored in pgvector |
| **Claim auditing** | Upload claim documents; Gemini compares claim vs policy and returns structured violations |
| **RAG chat** | Ask natural-language questions about an ingested policy using vector search + Gemini |
| **Real-time updates** | WebSocket streams pipeline steps (parsing, indexing, audit) to the UI |
| **User-scoped data** | JWT auth; policies, claims, and audits are isolated per user |

## Tech stack

- **FastAPI** + **Uvicorn** — HTTP API
- **SQLModel** / **SQLAlchemy** + **asyncpg** — async PostgreSQL
- **pgvector** — vector similarity search for RAG
- **Alembic** — database migrations
- **Google Gemini** (`google-genai`) — embeddings, claim audit, RAG answers
- **Docling Serve** — document-to-Markdown extraction (separate container)
- **JWT** (PyJWT) + **bcrypt** — authentication

## Prerequisites

- Docker and Docker Compose (recommended), **or**
- Python 3.12+, PostgreSQL 15 with pgvector, and a running Docling Serve instance

## Quick start (Docker — recommended)

### 1. Configure environment

Copy and edit the env file:

```bash
cp .env_docker .env_docker.local   # optional backup
```

Set these values in `.env_docker`:

```env
DB_USER=auditor_admin
DB_PASSWORD=password          # must match POSTGRES_PASSWORD in docker-compose.yml
DB_HOST=db
DB_PORT=5432
DB_NAME=claims_auditor_db

DOCLING_SERVICE_URL=http://docling_serve:5001/v1/convert/file
GEMINI_API_KEY=your-gemini-api-key
JWT_SECRET_KEY=your-long-random-secret

# UI origins allowed for CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

> **Important:** `DB_PASSWORD` must match `POSTGRES_PASSWORD` in `docker-compose.yml`.

### 2. Start all services

```bash
docker compose up -d --build
```

This starts:

| Service | Port | Role |
|---------|------|------|
| `api` | 8000 | FastAPI application |
| `db` | 5432 | PostgreSQL + pgvector |
| `docling_serve` | 8001 → 5001 | Document extraction |

Migrations run automatically on API startup (`alembic upgrade head`).

### 3. Verify

```bash
curl http://localhost:8000/health
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Create a user

```bash
curl -X POST http://localhost:8000/user/enroll \
  -H "Content-Type: application/json" \
  -d '{"username":"auditor1","password":"changeme","role":"AUDITOR"}'
```

## Local development (without Docker)

### 1. Install dependencies

Uses [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

### 2. Run PostgreSQL + Docling

Start Postgres with pgvector and Docling Serve separately, or use Docker for only those services:

```bash
docker compose up -d db docling_serve
```

### 3. Configure `.env_docker` (or export env vars)

Point `DB_HOST=localhost` and `DOCLING_SERVICE_URL=http://localhost:8001/v1/convert/file`.

### 4. Migrate and run

```bash
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Main API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/login` | Get JWT access token |
| `POST` | `/user/enroll` | Register a user |
| `GET` | `/user/me` | Current user profile |
| `POST` | `/api/v1/ingestion/policy/` | Upload & ingest a policy |
| `GET` | `/api/v1/ingestion/policy/` | List ingested policies |
| `POST` | `/api/v1/ingestion/claim/` | Submit a claim for audit |
| `GET` | `/api/v1/ingestion/claim/` | List completed audits |
| `GET` | `/api/v1/ingestion/claim/{id}` | Get full audit report |
| `POST` | `/api/v1/chat/query` | RAG Q&A on a policy |
| `WS` | `/ws/{tracking_id}?token=...` | Live pipeline events |

All ingestion and chat routes require `Authorization: Bearer <token>`.

## Project layout

```
claims-auditor-api/
├── main.py                 # FastAPI app entry point
├── config/                 # Settings, DB, auth
├── routes/                 # HTTP + WebSocket routers
├── models/                 # SQLModel tables & DTOs
├── repositories/           # Database access layer
├── services/               # Docling extraction
├── rag_engine/             # Embeddings & chunking
├── auditor/                # Gemini claim audit logic
├── ws_manager/             # WebSocket connection manager
├── alembic/                # DB migrations
└── doc/                    # Architecture documentation
```

## Architecture

See [doc/architecture.md](doc/architecture.md) for a full system overview, component map, and data-flow diagrams.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_USER` | `auditor_admin` | PostgreSQL user |
| `DB_PASSWORD` | — | PostgreSQL password |
| `DB_HOST` | `localhost` | Database host |
| `DB_PORT` | `5432` | Database port |
| `DB_NAME` | `claims_auditor_db` | Database name |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `GEMINI_EMBEDDING_DIMENSION` | `3072` | Vector dimension |
| `JWT_SECRET_KEY` | — | Secret for signing JWTs |
| `DOCLING_SERVICE_URL` | — | Docling file conversion URL |
| `CORS_ORIGINS` | localhost URLs | Comma-separated allowed origins |

## Common commands

```bash
# View logs
docker compose logs -f api

# Run migrations manually
docker compose exec api alembic upgrade head

# Reset database (destructive)
docker compose down -v && docker compose up -d

# Stop everything
docker compose down
```

## Connecting the UI

Start the [claims-auditor-ui](https://github.com/gowtham943/claims-auditor-ui/) dashboard and point it at `http://localhost:8000`. Ensure `CORS_ORIGINS` includes your UI URL (e.g. `http://localhost:3000`).
