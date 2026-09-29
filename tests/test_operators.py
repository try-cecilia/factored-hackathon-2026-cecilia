"""El directorio de operadores: una clave da un nombre, y una configuración mala impide arrancar sin filtrar claves."""
from __future__ import annotations

import pytest

from agent.session.operators import OperatorConfigError, OperatorDirectory

ANA = "ana-key-0123456789-abcdefgh"
BETO = "beto-key-0123456789-abcdefg"


def directory():
    return OperatorDirectory.parse(f"ana={ANA},beto={BETO}")


def test_a_valid_key_gives_its_name_and_anything_else_gives_nothing():
    d = directory()
    assert d.authenticate(ANA) == "ana" and d.authenticate(BETO) == "beto"
    for bad in (None, "", "nope", ANA + "x", ANA[:-1], ANA.upper()):
        assert d.authenticate(bad) is None


def test_an_empty_config_is_a_disabled_directory_that_authenticates_nobody():
    for raw in ("", "   ", " , "):
        d = OperatorDirectory.parse(raw)
        assert not d.enabled and d.authenticate(ANA) is None
    assert directory().enabled


def test_a_key_may_contain_an_equals_sign():
    key = "base64-looking-key-0123456789=="
    assert OperatorDirectory.parse(f"ana={key}").authenticate(key) == "ana"


@pytest.mark.parametrize("raw", [
    f"ana={ANA},ana={BETO}",       # the same name twice
    f"ana={ANA},beto={ANA}",       # two people, one key
    "ana=short",                   # key under 24 characters
    f"Ana={ANA}",                  # name outside [a-z0-9_.-]
    f"{'a' * 41}={ANA}",           # name over 40 characters
    f"={ANA}",                     # no name
    f"ana{ANA}",                   # no name=key form
])
def test_a_bad_config_stops_the_start_and_never_prints_a_key(raw):
    with pytest.raises(OperatorConfigError) as err:
        OperatorDirectory.parse(raw)
    assert ANA not in str(err.value) and BETO not in str(err.value) and "short" not in str(err.value)


def test_from_env_reads_operator_keys(monkeypatch):
    monkeypatch.setenv("OPERATOR_KEYS", f"ana={ANA}")
    assert OperatorDirectory.from_env().authenticate(ANA) == "ana"
    monkeypatch.delenv("OPERATOR_KEYS")
    assert not OperatorDirectory.from_env().enabled
