"""Huella de la evaluación: qué versión del sistema, del juez y de los casos se midió (en los reportes: `policy_sha256`).

Un reporte de evaluación describe el sistema que existía cuando se generó. La versión del prompt no alcanza para saber
si sigue siendo ese: la regla de revisión de rastreos cambió el comportamiento sin tocar el prompt, y los reportes
quedaron describiendo otro sistema. La huella cubre los archivos donde viven las decisiones y lo que el juez compara:
las políticas, las herramientas (que aplican propiedad y elegibilidad), el orquestador, las plantillas de respuesta y
lo que hay debajo (errores, sesión, privacidad, reintentos, prompt y clasificador de la guarda). También cubre lo que
decide qué cuenta como acierto: el juez, los modelos simulados (ideal y adversarial), la línea base, los casos con su
resultado esperado y el warehouse de prueba del set reservado. Cambiar el criterio del juez o el gold sin volver a medir
dejaba la compuerta en verde con reportes que ya no describían esta evaluación. El criterio es todo lo que la evaluación
offline importa y ejecuta (un test lo comprueba), no lo que parece importante: un módulo de "infraestructura" que hace la
llamada al modelo o tope el gasto de una sesión cambia resultados igual.

Se normalizan los saltos de línea (`\\r\\n` a `\\n`) solo en los archivos de texto; los binarios, como el .joblib, se
hashean tal cual. En Windows Git puede dejar el árbol de trabajo en CRLF, y el mismo código tiene que dar la misma huella
allí y en el CI. Editar cualquiera de estos archivos, aunque sea un comentario,
cambia la huella y exige volver a medir; es intencional y cuesta minutos.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Qué entra, y por qué. Criterio: todo lo que la evaluación offline importa y ejecuta, porque cualquiera de esos módulos puede
# cambiar un resultado (un test lo comprueba importando la evaluación). Por eso entra todo `agent/`: las decisiones
# (policy/, orchestrator), las plantillas que el juez compara (core/render.py), la llamada primaria al modelo simulado
# (core/experiments.py, llm/client.py), el tope de gasto por sesión que degrada un turno (llm/budget.py, llm/pricing.py), las
# herramientas y sus errores, la sesión, la privacidad, el prompt, los reintentos y plazos, y la persistencia (tools/state.py,
# audit.py, db.py) de la que dependen las novedades de un caso. Del resto del árbol:
#   eval/     el juez, los modelos simulados, la línea base, los casos con su resultado esperado y el clasificador de la guarda
#   data/     la ingesta que arma el warehouse de prueba del set reservado
#   tests/fixtures/raw   los CSV de ese warehouse
# Quedan fuera, en NOT_MEASURED, los módulos de agent/ que la evaluación no importa (credenciales de la demo, entrenamiento
# del clasificador), y en eval/ y data/: gate.py (los pisos juzgan el reporte, no lo producen), tracking.py (registro en
# MLflow), keyword_llm.py (modelo del servidor de pruebas), live_sample.py, leakage.py, operator_labels.py,
# evaluate_intent_classifier.py y validate_data_ml.py (otras evaluaciones), data/lineage.py (metadatos), reports/ (es la
# salida), test_cases/ (datos del clasificador, que entra ya entrenado como .joblib) y workload/cases_dev.jsonl (solo
# alimenta el reporte de desarrollo, que la compuerta no compara).
POLICY_GLOBS = (
    "agent/**/*.py",
    "eval/models/intent_clf.json",        # el modelo que se carga en ejecución (JSON, sin pickle)
    "eval/models/intent_clf.joblib",      # el clasificador que alimenta la guarda de escalación en ejecución
    "eval/models/intent_clf_meta.json",   # ...y su umbral
    "agent/policy/payment_rules.json",    # el catálogo de reglas de pago por país: comisiones, plazos y su fuente
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
    "data/contracts.py", "data/pipeline.py", "data/quality.py", "data/sources.py",  # la ingesta del warehouse de prueba
    "tests/fixtures/raw/**/*.csv",        # el warehouse de prueba sobre el que corre el set reservado
)
NOT_MEASURED = ("agent/session/identity.py", "agent/session/operators.py", "agent/session/secure_compare.py",
                "agent/llm/intent_classifier.py")
TEXT_SUFFIXES = {".py", ".json", ".jsonl", ".csv"}


LOCAL_PARTS = {"__pycache__", "site-packages", "node_modules", "venv"}  # los que .gitignore lista; ni env, build ni dist: no los ignora y podrían ser código


def _is_local(path: Path, root: Path) -> bool:
    """Lo que vive en la máquina de quien desarrolla y git ignora (un entorno virtual, cachés, dependencias): no es el sistema
    medido. Se decide por la ruta y por `pyvenv.cfg` (el marcador de todo entorno virtual, se llame como se llame) y no con
    `git ls-files`, para que dé lo mismo con y sin `.git` (CI, `git archive`)."""
    parts = path.relative_to(root).parts
    if any(part.startswith(".") or part in LOCAL_PARTS for part in parts):
        return True
    return any((root.joinpath(*parts[:depth]) / "pyvenv.cfg").exists() for depth in range(1, len(parts)))


def policy_files(root: Path = ROOT) -> list[Path]:
    skipped = {root / rel for rel in NOT_MEASURED}
    return sorted({path for pattern in POLICY_GLOBS for path in root.glob(pattern) if not _is_local(path, root)} - skipped)


def policy_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in policy_files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        data = path.read_bytes()
        digest.update((data.replace(b"\r\n", b"\n") if path.suffix in TEXT_SUFFIXES else data) + b"\0")
    return digest.hexdigest()
