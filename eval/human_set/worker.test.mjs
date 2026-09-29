// node --test eval/human_set/worker.test.mjs   (Node 22+: Request, Response and FormData are built in)
import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.js";

function db(fail = false) {
  const calls = [];
  return { calls, prepare: (sql) => ({ bind: (...args) => ({ run: async () => {
    if (fail) throw new Error("D1 down");
    calls.push({ sql, args });
  } }) }) };
}

const post = (path, fields) => new Request(`https://marvaq.com${path}`, { method: "POST", body: new URLSearchParams(fields) });
const ok = { country: "AR", saw: "no", consent: "si", balance_all: "  cuanto tengo?  ", fx: "a cuanto esta el dolar", fraud: "" };

test("the form renders in Spanish and Portuguese, with the ten situations", async () => {
  for (const [path, lang] of [["/encuesta", "es"], ["/encuesta/", "es"], ["/encuesta/pt", "pt-BR"]]) {
    const res = await worker.fetch(new Request(`https://marvaq.com${path}`), { DB: db() });
    const html = await res.text();
    assert.equal(res.status, 200);
    assert.match(html, new RegExp(`<html lang="${lang}"`));
    assert.equal(html.match(/<textarea /g).length, 10);
    assert.match(res.headers.get("Content-Security-Policy"), /default-src 'none'/);
  }
});

test("anything else under the route is a 404", async () => {
  const res = await worker.fetch(new Request("https://marvaq.com/encuestas"), { DB: db() });
  assert.equal(res.status, 404);
});

test("a valid submission stores the trimmed, non-empty answers and nothing else", async () => {
  const d = db();
  const res = await worker.fetch(post("/encuesta", ok), { DB: d });
  assert.equal(res.status, 200);
  assert.equal(d.calls.length, 1);
  const [, lang, country, saw, , answers] = d.calls[0].args;
  assert.deepEqual([lang, country, saw], ["es", "AR", 0]);
  assert.deepEqual(JSON.parse(answers), { balance_all: "cuanto tengo?", fx: "a cuanto esta el dolar" });
});

test("the Portuguese form stores pt", async () => {
  const d = db();
  await worker.fetch(post("/encuesta/pt", { ...ok, country: "BR" }), { DB: d });
  assert.equal(d.calls[0].args[1], "pt");
});

test("invalid submissions are refused and stored nowhere", async () => {
  const bad = [
    { ...ok, consent: "" },                                    // no consent
    { ...ok, country: "XX" },                                  // unknown country
    { ...ok, saw: "" },                                        // unanswered question
    { country: "AR", saw: "no", consent: "si", fx: "   " },    // no message at all
    { ...ok, fx: "x".repeat(501) },                            // over the limit
  ];
  for (const fields of bad) {
    const d = db();
    const res = await worker.fetch(post("/encuesta", fields), { DB: d });
    assert.equal(res.status, 400, JSON.stringify(fields).slice(0, 80));
    assert.equal(d.calls.length, 0);
  }
});

test("a bot that fills the hidden field is thanked and not stored", async () => {
  const d = db();
  const res = await worker.fetch(post("/encuesta", { ...ok, website: "http://spam" }), { DB: d });
  assert.equal(res.status, 200);
  assert.equal(d.calls.length, 0);
});

test("a storage failure says so instead of thanking", async () => {
  const res = await worker.fetch(post("/encuesta", ok), { DB: db(true) });
  assert.equal(res.status, 500);
});
