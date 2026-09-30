"""The labeling page of the human-written set (docs/human_set.md): one self-contained HTML file per labeler.

    python -m eval.human_set.classifier_eval page --labeler NAME [--labeler NAME ...] [--only-disagreements]

Each labeler gets a file instead of the CSV: it opens from the file system in a desktop or phone browser, shows each
message next to the situation its writer was given (the Spanish text of the form itself, `worker.js`, so the two can
never differ), and downloads `human_labels_<name>.csv` with the sheet's columns and the label filled in, which
`agreement` reads as is. The page shows no output of the system, makes no network call (its Content-Security-Policy
forbids one) and keeps the progress in the browser when the browser allows it. Its logic is `labeling_page.mjs`,
inlined as is and tested with node. `--only-disagreements` builds the third person's page: only the messages the
first two labeled differently.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).parent
WORKER_JS = HERE / "worker.js"
LOGIC_JS = HERE / "labeling_page.mjs"
CHOICES = (("matches", "Coincide"), ("ambiguous", "Ambiguo"), ("something_else", "Otra cosa"))
LANGUAGE = {"es": "Mensaje en español", "pt": "Mensaje en portugués"}
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
STYLE = """:root{--bg:#f6f4ef;--card:#fff;--ink:#1d2a28;--mute:#5b6664;--line:#d9d6ce;--accent:#0e5c52;--on-accent:#fff;--warn:#fff4dc;--done:#e3f1ee}
@media (prefers-color-scheme:dark){:root{--bg:#121816;--card:#1b2321;--ink:#e8ecea;--mute:#a3aeab;--line:#33403d;--accent:#5cc2b2;--on-accent:#0b1412;--warn:#3a3322;--done:#1f3531}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:720px;margin:0 auto;padding:24px 16px 140px}h1{font-size:1.5rem;line-height:1.25;margin:0 0 8px}p,ul{margin:0 0 12px}
.warn{background:var(--warn);border-radius:10px;padding:12px 14px}.mute,.meta{color:var(--mute);font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 14px}.card.done{border-color:var(--accent)}
.meta{margin:0 0 6px}.msg{font-size:1.1rem;white-space:pre-wrap;overflow-wrap:anywhere;border-left:4px solid var(--accent);
background:var(--bg);border-radius:0 8px 8px 0;padding:6px 10px}
fieldset{border:0;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}legend{color:var(--mute);font-size:.9rem;padding:0;margin:0 0 6px}
fieldset label{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}
fieldset label:has(input:checked){border-color:var(--accent);background:var(--done);font-weight:600}
.bar{position:fixed;left:0;right:0;bottom:0;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:center;
padding:10px 16px;background:var(--card);border-top:1px solid var(--line)}#status{flex-basis:100%;text-align:center;margin:0}
button{font:inherit;font-weight:600;color:var(--on-accent);background:var(--accent);border:0;border-radius:10px;padding:10px 18px;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}#csv{width:100%;min-height:160px;font:13px/1.4 ui-monospace,monospace}"""
INTRO = """<h1>Etiquetar mensajes</h1>
<p class="mute">Página de <b>{name}</b>: {n} mensajes.</p>
<noscript><p class="warn">Esta vista no ejecuta la página, así que no se puede etiquetar acá: abrí el archivo en un navegador (por ejemplo, en una computadora).</p></noscript>
<p>Estos mensajes los escribió gente que nunca vio el asistente: a cada persona le mostramos una situación y le pedimos el mensaje que le mandaría al chat de su banco. Para cada mensaje, marcá si pide lo que dice su situación:</p>
<ul><li><b>Coincide</b>: el mensaje pide lo de su situación.</li>
<li><b>Ambiguo</b>: podría pedir eso, pero lo correcto sería preguntarle a la persona qué quiere antes de responder.</li>
<li><b>Otra cosa</b>: el mensaje pide otra cosa.</li></ul>
<p class="warn">Etiquetá por tu cuenta y no hables de estos mensajes con la otra persona que etiqueta hasta que las dos hayan mandado su archivo. Acá no hay respuestas del sistema: juzgás solo el mensaje frente a su situación.</p>
<p>Los mensajes pueden estar en español o en portugués, con errores y abreviaturas: eso no cuenta. El 1234 es el número que pedimos poner en lugar de cualquier cuenta o tarjeta. El avance se guarda en este navegador si lo permite. Al terminar, tocá <b>Descargar CSV</b> y mandanos el archivo; si la descarga no anda, tocá <b>Copiar CSV</b> y pegalo en un mensaje.</p>
<p class="mute">Atajos de teclado: 1 Coincide, 2 Ambiguo, 3 Otra cosa. Marcan el mensaje donde estás y pasan al siguiente.</p>
<p class="warn" id="unsaved" hidden>Este navegador no guarda el avance: no cierres la página hasta descargar o copiar el CSV.</p>"""
FOOTER = """<p><textarea id="csv" readonly hidden aria-label="CSV para copiar"></textarea></p></main>
<footer class="bar"><span id="progress" aria-live="polite"></span><button id="download" type="button" disabled>Descargar CSV</button>
<button id="copy" type="button" disabled>Copiar CSV</button><p id="status" class="mute" aria-live="polite"></p></footer>"""


def situations(worker_js: Path = WORKER_JS) -> dict[str, str]:
    """Situation id -> the Spanish text the writers read, taken from the form's own SITUATIONS list."""
    js = worker_js.read_text(encoding="utf-8")
    start = js.index("const SITUATIONS = [")
    found = dict(re.findall(r'\[\s*"(\w+)",\s*"([^"\\]*)",\s*"[^"\\]*"\s*\]', js[start:js.index("];", start)]))
    if len(found) != 10:
        raise ValueError(f"expected the form's 10 situations in {worker_js}, read {len(found)}: update the parser")
    return found


def read_sheet(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: row[k] for k in ("message_id", "situation", "language", "message")} for row in csv.DictReader(f)]


def slug(name: str) -> str:
    """The labeler's name as it goes in file names: ASCII letters, digits, "-" and "_"."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    out = re.sub(r"[^A-Za-z0-9_-]+", "_", plain).strip("_")
    if not out:
        raise ValueError(f"the labeler name {name!r} has no letters or digits")
    return out


def _script_json(data: dict) -> str:
    """JSON that cannot end its <script> element: <, > and & go as escapes, which JSON.parse reads back unchanged."""
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _card(i: int, n: int, row: dict, texts: dict[str, str]) -> str:
    if row["situation"] not in texts:
        raise ValueError(f"{row['message_id']}: {row['situation']!r} is not a situation of the form")
    lang = html.escape(row["language"])
    choices = "".join(f'<label><input type="radio" name="m{i}" value="{v}"> {t}</label>' for v, t in CHOICES)
    return (f'<section class="card" id="m{i}"><p class="meta">{i + 1} de {n} · {LANGUAGE.get(row["language"], lang)}</p>\n'
            f'<p class="sit"><b>Situación:</b> {html.escape(texts[row["situation"]])}</p>\n'
            f'<p class="msg" lang="{lang}">{html.escape(row["message"])}</p>\n'
            f'<fieldset><legend>¿El mensaje pide lo de la situación?</legend>{choices}</fieldset></section>')


def page(rows: list[dict], labeler: str, texts: dict[str, str]) -> str:
    """The whole page. Messages go in as escaped text; the sheet goes in as JSON for the CSV, which is built from it."""
    name, logic = slug(labeler), LOGIC_JS.read_text(encoding="utf-8")
    if "</script" in logic.lower():
        raise ValueError(f"{LOGIC_JS.name} cannot be inlined: it contains </script")
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    cards = "\n".join(_card(i, len(rows), r, texts) for i, r in enumerate(rows))
    return (f'<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<meta http-equiv="Content-Security-Policy" content="{CSP}"><meta name="robots" content="noindex">\n'
            f"<title>Etiquetar mensajes: {name}</title><style>\n{STYLE}\n</style></head>\n<body><main>\n"
            + INTRO.format(name=name, n=len(rows)) + "\n" + cards + "\n" + FOOTER + "\n"
            + f'<script type="application/json" id="sheet">{_script_json({"labeler": name, "hash": digest, "rows": rows})}</script>\n'
            + f'<script type="module">\n{logic}\n</script>\n</body></html>\n')


def write_pages(labelers: list[str], sheet: Path, only: set[str] | None = None) -> list[Path]:
    """One page per labeler, next to the sheet. `only`: the message ids to keep (the third person's page)."""
    names = [slug(n) for n in labelers]
    if len({n.lower() for n in names}) != len(names):  # "Ana" and "ana" are one file on Windows and macOS
        raise ValueError(f"two labelers would get the same file: {names}")
    rows = [r for r in read_sheet(sheet) if only is None or r["message_id"] in only]
    if not rows:
        raise ValueError(f"no messages to label in {sheet}")
    texts, out = situations(), []
    for name in names:
        path = sheet.parent / f"human_labeling_{name}.html"
        path.write_text(page(rows, name, texts), encoding="utf-8", newline="")  # as built: a CR in a message stays one
        out.append(path)
    return out
