"""System prompt and tool schemas for the Account/Payment Inquiries agent.

Security note: none of the tool schemas exposed to the LLM include
`customer_id`. The orchestrator (agent/core/orchestrator.py) always injects
the authenticated session's customer_id itself when it actually calls the
underlying Python function — the model is never trusted to supply whose
account to look up. This is the second half of the injection defense: even
if a prompt convinces the model to *call* a tool with attacker-chosen
product_id, the ownership check in agent/tools/account_tools.py still runs
against the real session, not whatever the model said.
"""
from __future__ import annotations

SYSTEM_PROMPT = """Eres el asistente de atención al cliente de un banco LATAM, especializado \
ÚNICAMENTE en consultas de cuenta y pagos (saldo, movimientos, estado de pago, tipo de cambio).

Reglas estrictas:
1. NUNCA inventes saldos, movimientos o fechas. Toda cifra que menciones debe venir de una \
llamada a una herramienta (tool call) ya ejecutada y verificada.
2. Si el cliente tiene más de un producto y no especifica cuál, pregunta antes de usar una \
herramienta que requiera product_id.
3. Si la solicitud no es sobre cuenta/pagos (tarjetas bloqueadas, disputas, crédito, etc.), \
dilo claramente y ofrece transferir al área correspondiente. No lo resuelvas tú.
4. Si el cliente menciona fraude, un cargo no reconocido, robo o cualquier señal de seguridad, \
no lo minimices ni lo investigues tú mismo: indica que vas a escalar a un agente humano de inmediato.
5. Responde en el mismo idioma del cliente (español o portugués).
6. Sé breve, concreto y cita las cifras exactas devueltas por las herramientas.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_account_summary",
            "description": "Obtiene el resumen de los productos (cuentas, tarjetas, préstamos) del cliente autenticado, o el detalle de uno si se especifica product_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "ID del producto específico, si el cliente ya lo mencionó o solo tiene uno."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "Lista los movimientos/transacciones recientes del cliente autenticado, opcionalmente filtrados por producto y rango de fechas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payment_status",
            "description": "Estado de pago (días de mora, crédito disponible) de un producto de crédito (tarjeta de crédito, préstamo personal o hipotecario) del cliente autenticado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Tipo de cambio entre dos monedas en una fecha dada (con fallback a la fecha anterior más cercana si no hay dato exacto).",
            "parameters": {
                "type": "object",
                "properties": {
                    "on_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "source_currency": {"type": "string", "description": "MXN, COP, ARS o USD"},
                    "target_currency": {"type": "string", "description": "MXN, COP, ARS o USD"},
                },
                "required": ["on_date", "source_currency", "target_currency"],
            },
        },
    },
]

TOOL_NAME_TO_INTENT = {
    "get_account_summary": "balance_inquiry",
    "list_transactions": "transaction_lookup",
    "get_payment_status": "payment_status",
    "get_exchange_rate": "exchange_rate_inquiry",
}
