# 08 · Guía visual interactiva en HTML

**Fecha:** 2026-10-05

## Metadatos de ejecución

| Dato | Valor |
|---|---|
| Modelo | `claude-sonnet-5-5` (Sonnet 5.5) |
| Esfuerzo de razonamiento | 30 (nivel configurado para este turno) |
| Modo del agente | Ejecución normal (no plan mode), con permisos en modo *bypass* |
| Tiempo de ejecución | **≈ 17 minutos** de reloj (18:58:38 → 19:15:01 hasta terminar la guía: 16 min 23 s; más ≈ 1 min para este registro) |
| Incluye | Escribir ~3.000 líneas de contenido y código de la guía, construirla, validarla en Chrome sin interfaz (16 rutas sin errores de consola), revisar capturas, corregir el diagrama y encontrar y arreglar un bug real |

## Prompt (textual)

```
Perfecto, ahora quiero que crees una guia visual en HTML que explique la arquitectura de este proyecto, que analize las ADRs (me refiero a por que se tomaron las decisiones que se tomaron sobre las alternativas que existian, menciona 3 alternativas, y que te haria replantearte escoger otra alternativa, ademas una opinion honesta sobre los pro y contra de la alternativa escogida). Ademas que se mencionen todas las iteraciones/evaluaciones realizadas, acciones de ingenieria importantes tomadas, conceptos relevantes y demás. Quiero que esta guia permita entender muy facilmente la idea global del proyecto asi como cada detalle del mismo, que se pueda entender muy bien para que sirve cada codigo y sus funciones, como estan organizados los archivos del mismo proyecto. El objetivo es que en el menor tiempo posible alguien que no tiene idea del proyecto mismo pueda visualizar esta guia interactiva y entender desde lo general hasta lo especifico, que pueda tomar decisiones para bien escalar o modificar el proyecto mismo sabiendo que implican dichas acciones. (anota este prompt tambien en la carpeta prompts e incluye el modelo y esfuerzo usado, el modo del agente y cuanto tiempo tomo ejecutar la tarea)
```

## Resumen del output

Se creó **`docs/guide.html`** (254 KiB, un solo archivo sin dependencias externas; se abre con doble clic en cualquier navegador, con modo claro/oscuro y buscador global con la tecla `/`).

- **10 secciones** en tres niveles de profundidad: *Visión global* → *Arquitectura* y *Recorrido* → *Mapa del código*, *ADRs*, *Conceptos*, *Evaluaciones*, *Ingeniería*, *Escalar/modificar* y *Referencia*.
- **Arquitectura interactiva:** diagramas SVG clicables del flujo de consulta y de ingesta (qué hace cada caja, dónde está, qué recibe/entrega, cuándo falla), capas con sus reglas y dónde viven los datos.
- **Recorrido paso a paso** de una pregunta real, con contadores de llamadas, tokens y evidencias, y una casilla que simula una cita inventada y la reparación.
- **Mapa del código:** 44 archivos, 85 clases y 242 funciones, con descripción en español, «usa / lo usan» y pruebas que los cubren, **extraídos del código con `ast`** para que no se desfasen.
- **15 ADRs:** cada uno con contexto, decisión, **3 alternativas** y por qué se descartaron, **qué me haría replantearla**, pros y contras honestos (incluidos los fallos reales: Qdrant local no es seguro entre hilos, bug de `--rebuild` en Windows, 429 de Groq, `GEMINI_PAID_TIER` auto-declarado) y costo de cambiarla.
- **Evaluaciones e iteraciones:** las dos corridas de recuperación (hash vs nomic), los dos intentos del vault demo, las pruebas locales, el crecimiento de pruebas 36 → 54, una línea de tiempo y la lista explícita de **lo que no se ha evaluado**.
- **22 acciones de ingeniería** (bugs, seguridad, robustez, rendimiento, calidad, proceso), **30 conceptos** de glosario, **14 objetivos «quiero…»** con pasos/implicaciones/verificación, 13 perillas de configuración y una tabla de qué se rompe al escalar.
- Archivos nuevos: `docs/build_guide.py`, `docs/guide_src/` (fuente editable) y el enlace desde `README.md`. Regenerar: `python docs/build_guide.py`.

**Hallazgo durante la tarea:** al existir tu `.env` real, la prueba `test_gemini_free_tier_is_refused` falló porque la variable de entorno pisaba las sobreescrituras explícitas. Se corrigió la precedencia en `config.py` (defaults < YAML < entorno < sobreescrituras) y las 54 pruebas, ruff y mypy quedaron en verde.

**Límites declarados en la guía:** el esfuerzo/riesgo de los cambios y las opiniones de los ADRs son estimaciones mías; los tokens del recorrido son ilustrativos (calibrados con una corrida real); no se probó en Firefox/Safari ni en móvil real, solo Chrome sin interfaz.
