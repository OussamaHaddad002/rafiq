# Rafiq · رفيق

**A voice and chat AI receptionist for clinics, in Arabic, French and English.** It answers patient questions from the clinic's documents (RAG), and books and manages appointments (tool calling). It comes with an eval suite, a cost and latency dashboard, and CI that fails when eval scores drop.

> 🚧 Work in progress. The foundation (streaming trilingual chat, Docker, CI) is done. RAG, tools, evals, dashboard and voice are next. See the [roadmap](docs/ROADMAP.md).

## Stack

- **Backend:** Python 3.13 · FastAPI (SSE) · SQLAlchemy 2 (async) · Alembic · PostgreSQL + pgvector · OpenAI `gpt-5.4-mini` (Claude also supported)
- **Frontend:** React 19 · TypeScript · Vite · Tailwind CSS · shadcn/ui · TanStack Query · i18next (RTL Arabic)
- **Ops:** Docker Compose · GitHub Actions · uv · ruff · mypy · Vitest · oxlint

## Quick start

```bash
cp .env.example .env    # set OPENAI_API_KEY, or LLM_PROVIDER=fake to run without a key
docker compose up -d --build
```

Open http://localhost:8080.

Local development commands are in [CLAUDE.md](CLAUDE.md#commands).

## Docs

- [Project description](docs/PROJECT.md): scope, architecture, stack, eval design, decisions log
- [Roadmap & progress](docs/ROADMAP.md): milestones, what's done, what's left

## License

[MIT](LICENSE)
