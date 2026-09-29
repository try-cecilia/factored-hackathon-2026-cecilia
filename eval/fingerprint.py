"""Huella de la evaluación: qué versión del sistema, del juez y de los casos se midió (en los reportes: `policy_sha256`).

Un reporte de evaluación describe el sistema que existía cuando se generó. La versión del prompt no alcanza para saber
si sigue siendo ese: la regla de revisión de rastreos cambió el comportamiento sin tocar el prompt, y los reportes
quedaron describiendo otro sistema. La huella cubre los archivos donde viven las decisiones y lo que el juez compara:
las políticas, las herramientas (que aplican propiedad y elegibilidad), el orquestador, las plantillas de respuesta y
lo que hay debajo (errores, sesión, privacidad, reintentos, prompt y clasificador de la guarda). También cubre lo que
decide qué cuenta como acierto: el juez, los modelos simulados (ideal y adversarial), la línea base, los casos con su
resultado esperado y el warehouse de prueba del set reservado. Cambiar el criterio del juez o el gold sin volver a medir
dejaba la compuerta en verde con reportes que ya no describían esta evaluación.

Se normalizan los saltos de línea (`\\r\\n` a `\\n`): en Windows Git puede dejar el árbol de trabajo en CRLF, y el mismo
código tiene que dar la misma huella allí y en el CI. Editar cualquiera de estos archivos, aunque sea un comentario,
cambia la huella y exige volver a medir; es intencional y cuesta minutos.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Qué entra, y por qué. Lo que queda fuera no cambia un resultado medido: agent/llm/client.py (la evaluación usa un modelo
# simulado), audit.py, state.py y db.py (persistencia), identity.py y operators.py (credenciales de la demo), budget.py y
# experiments.py (apagados por defecto), pricing.py (solo costos). En eval/: gate.py (los pisos juzgan el reporte, no lo
# producen), tracking.py (registro en MLflow), keyword_llm.py (modelo del servidor de pruebas, ops/serve_fixture.py),
# live_sample.py, leakage.py, operator_labels.py, evaluate_intent_classifier.py y validate_data_ml.py (otras evaluaciones),
# reports/ (es la salida), test_cases/ (datos del clasificador, que entra ya entrenado como .joblib) y
# workload/cases_dev.jsonl (solo alimenta el reporte de desarrollo, que la compuerta no compara).
POLICY_GLOBS = (
    "agent/policy/*.py",                  # router, guarda, escalación, mesa: las decisiones
    "agent/core/orchestrator.py",         # aplica las decisiones, el modo degradado y los traspasos
    "agent/core/render.py",               # plantillas (render.MSG): el juez compara las respuestas contra ellas
    "agent/tools/account_tools.py",       # propiedad y elegibilidad de cada consulta
    "agent/tools/traces.py",              # pedidos de rastreo: alta, duplicados, SLA
    "agent/tools/errors.py",              # qué excepción de herramienta significa qué desenlace
    "agent/session/auth.py",              # vencimiento y validez de la sesión
    "agent/llm/privacy.py",               # qué se enmascara antes de salir hacia el modelo
    "agent/llm/prompts.py",               # lo que ve el modelo, aunque no suba PROMPT_VERSION
    "agent/resilience.py",                # plazos y reintentos: definen cuándo falla una herramienta o el turno
    "eval/models/intent_clf.joblib",      # el clasificador que alimenta la guarda de escalación en ejecución
    "eval/models/intent_clf_meta.json",   # ...y su umbral
    "eval/run_system_eval.py",            # el juez (disposition_ok, seguridad, traspaso), los fallos simulados y el modelo ideal y adversarial
    "eval/categories.py",                 # cómo se agrupa y qué cuenta como resuelto o seguro por categoría
    "eval/failure_eval.py",               # el reporte por categoría de fallo
    "eval/heldout.py",                    # el set reservado, su parche del warehouse y su escritura
    "eval/workload.py",                   # generador de casos, gold y el oráculo de cada tipo
    "eval/stats.py",                      # los intervalos y tasas que se publican
    "eval/baseline_bot.py",               # la línea base contra la que se compara
    "eval/fake_llm.py",                   # modelo simulado: las respuestas del modelo ideal
    "eval/workload/cases_test.jsonl",     # los casos del split de test con su resultado esperado
    "eval/heldout/*.jsonl",               # los casos reservados con su resultado esperado
    "tests/fixtures/raw/**/*.csv",        # el warehouse de prueba sobre el que corre el set reservado
)
TEXT_SUFFIXES = {".py", ".json", ".jsonl", ".csv"}


def policy_files(root: Path = ROOT) -> list[Path]:
    return sorted({path for pattern in POLICY_GLOBS for path in root.glob(pattern)})


def policy_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in policy_files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()
