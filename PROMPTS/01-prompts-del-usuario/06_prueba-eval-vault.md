# 06 · Prueba de evaluación con modelos reales

**Fecha:** 2026-10-02

## Prompt (textual)

```
YA tengo el .env guardado. Haz la prueba
```

## Comando ejecutado
`research eval vault --limit 6 --judge --config config/groq-only.yaml`

## Resumen del output
- **Primer intento:** los 6 ítems fallaron con 404: tu cuenta de Groq no tiene `llama-3.3-70b-versatile` ni `llama-3.1-8b-instant`. Se listaron los modelos disponibles y se cambió la config a `openai/gpt-oss-120b` (agente y síntesis) y `openai/gpt-oss-20b` (router y juez).
- **Segundo intento:** 4 de 6 preguntas completadas; 2 fallaron por el límite de tokens por minuto (429) del plan gratuito.

| Métrica (4 preguntas, modo notas) | Valor |
|---|---|
| Nota correcta citada | 100 % |
| Cobertura de palabras clave | 87,5 % |
| Afirmaciones respaldadas al primer intento | 95 % |
| Fidelidad del juez LLM (1–5) | 4,5 |
| Cumplimiento del modo (0 llamadas externas) | 100 % |
| Ideas del agente etiquetadas `[IA-n]` | 100 % |
| Costo por pregunta (estimado) | ≈ $0,004 |
| Latencia p50 / p95 | 126 s / 189 s (reintentos por 429) |

- Salvedades: n=4, métricas de veredicto/abstención/DOI en "n/a", costo subestimado (`gpt-oss-20b` sin precio).
- Reporte: `eval/reports/vault-20261002-144026.json`.
- Se ofrecieron tres siguientes pasos (reintentar los 2 fallidos con caché, correr el resto con pausas, reducir contexto o mejorar el plan de Groq).
