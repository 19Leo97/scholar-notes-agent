# 03 · Ejecutar el plan

**Fecha:** 2026-10-01 · **Comando previo:** `/model sonnet` (cambio a `claude-sonnet-5-5`)

## Prompt (textual)

```
perfecto, quiero que ejecutes el plan creado en esta carpeta
```

## Resumen del output
Se construyó el proyecto completo `scholar-notes-agent` (CLI `research`), ~5.500 líneas de Python:

- **Ingesta:** loaders de Obsidian (frontmatter, wikilinks con etiquetas de relación, embeds, URLs, hashes de Notion) y `.txt` (codificaciones antiguas), chunker por encabezados con rangos de línea exactos, pipeline incremental por hash.
- **Indexación y recuperación:** Qdrant local con búsqueda híbrida (denso + BM25 hasheado con IDF, fusión RRF), catálogo SQLite con grafo de wikilinks, MMR, expansión por enlaces, reranker opcional.
- **Agente (LangGraph):** plan → siembra de evidencia → bucle de herramientas → síntesis estructurada → verificación → render. Herramientas de notas, literatura (OpenAlex, Europe PMC, arXiv, Semantic Scholar) y web.
- **Referencias:** almacén de evidencia con IDs `N/P/W`, citas textuales verificadas, DOI contra Crossref/DataCite, ideas del agente como `[IA-n]`, hipótesis propias marcadas.
- **Tokens y privacidad:** presupuesto por consulta, registro de gasto, rechazo de Gemini sin plan de pago, guarda de salida contra fuga de texto de notas, guarda SSRF.
- **Evaluación:** 5 suites (recuperación, verificación, PubMedQA, vault demo, referencias), vault demo público de 19 notas ES/EN.
- **Calidad:** 54 tests, ruff y mypy limpios; docs, CI, Makefile, licencia.
- **Resultado medido:** recuperación en SciFact (188 claims) nDCG@10 = 0,821 (BM25), 0,844 (denso), **0,867 (híbrido)**.
- **Prueba real** con LLM local de 3B: flujo completo correcto, citas literales verificadas.
- **Errores encontrados y corregidos:** wikilinks con `[1]`, `--rebuild` en Windows, SSRF por redirecciones, concurrencia de SQLite/Qdrant.
- **Pendiente declarado:** suites con LLM reales sin ejecutar (faltaban claves).
