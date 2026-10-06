# 05 · Decisiones: config Groq, subconjunto de notas, evaluación demo

**Fecha:** 2026-10-02

## Prompt (textual)

```
Ya he puesto GEMINI_PAID_TIER en false. 1. Si crealo. 2. Solo usa una parte, que no dure mucho. 3. Intenta el vault demo.
```

## Resumen del output
- Creado `config/groq-only.yaml` (los cuatro roles en Groq; solo requiere `GROQ_API_KEY`).
- **Commit `14e1269`** con 108 archivos; `.env` verificado como ignorado.
- Tu carpeta `plasticidad sinaptica` tiene 78 notas (37 CON, 20 RES, 10 PRG, 9 MAPA, 1 SIN, 1 índice). Se copiaron **25 notas CON** a `.cache/user_subset` (sin tocar tu vault) y se indexaron con `bge-m3`: 106 fragmentos en 27 s (~4/s). La búsqueda "qué es la captura sináptica" devolvió notas relevantes.
- Hallazgo: un índice viejo de pruebas usaba otro embedder; el guardia pidió `--rebuild` (comportamiento correcto).
- Se detectó que `GROQ_API_KEY` llegaba **vacía** (el `.env` no estaba guardado), por lo que la evaluación quedó en espera.
