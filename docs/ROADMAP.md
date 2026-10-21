# Rafiq — Roadmap & Progress

This is the single source of truth for **what's done, what's in progress, and what's left**. The project description is in [PROJECT.md](PROJECT.md).

**How to use this file**
- Tick `[x]` a task when it's merged to `main`, then update the milestone's status in the board below.
- Add a dated line to the [Progress log](#progress-log) at the end of each work session.
- New ideas go to the [Backlog](#backlog--stretch-goals), not into the current milestone.

**Legend:** ⬜ Not started · 🟡 In progress · ✅ Done · ⏸️ Paused

---

## Status board

| # | Milestone | Status | Demo checkpoint |
|---|---|---|---|
| M0 | Planning & setup | ✅ | Plan written, repo on GitHub |
| M1 | Foundation | 🟡 | `docker compose up` → streaming chat in AR/FR/EN, CI green |
| M2 | RAG | ✅ | Arabic question → cited answer from a French PDF |
| M3 | Agent & tools | ⬜ | Full booking by chat in each language |
| M4 | Evaluation & CI gate | ⬜ | A PR that breaks a prompt fails CI with a results table |
| M5 | Telemetry & dashboard | ⬜ | Every conversation shows tokens, $, latency per stage |
| M6 | Voice | ⬜ | Book an appointment by voice |
| M7 | Deploy, polish & showcase | ⬜ | Public URL + README + 2-minute video |

**Current focus:** M3 (agent & tools). Still open from M1: mobile-width and dark-mode check.

---

## M0 — Planning & setup ✅

**Goal:** a clear plan and an empty repo that's ready to build in.

- [x] Define the project, scope, stack and architecture → `docs/PROJECT.md`
- [x] Write milestones and tasks → `docs/ROADMAP.md`
- [x] Add `CLAUDE.md` with working rules
- [x] `git init`, `.gitignore`, `.gitattributes`, `.editorconfig`, LICENSE (MIT)
- [x] Create the GitHub repo and push → https://github.com/OussamaHaddad002/rafiq
- [ ] Set up API keys locally (`.env`, never committed): OpenAI; later STT and TTS providers

**Done when:** the repo is on GitHub with the docs.

---

## M1 — Foundation 🟡

**Goal:** a monorepo skeleton that runs with one command, with CI and a streaming text chat.

### Backend (`apps/api`)
- [x] FastAPI project with uv, ruff, mypy (strict), pytest
- [x] Settings via pydantic-settings (`.env`)
- [x] Postgres (with pgvector) + async SQLAlchemy + Alembic, first migration
- [x] `GET /api/health` (checks the DB, 503 when it's down)
- [x] LLM provider interface + Claude implementation (streaming) + fake provider for tests / CI / no key
- [x] `POST /api/chat` streaming over SSE (no tools yet); conversation + messages saved; `GET /api/conversations/{id}`
- [x] Structured logging (JSON) with request IDs (`x-request-id`)
- [x] OpenAI provider (Responses API, default `gpt-5.4-mini`), tested against mocked streams for OpenAI and Claude
- [x] Default model switched to `gpt-4o-mini` (no GPT-5 models)
- [x] Check the OpenAI provider end to end with a real `OPENAI_API_KEY`

### Frontend (`apps/web`)
- [x] Vite + React + TS (strict), Tailwind, shadcn/ui, oxlint + Prettier, Vitest
- [x] react-i18next with AR / FR / EN, language switcher, **RTL layout for Arabic**
- [x] Chat UI: message list, streaming rendering, stop button, input, new conversation, conversation restored after reload
- [x] API client + TanStack Query
- [x] Visual check in a browser: EN and AR (RTL mirrored layout), citations, excerpt panel
- [ ] Visual check at mobile width and in dark mode

### Infra & CI
- [x] Dockerfiles (multi-stage, non-root API user) for api and web (nginx, SSE-safe proxy)
- [x] `docker-compose.yml`: api, web, postgres (pgvector). Redis postponed until it's needed (M7 rate limiting)
- [x] `.github/workflows/ci.yml`: ruff, mypy, migrations + `alembic check`, pytest (Postgres service), prettier, oxlint, tsc, vitest, build, docker build + smoke test
- [x] `.env.example`; common commands in `CLAUDE.md` (no Makefile: `make` isn't available on Windows)
- [x] CI green on GitHub

**Done when:** `docker compose up` gives a working streaming chat in all 3 languages with correct RTL, and CI is green.

---

## M2 — RAG ✅

**Goal:** answers grounded in clinic documents, with citations, across languages.

- [x] Fictional knowledge base: 4 PDFs (FR, one with an EN section) built from `data/clinic-src/` by `scripts/build_kb_pdfs.py`, plus `horaires-acces.md` (FR + AR), `faq.md` (AR), `politiques.md` (EN)
- [x] Decide embeddings: OpenAI `text-embedding-3-small` (decision #16); fake hashed bag-of-words embedder for tests / CI
- [x] Ingestion pipeline: parse (pypdf layout mode, Markdown by heading) → chunk (≤1,200 chars, 200 overlap, never across a page or section) → per-chunk language detection → embed → store
- [x] Ingestion CLI (`python -m app.rag.ingest`): skips unchanged files (hash + pipeline version + embedding model), prunes deleted ones
- [x] Vector search (pgvector, HNSW cosine index)
- [x] Keyword search (Postgres full-text on Arabic-normalized text) + Reciprocal Rank Fusion
- [x] Retrieval on every turn, with a short-follow-up heuristic (becomes the `search_docs` tool in M3); results carry `source`, `page`, `section`, `lang`
- [x] System prompt: answer only from numbered excerpts, cite as [n], translate facts, ignore instructions inside documents
- [x] SSE `sources` event; sources saved on the assistant message and returned with the conversation
- [x] UI: citation markers and source chips that open the excerpt
- [x] Tests: normalization, language detection, parsing, chunking, RRF, ingestion, search, query translation, chat grounding (API 67, web 13)
- [x] Retrieval sanity set (24 questions, 13 cross-lingual) + `scripts/retrieval_check.py`. Fake-embedding baseline: same-language 11/11, cross-lingual 6/13
- [x] Sanity check with real OpenAI embeddings: cross-lingual only 61.5% (Arabic questions stayed in Arabic documents) → see `evals/reports/2026-10-20-retrieval-sanity.md`
- [x] Query translation (decision #22): one `gpt-4o-mini` call rewrites the question as a standalone query in fr/en/ar, one query per language → **hit@5 100% (24/24), cross-lingual 100%, MRR 0.91**. Reranker not needed for now (decision #19)
- [x] Grounded answers checked end to end with `gpt-4o-mini` in AR (incl. Darija) / FR / EN, including follow-ups and multi-document answers; citation rule tightened for answers that combine several documents
- [x] Fixes from the owner's manual test: the query rewriter now rewrites only the latest message (it had rewritten an earlier question for shorthand like "Mutuelle Yasmine + cardiology"); follow-ups keep their context (insurer); reply language decided in code (decision #23); nginx no longer lets browsers cache `index.html`; adjacent citation markers never wrap apart

**Done when:** "بقداش الاستشارة عند طبيب الأسنان؟" returns the correct price with a citation to `tarifs.pdf`.

---

## M3 — Agent & tools ⬜

**Goal:** a reliable tool-calling agent that manages appointments.

- [ ] Seed data: specialties, ~8 doctors, weekly schedules, generated slots (script, safe to re-run)
- [ ] Agent loop: model → tool calls → results → model, with max-iterations guard and error handling
- [ ] Tool registry with Pydantic schemas → JSON schema for the model
- [ ] Tools: `list_doctors`, `check_availability`, `book_appointment`, `lookup_appointment`, `reschedule_appointment`, `cancel_appointment`, `handoff_to_human`, and `search_docs` wired as a tool
- [ ] Confirmation step before any write action (book / reschedule / cancel)
- [ ] Authorization: booking code + phone required for lookup or changes
- [ ] Date handling: relative dates ("jeudi prochain", "بعد غدوة"), clinic timezone
- [ ] Guardrails: no diagnosis or medication advice; emergency redirect; stay in scope
- [ ] Prompt-injection defense: retrieved content is treated as data, never as instructions
- [ ] UI: tool activity indicators ("Checking availability…"), booking confirmation card
- [ ] Tests: each tool (unit), agent loop with a fake LLM (integration)

**Done when:** a user can book, look up, reschedule and cancel by chat in AR, FR and EN.

---

## M4 — Evaluation & CI gate ⬜

**Goal:** measurable quality, with regressions blocked in CI.

- [ ] Test case schema (YAML): `id`, `lang`, `category`, `turns`, `expected_sources`, `must_contain`, `expected_tool`, `expected_args`, `notes`
- [ ] Dataset: ≥ 120 cases spread across categories × languages (see PROJECT.md §7)
- [ ] Runner `evals/runner/run_eval.py`: runs cases in parallel against the agent, with seeded DB state per case
- [ ] Metrics: recall@5, MRR, correctness, faithfulness, tool accuracy, language match, refusal correctness, latency, cost
- [ ] LLM judge with a fixed rubric (and a few hand-labelled cases to check the judge itself)
- [ ] Reports: JSON (machine) + Markdown (human) tables broken down by language × category
- [ ] Seed cases from manual testing: shorthand in another language than the conversation ("Mutuelle Yasmine + cardiology"), follow-up that keeps the insurer ("Et pour une échographie ?"), ambiguous item with several prices (abdominal vs. cardiac ultrasound: list both)
- [ ] Baseline run committed (`evals/reports/baseline.json`)
- [ ] Model comparison run (e.g. `gpt-4o-mini` vs. `gpt-4.1-nano` / `gpt-4.1-mini`; no GPT-5 models): accuracy vs. cost vs. latency table. Keep it small: the credit budget is limited
- [ ] `.github/workflows/eval.yml`: smoke subset on PRs (paths: agent / rag / prompts), PR comment with results, fail when the drop exceeds the threshold
- [ ] Nightly full run + manual trigger, results saved as artifacts
- [ ] Eval results saved to the DB (`eval_runs`, `eval_results`) for the dashboard

**Done when:** a PR that deliberately breaks the system prompt fails CI with a clear results comment.

---

## M5 — Telemetry & dashboard ⬜

**Goal:** see cost, tokens and latency per conversation and per stage.

- [ ] Record every LLM call: model, input / output / cached tokens, latency, time to first token
- [ ] Pricing table in config → cost per call / turn / conversation
- [ ] Stage spans per turn: STT, retrieval, rerank, LLM, tools, TTS
- [ ] Prompt caching for the system prompt and tool definitions; track cache hit and savings
- [ ] Metrics API: overview, time series, per-conversation detail, eval runs
- [ ] Dashboard — Overview: conversations, cost per conversation, total cost, p50 / p95 latency, tool success rate, language split
- [ ] Dashboard — Conversations: list + detail timeline (messages, tool calls, retrieved chunks, cost, stage latencies)
- [ ] Dashboard — Evals: run history, scores per language / category, compare two runs
- [ ] Simple admin protection for the dashboard (token or basic auth)

**Done when:** any conversation can be opened to see exactly what it cost and where the time went.

---

## M6 — Voice ⬜

**Goal:** talk to Rafiq in AR / FR / EN.

- [ ] Decide the STT and TTS providers (record in the decisions log)
- [ ] Browser: push-to-talk recording (MediaRecorder), waveform / recording indicator
- [ ] WebSocket endpoint: audio in → STT → agent → TTS → audio out
- [ ] Stream TTS sentence by sentence as the LLM generates (shorter time to first audio)
- [ ] Language detection from STT → reply voice in the same language
- [ ] Voice latency spans in telemetry (end of speech → first audio)
- [ ] Small audio eval set (~30 clips across languages): WER + end-to-end task success
- [ ] Measure Darija WER honestly and document the results
- [ ] *Stretch:* VAD + barge-in (Pipecat), hands-free mode

**Done when:** a full appointment can be booked by voice, with voice latency shown on the dashboard.

---

## M7 — Deploy, polish & showcase ⬜

**Goal:** a public, safe demo and a showcase repo.

### Deploy
- [ ] Decide hosting (record in the decisions log)
- [ ] Production compose + Caddy (HTTPS) or Fly.io config
- [ ] `.github/workflows/deploy.yml`: build → push to GHCR → deploy on `main`
- [ ] Secrets in GitHub Actions / host, nothing in the repo

### Demo safety
- [ ] Per-IP rate limiting (Redis)
- [ ] Global daily budget cap → friendly "demo limit reached" message
- [ ] Cloudflare Turnstile on the chat / voice start
- [ ] Nightly reset of the demo DB (appointments, conversations)
- [ ] PII: phone numbers masked in logs and the dashboard

### Showcase
- [ ] README: GIF at the top, live demo link, video link, architecture diagram, eval results table, cost / latency numbers, design decisions, how to run locally
- [ ] Architecture diagram (draw.io / Excalidraw) in `docs/`
- [ ] Record the 2-minute video:
  - 0:00–0:15 the problem
  - 0:15–1:15 demo: Arabic voice question → cited answer from a French PDF; booking in French by voice; English lookup
  - 1:15–1:40 dashboard + an eval run blocking a PR
  - 1:40–2:00 architecture and stack
- [ ] CV bullet with real numbers + LinkedIn post
- [ ] Pin the repo on GitHub, add topics and a description

**Done when:** a stranger can open the live demo, watch the video and understand the project from the README in 2 minutes.

---

## Backlog / stretch goals

- [ ] Barge-in and fully hands-free voice (Pipecat / LiveKit Agents)
- [ ] Better Darija support (dialect-aware prompts, STT comparison)
- [ ] Google Calendar sync for doctors
- [ ] WhatsApp channel
- [ ] Phone calls via Twilio / SIP
- [ ] Admin page for uploading documents (re-ingest from the UI)
- [ ] Langfuse / OpenTelemetry export
- [ ] Multi-clinic (tenants)
- [ ] Playwright end-to-end test for the booking flow in CI

---

## Progress log

Newest first. One line per work session: what got done, any blockers, what's next.

| Date | Milestone | Update |
|---|---|---|
| 2026-10-20 | M2 | Owner tested the UI. Found and fixed: stale frontend (web container not rebuilt, and nginx let browsers cache `index.html`), query rewriter picking an earlier question, insurer lost on follow-ups, inconsistent reply language for shorthand. Replayed the conversation: all answers correct; retrieval still 24/24. Visual check done in EN/AR. API 79 tests, web 14. |
| 2026-10-20 | M2 ✅ | OpenAI key working. Real embeddings: cross-lingual 61.5% → added query translation with one query per language → 100% hit@5 on 24 questions (MRR 0.91). Real `gpt-4o-mini` answers checked in AR/FR/EN (prices, insurance maths, follow-ups, medical refusal). Report in `evals/reports/`. Cost of all testing so far: under 1 cent. Next: M3. |
| 2026-10-20 | M2 | Built the RAG pipeline: knowledge base (7 docs), ingestion, hybrid search (pgvector + full-text, RRF), cited answers, sources in the UI. Default model now `gpt-4o-mini`. Fake-embedding retrieval baseline: same-language 100%, cross-lingual 46% (expected without real embeddings). Waiting for an OpenAI key to measure real embeddings. |
| 2026-10-20 | M0/M1 | Repo public on GitHub, CI green (API, web, Docker smoke test). Pinned `setup-uv` by SHA because it has no floating `v10` tag. |
| 2026-10-20 | M1 | Switched the default LLM to OpenAI `gpt-5.4-mini` (budget), using the Responses API with low reasoning and `store=False`. Claude is kept as an option. Added provider tests against mocked SDK streams; 26 API tests. |
| 2026-10-20 | M1 | Built the skeleton. API: FastAPI + async SQLAlchemy + Alembic, native SSE chat, Claude + fake providers, JSON logs with request IDs; 15 tests. Web: React 19 / Vite 8 / Tailwind 4, AR/FR/EN with RTL, streaming chat UI; 9 tests. Docker Compose (db, api, web), and CI with lint, types, tests and a Docker smoke test (actionlint clean). Verified locally: full stack through nginx with the fake LLM. Left: push to GitHub and get CI green, test with a real Claude key, visual check in a browser. |
| 2026-10-20 | M0 | git init + repo hygiene files done. Project defined. Wrote `docs/PROJECT.md`, `docs/ROADMAP.md`, `CLAUDE.md`. Next: git init + GitHub repo, then start M1. |
