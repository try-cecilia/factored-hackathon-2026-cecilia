// The logic of the labeling page of the human-written set (docs/human_set.md). eval/human_set/labeling.py inlines this
// file into each labeler's page as a module script; `node --test eval/human_set/labeling_page.test.mjs` tests the
// exported functions, which are the ones that decide what reaches `agreement`. The page runs from the file system and
// makes no network call: its Content-Security-Policy forbids one.

export const LABELS = { matches: "Coincide", ambiguous: "Ambiguo", something_else: "Otra cosa" };
export const COLUMNS = ["message_id", "situation", "language", "message", "label"];
const KEYS = { 1: "matches", 2: "ambiguous", 3: "something_else" };

// One CSV field as Python's csv module writes it (QUOTE_MINIMAL): quoted only with a comma, a quote or a line break.
export function field(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

// The sheet's columns with the label filled in. CRLF line ends, as Python's csv writer uses, and no byte order mark:
// `read_labels` opens the file as plain UTF-8 and would take the mark for part of the first column's name.
export function toCsv(rows, labels) {
  const lines = [COLUMNS, ...rows.map((r) => [r.message_id, r.situation, r.language, r.message, labels[r.message_id] ?? ""])];
  return lines.map((cells) => cells.map(field).join(",")).join("\r\n") + "\r\n";
}

export function unlabeled(rows, labels) {
  return rows.filter((r) => !Object.hasOwn(LABELS, labels[r.message_id] ?? "")).length;
}

// Saved progress, kept only for this sheet's messages and the three labels: anything else in storage is ignored.
export function restore(saved, rows) {
  let parsed;
  try {
    parsed = JSON.parse(saved ?? "{}");
  } catch {
    return {};
  }
  const ids = new Set(rows.map((r) => r.message_id));
  const labels = {};
  for (const [id, label] of Object.entries(parsed && typeof parsed === "object" ? parsed : {})) {
    if (ids.has(id) && Object.hasOwn(LABELS, label)) labels[id] = label;
  }
  return labels;
}

// A regenerated sheet gets a new hash, so progress saved for an older one is never applied to it.
export const storageKey = (labeler, sheetHash) => `human-set-labels:${labeler}:${sheetHash}`;

// Browser storage throws on some file:// pages and in private modes: then the page works without it and says so.
export function load(store, key) {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

export function save(store, key, labels) {
  try {
    store.setItem(key, JSON.stringify(labels));
    return true;
  } catch {
    return false;
  }
}

function boot(doc, win) {
  const { labeler, hash, rows } = JSON.parse(doc.getElementById("sheet").textContent);
  const key = storageKey(labeler, hash);
  let store = null;
  try {
    store = win.localStorage;
  } catch {
    store = null;
  }
  const labels = restore(load(store, key), rows);
  const cards = rows.map((_, i) => doc.getElementById(`m${i}`));
  const [progress, download, copy, status, out] = ["progress", "download", "copy", "status", "csv"].map((id) => doc.getElementById(id));
  const unsaved = () => { doc.getElementById("unsaved").hidden = false; };

  function refresh() {
    const left = unlabeled(rows, labels);
    progress.textContent = `${rows.length - left} de ${rows.length} etiquetados`;
    download.disabled = copy.disabled = left > 0;
  }

  function mark(i) {
    const label = labels[rows[i].message_id];
    const input = label && cards[i].querySelector(`input[value="${label}"]`);
    if (input) input.checked = true;
    cards[i].classList.toggle("done", Boolean(input));
  }

  function choose(i, label) {
    labels[rows[i].message_id] = label;
    mark(i);
    if (!save(store, key, labels)) unsaved();
    refresh();
  }

  cards.forEach((card, i) => {
    mark(i);
    card.addEventListener("change", (event) => choose(i, event.target.value));
  });
  if (!save(store, key, labels)) unsaved();

  // 1, 2 and 3 label the message being worked on (the one with the focus, or else the first one left) and move on.
  doc.addEventListener("keydown", (event) => {
    const label = KEYS[event.key];
    if (!label || event.ctrlKey || event.metaKey || event.altKey || event.target === out) return;
    const here = cards.findIndex((card) => card.contains(doc.activeElement));
    const i = here >= 0 ? here : rows.findIndex((r) => !labels[r.message_id]);
    if (i < 0) return;
    event.preventDefault();
    choose(i, label);
    const after = rows.findIndex((r, j) => j > i && !labels[r.message_id]);
    const next = after >= 0 ? after : rows.findIndex((r) => !labels[r.message_id]);
    if (next >= 0) {
      cards[next].querySelector("input").focus({ preventScroll: true });
      cards[next].scrollIntoView({ block: "center" });
    }
  });

  download.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([toCsv(rows, labels)], { type: "text/csv;charset=utf-8" }));
    const link = Object.assign(doc.createElement("a"), { href: url, download: `human_labels_${labeler}.csv` });
    doc.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    status.textContent = `Se descargó human_labels_${labeler}.csv: mandanos ese archivo.`;
  });

  // Where a download does not work: the CSV goes to the clipboard, or stays selected on the page to copy by hand. The
  // clipboard gets the text itself: a text box turns every CRLF into LF (read_labels takes either).
  copy.addEventListener("click", async () => {
    const csv = toCsv(rows, labels);
    out.value = csv;
    out.hidden = false;
    out.select();
    let copied = false;
    try {
      await win.navigator.clipboard.writeText(csv);
      copied = true;
    } catch {
      try {
        copied = doc.execCommand("copy");
      } catch {
        copied = false;
      }
    }
    status.textContent = copied ? "Copiado: pegalo en un mensaje y mandánoslo."
      : "No se pudo copiar solo: el texto quedó seleccionado abajo, copialo a mano y mandánoslo.";
    out.scrollIntoView({ block: "center" });
  });

  refresh();
}

if (typeof document !== "undefined") boot(document, window);
