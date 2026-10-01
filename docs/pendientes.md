# Pending work

What remains after the alerts (item 6) and the live quality report (item 5) are closed.
Status as of 2026-09-29.

## 3b. Evaluate the human path

**What is missing:** measure separately the path in which a person intervenes (escalation to an operator, approval,
feedback), apart from the controlled automation that is already merged and measured (item 3).

**Can be done now:** it does not depend on new data. The operator and approval code is merged
(`agent/session/operators.py`, `agent/policy/escalation.py`, `eval/operator_labels.py`).

**Closing criterion:** a report in `eval/reports/` with the same metrics as the rest of the system
evaluation, measured only on the cases that go through a person, and a section in `EVALUATION.md` that cites it.

## 3c. Evaluate the operator screen

**What is missing:** evaluate the screen the operator uses (the web view in `web/` that consumes the API in `api/`) as
a separate piece: what they see, what they can approve or reject and what gets recorded of what they do (the API requires the operator key,
`require_operator` in `api/main.py`).

**Can be done now:** yes, against the local demo.

**Closing criterion:** a list of cases walked through by hand or with an automated test (`tests/test_api.py` as a
starting point), with the result of each one, and the failures noted in `LIMITATIONS.md`.

## 4. Data and ML

**Status:** the tool is already merged, but **there are no results** and there is nothing to do yet.

**Blocker:** messages written by real people are needed. The organizer's transcripts are not usable
(42 distinct customer texts, all about balances; see `docs/data_quality.md`). The messages come from the
form described in `docs/human_set.md`, with a floor of 60 messages from 8 people.

**Once unblocked:**
1. Download the messages from the form's D1 database and anonymize them as `docs/human_set.md` indicates.
2. Run the data and ML tool on them.
3. Record the result in `EVALUATION.md`. If the floor is not reached, say so there and do not report it as a result.

**Mind the deadline:** the D1 database is deleted after the final (October 16, 2026), so the messages must be exported
before then.
