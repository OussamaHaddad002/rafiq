# Rafiq · رفيق

[![CI](https://github.com/OussamaHaddad002/rafiq/actions/workflows/ci.yml/badge.svg)](https://github.com/OussamaHaddad002/rafiq/actions/workflows/ci.yml)

**A voice and chat AI receptionist for clinics, in Arabic, French and English.** It answers patient questions from the clinic's documents (RAG), and books and manages appointments (tool calling). It comes with an eval suite, a cost and latency dashboard, and CI that fails when eval scores drop.

> 🚧 Work in progress. Done: streaming trilingual chat, answers grounded in the clinic's documents with citations (RAG), Docker, CI. Next: tools (appointments), evals, dashboard, voice. See the [roadmap](docs/ROADMAP.md).

## Results so far

- **Retrieval:** the right document is in the top 5 for **24/24** test questions, including 13 asked in a different language than their source document (Arabic and Darija questions answered from French PDFs). [Report](evals/reports/2026-10-20-retrieval-sanity.md)

## Stack

- **Backend:** Python 3.13 · FastAPI (SSE) · SQLAlchemy 2 (async) · Alembic · PostgreSQL + pgvector (hybrid search) · OpenAI `gpt-4o-mini` + `text-embedding-3-small` (Claude also supported)
- **Frontend:** React 19 · TypeScript · Vite · Tailwind CSS · shadcn/ui · TanStack Query · i18next (RTL Arabic)
- **Ops:** Docker Compose · GitHub Actions · uv · ruff · mypy · Vitest · oxlint

## Quick start

```bash
cp .env.example .env    # set OPENAI_API_KEY, or LLM_PROVIDER=fake to run without a key
docker compose up -d --build
docker compose exec api python -m app.rag.ingest   # load the clinic documents
```

Open http://localhost:8080.

Local development commands are in [CLAUDE.md](CLAUDE.md#commands).

## Docs

- [Project description](docs/PROJECT.md): scope, architecture, stack, eval design, decisions log
- [Roadmap & progress](docs/ROADMAP.md): milestones, what's done, what's left

## License

[MIT](LICENSE)
