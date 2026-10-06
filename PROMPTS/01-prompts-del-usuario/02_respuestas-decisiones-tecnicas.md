# 02 · Respuestas a las preguntas de aclaración

**Fecha:** 2026-10-01 · **Modo:** plan

## Prompt (textual, selecciones y texto libre)

| Pregunta | Tu respuesta |
|---|---|
| ¿Qué framework de orquestación del agente prefieres? | LangGraph (Recommended) |
| ¿Qué interfaces quieres en la v1? | CLI (Typer) |
| ¿En qué formatos están tus +3000 notas? | Markdown Obsidian, "pueden ser tambien archivos .txt sin algun formato dado" |
| ¿Qué proveedor de LLM quieres como predeterminado? | Groq + Gemini pago (Recommended) |

## Resumen del output
- Plan finalizado con esas decisiones: LangGraph, solo CLI, loaders para `.md` de Obsidian y `.txt` plano, Groq (router/agente/juez) + Gemini de pago (síntesis).
- Se explicó que el tier gratuito de Gemini puede entrenar con los datos, por lo que la app se negaría a usarlo sin confirmación de plan de pago.
- Se presentó el plan para aprobación; luego pasaste a ejecución (ver `03_ejecutar-plan.md`).
