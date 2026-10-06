# vault

_20261002-144026 · config `{'router': 'groq:openai/gpt-oss-20b', 'agent': 'groq:openai/gpt-oss-120b', 'synthesizer': 'groq:openai/gpt-oss-120b', 'judge': 'groq:openai/gpt-oss-20b'}` · embeddings `ollama:bge-m3` · prompts `4563d2a7ce`_

| metric (demo vault, end-to-end) | value |
|---|---|
| gold-note citation recall | 1.000 |
| keyword coverage | 0.875 |
| verdict accuracy (verify_idea) | n/a |
| correct abstention (out-of-vault questions) | n/a |
| answer shows required reference (DOI / own-hypothesis tag) | n/a |
| mode compliance (notes mode = 0 external calls) | 1.000 |
| AI ideas labelled [IA-n] | 1.000 |
| raw claim support rate (before pruning) | 0.950 |
| claims removed by the verifier (per answer) | 0.250 |
| judge faithfulness (1-5) | 4.500 |

| cost / latency | value |
|---|---|
| items evaluated / errors | 6 / 2 |
| USD per item (total) | $0.0042 ($0.017) |
| tokens in / out per item | 12366 / 3421 |
| tool calls per item | 2.2 |
| latency p50 / p95 | 126.3s / 188.7s |
