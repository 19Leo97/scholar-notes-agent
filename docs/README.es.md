# scholar-notes-agent (resumen en español)

Agente de investigación que responde preguntas y **verifica ideas** combinando tres fuentes: tus notas
personales (Markdown de Obsidian y `.txt`), la literatura científica y la web. Hecho para neurociencia
teórica, pero no depende del dominio.

## Qué lo caracteriza

* **Todo queda referenciado.** Notas: archivo, líneas y `[[enlace#sección]]`. Artículos: referencia APA + DOI
  verificado en Crossref/DataCite. Web: URL y fecha de acceso. Cada afirmación lleva una cita textual que se
  comprueba contra la fuente; las afirmaciones sin respaldo se eliminan de la respuesta.
* **Las ideas del agente van marcadas** como `[IA-n]`, con la evidencia que las inspiró, separadas de lo que
  dicen las fuentes. Tus notas `HIP —` se muestran como "tu hipótesis", nunca como hecho establecido.
* **Tú eliges las fuentes:** `--mode notes` (solo tus notas, cero llamadas externas), `--mode literature`
  (artículos y web) o `--mode hybrid`.
* **Privacidad:** embeddings e índice locales; al proveedor del LLM solo llegan la pregunta y los fragmentos
  elegidos; la app se niega a usar Gemini sin confirmar plan de pago; se bloquean consultas externas que copien
  texto de tus notas. Ver [privacy.md](privacy.md).
* **Control de tokens:** presupuesto por consulta, modelos distintos por rol, salidas compactas, cachés y un
  registro (`research usage`). Cada respuesta muestra tokens y costo. Ver [token-efficiency.md](token-efficiency.md).
* **Evaluación con datos externos** (SciFact, PubMedQA) antes de usar tus notas. Ver [evaluation.md](evaluation.md).

## Uso rápido

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env          # agrega GROQ_API_KEY y, si usas Gemini, GOOGLE_API_KEY y GEMINI_PAID_TIER=true
ollama pull bge-m3              # embeddings multilingües locales

research ingest "C:/ruta/a/tu/vault"          # indexa .md y .txt de forma incremental
research doctor                               # notas vacías, duplicadas, huérfanas, enlaces rotos
research search "captura sináptica"           # solo recuperación, 0 tokens de LLM
research ask "¿Qué relación hay entre BCM y LTD?" --mode notes
research ask "Mi idea: la metaplasticidad estabiliza engramas" --mode hybrid --budget 0.03 --save
research eval retrieval                       # evaluación externa (SciFact)
```

`--save` guarda la respuesta como una nota `SIN —` compatible con tu vault.

## Con tus +3000 notas

1. `research ingest <vault>` (la primera vez tarda por los embeddings; luego solo procesa lo que cambió).
2. `research doctor` para ver el estado del desorden sin gastar tokens.
3. Prueba `research search` para comprobar que encuentra lo que esperas antes de gastar en `ask`.
4. Cuando quieras evaluar sobre tus notas, hazlo en `eval/private/` (ignorado por git).
