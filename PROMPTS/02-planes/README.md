# 02 · Planes generados

| Archivo | Origen | Resumen |
|---|---|---|
| `plan_agente-investigacion.md` | Respuesta al prompt `01` en modo plan (copia de `C:\Users\david\.claude\plans\pasted-content-id-911a-quiero-que-giggly-heron.md`) | Contexto y requisitos; stack (LangGraph, Qdrant local, Ollama `bge-m3`, Groq + Gemini de pago); estructura del repo; ingesta incremental; grafo `plan → seed → research → synthesize → verify → render`; control de tokens; privacidad; evaluación E1–E5 con datos externos (SciFact, PubMedQA, vault demo); fases F0–F6 y verificación. |

**Estado de ejecución del plan** (a 2026-10-05): F0–F5 implementadas y probadas; E1 medida (nDCG@10 híbrido 0,867); E4 corrida parcialmente con modelos reales (4/6 ítems); E2, E3 y E5 sin ejecutar con LLM reales; F6 (portafolio) en curso: README, docs y CI listos, falta añadir resultados vivos de E2–E5.
**Desviaciones respecto al plan:** código de evaluación dentro del paquete (`src/scholar_agent/evaluation/`) y no en `eval/`; SciFact original en lugar de BEIR (BEIR no resolvió); reranker implementado pero desactivado por defecto; configs adicionales `local.yaml` y `groq-only.yaml`.
