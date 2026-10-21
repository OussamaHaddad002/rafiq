# Rafiq (رفيق)

A voice and chat receptionist for a fictional clinic, in Arabic, French and English: RAG over clinic documents, tool calling for appointments, an eval suite with a CI gate, and a cost/latency dashboard. It's a portfolio project, so code quality, tests and docs matter as much as features.

- **What & why:** [docs/PROJECT.md](docs/PROJECT.md): scope, architecture, stack, eval design, decisions log
- **What's done / left:** [docs/ROADMAP.md](docs/ROADMAP.md): milestones, task checklists, progress log

## Working rules

- At the start of a session, read `docs/ROADMAP.md` to find the current milestone and the next unchecked tasks.
- When a task is finished, tick it in `docs/ROADMAP.md`, update the milestone status in the status board, and add a dated line to the progress log.
- Record any significant technical decision (or change of decision) in the decisions log in `docs/PROJECT.md`.
- Stay inside the current milestone. Put new ideas in the roadmap backlog.
- Never commit secrets. Config goes through `.env` (with `.env.example` kept up to date).
- The demo clinic and all its data are fictional. Never add real patient data.

## Stack

- Backend: FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, Postgres + pgvector, Redis (from M7). Tooling: uv, ruff, mypy, pytest.
- Frontend: Vite + React + TypeScript (strict), Tailwind, shadcn/ui, TanStack Query, react-i18next (RTL for Arabic). Tooling: oxlint, Prettier, Vitest.
- LLM: OpenAI `gpt-4o-mini` by default (Responses API). Don't use GPT-5 models. Claude and a fake provider are also available behind the same interface. Embeddings: `text-embedding-3-small`. The credit budget is small, so keep API calls cheap and never call real APIs in tests.

## Conventions

- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`).
- Every feature ships with tests. After M4, changes to the agent, RAG or prompts must not lower eval scores.
- RTL: use logical Tailwind utilities (`ms-`, `me-`, `ps-`, `pe-`, `start`, `end`) instead of `ml-`/`mr-`/`left`/`right`, and `dir="auto"` on user-generated text.
- Tests use the fake LLM provider; never call the real API in tests.

## Commands

If `uv` isn't on your PATH, `python -m uv` works too.

```bash
# Whole stack (http://localhost:8080). Uses .env; LLM_PROVIDER=fake works without an API key.
docker compose up -d --build
docker compose exec api python -m app.rag.ingest  # load the knowledge base
docker compose exec api python -m app.clinic.seed # doctors and weekly schedules

# Database only (for local dev and tests). Creates `rafiq` and `rafiq_test` on first start.
docker compose up -d db

# API (apps/api)
uv sync
uv run alembic upgrade head                       # apply migrations
uv run alembic revision --autogenerate -m "..."  # new migration after model changes
uv run uvicorn app.main:app --reload             # http://localhost:8000/docs
uv run pytest                                     # needs the db container
uv run python -m app.rag.ingest                   # load data/clinic into the db (re-run safe)
uv run python -m app.clinic.seed                  # doctors + schedules (re-run safe)
uv run python -m scripts.retrieval_check          # retrieval hit rate / MRR on the sanity set
uv run python scripts/build_kb_pdfs.py            # rebuild the KB PDFs from data/clinic-src
uv run ruff format . && uv run ruff check . && uv run mypy app tests

# Web (apps/web): dev server proxies /api to :8000
npm install
npm run dev                                       # http://localhost:5173
npm test && npm run lint && npm run typecheck && npm run format:check
```
