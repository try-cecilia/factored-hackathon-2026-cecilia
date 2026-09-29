"""Validación de buenas prácticas de datos y ML: un comando, un reporte de evidencia.

Corre `tests/test_data_ml_validation.py` (una prueba por afirmación de los documentos; herméticas: warehouse de
prueba, sin S3 ni claves) y escribe `docs/evidence/data_ml_validation.md` y `.json` con el resultado por criterio:
PASS o FAIL, la evidencia que cada prueba registró y el comando que lo reproduce. Un criterio pasa solo si corrieron
pruebas y todas pasaron: una prueba omitida o que no se pudo recolectar cuenta como FAIL.

    python -m eval.validate_data_ml        # sale con código 1 si algún criterio no pasa
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from data.pipeline import _git_sha

ROOT = Path(__file__).resolve().parent.parent
TESTS = "tests/test_data_ml_validation.py"
OUT_MD = ROOT / "docs" / "evidence" / "data_ml_validation.md"
OUT_JSON = ROOT / "docs" / "evidence" / "data_ml_validation.json"

# prefijo de las pruebas -> criterio, y el documento que hace la afirmación
CRITERIA = [
    ("contracts", "Contratos", "docs/data_quality.md (Pipeline, pasos 2-5), data/contracts.py"),
    ("quality", "Calidad", "docs/data_quality.md (Pipeline paso 4, Findings)"),
    ("lineage", "Linaje", "docs/data_quality.md (Pipeline paso 8), data/lineage.py"),
    ("freshness", "Política de frescura", "docs/data_quality.md (Update and freshness policy)"),
    ("learned", "Componente aprendido contra una línea base", "EVALUATION.md §2, eval/reports/intent_classifier.md"),
    ("leakage", "Sin fuga de datos", "EVALUATION.md §2, eval/leakage.py, LIMITATIONS.md (Data and ML)"),
]

# Lo que estas pruebas no cierran y está declarado, para que el reporte no parezca más de lo que es.
DECLARED = [
    "Los textos de entrenamiento y de held-out los escribió el mismo equipo (LIMITATIONS.md, «No usable text»): la "
    "diferencia con la línea base es real en este held-out, no una medida sobre clientes reales.",
    "El orden cronológico (entrenamiento y línea base congelados antes de escribir el held-out) no se puede probar con "
    "el historial de git, que empieza en una sola importación; lo que sí se prueba es que los archivos no cambiaron desde "
    "que se midieron (hashes).",
    "Los cortes de similitud (0.90 y 0.60) se fijaron mirando la distribución de todo el held-out, dev y test juntos; "
    "una frase se dejó fuera (LIMITATIONS.md).",
    "La decisión de no reentrenar el clasificador con ejemplos de rastreo se tomó viendo el split de test "
    "(LIMITATIONS.md, «The action»).",
    "Una similitud de caracteres no ve una paráfrasis con otras palabras (eval/leakage.py).",
    "El reporte de calidad de la corrida completa (`data/reports/quality_report.json`) sale del bucket del organizador y "
    "no se regenera aquí; estas pruebas comprueban que el documento lo cita bien, no que los datos sigan siendo esos.",
]


def run_tests(xml_path: Path) -> subprocess.CompletedProcess:
    # junit_family=legacy: the only family that takes the per-test `evidence` property without a warning
    command = [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider", "-o", "junit_family=legacy",
               f"--junitxml={xml_path}"]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def parse(xml_path: Path) -> list[dict]:
    if not xml_path.exists():
        return []
    out = []
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        status = "PASS"
        detail = ""
        if problem is not None:
            status, detail = "FAIL", (problem.get("message") or problem.text or "").strip().splitlines()[0][:300]
        elif case.find("skipped") is not None:
            status, detail = "FAIL", "omitida: un chequeo que no corre no cuenta como aprobado"
        evidence = next((p.get("value") for p in case.iter("property") if p.get("name") == "evidence"), "")
        out.append({"test": case.get("name"), "status": status, "evidence": evidence, "detail": detail})
    return out


def summarize(cases: list[dict]) -> list[dict]:
    rows = []
    for prefix, title, source in CRITERIA:
        mine = [c for c in cases if c["test"].startswith(f"test_{prefix}_")]
        ok = bool(mine) and all(c["status"] == "PASS" for c in mine)
        rows.append({"id": prefix, "criterion": title, "source": source, "status": "PASS" if ok else "FAIL", "tests": mine,
                     "command": f"python -m pytest {TESTS} -k test_{prefix}_ -q"})
    return rows


def _title(test: str, prefix: str) -> str:
    return test.removeprefix(f"test_{prefix}_").replace("_", " ")


def to_markdown(rows: list[dict], generated_at: str, code: str, pytest_line: str) -> str:
    verdict = "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL"
    summary = "\n".join(f"| {r['criterion']} | **{r['status']}** | {sum(t['status'] == 'PASS' for t in r['tests'])}/{len(r['tests'])} | "
                        f"`{r['command']}` |" for r in rows)
    detail = []
    for r in rows:
        lines = "\n".join(f"| {_title(t['test'], r['id'])} | {t['status']} | {t['evidence'] or t['detail']} |" for t in r["tests"])
        detail.append(f"### {r['criterion']}: {r['status']}\n\nAfirma: {r['source']}.\n\n| Prueba | Resultado | Evidencia |\n|---|---|---|\n"
                      f"{lines or '| (ninguna prueba corrió) | FAIL | |'}")
    declared = "\n".join(f"- {d}" for d in DECLARED)
    return f"""# Validación de buenas prácticas de datos y ML (auto-generado)

Generado por `make validate-data-ml` (`python -m eval.validate_data_ml`) el {generated_at} sobre el código `{code}`.
Rúbrica: «Buena práctica de datos y ML: contratos, calidad, linaje, política de frescura, y al menos un componente aprendido
contra una línea base, sin fuga de datos». Resultado global: **{verdict}**. {pytest_line}

Cada fila es una prueba de `{TESTS}`: hermética (warehouse de prueba de `tests/fixtures`, sin S3 ni claves), y falla si la
frase del documento que cita deja de ser cierta. Las cifras de la evidencia salen de la propia prueba, no se escriben a mano.

| Criterio | Resultado | Pruebas | Comando |
|---|---|---|---|
{summary}

{(chr(10) * 2).join(detail)}

## Lo que esto no cierra (declarado)

{declared}
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "junit.xml"
        proc = run_tests(xml_path)
        cases = parse(xml_path)
    rows = summarize(cases)
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    pytest_line = f"pytest: {lines[-1].strip('= ')}." if lines else "pytest no produjo salida."
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(to_markdown(rows, generated_at, _git_sha(), pytest_line), encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"generated_at": generated_at, "code_version": _git_sha(), "pytest": pytest_line, "criteria": rows},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    for r in rows:
        print(f"{r['status']}  {r['criterion']}  ({sum(t['status'] == 'PASS' for t in r['tests'])}/{len(r['tests'])})")
    failed = [r for r in rows if r["status"] != "PASS"]
    if proc.returncode != 0 or failed:
        print(proc.stdout[-3000:])
    print(f"evidencia: {OUT_MD.relative_to(ROOT)}")
    return 1 if failed or proc.returncode != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
