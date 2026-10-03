"""Identidad por operador: cada acción sobre un caso queda atribuida a una persona, no a una clave compartida.

`OPERATOR_KEYS` es una lista `nombre=clave` separada por comas. El nombre de quien actúa sale de la clave que presentó,
nunca de un campo que él mismo envíe. Un nombre o una clave repetidos, una clave corta o un nombre mal formado hacen
que la configuración se rechace (el servicio no arranca): dos personas con la misma clave romperían la atribución.
El nombre `demo` está reservado para la consola de la demo del jurado (api/demo_desk.py), que actúa con ese nombre sin clave:
un operador real con ese nombre compartiría su identidad con cualquier visitante, así que la configuración se rechaza.
Vacía, el directorio queda deshabilitado y los endpoints de operador fallan cerrados.

Solo se guarda el hash de cada clave, y los mensajes de error nombran el problema sin imprimir ninguna clave.
Límites: sin MFA, claves en el entorno y rotación manual; en producción esto es SSO corporativo (OIDC).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

MIN_KEY_LENGTH = 24
NAME_RE = re.compile(r"[a-z0-9_.-]{1,40}")
DEMO_ACTOR = "demo"  # the demo console's actor (api/demo_desk.py); no real operator may carry it
RESERVED_NAMES = frozenset({DEMO_ACTOR})


class OperatorConfigError(ValueError):
    pass


def _digest(key: str) -> bytes:
    return hashlib.sha256(key.encode()).digest()


class OperatorDirectory:
    def __init__(self, hashes: dict[str, bytes]):
        self._hashes = hashes

    @classmethod
    def parse(cls, raw: str) -> "OperatorDirectory":
        hashes: dict[str, bytes] = {}
        for position, entry in enumerate((e.strip() for e in raw.split(",")), start=1):
            if not entry:
                continue
            name, sep, key = entry.partition("=")
            if not sep:
                raise OperatorConfigError(f"OPERATOR_KEYS: la entrada {position} no tiene la forma nombre=clave")
            if not NAME_RE.fullmatch(name):
                raise OperatorConfigError(f"OPERATOR_KEYS: nombre inválido {name!r} (permitido: [a-z0-9_.-], 1 a 40 caracteres)")
            if name in RESERVED_NAMES:
                raise OperatorConfigError(f"OPERATOR_KEYS: el nombre {name!r} está reservado para la consola de la demo")
            if len(key) < MIN_KEY_LENGTH:
                raise OperatorConfigError(f"OPERATOR_KEYS: la clave de {name!r} tiene menos de {MIN_KEY_LENGTH} caracteres")
            if name in hashes:
                raise OperatorConfigError(f"OPERATOR_KEYS: el nombre {name!r} está repetido")
            clash = next((other for other, h in hashes.items() if h == _digest(key)), None)
            if clash:
                raise OperatorConfigError(f"OPERATOR_KEYS: {clash!r} y {name!r} comparten la misma clave")
            hashes[name] = _digest(key)
        return cls(hashes)

    @classmethod
    def from_env(cls) -> "OperatorDirectory":
        return cls.parse(os.environ.get("OPERATOR_KEYS", ""))

    @property
    def enabled(self) -> bool:
        return bool(self._hashes)

    def authenticate(self, presented: str | None) -> str | None:
        """The operator this key belongs to, or None. Every key is compared, with no early exit, so the time taken
        does not say how many were tried or which one matched."""
        if not presented:
            return None
        digest, found = _digest(presented), None
        for name, known in self._hashes.items():
            if hmac.compare_digest(digest, known):
                found = name
        return found
