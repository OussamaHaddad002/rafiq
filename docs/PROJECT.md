# Rafiq (رفيق) — Project Description

> A voice and chat receptionist for clinics that works in Arabic, French and English. It answers patient questions from the clinic's own documents (RAG) and books, reschedules and cancels appointments (tool calling). The project also includes an eval suite, a cost and latency dashboard, and CI that fails when eval scores drop.

This is the **stable reference** for the project: what we are building and why. The milestones, tasks and done/left status live in [ROADMAP.md](ROADMAP.md).

---

## 1. Problem & pitch

Clinics in the Maghreb get a constant stream of phone calls asking the same questions: *How much is a consultation? Is it covered by my insurance? What do I bring? Can I book with Dr. X on Thursday?* Patients ask in Arabic (often dialect), French or English, while the clinic's documents are usually written in French.

**Rafiq** answers these questions 24/7, by voice or chat, in the patient's language. Answers are grounded in the clinic's documents and cite their sources. Rafiq can also manage appointments.

**Portfolio goal:** show applied LLM engineering end to end: RAG across languages, agentic tool calling, evaluation, observability, cost control, Docker, CI/CD and a live deployment.

## 2. Highlights (what recruiters should remember)

1. **Search across languages:** a question in Arabic gets a cited answer from a French PDF. Accuracy is reported **per language**.
2. **CI that checks quality:** a PR that lowers agent accuracy fails CI, and the results table is posted as a PR comment.
3. **Cost and latency for every turn**, split by stage: STT → retrieval → LLM time to first token → tools → TTS.
4. **Model comparison table:** accuracy vs. cost vs. latency across models, measured with our own eval suite.
5. **Production details:** daily budget cap, rate limiting, prompt-injection test cases, confirmation before any booking, never gives medical diagnoses.

## 3. Scope

### In scope
- Text chat (streaming) and voice (push-to-talk first, streaming later) in **AR / FR / EN**
- RAG over a fictional clinic's documents, with citations
- Appointment tools: availability, book, look up, reschedule, cancel, hand off to a human
- Eval suite with accuracy scores, run locally and in CI
- Telemetry and a dashboard: tokens, cost per conversation, latency per stage, eval history
- Docker Compose, GitHub Actions (CI, evals, deploy), public demo, 2-minute video

### Non-goals
- Real patient data or real medical advice. The demo clinic is **fictional** ("Clinique Rafiq").
- Multi-tenant SaaS, user accounts, billing. One demo clinic with seeded data.
- Mobile app, phone or SIP calls (possible later; see the backlog in the roadmap).
- Fine-tuning models.

## 4. Users & core flows

| Flow | Example | What it exercises |
|---|---|---|
| Ask a question | "بقداش الاستشارة عند طبيب الأسنان؟" → answer from `tarifs.pdf` (FR), with citation | Search across languages, citations |
| Book an appointment | "Je veux un rdv avec un cardiologue jeudi matin" → slots → patient picks one → confirm → booking code | Multi-turn tool calling, confirmation step |
| Manage an appointment | "Cancel my appointment, code RFQ-4821" → verify phone → cancel | Tool authorization, lookup |
| Out of scope / medical | "I have chest pain, what should I take?" → no diagnosis; points to emergency services / a doctor | Guardrails |
| Hand off to a human | "I want to talk to someone" → callback request created | Escalation |
| Admin / demo viewer | Dashboard: costs, latency, conversations, eval runs | Observability |

## 5. Architecture

```
┌──────────────────────── React (Vite + TS) ────────────────────────┐
│  Chat (SSE)  ·  Voice (WebSocket, push-to-talk)  ·  Dashboard     │
└───────────────┬────────────────────────────┬──────────────────────┘
                │                            │
          ┌─────▼────────────────────────────▼─────┐
          │               FastAPI                   │
          │  STT ─► Agent loop (Claude) ─► TTS      │
          │           │                             │
          │           ├─ search_docs ─► hybrid retrieval (vector + keyword, RRF) ─► rerank
          │           ├─ list_doctors / check_availability
          │           ├─ book / lookup / reschedule / cancel_appointment
          │           └─ handoff_to_human
          │  Telemetry: tokens, $, ms per stage     │
          └─────┬──────────────────────┬────────────┘
                │                      │
        ┌───────▼────────┐     ┌───────▼──────┐
        │ Postgres +     │     │ Redis        │
        │ pgvector       │     │ rate limits, │
        │ (data+vectors+ │     │ sessions     │
        │  metrics)      │     └──────────────┘
        └────────────────┘
```

### Agent tools

| Tool | Purpose | Notes |
|---|---|---|
| `search_docs(query, lang?)` | Retrieve relevant chunks with source + page | Returns citations the UI renders |
| `list_doctors(specialty?)` | Doctors and specialties | |
| `check_availability(doctor_id \| specialty, date_from, date_to)` | Free slots | |
| `book_appointment(doctor_id, slot_start, patient_name, phone)` | Create a booking, return a booking code | **Requires explicit user confirmation first** |
| `lookup_appointment(booking_code, phone)` | Get booking details | Both fields required (basic authorization) |
| `reschedule_appointment(booking_code, phone, new_slot)` | Move a booking | Confirmation required |
| `cancel_appointment(booking_code, phone)` | Cancel a booking | Confirmation required |
| `handoff_to_human(reason, phone?)` | Create a callback request | |

### Knowledge base (fictional, written by us)

The languages are mixed on purpose, so search across languages is actually needed:

| Document | Language | Content |
|---|---|---|
| `tarifs.pdf` | FR | Consultation and procedure prices |
| `assurance.pdf` | FR | Insurance coverage rules, reimbursement steps (fictional) |
| `horaires-acces.md` | FR + AR | Opening hours, address, parking, contact |
| `preparation-examens.pdf` | FR + EN | Fasting for blood tests, colonoscopy prep, etc. |
| `medecins.pdf` | FR | Doctors directory, specialties, languages spoken |
| `faq.md` | AR | Common patient questions |
| `politiques.md` | EN | Cancellation policy, documents to bring, privacy |

### Data model (first draft)

`specialties`, `doctors`, `schedules`/`slots`, `patients` (name, phone only), `appointments` (booking_code, status), `callback_requests`, `documents`, `chunks` (text, lang, embedding, metadata), `conversations`, `messages`, `llm_calls` (model, tokens in/out/cached, cost, latency), `turn_spans` (stage timings), `eval_runs`, `eval_results`.

## 6. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Vite 8 + React 19 + TypeScript 6 (strict), Tailwind 4 + shadcn/ui, TanStack Query, react-i18next (RTL), Recharts (M5), oxlint + Prettier, Vitest | Familiar stack; proper RTL Arabic is a visible quality signal |
| Backend | Python 3.13, FastAPI (native SSE), Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, uv, ruff, mypy (strict), pytest | Familiar stack with modern Python tooling |
| Database | PostgreSQL + pgvector | One database for relational data, vectors and metrics |
| Cache / limits | Redis (added in M7, when needed) | Rate limiting |
| LLM | OpenAI `gpt-5.4-mini` (default, low reasoning effort) via the Responses API; Claude also supported; fake provider for tests. All behind one provider interface, model set by `LLM_MODEL` | Low cost on a small budget; the interface makes model comparison possible |
| Agent | Hand-written tool-calling loop | No framework magic; every line can be explained in an interview |
| Document parsing | Docling (fallback: PyMuPDF) | PDF layout, tables, Arabic text |
| Embeddings | BGE-M3 (local) — *tentative*, a hosted multilingual API if the VPS is too small | Strong multilingual / Arabic retrieval |
| Reranker | bge-reranker-v2-m3 (or hosted rerank API) | Better precision after retrieval |
| STT | Whisper large-v3 (Groq API or faster-whisper) | AR / FR / EN support |
| TTS | Azure Speech (has ar-TN / ar-MA voices) or ElevenLabs — *to decide* | Natural voices in all 3 languages |
| Voice transport | WebSocket (push-to-talk); Pipecat for streaming / barge-in later | Simple first, upgrade later |
| Infra | Docker Compose, GitHub Actions, GHCR, VPS + Caddy (or Fly.io) | Cheap, reproducible, auto-HTTPS |

## 7. Evaluation design

**Dataset:** at least 120 YAML test cases in `evals/datasets/`, tagged by `lang` and `category`.

| Category | Example | Checked by |
|---|---|---|
| `rag_same_lang` | FR question → FR doc | Retrieval + answer judge |
| `rag_cross_lingual` | AR question → FR doc | Retrieval + answer judge |
| `tool_booking` | Multi-turn booking | Tool name + args match, confirmation asked |
| `tool_manage` | Lookup / reschedule / cancel | Tool name + args match |
| `out_of_scope` | Medical advice, unrelated topics | Refusal / redirection judge |
| `prompt_injection` | Malicious doc chunk or user message | Must not follow injected instructions |
| `handoff` | Asks for a human | `handoff_to_human` called |

**Metrics (all reported per language and per category):**
- Retrieval: recall@5, MRR
- Answer correctness and faithfulness (LLM judge with a rubric, plus `must_contain` checks)
- Tool-call accuracy (right tool and right arguments)
- Language match (the reply is in the user's language)
- Refusal correctness
- Latency p50 / p95, cost per case

**In CI:**
- On PRs that touch the agent, RAG or prompts: a ~30-case smoke subset. Results are posted as a PR comment, and the PR fails if accuracy drops by more than the threshold vs. the `main` baseline.
- Full suite nightly and on manual trigger. Reports are stored in `evals/reports/`.

## 8. Success targets (initial, adjust after the M4 baseline)

| Metric | Target |
|---|---|
| Answer correctness (overall) | ≥ 85% |
| Answer correctness (AR → FR cross-lingual) | ≥ 80% |
| Retrieval recall@5 | ≥ 90% |
| Tool-call accuracy | ≥ 90% |
| Language match | ≥ 98% |
| Text latency p95 (first token) | < 2 s |
| Voice latency (end of speech → first audio) | < 2.5 s |
| Cost per conversation | < $0.01 |

## 9. Repository structure (planned)

```
.
├── apps/
│   ├── api/                  # FastAPI backend
│   │   ├── app/
│   │   │   ├── core/         # config, db, logging, middleware
│   │   │   ├── llm/          # provider interface, Claude + fake providers
│   │   │   ├── agent/        # chat service, prompts (M3: loop, tool registry)
│   │   │   ├── tools/        # appointments, handoff
│   │   │   ├── rag/          # ingest, chunk, embed, retrieve, rerank
│   │   │   ├── voice/        # stt, tts, websocket handler
│   │   │   ├── telemetry/    # usage, cost, latency spans
│   │   │   ├── models/       # SQLAlchemy models
│   │   │   ├── schemas/      # Pydantic request/response models
│   │   │   └── routes/       # chat, health (later: voice, admin, metrics)
│   │   ├── alembic/
│   │   └── tests/
│   └── web/                  # React + Vite + TS
│       └── src/
│           ├── components/   # shared UI (shadcn/ui in components/ui)
│           ├── features/     # chat, voice, dashboard, evals
│           ├── i18n/         # i18next setup + ar/fr/en locales
│           └── lib/          # API client, SSE parser, utils
├── evals/
│   ├── datasets/             # *.yaml test cases
│   ├── runner/               # run_eval.py, judges, metrics
│   └── reports/              # JSON + Markdown results
├── data/clinic/              # knowledge base source documents
├── infra/                    # postgres init, Caddyfile, prod compose, deploy scripts
├── .github/workflows/        # ci.yml, eval.yml, deploy.yml
├── docs/                     # PROJECT.md, ROADMAP.md, diagrams
├── docker-compose.yml
├── CLAUDE.md
└── README.md                 # showcase README (written in M7)
```

## 10. Decisions log

Add a row whenever a significant technical decision is made or changed.

| # | Date | Decision | Why |
|---|---|---|---|
| 1 | 2026-10-20 | Domain: clinic receptionist | Real multi-turn tools, documents exist naturally, a real need for three languages |
| 2 | 2026-10-20 | Postgres + pgvector, no separate vector DB | Fewer services, easy to defend, enough for this scale |
| 3 | 2026-10-20 | Hand-written agent loop (no LangChain) | Full understanding and control; a strong interview story |
| 4 | 2026-10-20 | ~~Sonnet 5.5 for the agent, Haiku 4.5 for cheap steps~~. Replaced by #14 | — |
| 5 | 2026-10-20 | Build evals (M4) before voice (M6) | Evals guide every later decision |
| 6 | 2026-10-20 | Push-to-talk voice first; streaming / barge-in as a stretch goal | Reduce risk; ship a working demo early |
| 7 | 2026-10-20 | Build our own dashboard (Langfuse export optional) | The dashboard is part of the skills showcase |
| 8 | 2026-10-20 | FastAPI's built-in SSE (`EventSourceResponse`), no extra library | Fewer dependencies; keep-alive pings built in |
| 9 | 2026-10-20 | Fake LLM provider (`LLM_PROVIDER=fake`) | Deterministic tests, CI without secrets, anyone can run the demo without a key |
| 10 | 2026-10-20 | oxlint + Prettier instead of ESLint | Vite's scaffold default now; much faster; Prettier enforces formatting |
| 11 | 2026-10-20 | Redis postponed until M7 | Nothing needs it yet; avoid unused services |
| 12 | 2026-10-20 | Migrations run when the API container starts | Simple for a single instance; move to a release step if we scale out |
| 13 | 2026-10-20 | Same-origin `/api` (Vite proxy in dev, nginx in Docker) | No CORS configuration needed |
| 14 | 2026-10-20 | Default LLM: OpenAI `gpt-5.4-mini`, reasoning effort `low`, `store=False`; Claude stays available | Only an OpenAI key is available and the credit budget is small. Low reasoning keeps cost and latency down; `store=False` keeps conversations off OpenAI's servers |

## 11. Open questions

| Question | Options | Decide by |
|---|---|---|
| Hosting | Hetzner VPS + Caddy vs. Fly.io vs. Railway | M7 |
| Embeddings | BGE-M3 local vs. hosted multilingual API | M2 |
| TTS provider | Azure Speech vs. ElevenLabs | M6 |
| STT provider | Groq Whisper vs. local faster-whisper vs. Deepgram | M6 |
| Darija support | Only measure it (WER) vs. try to improve it | M6 |
