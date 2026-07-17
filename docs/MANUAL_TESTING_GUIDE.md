# 🧪 Manual Testing Guide (Hinglish)

> **Ye file har baar kholo jab project test karna ho.** Koi cheez yaad rakhne
> ki zaroorat nahi — sirf steps follow karo.

---

## 📖 Pehle samjho: is project ke 2 hisse hain

1. **Infrastructure** (Docker mein chalte hain) → Postgres, Redis, MinIO, ChromaDB
2. **Backend code** (aap chalate ho) → FastAPI server + Celery worker

Test karne ke liye **dono chalne chahiye**.

---

## 🚀 STEP 1: Sab kuch chalu karo (har session ki shuruaat)

PowerShell kholo, project folder mein jao:

```powershell
cd "C:\Users\ankur\OneDrive\Desktop\AI Meeting Intelligence Platform"
```

### 1a. Docker Desktop chalu hai? (whale icon 🐳 taskbar mein green)
Agar nahi to Docker Desktop kholo, engine ready hone ka wait karo.

### 1b. Infrastructure start karo
```powershell
docker compose --env-file .env -f docker/docker-compose.yml up -d postgres redis
```
> Pehli baar images download hongi. Baad mein 2-3 second.

### 1c. Check karo sab "healthy" hai
```powershell
docker compose --env-file .env -f docker/docker-compose.yml ps
```
`mp-postgres` aur `mp-redis` ke aage **"(healthy)"** dikhna chahiye.

### 1d. Backend server chalu karo
```powershell
cd backend
$env:PYTHONPATH="."
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```
> Ye terminal **khula chhodo** — yahan live logs dikhenge. Band karne ke liye `Ctrl+C`.
> `--reload` = code change karo to server apne aap restart hoga.

Jab ye line dikhe to server ready hai:
```
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

---

## 🎯 STEP 2: Swagger UI se test karo (sabse EASY tareeka)

Browser mein kholo:

### 👉 http://localhost:8000/api/v1/docs

Yahan **saari APIs** buttons ke saath dikhengi. Koi command nahi, sirf click!

### Swagger kaise use karein (5 steps):
1. Koi bhi endpoint pe **click** karo (jaise `POST /auth/signup`)
2. Right side **"Try it out"** button dabao
3. JSON body edit karo (example already bhara hota hai)
4. Neeche **"Execute"** dabao
5. **Response** neeche dikhega — status code + body

---

## 📝 STEP 3: Auth flow test karo (copy-paste ready)

### Test 1 — Signup (naya account banao)
Endpoint: **`POST /auth/signup`** → Try it out → ye body paste karo → Execute
```json
{
  "email": "test@example.com",
  "password": "MyStr0ng-pass!",
  "full_name": "Test User",
  "organization_name": "My Company"
}
```
✅ **Expect:** `201` status, `"role": "admin"` (pehla user admin banta hai)
❌ Same email dobara → `409 Conflict`

### Test 2 — Login (token lo)
Endpoint: **`POST /auth/login`** → Try it out → Execute
```json
{
  "email": "test@example.com",
  "password": "MyStr0ng-pass!"
}
```
✅ **Expect:** `200`, response mein `access_token` aur `refresh_token` milega.
👉 **`access_token` ki poori value COPY karo** (agla step mein chahiye).

### Test 3 — Protected route (token use karo)
1. Swagger mein sabse upar **"Authorize" 🔓** button dabao
2. Box mein apna `access_token` paste karo → Authorize → Close
3. Ab endpoint **`GET /auth/me`** → Try it out → Execute

✅ **Expect:** `200`, aapki details (email, role) dikhengi.
❌ Bina Authorize kiye → `401 Unauthorized`

### Test 4 — Wrong password (security check)
`POST /auth/login` mein galat password daalo:
```json
{ "email": "test@example.com", "password": "galat-password" }
```
✅ **Expect:** `401` — aur message **wahi** hoga jo unknown email pe aata (anti-enumeration).

### Test 5 — Meeting Upload (M4)
> Pehle Swagger mein **Authorize 🔓** kar lo (Test 2 ka access_token).

Endpoint: **`POST /meetings`** → Try it out →
- `file`: **Choose File** dabao, koi `.mp3` / `.wav` / `.mp4` select karo
  (ya koi bhi file rename karke `.mp3` — magic-byte check usse reject kar dega!)
- `title`: (optional) meeting ka naam
- Execute

✅ **Expect:** `201`, `"status": "uploaded"`, file details.
❌ `.exe` ya renamed file → `400` (magic bytes validation).

Baaki meeting endpoints:
- **`GET /meetings`** → apni saari meetings (paginated). `page`, `page_size`, `search` try karo.
- **`GET /meetings/{id}`** → ek meeting ki full detail + files.
- **`GET /meetings/{id}/download`** → time-limited download URL.
- **`PATCH /meetings/{id}`** → title/description/tags update (`{"tags":["q3"]}`).
- **`DELETE /meetings/{id}`** → soft delete (list se gayab, DB mein rehta hai).

### Test 6 — Audio Pipeline (M5): transcription
> Pipeline **Celery worker** mein chalti hai — is test ke liye **poora stack**
> Docker mein hona chahiye (sirf postgres+redis nahi). Aur real transcription
> ke liye worker mein `TRANSCRIPTION_PROVIDER` set hona chahiye.

**Poora stack start karo (backend + worker sameta):**
```powershell
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
docker compose --env-file .env -f docker/docker-compose.yml ps   # sab healthy?
```

**Bina Whisper model download kiye pipeline test karni ho** (fast smoke test):
`.env` mein `TRANSCRIPTION_PROVIDER=stub` set karo → stack restart → upload karo.
Stub 3 fake segments deta hai (real ffmpeg phir bhi chalta hai). Real
transcription ke liye `=local` (faster-whisper, pehli baar model download) ya
`=openai` (API key chahiye).

**Flow (Swagger ya curl):**
1. **`POST /meetings`** se koi `.wav`/`.mp3`/`.mp4` upload karo → `201`, `status: uploaded`.
2. **`GET /meetings/{id}/status`** baar-baar hit karo → status badalta dikhega:
   `uploaded → extracting → transcribing → completed` (poll karte raho).
3. **`GET /meetings/{id}/transcript`** → segments (text + timestamps + confidence).
4. **`POST /meetings/{id}/reprocess`** → dobara chalao (sirf completed/failed pe allowed).

**Worker logs dekhna** (pipeline live dikhega):
```powershell
docker compose --env-file .env -f docker/docker-compose.yml logs -f worker
```

### Test 7 — Speaker Diarization (M6): "kaun bola"
> Diarization **optional** hai — HF_TOKEN nahi hai to skip (transcript phir
> bhi milega, segments ke `speaker_label` `null` honge). Bina HuggingFace token
> ke test karne ke liye `.env` mein `DIARIZATION_PROVIDER=stub` set karo (real
> pyannote model download nahi hoga, 2 fake speakers alternate karenge).

`.env` mein test ke liye: `TRANSCRIPTION_PROVIDER=stub` + `DIARIZATION_PROVIDER=stub`,
phir `docker compose ... up -d --force-recreate worker backend`.

**Flow:**
1. Koi audio upload karo → pipeline complete hone do (status `completed`).
2. **`GET /meetings/{id}/transcript`** → har segment mein ab `speaker_label`
   dikhega (`SPEAKER_00`, `SPEAKER_01`, ya `null`).
3. **`GET /meetings/{id}/speakers`** → detected speakers ki list.
4. **`PATCH /meetings/{id}/speakers/{speaker_id}`** → `{"display_name":"Ankur"}`
   se rename. Transcript dobara dekho → us speaker ke segments mein ab "Ankur".

Real diarization ke liye: HuggingFace pe `pyannote/speaker-diarization-3.1`
model accept karo, token `.env` ke `HF_TOKEN` mein daalo, `DIARIZATION_PROVIDER=auto`.

### Test 8 — Meeting Intelligence (M7): LLM summary + action items
> Analysis pipeline ka aakhri stage hai (`analyzing` status). Bina OpenAI
> key ke test karne ke liye `.env` mein `LLM_PROVIDER=stub` set karo (fixed
> fake intelligence deta hai). Real ke liye `=openai` + `OPENAI_API_KEY`.

**Fast full-pipeline test (no keys):** `.env` mein teeno stub —
`TRANSCRIPTION_PROVIDER=stub`, `DIARIZATION_PROVIDER=stub`, `LLM_PROVIDER=stub`
→ `docker compose ... up -d --force-recreate worker backend` → upload karo.

**Flow:**
1. Upload → pipeline complete hone do (status ab `analyzing` stage se guzarta hai).
2. **`GET /meetings/{id}/intelligence`** → summaries (full + executive),
   insights (decisions/risks/discussion points/open questions/follow-ups),
   action items (owner, due date, priority).
3. **`PATCH /meetings/{id}/action-items/{item_id}`** → `{"status":"done"}`
   se task complete mark karo (ya priority/assignee/description update).

Real LLM ke liye: `.env` mein `LLM_PROVIDER=openai` + `OPENAI_API_KEY=sk-...`,
stack restart. GPT-4.1 real transcript se intelligence nikalega.

### Test 9 — RAG: Semantic Search + Chat with Meeting (M8)
> Isme **ChromaDB** use hota hai. Pipeline ke aakhri stage (`embedding`) mein
> transcript chunk hokar embeddings ChromaDB mein store hote hain. Phir search
> aur chat un vectors se relevant chunks retrieve karte hain.

**Key-free full test:** `.env` mein `EMBEDDING_PROVIDER=stub` +
`TRANSCRIPTION/DIARIZATION/LLM_PROVIDER=stub`, `VECTORSTORE=chroma`
(default — real ChromaDB) → stack restart → upload → complete hone do.

**Semantic Search:**
- **`POST /search`** → `{"query": "kaun deployment karega?"}` → semantically
  matching transcript chunks (score ke saath). `meeting_id` optional (ek meeting
  mein search), warna poore org mein.

**Chat with Meeting (RAG):**
1. **`POST /chat/sessions`** → `{"meeting_id": "..."}` (ya bina — cross-meeting)
   → session banega.
2. **`POST /chat/sessions/{id}/messages`** → `{"question": "release kab hai?"}`
   → AI answer **citations ke saath** (kaunse chunk/timestamp se answer aaya).
3. **`GET /chat/sessions/{id}`** → poori conversation history.
4. **`GET /chat/sessions`** → aapki saari chat sessions.

Real embeddings ke liye: `.env` mein `EMBEDDING_PROVIDER=local` (sentence-
transformers, pehli baar model download ~90MB). Real chat answers: `LLM_PROVIDER=openai`.

---

## 🔍 STEP 4: Doosre tareeke se test (optional)

### Terminal se (Git Bash ya PowerShell):
```bash
# Health check
curl http://localhost:8000/api/v1/health

# Signup
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"a@b.com","password":"MyStr0ng-pass!","full_name":"A","organization_name":"Org"}'
```

### Automated tests (sab kuch ek saath, sabse fast):
```powershell
# Project root se:
.\.venv\Scripts\python.exe -m pytest tests/backend/unit -v
```
✅ **Expect:** `68 passed` (abhi tak ke saare tests)

---

## 🗄️ STEP 5: Database mein jhaank ke dekho (data sach mein saved hua?)

```powershell
# Saare users dekho
docker exec mp-postgres psql -U meeting_user -d meeting_platform -c "SELECT email, role FROM users;"

# Kitne audit logs bane (har login/signup record hota hai)
docker exec mp-postgres psql -U meeting_user -d meeting_platform -c "SELECT action, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 10;"

# Saari tables ki list
docker exec mp-postgres psql -U meeting_user -d meeting_platform -c "\dt"
```

---

## 🛑 STEP 6: Kaam khatam — band karo

```powershell
# Server band: jis terminal mein server chal raha hai wahan Ctrl+C

# Infrastructure band (data safe rehta hai):
docker compose --env-file .env -f docker/docker-compose.yml down

# Test data saaf karni ho (users/logs delete):
docker exec mp-postgres psql -U meeting_user -d meeting_platform -c "TRUNCATE organizations, users, refresh_tokens, audit_logs CASCADE;"
```

---

## 🆘 Common Problems (agar kuch atke)

| Problem | Solution |
|---|---|
| `docker: not recognized` | Docker Desktop kholo, ready hone ka wait karo |
| Server pe `INTERNAL_ERROR` | Ek hi server chalna chahiye — purane band karo (neeche command) |
| `ModuleNotFoundError: app` | `$env:PYTHONPATH="."` set kiya? `backend` folder ke andar ho? |
| `port 8000 already in use` | Purana server chal raha hai (neeche command se band karo) |
| Swagger nahi khul raha | Server chal raha hai? http://localhost:8000/api/v1/health try karo |

### Purane Python servers band karne ke liye:
```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.Path -like "*AI Meeting*"} | Stop-Process -Force
```

---

## 🎨 Frontend (M9): Browser UI

> Ab actual UI hai! Backend (Docker) chalu hona chahiye pehle.

```powershell
# Terminal 1: backend stack (agar nahi chal raha)
docker compose --env-file .env -f docker/docker-compose.yml up -d

# Terminal 2: frontend dev server
cd frontend
npm install       # pehli baar
npm run dev
```

Browser mein kholo: **http://localhost:3000**

**Flow:** Signup (aap admin) → Login → Dashboard (stats + recent meetings) →
Meetings (search + pagination) → Dark mode toggle (top-right). Upload/Search/
Chat pages abhi "coming soon" (M10-M11 mein full).

---

## 🧭 Quick Reference — sab links ek jagah

| Kya | URL / Command |
|---|---|
| **Swagger (API testing)** | http://localhost:8000/api/v1/docs |
| Health check | http://localhost:8000/api/v1/health |
| Readiness (DB+Redis) | http://localhost:8000/api/v1/health/ready |
| ReDoc (doosri docs style) | http://localhost:8000/api/v1/redoc |
| Automated tests | `.\.venv\Scripts\python.exe -m pytest tests/backend/unit -v` |

---

## 📚 Project ko "basic se" samajhne ka short map

```
Request aati hai → API endpoint (api/v1/endpoints/)
                        ↓
                   Service (services/) — yahan business logic + decision
                        ↓
                   Repository (repositories/) — yahan sirf database queries
                        ↓
                   PostgreSQL (models/ mein tables define hain)
```

- **config.py** → saari settings (passwords, URLs) ek jagah
- **security.py** → password hashing, JWT tokens
- **dependencies.py** → "kaun logged in hai?" check
- **exceptions.py** → saare errors ka ek jaisa format

> Har module ke end mein maine detailed explanation diya hai — wo scroll
> karke padhoge to poora flow samajh aayega.
