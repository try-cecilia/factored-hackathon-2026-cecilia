# Pendientes

Lo que falta después de que las alertas (punto 6) y el reporte de calidad en vivo (punto 5) queden cerrados.
Estado al 2026-09-29.

## 3b. Evaluar el camino humano

**Qué falta:** medir por separado el camino en que una persona interviene (escalación a operador, aprobación,
feedback), aparte de la automatización controlada que ya está mergeada y medida (punto 3).

**Se puede hacer ya:** no depende de datos nuevos. El código de operadores y aprobación está mergeado
(`agent/session/operators.py`, `agent/policy/escalation.py`, `eval/operator_labels.py`).

**Criterio de cierre:** un reporte en `eval/reports/` con las mismas métricas que el resto de la evaluación del
sistema, medidas solo sobre los casos que pasan por una persona, y una sección en `EVALUATION.md` que lo cite.

## 3c. Evaluar la pantalla de operador

**Qué falta:** evaluar la pantalla que usa el operador (la vista web de `web/` que consume la API de `api/`) como
pieza aparte: qué ve, qué puede aprobar o rechazar y qué queda registrado de lo que hace (la API exige la clave de operador,
`require_operator` en `api/main.py`).

**Se puede hacer ya:** sí, contra el demo local.

**Criterio de cierre:** una lista de casos recorridos a mano o con prueba automática (`tests/test_api.py` como
punto de partida), con el resultado de cada uno, y las fallas anotadas en `LIMITATIONS.md`.

## 4. Datos y ML

**Estado:** la herramienta ya está mergeada, pero **no hay resultados** y no hay nada que hacer todavía.

**Bloqueo:** hacen falta mensajes escritos por personas reales. Las transcripciones del organizador no sirven
(42 textos distintos de cliente, todos sobre saldo; ver `docs/data_quality.md`). Los mensajes vienen del
formulario descrito en `docs/human_set.md`, con piso de 60 mensajes de 8 personas.

**Cuando se desbloquee:**
1. Bajar los mensajes de la base D1 del formulario y anonimizarlos como indica `docs/human_set.md`.
2. Correr la herramienta de datos y ML sobre ellos.
3. Registrar el resultado en `EVALUATION.md`. Si no se llega al piso, decirlo ahí y no reportarlo como resultado.

**Ojo con el plazo:** la base D1 se borra después de la final (16/10/2026), así que hay que exportar los mensajes
antes.
