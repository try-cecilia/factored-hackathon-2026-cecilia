# Data evidence for the workflow choice

Pulled directly from the organizer's S3 dataset during scoping (not sampled
from documentation — the full `call_center_interactions` and `complaints`
tables, downloaded and aggregated with pandas).

## Contact reason distribution (`call_center_interactions`, 686,296 rows)

| `reason_category` | Count | % |
|---|---|---|
| Transaccional | 240,056 | 35.0% |
| Producto | 150,863 | 22.0% |
| Queja | 117,021 | 17.1% |
| Técnico | 102,899 | 15.0% |
| Comercial | 54,879 | 8.0% |
| Retención | 20,578 | 3.0% |

`contact_reason` and `reason_category` turned out to carry the same 6-value
taxonomy in this dataset (a data-quality/schema-evolution quirk the data
dictionary itself warns about) — so this is the full granularity available
directly from that field.

## Runner-up considered: transaction disputes (`complaints`, 67,095 rows)

| `category` | Count | % |
|---|---|---|
| Transactions | 13,580 | 20.2% |
| Fees | 13,553 | 20.2% |
| Technical | 13,407 | 20.0% |
| Branch | 13,361 | 19.9% |
| Service | 13,194 | 19.7% |

Top subcategories: **"Cargo no reconocido"** (12,297) and **"Cobro
indebido"** (12,194) — together ~36% of all complaints. 20% of cases breach
SLA. Lower raw volume than account/payment inquiries, but higher per-case
cost and complexity (fraud linkage via `transactions.fraud_score`/`is_fraud`,
mandatory human escalation). Documented here as the clear second choice,
in case the workflow scope is revisited post-hackathon.

## Product mix (`products`, 400,000 rows) — for context

| `product_type` | % |
|---|---|
| Cuenta Ahorro | 30.1% |
| Tarjeta Crédito | 25.0% |
| Cuenta Corriente | 25.0% |
| Tarjeta Débito | 10.0% |
| Préstamo Personal | 5.0% |
| Préstamo Hipotecario | 3.0% |
| Inversión | 1.5% |
| Seguro | 0.5% |

## Conclusion

Account/Payment Inquiries is the highest-volume contact reason in the bank's
own operational data (35%, vs. 22% for the next-largest category), which is
exactly the kind of "problem supported by data" evidence item 1 of the
challenge's rubric asks for. It's also the workflow where full automation is
safest to attempt: no money movement, no credit decisioning, and a bounded,
verifiable answer space (numbers that exist in `products`/`transactions`,
not judgment calls).
