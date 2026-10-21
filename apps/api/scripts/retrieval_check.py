"""Retrieval sanity check: is the right document in the top k for each question?

Reports hit rate@k and MRR overall, per language and per category, then lists the misses.
Uses the knowledge base already in the database (run `python -m app.rag.ingest` first) and the
configured embedder and LLM (for query translation). With OpenAI, a full run costs well under
one cent.

Run from apps/api: uv run python -m scripts.retrieval_check [--k 5] [--dataset PATH]
"""

import argparse
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.db import SessionFactory, engine
from app.llm import get_provider
from app.llm.base import ChatMessage
from app.rag.embeddings import get_embedder
from app.rag.retrieve import retrieve

DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "evals/datasets/retrieval_sanity.yaml"


@dataclass
class Result:
    case_id: str
    lang: str
    category: str
    question: str
    expected: list[str]
    retrieved: list[str]

    @property
    def rank(self) -> int | None:
        """1-based position of the first expected document, or None if missing."""
        for position, source in enumerate(self.retrieved, start=1):
            if source in self.expected:
                return position
        return None


def summarize(label: str, results: list[Result]) -> str:
    hits = sum(r.rank is not None for r in results)
    mrr = sum(1 / r.rank for r in results if r.rank) / len(results)
    return f"{label:<16} {hits:>3}/{len(results):<3} hit={hits / len(results):6.1%}  MRR={mrr:.3f}"


async def run(cases: list[dict[str, Any]], k: int, translate: bool) -> list[Result]:
    embedder = get_embedder()
    provider = get_provider()
    results = []
    try:
        async with SessionFactory() as session:
            for case in cases:
                chunks = await retrieve(
                    session=session,
                    embedder=embedder,
                    provider=provider,
                    history=[ChatMessage("user", case["question"])],
                    user_text=case["question"],
                    k=k,
                    translate=translate,
                )
                results.append(
                    Result(
                        case_id=case["id"],
                        lang=case["lang"],
                        category=case["category"],
                        question=case["question"],
                        expected=case["expected_sources"],
                        retrieved=[c.source for c in chunks],
                    )
                )
    finally:
        await engine.dispose()
    print(f"embedder={embedder.model} k={k} translate={translate} cases={len(results)}\n")
    return results


def report(results: list[Result]) -> None:
    print(summarize("overall", results))
    groups: defaultdict[str, list[Result]] = defaultdict(list)
    for r in results:
        groups[f"lang={r.lang}"].append(r)
        groups[r.category].append(r)
    for label in sorted(groups):
        print(summarize(label, groups[label]))
    misses = [r for r in results if r.rank is None]
    if misses:
        print("\nMisses:")
        for r in misses:
            print(f"  {r.case_id}: {r.question}")
            print(f"      expected {r.expected}, got {r.retrieved}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--no-translate", action="store_true", help="search with the original question only"
    )
    args = parser.parse_args()
    dataset = yaml.safe_load(args.dataset.read_text(encoding="utf-8"))
    report(asyncio.run(run(dataset, args.k, translate=not args.no_translate)))
