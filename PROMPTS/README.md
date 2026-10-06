# PROMPTS

Registro organizado de los prompts del proyecto `scholar-notes-agent`, los planes generados y el resumen de lo que produjo cada uno.
Los textos de `01-prompts-del-usuario/` son tus mensajes copiados tal cual; los resúmenes son mi síntesis del resultado.

## Índice

| # | Archivo | Fecha | Qué pediste | Resumen del output |
|---|---|---|---|---|
| 00 | [01-prompts-del-usuario/00_instruccion-global.md](01-prompts-del-usuario/00_instruccion-global.md) | persistente | Código en inglés, respuestas en español | Todo el código/docs en inglés; respuestas en español |
| 01 | [01_solicitud-inicial.md](01-prompts-del-usuario/01_solicitud-inicial.md) | 2026-10-01 | Plan de un agente RAG + tool calling sobre notas, literatura y web | Exploración del vault, 4 preguntas y plan completo |
| 02 | [02_respuestas-decisiones-tecnicas.md](01-prompts-del-usuario/02_respuestas-decisiones-tecnicas.md) | 2026-10-01 | LangGraph, CLI, md + txt, Groq + Gemini pago | Plan finalizado con esas decisiones |
| 03 | [03_ejecutar-plan.md](01-prompts-del-usuario/03_ejecutar-plan.md) | 2026-10-01 | Ejecutar el plan | Proyecto completo, 54 tests, E1 medida (híbrido nDCG@10 0,867) |
| 04 | [04_preguntas-env-y-contact-email.md](01-prompts-del-usuario/04_preguntas-env-y-contact-email.md) | 2026-10-01/02 | Dudas sobre `.env`, commit, CONTACT_EMAIL | Respuestas y 3 preguntas, sin ejecutar nada |
| 05 | [05_decisiones-config-ingesta-commit.md](01-prompts-del-usuario/05_decisiones-config-ingesta-commit.md) | 2026-10-02 | Config Groq, subconjunto de notas, eval demo | `groq-only.yaml`, commit `14e1269`, 25 notas indexadas |
| 06 | [06_prueba-eval-vault.md](01-prompts-del-usuario/06_prueba-eval-vault.md) | 2026-10-02 | Correr la evaluación | 404 por modelos no disponibles, luego 4/6 ítems con métricas |
| 07 | [07_carpeta-prompts.md](01-prompts-del-usuario/07_carpeta-prompts.md) | 2026-10-05 | Esta carpeta | Este registro |
| 08 | [08_guia-visual-html.md](01-prompts-del-usuario/08_guia-visual-html.md) | 2026-10-05 | Guía visual interactiva en HTML (arquitectura, ADRs, evaluaciones, código) | `docs/guide.html`; incluye modelo, esfuerzo, modo y tiempo (≈ 17 min) |

## Otras secciones
- [02-planes/](02-planes/README.md): el plan generado y su estado de ejecución.
- [03-prompts-internos-del-agente/](03-prompts-internos-del-agente/README.md): prompts de sistema que usa el agente (`plan`, `research`, `synthesize`).

## Notas
- El mensaje 03 fue precedido por el comando `/model sonnet`.
- Las respuestas del asistente no se transcriben completas; solo su resumen. Lo exacto está en el código, `docs/` y `eval/reports/`.
- Esta carpeta no contiene claves ni datos de tus notas. No está commiteada todavía.
