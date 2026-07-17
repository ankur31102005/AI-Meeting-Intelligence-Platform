# Deployment Guide

This platform ships as containers. There are two stacks:

| Stack | File | Use |
|-------|------|-----|
| **Dev** | `docker/docker-compose.yml` | Backend + infra in Docker, frontend on host (`npm run dev`, hot reload) |
| **Prod** | `docker/docker-compose.prod.yml` | Everything in Docker: backend, workers, **frontend**, infra — immutable images |

---

## 1. Prerequisites

- Docker + Docker Compose
- A configured `.env` (copy from `.env.example`)

---

## 2. Production configuration (`.env`)

The backend **refuses to start in production** with dev-default secrets, so set
real values:

```env
ENVIRONMENT=production
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(64))">
POSTGRES_PASSWORD=<strong-password>
S3_ACCESS_KEY=<strong>
S3_SECRET_KEY=<strong>

# Public URL the browser uses to reach the API (baked into the frontend build)
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com/api/v1
CORS_ORIGINS=https://app.yourdomain.com

# AI providers (choose per cost/quality — see below)
TRANSCRIPTION_PROVIDER=local
EMBEDDING_PROVIDER=local
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### AI provider options

| Concern | Free | Paid / hosted |
|---------|------|---------------|
| Transcription | `local` (faster-whisper) | `openai` (Whisper API) |
| Summaries / chat | `ollama` (local LLM) | `openai` (GPT-4.1) |
| Embeddings | `local` (sentence-transformers) | — |
| Speakers | needs `HF_TOKEN` (free) | — |

---

## 3. Launch the production stack

```bash
docker compose --env-file .env -f docker/docker-compose.prod.yml up -d --build
# or: make prod-up
```

This starts: postgres, redis, minio, chromadb, backend (4 uvicorn workers),
`worker-ai` (heavy queue), `worker-default` (light queue), and the frontend.

**Apply database migrations** (first deploy + after any model change):

```bash
docker compose -f docker/docker-compose.prod.yml exec backend \
  python -m alembic upgrade head
```

Verify:

```bash
make prod-logs
curl http://localhost:8000/api/v1/health/ready   # expect 200
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000/api/v1 |
| API docs | http://localhost:8000/api/v1/docs |

---

## 4. Production hardening checklist

- [ ] **Reverse proxy** (nginx/Caddy/Traefik) terminating TLS in front of
      frontend (:3000) and backend (:8000). Infra ports (Postgres/Redis/MinIO/
      Chroma) are already NOT published to the host by the prod compose.
- [ ] **Managed Postgres** (RDS/Cloud SQL) + **PgBouncer** once you run >3
      backend replicas (connection pooling).
- [ ] **Real object storage** — point `S3_*` at AWS S3 (same code path as MinIO).
- [ ] **Backups** — Postgres (pg_dump/PITR), MinIO bucket, Chroma volume.
- [ ] **Secrets** via a secret manager, not a committed file.
- [ ] **Log aggregation** — set `LOG_FORMAT=json`; ship to CloudWatch/Datadog/Loki.
- [ ] **Scale workers** — run more `worker-ai` replicas on GPU hosts for
      transcription; keep `worker-default` cheap.
- [ ] **Monitoring** — health probes wired to your orchestrator; add Sentry.

---

## 5. Scaling notes

- **Stateless API** — scale `backend` horizontally behind a load balancer.
- **Queue isolation** — `ai_pipeline` vs `default` queues scale independently.
- **Vector store** — ChromaDB is single-node here; for large corpora move to a
  clustered vector DB (same `VectorStore` interface, one new class).
- **Whisper/embeddings** — model weights load per worker process; keep workers
  warm and size `--concurrency` to available RAM/GPU.
