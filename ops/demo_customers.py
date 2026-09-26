"""Pick sandbox demo customers that exercise each behavior, from whatever
warehouse is loaded (full or sampled). Printed as a comma list for
DEMO_PUBLIC_CUSTOMERS; see api/main.py /demo/customers.

  1) two open savings accounts        -> clarification + multi-turn demo
  2) credit product with days of delay -> payment status with arrears
  3) credit product missing dpd        -> data-unavailable escalation
  4) a Colombian or Argentine customer -> other countries/currencies
  5) a Suspended customer              -> compliance hold
"""
from __future__ import annotations

from agent.tools.db import get_connection

CREDIT = "('Tarjeta Crédito','Préstamo Personal','Préstamo Hipotecario')"
QUERIES = [
    """SELECT c.customer_id FROM customers c JOIN products p USING (customer_id) WHERE c.customer_status='Active'
       AND p.product_type='Cuenta Ahorro' AND p.product_status<>'Closed' GROUP BY 1 HAVING count(*) >= 2 ORDER BY 1 LIMIT 1""",
    f"""SELECT c.customer_id FROM customers c JOIN products p USING (customer_id) WHERE c.customer_status='Active'
        AND p.product_type IN {CREDIT} AND p.days_past_due > 0 ORDER BY 1 LIMIT 1""",
    f"""SELECT c.customer_id FROM customers c JOIN products p USING (customer_id) WHERE c.customer_status='Active'
        AND p.product_type IN {CREDIT} AND p.days_past_due IS NULL AND p.product_status<>'Closed' ORDER BY 1 LIMIT 1""",
    """SELECT customer_id FROM customers WHERE customer_status='Active' AND country IN ('Colombia','Argentina') ORDER BY 1 LIMIT 1""",
    """SELECT customer_id FROM customers WHERE customer_status='Suspended' ORDER BY 1 LIMIT 1""",
]


def pick() -> list[str]:
    con, out = get_connection(), []
    for q in QUERIES:
        row = con.execute(q).fetchone()
        if row and row[0] not in out:
            out.append(row[0])
    return out


if __name__ == "__main__":
    print(",".join(pick()))
