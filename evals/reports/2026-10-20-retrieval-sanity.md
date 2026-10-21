# Retrieval sanity check — 2026-10-20

Dataset: `evals/datasets/retrieval_sanity.yaml`: 24 questions (8 AR including 3 in Darija, 8 FR, 8 EN). 13 of them are **cross-lingual**: the answer is only in a document written in another language.
Knowledge base: 7 documents, 40 chunks. Metric: the expected document is in the top 5 (hit@5), and MRR.
Command: `uv run python -m scripts.retrieval_check --k 5` (add `--no-translate` for the second row).

| Setup | Overall hit@5 | Same-language | Cross-lingual | Arabic | MRR |
|---|---|---|---|---|---|
| Fake embeddings (hashed bag of words, offline baseline) | 70.8% | 100% | 46.2% | 62.5% | 0.528 |
| `text-embedding-3-small`, original question only | 79.2% | 100% | 61.5% | 62.5% | 0.685 |
| + query translation (original + fr/en/ar) | 95.8% | 100% | 92.3% | 100% | 0.889 |
| + one query per language (rewrite replaces the original) | **100%** | **100%** | **100%** | **100%** | **0.910** |

## Findings

- **Language bias.** With embeddings alone, Arabic questions retrieve Arabic documents even when the answer is only in a French PDF. For example "بقداش الاستشارة عند طبيب الأسنان؟" returned five FAQ chunks and no price list.
- **Query translation fixes it.** One `gpt-4o-mini` call per question (about 300 tokens, roughly $0.0001) rewrites the question as a standalone query in French, English and Arabic. It also resolves follow-ups such as "Et pour une échographie abdominale ?".
- **Balanced voting matters.** Keeping both the original question and its same-language rewrite gave that language two votes in Reciprocal Rank Fusion. That drowned out the right document in another language: a French Wi-Fi question whose answer is only in the Arabic FAQ was missed. Using one query per language fixed the last miss.
- **Reranker not needed for now.** Every expected document is already in the top 5, so a reranker isn't worth its cost and latency yet. The full eval in M4 will check this again.

## End-to-end spot check (`gpt-4o-mini`)

| Question | Answer | Correct |
|---|---|---|
| بقداش الاستشارة عند طبيب الأسنان؟ | 50 DT, cites `tarifs.pdf` p1 | ✅ |
| Mutuelle Yasmine + cardiology consultation | 20% of 80 DT = 16 DT, cites `assurance.pdf` + `tarifs.pdf` | ✅ |
| Follow-up: "Et pour une échographie abdominale ?" | 20% of 90 DT = 18 DT, cites both documents | ✅ |
| كم أدفع مع Sahha Assurances لتخطيط القلب؟ | 30% of 30 DT = 9 DT, cites both documents | ✅ |
| Missed appointment without cancelling (EN) | 20 DT fee, waived for documented emergencies | ✅ |
| Chest pain, asks for medication (EN) | Refuses to advise, points to emergency services | ✅ |

The first run cited only one of two documents on multi-source answers. A prompt rule ("cite each excerpt a sentence combines") fixed it.
