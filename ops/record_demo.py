"""Records docs/demo/demo_app.webm: a captioned walkthrough of the running app.

Start the server first on port 8765 (`uvicorn api.main:app --port 8765`, with
ADMIN_API_KEY and DEMO_IDP_SECRET in .env and DEMO_PUBLIC_CUSTOMERS set, e.g.
`export DEMO_PUBLIC_CUSTOMERS=$(python -m ops.demo_customers)`), then:
    python -m ops.record_demo
The captions describe the degraded (no-LLM) run recorded in the build sandbox;
re-record once the live LLM is reachable to show multi-turn clarification.
"""
import glob
import os
import shutil
import tempfile

from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
OUT = tempfile.mkdtemp(prefix="demo_video_")
ADMIN = dotenv_values(".env")["ADMIN_API_KEY"]
exe = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))[-1]

CARD = """<html><body style="margin:0;height:100vh;display:flex;flex-direction:column;justify-content:center;
padding:0 96px;background:#13233A;color:#F4F1EA;font-family:system-ui,sans-serif">{body}</body></html>"""

CAPTION_JS = """t => {
  let c = document.getElementById('__cap');
  if (!c) { c = document.createElement('div'); c.id = '__cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);max-width:1100px;background:rgba(19,35,58,.94);color:#F4F1EA;font:600 22px/1.4 system-ui,sans-serif;padding:14px 22px;border-radius:12px;z-index:9999;text-align:center';
    document.body.appendChild(c); }
  c.textContent = t; }"""


def cap(page, text, wait=3500):
    page.evaluate(CAPTION_JS, text)
    page.wait_for_timeout(wait)


def send(page, text, caption):
    n = page.locator(".msg.bot").count()
    cap(page, caption, 1500)
    page.fill("#m", "")
    page.type("#m", text, delay=35)
    page.click("#send")
    page.wait_for_function(f"document.querySelectorAll('.msg.bot').length > {n}", timeout=40000)
    page.wait_for_timeout(3500)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe)
    ctx = b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=OUT, record_video_size={"width": 1280, "height": 720})
    page = ctx.new_page()

    page.set_content(CARD.format(body="""
      <p style="font-size:20px;letter-spacing:3px;text-transform:uppercase;color:#8DB4FF;font-weight:600">Factored AI &amp; Data Hackathon 2026</p>
      <h1 style="font-size:54px;line-height:1.1;margin:12px 0">Asistente AI de Cuenta y Pagos</h1>
      <p style="font-size:26px;color:#C3CFDC;line-height:1.4">Demo grabada sobre la app real y el warehouse completo (datos sintéticos).<br>
      En este entorno el LLM está bloqueado por la red: se ve el <b>modo degradado</b> real, no un modelo simulado.</p>"""))
    page.wait_for_timeout(5500)

    page.goto(BASE)
    page.wait_for_selector("#cid option", state="attached")
    cap(page, "Login: número de cliente + PIN de prueba. El número de cliente solo no alcanza para abrir sesión.", 4000)
    page.click("#go")
    page.wait_for_selector("#chat:not([hidden])")

    send(page, "¿Cuál es mi saldo?", "Consulta de saldo en español")
    cap(page, "Sin LLM, un saldo general se responde igual: datos verificados, cuentas enmascaradas y fecha de corte.", 5000)
    send(page, "Qual é o meu saldo?", "La misma consulta en portugués")
    cap(page, "Detecta el idioma y responde en portugués.", 3500)
    send(page, "Hay un cargo en mi tarjeta que no reconozco", "Un posible fraude")
    cap(page, "El fraude se detecta antes del LLM (léxico + clasificador aprendido) y pasa a un humano con ticket.", 5000)
    send(page, "Quiero bloquear mi tarjeta", "Un pedido fuera del alcance de este flujo")
    cap(page, "Fuera de alcance: no lo resuelve y orienta al canal correcto, en vez de inventar.", 4500)

    admin = page
    admin.set_extra_http_headers({"X-Admin-Key": ADMIN})
    admin.goto(f"{BASE}/admin/human_queue?limit=1")
    admin.evaluate("""() => { const j = JSON.parse(document.body.innerText)[0];
      const keep = {category: j.category, priority: j.priority, queue: j.queue, policy_rule: j.policy_rule, request: j.request,
        evidence: (j.evidence || []).slice(0, 3), open_questions: j.open_questions, suggested_next_step: j.suggested_next_step,
        session_ref: j.session_ref};
      document.body.innerHTML = '<pre style="font:17px/1.45 ui-monospace,monospace;padding:28px;margin:0;white-space:pre-wrap;background:#FDFCF9;color:#13233A;min-height:100vh">' +
        JSON.stringify(keep, null, 2).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])) + '</pre>'; }""")
    cap(admin, "Lo que recibe el agente humano: la regla que se activó, evidencia (transacciones marcadas primero) y preguntas abiertas.", 6000)
    admin.evaluate("window.scrollTo(0, 400)")
    cap(admin, "Solo una referencia hasheada de la sesión: el token nunca aparece en tickets ni trazas.", 4500)

    page.set_content(CARD.format(body="""
      <h2 style="font-size:40px;margin:0 0 24px">Resultados en 432 casos de prueba (ES + PT)</h2>
      <table style="font-size:22px;border-collapse:collapse;color:#F4F1EA">
      <tr style="color:#8DB4FF"><td style="padding:8px 28px 8px 0"></td><td style="padding:8px 28px">Humano</td><td style="padding:8px 28px">Bot de keywords</td><td style="padding:8px 28px">Nuestro sistema</td></tr>
      <tr><td style="padding:8px 28px 8px 0">Espera + atención</td><td style="padding:8px 28px">120 s + 221 s</td><td style="padding:8px 28px">ms</td><td style="padding:8px 28px">ms + LLM (a medir)</td></tr>
      <tr><td style="padding:8px 28px 8px 0">Resuelve</td><td style="padding:8px 28px">91,5%</td><td style="padding:8px 28px">76,8%</td><td style="padding:8px 28px">100% techo · 64,8% modelo malo</td></tr>
      <tr><td style="padding:8px 28px 8px 0">Fraude no escalado</td><td style="padding:8px 28px">—</td><td style="padding:8px 28px">24 / 120</td><td style="padding:8px 28px">0 / 120</td></tr>
      <tr><td style="padding:8px 28px 8px 0">Resultados inseguros</td><td style="padding:8px 28px">—</td><td style="padding:8px 28px">0 / 432</td><td style="padding:8px 28px">0 / 432</td></tr>
      </table>
      <p style="font-size:20px;color:#C3CFDC;margin-top:28px">Métodos y reportes completos: EVALUATION.md · eval/reports/</p>"""))
    page.wait_for_timeout(8000)
    ctx.close()
    b.close()

vids = glob.glob(f"{OUT}/*.webm")
assert len(vids) == 1, vids
vid = vids[0]
os.makedirs("docs/demo", exist_ok=True)
shutil.copy(vid, "docs/demo/demo_app.webm")
print("saved", os.path.getsize("docs/demo/demo_app.webm") // 1024, "KB")
