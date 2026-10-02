# retrieval

_20261001-180559 · config `{'router': 'groq:llama-3.1-8b-instant', 'agent': 'groq:openai/gpt-oss-120b', 'synthesizer': 'gemini:gemini-2.5-flash', 'judge': 'groq:llama-3.3-70b-versatile'}` · embeddings `ollama:nomic-embed-text` · prompts `7af0f61676`_

| config | nDCG@10 | Recall@5 | Recall@10 | MRR@10 | ms/query |
|---|---|---|---|---|---|
| bm25 (lexical) | 0.821 | 0.880 | 0.933 | 0.789 | 215 |
| dense | 0.844 | 0.899 | 0.966 | 0.816 | 89 |
| hybrid (RRF) | 0.867 | 0.920 | 0.976 | 0.840 | 317 |
