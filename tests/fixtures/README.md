# Test fixtures — hand-made, synthetic, NOT from the organizer dataset

Tiny CSVs with the same schema as the LATAM Bank dataset, written by hand to
exercise specific cases hermetically (no S3, no credentials):

- `raw/`: base warehouse with 5 customers (one with two savings accounts to force
  a clarification, one Suspended), a credit card with `days_past_due` missing,
  a fraud-flagged transaction, one exact duplicate transaction, a duplicate
  customer record with an older `last_updated`, an FX gap on 2024-01-15, and
  complaints covering allowed nulls, a later-file duplicate, invalid ownership,
  and missing optional references.
- `raw_late/`: a re-delivered 2024-01-16 partition with one corrected amount and
  one new transaction (update-correctness fixture for the incremental load).
- `raw_bad/`: a partition with an enum violation and an uncastable amount
  (quarantine / quality-gate fixture).
- `raw_complaints_late/`: a re-delivered complaints partition with one resolved
  correction and one new complaint.
- `raw_complaints_bad/`: one valid complaint plus one row with a missing
  required description, invalid priority, and malformed required boolean.
