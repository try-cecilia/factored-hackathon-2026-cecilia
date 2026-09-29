"""Huella de las políticas: qué versión del código que decide se midió.

Un reporte de evaluación describe el sistema que existía cuando se generó. La versión del prompt no alcanza para saber
si sigue siendo ese: la regla de revisión de rastreos cambió el comportamiento sin tocar el prompt, y los reportes
quedaron describiendo otro sistema. La huella cubre los archivos donde viven las decisiones: las políticas, las
herramientas (que aplican propiedad y elegibilidad) y el orquestador.

Se normalizan los saltos de línea (`\\r\\n` a `\\n`): en Windows Git puede dejar el árbol de trabajo en CRLF, y el mismo
código tiene que dar la misma huella allí y en el CI. Editar cualquiera de estos archivos, aunque sea un comentario,
cambia la huella y exige volver a medir; es intencional y cuesta minutos.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_GLOBS = ("agent/policy/*.py", "agent/tools/account_tools.py", "agent/core/orchestrator.py")


def policy_files(root: Path = ROOT) -> list[Path]:
    return sorted({path for pattern in POLICY_GLOBS for path in root.glob(pattern)})


def policy_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in policy_files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()
