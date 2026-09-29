"""Pick sandbox demo customers that exercise each behavior, from whatever
warehouse is loaded (full or sampled). `roles()` feeds the jury demo's guided
scenarios (api/demo.py); `pick()` prints them as a comma list for
DEMO_PUBLIC_CUSTOMERS (api/main.py /demo/customers).

  multi      two open savings accounts             -> clarification + multi-turn
  arrears    a credit product with days of delay   -> payment status with arrears
  no_dpd     a credit product missing its arrears  -> data-unavailable escalation
  abroad     a Colombian or Argentine customer     -> another currency; their product is the attack's target
  suspended  a Suspended customer                  -> compliance hold
  pending    one pending transfer, payment or deposit -> the verified action: trace it on the customer's yes

The credit products are the customer's only open product of their type, so
naming the type finds them without a clarifying question. The abroad
customer is never the multi one: an attack by multi must name a product
that is not theirs.
"""
from __future__ import annotations

from agent.tools.account_tools import TRACEABLE_TYPES
from agent.tools.db import get_connection

CREDIT = "('Tarjeta Crédito','Préstamo Personal','Préstamo Hipotecario')"
_TRACEABLE = "(" + ", ".join(f"'{t}'" for t in TRACEABLE_TYPES) + ")"
PENDING = f"""SELECT t.customer_id, t.transaction_type FROM customers c JOIN transactions t ON t.customer_id = c.customer_id
              WHERE c.customer_status = 'Active' AND t.transaction_status = 'Pending' AND t.transaction_type IN {_TRACEABLE}
              AND (SELECT count(*) FROM transactions u WHERE u.customer_id = c.customer_id AND u.transaction_status = 'Pending'
                   AND u.transaction_type IN {_TRACEABLE}) = 1
              ORDER BY 1 LIMIT 1"""
LOCAL_CURRENCY = {"Colombia": "COP", "Argentina": "ARS"}
MULTI = """SELECT c.customer_id FROM customers c JOIN products p USING (customer_id) WHERE c.customer_status = 'Active'
           AND p.product_type = 'Cuenta Ahorro' AND p.product_status <> 'Closed' GROUP BY 1 HAVING count(*) >= 2 ORDER BY 1 LIMIT 1"""
CREDIT_PRODUCT = f"""SELECT p.customer_id, p.product_type FROM customers c JOIN products p USING (customer_id)
    WHERE c.customer_status = 'Active' AND p.product_type IN {CREDIT} AND p.product_status <> 'Closed' AND {{dpd}}
    AND (SELECT count(*) FROM products q WHERE q.customer_id = p.customer_id AND q.product_type = p.product_type
         AND q.product_status <> 'Closed') = 1
    ORDER BY 1, 2 LIMIT 1"""
ABROAD = """SELECT c.customer_id, c.country, p.product_id FROM customers c JOIN products p USING (customer_id)
            WHERE c.customer_status = 'Active' AND c.country IN ('Colombia', 'Argentina') AND p.product_status <> 'Closed'
            AND c.customer_id <> ? ORDER BY 1, 3 LIMIT 1"""
SUSPENDED = "SELECT customer_id FROM customers WHERE customer_status = 'Suspended' ORDER BY 1 LIMIT 1"


def _first(sql: str, params: list | None = None) -> dict | None:
    cur = get_connection().execute(sql, params or [])
    row = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], row)) if row else None


def roles() -> dict[str, dict]:
    """role -> the customer (and what its scenario needs); a role the warehouse cannot fill is left out."""
    found = {"multi": _first(MULTI),
             "arrears": _first(CREDIT_PRODUCT.format(dpd="p.days_past_due > 0")),
             "no_dpd": _first(CREDIT_PRODUCT.format(dpd="p.days_past_due IS NULL")),
             "suspended": _first(SUSPENDED), "pending": _first(PENDING)}
    abroad = _first(ABROAD, [(found["multi"] or {}).get("customer_id", "")])
    found["abroad"] = abroad and {**abroad, "currency": LOCAL_CURRENCY[abroad["country"]]}
    order = ("multi", "arrears", "no_dpd", "abroad", "suspended", "pending")
    return {r: found[r] for r in order if found[r]}


def pick() -> list[str]:
    return list(dict.fromkeys(r["customer_id"] for r in roles().values()))


if __name__ == "__main__":
    print(",".join(pick()))
