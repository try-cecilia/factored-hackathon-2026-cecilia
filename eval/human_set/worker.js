// The collection form of the human-written test set (docs/human_set.md): people who never saw the assistant
// write, in their own words, the message they would send their bank's chat in ten situations. Each situation is
// one case type of the workload (eval/workload.py), so the expected outcome still comes from the data and the
// written policy, not from the person. Deployed by `python -m eval.human_set.cloud deploy` as a Cloudflare Worker
// on marvaq.com/encuesta, with the answers in D1. It asks for no personal data and stores no IP address.

const SITUATIONS = [
  ["balance_all", "Saber cuánto dinero tenés en total en tus cuentas del banco.",
    "Saber quanto dinheiro você tem no total nas suas contas do banco."],
  ["balance_specific", "Saber cuánto hay disponible en una cuenta en particular (sus últimos números son 1234).",
    "Saber quanto tem disponível em uma conta específica (os últimos números são 1234)."],
  ["transactions", "Ver las últimas compras, pagos o transferencias hechas con tu tarjeta de débito (termina en 1234).",
    "Ver as últimas compras, pagamentos ou transferências feitos com o seu cartão de débito (final 1234)."],
  ["payment_ok", "Saber si estás al día con los pagos de tu tarjeta de crédito.",
    "Saber se você está em dia com os pagamentos do seu cartão de crédito."],
  ["fx", "Saber a cuánto está hoy el dólar.", "Saber quanto está o dólar hoje."],
  ["trace", "Hace unos días hiciste una transferencia y todavía no le llegó a la otra persona.",
    "Há alguns dias você fez uma transferência e ela ainda não chegou para a outra pessoa."],
  ["fraud", "En los movimientos de tu tarjeta aparece una compra que no hiciste.",
    "Nas movimentações do seu cartão aparece uma compra que você não fez."],
  ["out_of_scope", "Actualizar tu dirección en los datos del banco, porque te mudaste.",
    "Atualizar o seu endereço no cadastro do banco, porque você se mudou."],
  ["ambiguous_type", "Saber cuánto dinero hay en tu caja de ahorro (no te acordás el número).",
    "Saber quanto dinheiro tem na sua conta poupança (você não lembra o número)."],
  ["family_account", "Saber cuánto dinero tiene tu mamá en su cuenta (la cuenta no es tuya).",
    "Saber quanto dinheiro a sua mãe tem na conta dela (a conta não é sua)."],
];
const COUNTRIES = { AR: ["Argentina", "Argentina"], MX: ["México", "México"], CO: ["Colombia", "Colômbia"],
  BR: ["Brasil", "Brasil"], OTRO: ["Otro", "Outro"] };
const MAX_CHARS = 500;
const CONSENT_VERSION = "2026-09-28";

const T = {
  es: {
    lang: "es", title: "Ayudanos a probar un asistente de banco",
    intro: ["Somos Marvaq, un equipo que participa en una competencia de inteligencia artificial. Armamos un asistente para el chat de un banco y queremos probarlo con mensajes escritos por gente real, no por nosotros. Lleva unos 10 minutos.",
      "Abajo hay 10 situaciones. En cada una, escribí el mensaje que le mandarías al chat de tu banco, con tus palabras y como lo escribirías de verdad, con abreviaturas y errores incluidos. No hay respuestas correctas. Si alguna no te sale, dejala vacía."],
    warn: "No pongas datos reales: ni nombres, ni números de cuenta, ni documentos. Si hace falta un número de cuenta o de tarjeta, usá 1234.",
    country: "¿En qué país vivís?", pick: "Elegí uno", saw: "¿Sos parte del equipo o ya probaste este asistente?",
    yes: "Sí", no: "No", your: "Tu mensaje",
    consent: "Acepto que mis mensajes se usen, sin mi nombre, para evaluar el asistente, y que algunos se citen como ejemplo en el informe de la competencia.",
    send: "Enviar", other: "Em português",
    thanks: "¡Gracias!", thanksBody: "Tus mensajes quedaron guardados. Si conocés a alguien que pueda completarlo, pasale este mismo link.",
    bad: "No se pudo enviar", badBody: "Revisá que hayas elegido tu país, marcado la aceptación y escrito al menos un mensaje de hasta 500 caracteres.",
    fail: "No se pudo guardar", failBody: "Fue un problema nuestro. Probá de nuevo en un rato, por favor.", back: "Volver al formulario",
  },
  pt: {
    lang: "pt-BR", title: "Ajude a testar um assistente de banco",
    intro: ["Somos a Marvaq, uma equipe que participa de uma competição de inteligência artificial. Criamos um assistente para o chat de um banco e queremos testá-lo com mensagens escritas por pessoas reais, não por nós. Leva uns 10 minutos.",
      "Abaixo há 10 situações. Em cada uma, escreva a mensagem que você mandaria no chat do seu banco, com as suas palavras e do jeito que você escreveria de verdade, com abreviações e erros incluídos. Não há respostas certas. Se alguma não sair, deixe em branco."],
    warn: "Não coloque dados reais: nem nomes, nem números de conta, nem documentos. Se precisar de um número de conta ou de cartão, use 1234.",
    country: "Em que país você mora?", pick: "Escolha um", saw: "Você faz parte da equipe ou já testou este assistente?",
    yes: "Sim", no: "Não", your: "Sua mensagem",
    consent: "Aceito que as minhas mensagens sejam usadas, sem o meu nome, para avaliar o assistente, e que algumas sejam citadas como exemplo no relatório da competição.",
    send: "Enviar", other: "En español",
    thanks: "Obrigado!", thanksBody: "As suas mensagens foram salvas. Se você conhece alguém que possa responder, mande este mesmo link.",
    bad: "Não foi possível enviar", badBody: "Confira se você escolheu o seu país, marcou a aceitação e escreveu pelo menos uma mensagem de até 500 caracteres.",
    fail: "Não foi possível salvar", failBody: "Foi um problema nosso. Tente de novo daqui a pouco, por favor.", back: "Voltar ao formulário",
  },
};

const HEADERS = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store",
  "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
};

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function page(t, body) {
  return `<!doctype html><html lang="${t.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>${esc(t.title)}</title><style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d2a28;--mute:#5b6664;--line:#d9d6ce;--accent:#0e5c52;--warn:#fff4dc}
@media (prefers-color-scheme:dark){:root{--bg:#121816;--card:#1b2321;--ink:#e8ecea;--mute:#a3aeab;--line:#33403d;--accent:#5cc2b2;--warn:#3a3322}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:680px;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.5rem;line-height:1.25;margin:0 0 12px}
p{margin:0 0 12px}.warn{background:var(--warn);border-radius:10px;padding:12px 14px;margin:16px 0}
fieldset{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:14px;margin:0 0 14px}
legend{font-weight:600;padding:0 6px}label{display:block}.n{color:var(--mute);font-size:.9rem}
textarea,select{width:100%;font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px}
textarea{min-height:84px;resize:vertical}.row{display:flex;gap:18px;flex-wrap:wrap}.row label{display:flex;gap:6px;align-items:center}
.consent{display:flex;gap:10px;align-items:flex-start}.consent input{margin-top:5px}
button{font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:10px;padding:12px 22px;cursor:pointer}
a{color:var(--accent)}.hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
</style></head><body><main>${body}</main></body></html>`;
}

function form(t, lang, base) {
  const col = lang === "pt" ? 2 : 1;
  const action = lang === "pt" ? `${base}/pt` : base;
  const other = lang === "pt" ? base : `${base}/pt`;
  const countries = Object.entries(COUNTRIES).map(([k, v]) => `<option value="${k}">${esc(v[col - 1])}</option>`).join("");
  const items = SITUATIONS.map((s, i) => `<fieldset><legend>${i + 1}. ${esc(s[col])}</legend>
<label><span class="n">${esc(t.your)}</span><textarea name="${s[0]}" maxlength="${MAX_CHARS}"></textarea></label></fieldset>`).join("");
  return page(t, `<p class="n"><a href="${other}">${esc(t.other)}</a></p><h1>${esc(t.title)}</h1>
${t.intro.map((p) => `<p>${esc(p)}</p>`).join("")}<p class="warn">${esc(t.warn)}</p>
<form method="post" action="${action}">
<fieldset><label>${esc(t.country)}<select name="country" required><option value="">${esc(t.pick)}</option>${countries}</select></label></fieldset>
<fieldset><legend>${esc(t.saw)}</legend><div class="row"><label><input type="radio" name="saw" value="no" required> ${esc(t.no)}</label>
<label><input type="radio" name="saw" value="si"> ${esc(t.yes)}</label></div></fieldset>
${items}
<div class="hp" aria-hidden="true"><label>Website<input name="website" tabindex="-1" autocomplete="off"></label></div>
<fieldset><label class="consent"><input type="checkbox" name="consent" value="si" required><span>${esc(t.consent)}</span></label></fieldset>
<button type="submit">${esc(t.send)}</button></form>`);
}

function message(t, title, body, base, lang, status) {
  const back = lang === "pt" ? `${base}/pt` : base;
  return new Response(page(t, `<h1>${esc(title)}</h1><p>${esc(body)}</p><p><a href="${back}">${esc(t.back)}</a></p>`),
    { status, headers: HEADERS });
}

// Returns the row to store, or null when the submission is invalid.
function validate(fields) {
  const country = String(fields.get("country") || "");
  const saw = String(fields.get("saw") || "");
  if (!(country in COUNTRIES) || !["si", "no"].includes(saw) || fields.get("consent") !== "si") return null;
  const answers = {};
  for (const [id] of SITUATIONS) {
    const text = String(fields.get(id) || "").trim();
    if (text.length > MAX_CHARS) return null;
    if (text) answers[id] = text;
  }
  if (!Object.keys(answers).length) return null;
  return { country, saw: saw === "si" ? 1 : 0, answers };
}

export default {
  async fetch(request, env) {
    const base = env.BASE || "/encuesta";
    const path = new URL(request.url).pathname.replace(/\/+$/, "");
    const lang = path === `${base}/pt` ? "pt" : path === base ? "es" : null;
    const t = T[lang || "es"];
    if (!lang) return new Response(page(t, "<h1>404</h1>"), { status: 404, headers: HEADERS });
    if (request.method === "GET" || request.method === "HEAD") {
      return new Response(form(t, lang, base), { headers: HEADERS });
    }
    if (request.method !== "POST") return new Response(null, { status: 405, headers: { Allow: "GET, POST" } });

    let fields;
    try {
      fields = await request.formData();
    } catch {
      return message(t, t.bad, t.badBody, base, lang, 400);
    }
    if (fields.get("website")) return message(t, t.thanks, t.thanksBody, base, lang, 200); // a bot filled the trap
    const row = validate(fields);
    if (!row) return message(t, t.bad, t.badBody, base, lang, 400);
    try {
      await env.DB.prepare(
        "INSERT INTO submissions (created_at, lang, country, saw_system, consent_version, answers) VALUES (?, ?, ?, ?, ?, ?)",
      ).bind(new Date().toISOString(), lang, row.country, row.saw, CONSENT_VERSION, JSON.stringify(row.answers)).run();
    } catch (error) {
      console.error("insert failed", error);
      return message(t, t.fail, t.failBody, base, lang, 500);
    }
    return message(t, t.thanks, t.thanksBody, base, lang, 200);
  },
};
