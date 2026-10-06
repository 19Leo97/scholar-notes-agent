# 04 · Estado del `.env`, notas disponibles, commit y CONTACT_EMAIL

**Fecha:** 2026-10-01/02

## Prompt (textual)

```
Ya cree .env. Todavia funcionaria si solo aplico ubico la GROQ_API_KEY?, ya puse GOOGLE_API_KEY pero no logre aun pagar la version paga, sin embargo le puse TRUE a GEMINI_PAID_TIER. Mis notas todavia no estan cargadas sin embargo hay algunas disponibles en "C:\Users\david\Downloads\Obsidian vaults\Neuro\plasticidad sinaptica" que no importa si son privadas. Ya he ejecutado ollama pull bge-m3. Quiero que hagas commit a lo que ya hiciste. Y luego si hagas los cambios que vengan, entiendo que es correr research eval vault --limit 6 --judge. Antes de que hagas algo, respondeme las preguntas pertinentes. Ah, y tambien, quiero saber que debo ubicar en CONTACT_EMAIL y por qué?
```

## Resumen del output (solo respuestas, sin ejecutar nada)
- **Solo `GROQ_API_KEY` no basta** con la config por defecto (la síntesis usa Gemini). Poner `GEMINI_PAID_TIER=true` sin plan de pago anula la protección de privacidad con una afirmación falsa; se recomendó `false` y una config solo-Groq.
- **CONTACT_EMAIL:** correo opcional enviado como `mailto` a OpenAlex y Crossref para su "polite pool" (mejor rendimiento y contacto en caso de problemas). Viaja en la URL a terceros; usar uno que no importe exponer. Vacío también funciona.
- Se confirmó que `.env` está en `.gitignore` y se verificaría antes del commit.
- **Tres preguntas:** crear `config/groq-only.yaml`, cuánto de las notas reales indexar, y orden de la evaluación (demo primero).
