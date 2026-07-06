# Claims Auditor — System Architecture

This document explains how the **ClaimsAuditor AI** platform fits together in simple terms. It covers the API backend, supporting services, and how the React UI connects to them.

---

## High-level overview

ClaimsAuditor AI helps insurance auditors:

1. **Ingest** a master policy document (Evidence of Coverage).
2. **Index** it for semantic search (RAG).
3. **Upload** operational claim forms.
4. **Audit** each claim against the policy using AI.
5. **Review** results and ask follow-up questions about the policy.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Claims Auditor UI (React)                       │
│  Policy Ingestion │ Claims Desk │ Audit Console │ RAG Chat              │
└────────────┬───────────────────────────────┬────────────────────────────┘
             │ REST (JWT)                   │ WebSocket (JWT ?token=)
             ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Claims Auditor API (FastAPI)                       │
│  Auth │ Policy Ingestion │ Claim Ingestion │ RAG Chat │ WebSocket       │
└────┬──────────────┬─────────────────┬──────────────┬───────────────────┘
     │              │                 │              │
     ▼              ▼                 ▼              ▼
┌─────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐
│PostgreSQL│  │Docling Serve│  │ Google Gemini │  │ Background Workers  │
│+ pgvector│  │ (Markdown)  │  │ (AI reasoning)│  │ (async pipelines)   │
└─────────┘  └─────────────┘  └──────────────┘  └─────────────────────┘
```

---

## Core user journeys

### Journey 1 — Policy ingestion

```
User uploads PDF/DOCX
        │
        ▼
API saves empty policy row (instant 202 response)
        │
        ▼
Background worker starts
        │
        ├──► Docling: file → clean Markdown
        ├──► RAG engine: split by headings → embed chunks (Gemini)
        ├──► PostgreSQL: save Markdown + vectors (pgvector)
        └──► WebSocket: PARSING_POLICY → VECTOR_INDEXING → SAVING_DATA → COMPLETED
```

**Why background workers?** Policy files can be large. Docling and embedding take time. The API responds immediately with a tracking ID; the UI watches progress over WebSocket.

### Journey 2 — Claim audit

```
User selects policy + uploads claim file
        │
        ▼
API saves claim row (PENDING) → 202 response
        │
        ▼
Background worker
        │
        ├──► Docling: claim file → Markdown
        ├──► Load master policy Markdown from DB
        ├──► Gemini (Claims Auditor): structured audit JSON
        ├──► Save audit report in claim_metadata
        └──► WebSocket: PARSING_CLAIM → COGNITIVE_AUDIT → COMPLETED
```

The audit result includes status (`APPROVED`, `FLAGGED_ANOMALY`, `DENIED`), dollar amounts, and a list of violations with policy citations.

### Journey 3 — RAG chat

```
User asks a question about a policy
        │
        ▼
Embed the question (Gemini embedding model)
        │
        ▼
pgvector: find 4 most similar policy chunks (L2 distance)
        │
        ▼
Gemini: answer using only retrieved chunks as context
        │
        ▼
Return answer + citations to UI
```

---

## API components

### `main.py` — Application entry point

Wires all routers, CORS, and database shutdown. This is where the FastAPI app is created and mounted.

### `config/` — Configuration & infrastructure

| File | Role |
|------|------|
| `config_setting.py` | Reads env vars (DB, Gemini, JWT, CORS) via Pydantic Settings |
| `database_config.py` | Async SQLAlchemy engine + session factory for PostgreSQL |
| `auth.py` | JWT validation dependency (`get_current_user`) |
| `security.py` | Password hashing utilities |

**In simple words:** `config` is the control panel — connection strings, API keys, and who is allowed to call what.

---

### `routes/` — HTTP and WebSocket endpoints

| Router | Prefix | What it does |
|--------|--------|--------------|
| `auth_route.py` | `/auth` | Login → JWT token |
| `user_route.py` | `/user` | Register user, get profile |
| `policy_ingestion.py` | `/api/v1/ingestion/policy` | Upload policy, list policies |
| `claim_ingestion.py` | `/api/v1/ingestion/claim` | Submit claim, list/view audits |
| `rag_chat.py` | `/api/v1/chat` | Policy Q&A |
| `websocket.py` | `/ws` | Real-time pipeline events |
| `health_Check.py` | `/health` | Liveness check |

**In simple words:** `routes` are the front door — each file handles one area of the product.

---

### `models/` — Database tables & request shapes

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | Auditor accounts (username, hashed password, role) |
| `PolicyRulebook` | `policy_rulebooks` | Ingested policy metadata + full Markdown |
| `PolicyChunk` | `policy_chunks` | Text chunks + 3072-dim embedding vectors |
| `ClaimSubmission` | `claim_submissions` | Claim uploads, status, audit payload in JSON |

DTOs in `schema.py` define API request/response shapes (create policy, audit summary, etc.).

**In simple words:** `models` describe what gets stored in the database and what the API sends/receives.

---

### `repositories/` — Database queries

| Repository | Responsibility |
|------------|----------------|
| `user_repo.py` | Find users by username |
| `policy_repo.py` | Save/update policies; list by user |
| `claim_repo.py` | Create claims; update status; list audit history |
| `rag_repository.py` | Save chunks; vector similarity search |

**In simple words:** repositories are the librarians — they know how to read and write data without putting SQL in every route.

---

### `services/` — External integrations

| Service | Role |
|---------|------|
| `docling_extraction_service.py` | Sends files to Docling Serve; returns normalized Markdown |
| `document_extraction_service.py` | Base interface for extraction backends |

**Docling flow:**
- Validates file type (PDF, DOCX, images) and size (25 MB cap)
- POSTs multipart file to Docling `/v1/convert/file`
- Cleans up noisy Markdown before storage

**In simple words:** services talk to outside tools so the rest of the app stays focused on business logic.

---

### `rag_engine/` — Vector indexing

| Piece | Role |
|-------|------|
| `policy_rag_engine.py` | Chunks Markdown by headings; calls Gemini embeddings; builds `PolicyChunk` rows |

**Chunking strategy:** Split on `#` heading lines so each chunk keeps its section context (e.g. copays, referrals).

**Embeddings:** `gemini-embedding-001` at 3072 dimensions, stored in pgvector.

**In simple words:** the RAG engine turns a long policy document into searchable pieces the chat and search can use.

---

### `auditor/` — Claim compliance engine

| File | Role |
|------|------|
| `claims_auditor.py` | Sends policy + claim Markdown to Gemini with audit instructions |
| `audit_report_schema.py` | Expected JSON output shape |
| `violation_details.py` | Structure for each violation (rule, severity, citation) |

Uses **Gemini 2.5 Flash** with a strict system prompt (HMO referral checks, charge matching, citation requirements).

**In simple words:** the auditor is the AI compliance officer — it reads the policy and claim side by side and reports problems.

---

### `ws_manager/` — Real-time updates

| File | Role |
|------|------|
| `connection_manager.py` | Tracks WebSocket clients per tracking ID; broadcasts step + message + payload |

Used by both policy and claim background workers. The UI subscribes to `/ws/{policy_or_claim_id}?token=...`.

**In simple words:** WebSockets are the live status feed so users see “Parsing… Indexing… Done” without refreshing.

---

### `alembic/` — Database migrations

Version-controlled schema changes (users, policies, chunks, user ownership). Runs automatically on Docker startup.

---

## Data model (simplified)

```
User
 ├── PolicyRulebook (many)
 │    ├── raw_markdown_layout (full text)
 │    └── PolicyChunk (many)
 │         ├── chunk_text
 │         ├── heading_context
 │         └── embedding (vector 3072)
 └── ClaimSubmission (many)
      ├── policy_id → PolicyRulebook
      ├── patient_name
      ├── status (PENDING | APPROVED | FLAGGED | DENIED)
      └── claim_metadata (JSON)
           ├── raw_claim_markdown
           ├── audit_report_summary
           └── audited_at
```

Every policy and claim row has a `user_id` — users only see their own data.

---

## Security model

| Layer | Mechanism |
|-------|-----------|
| Authentication | JWT bearer token after `/auth/login` |
| Authorization | `get_current_user` on protected routes; repos filter by `user_id` |
| WebSocket | JWT passed as `?token=` query param; ownership verified before connect |
| Passwords | bcrypt hashes in `users.password_hash` |
| CORS | Configurable origin list (`CORS_ORIGINS`) |

---

## External dependencies

| Service | Why we need it |
|---------|----------------|
| **PostgreSQL + pgvector** | Persistent storage + fast vector search |
| **Docling Serve** | High-quality document layout extraction |
| **Google Gemini API** | Embeddings, claim audit reasoning, RAG answers |

---

## UI components (companion app)

The React UI in `claims-auditor-ui/` maps to API features:

| UI component | Backend touchpoints |
|--------------|---------------------|
| `LoginScreen` | `/auth/login`, `/user/enroll` |
| `PolicyIngestionView` | `POST /ingestion/policy`, WebSocket |
| `ClaimsAuditDesk` | `GET /ingestion/policy`, `POST /ingestion/claim`, WebSocket |
| `AuditingConsole` | `GET /ingestion/claim`, `GET /ingestion/claim/{id}` |
| `RagChatAssistant` | `GET /ingestion/policy`, `POST /chat/query` |
| `AuthContext` | JWT storage, session restore on refresh |
| `AppContext` | Loads policy list from API on login |
| `useWebSocket` | Subscribes to pipeline events |

---

## Deployment topology (Docker)

```
┌──────────────── docker network: claims-net ────────────────┐
│                                                            │
│  claims_auditor_ui:3000  ──►  claims_auditor_api:8000      │
│                                    │         │             │
│                                    ▼         ▼             │
│                          claims_auditor_db  docling:5001   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

- UI is static files behind Nginx; API URL is set at **build time** (`VITE_API_BASE_URL`).
- API uses live code mount (`--reload`) in dev compose for fast iteration.

---

## Key design choices

1. **202 Accepted + background tasks** — Long jobs never block HTTP; UI tracks by ID.
2. **User-scoped repositories** — Multi-tenant safety at the query layer.
3. **Markdown as lingua franca** — Docling output is stored and passed to Gemini as text.
4. **Structured audit output** — Gemini returns JSON schema, not free text, for reliable UI rendering.
5. **RAG with citations** — Chat answers are grounded in retrieved policy chunks, not model memory.

---

## Related docs

- API setup & run: [../README.md](../README.md)
- UI setup & run: [../../claims-auditor-ui/README.md](../../claims-auditor-ui/README.md)
