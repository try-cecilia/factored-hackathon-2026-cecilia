"""Huella de las políticas: qué versión del código que decide se midió.

Un reporte de evaluación describe el sistema que existía cuando se generó. La versión del prompt no alcanza para saber
si sigue siendo ese: la regla de revisión de rastreos cambió el comportamiento sin tocar el prompt, y los reportes
quedaron describiendo otro sistema. La huella cubre los archivos donde viven las decisiones y lo que el juez compara:
las políticas, las herramientas (que aplican propiedad y elegibilidad), el orquestador, las plantillas de respuesta y
lo que hay debajo (errores, sesión, privacidad, reintentos, prompt y clasificador de la guarda).

Se normalizan los saltos de línea (`\\r\\n` a `\\n`): en Windows Git puede dejar el árbol de trabajo en CRLF, y el mismo
código tiene que dar la misma huella allí y en el CI. Editar cualquiera de estos archivos, aunque sea un comentario,
cambia la huella y exige volver a medir; es intencional y cuesta minutos.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Qué entra, y por qué. Lo que queda fuera es infraestructura que no cambia un resultado medido: agent/llm/client.py (la
# evaluación usa un modelo simulado), audit.py, state.py y db.py (persistencia), identity.py y operators.py (credenciales
# de la demo), budget.py y experiments.py (apagados por defecto), pricing.py (solo costos).
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
)


def policy_files(root: Path = ROOT) -> list[Path]:
    return sorted({path for pattern in POLICY_GLOBS for path in root.glob(pattern)})


def policy_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in policy_files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()
