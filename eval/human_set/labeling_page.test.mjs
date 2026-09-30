// node --test eval/human_set/labeling_page.test.mjs   (tests/test_human_set_labeling.py runs it when node is installed)
import assert from "node:assert/strict";
import { test } from "node:test";
import { COLUMNS, field, load, restore, save, storageKey, toCsv, unlabeled } from "./labeling_page.mjs";

// Fake messages, written to test the page.
const rows = [
  { message_id: "1:fx", situation: "fx", language: "es", message: "a cuánto está el dólar?" },
  { message_id: "2:fraud", situation: "fraud", language: "pt", message: 'compra "estranha", no cartão\r\nfinal 1234' },
];

test("a field is quoted only with a comma, a quote or a line break, as Python's csv module writes it", () => {
  assert.equal(field("plain text"), "plain text");
  assert.equal(field("a, b"), '"a, b"');
  assert.equal(field('say "hi"'), '"say ""hi"""');
  assert.equal(field("two\nlines"), '"two\nlines"');
  assert.equal(field("carriage\rreturn"), '"carriage\rreturn"');
  assert.equal(field(""), "");
  assert.equal(field(undefined), "");
});

test("the CSV has the sheet's columns, the labels filled in, CRLF line ends and no byte order mark", () => {
  const csv = toCsv(rows, { "1:fx": "matches", "2:fraud": "something_else" });
  assert.equal(csv, `${COLUMNS.join(",")}\r\n1:fx,fx,es,a cuánto está el dólar?,matches\r\n`
    + '2:fraud,fraud,pt,"compra ""estranha"", no cartão\r\nfinal 1234",something_else\r\n');
  assert.notEqual(csv.charCodeAt(0), 0xfeff);
});

test("only the three labels count as labeled", () => {
  assert.equal(unlabeled(rows, {}), 2);
  assert.equal(unlabeled(rows, { "1:fx": "ambiguous", "2:fraud": "maybe" }), 1);
  assert.equal(unlabeled(rows, { "1:fx": "ambiguous", "2:fraud": "something_else" }), 0);
});

test("saved progress comes back only for this sheet's messages and the three labels", () => {
  const saved = '{"1:fx": "matches", "2:fraud": "maybe", "9:fx": "matches", "__proto__": "matches"}';
  assert.deepEqual(restore(saved, rows), { "1:fx": "matches" });
  for (const broken of [null, "", "not json", "[1, 2]", "null", "42"]) assert.deepEqual(restore(broken, rows), {});
});

test("the storage key changes with the labeler and with the sheet", () => {
  assert.notEqual(storageKey("ana", "abc"), storageKey("beto", "abc"));
  assert.notEqual(storageKey("ana", "abc"), storageKey("ana", "abd"));
});

test("storage that throws, or that is missing, never breaks the page", () => {
  const throwing = { getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("QuotaExceeded"); } };
  assert.equal(load(throwing, "k"), null);
  assert.equal(save(throwing, "k", {}), false);
  assert.equal(load(null, "k"), null);
  assert.equal(save(null, "k", {}), false);
  const kept = new Map();
  const memory = { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => kept.set(k, v) };
  assert.equal(save(memory, "k", { "1:fx": "matches" }), true);
  assert.deepEqual(restore(load(memory, "k"), rows), { "1:fx": "matches" });
});
