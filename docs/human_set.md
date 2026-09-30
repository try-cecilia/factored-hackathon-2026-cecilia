# The human-written test set

Every message in the offline and live workloads was written by the team that built the system; the organizer's
transcripts cannot replace them (42 distinct customer texts, all in Spanish and every one about a balance). A score measured on
our own phrasing can hide how the assistant reads the way customers actually write. This set measures that: people
who never saw the assistant write the messages, and nothing in the system changes after seeing the results.

## Collection

- **The form** (`eval/human_set/worker.js`, live at `marvaq.com/encuesta`, Portuguese at `/encuesta/pt`) shows ten
  situations, one per case type of the workload, and asks for the message the person would send their bank's chat,
  in their own words. The situations name the goal, not the words: "saber cuánto dinero tenés en total en tus
  cuentas", not "consultar el saldo".
- **Who.** Relatives, friends and co-workers of the team, invited by message. Anyone who is on the team or has
  tried the assistant says so on the form and is excluded.
- **No personal data.** The form asks only for the country and the consent; it stores no name, no e-mail and no IP
  address, and asks people to write 1234 wherever an account number would go. The answers live in a D1 database
  that is deleted after the final (16/10/2026).
- **Floor.** At least 60 messages from 8 people by 30/09/2026 at night. Below that, the set is not reported as a
  result, and this document says so.

## From messages to cases

`python -m eval.human_set.cloud export` downloads the answers to `eval/workload/human_raw.jsonl`. Each labeled message
(see below) becomes one case of the workload format (`python -m eval.human_set.cases`), with the case type of its
situation and a synthetic customer chosen the way `eval/workload.py` chooses one for that type (Active, with the data
the type needs; one per message, by `md5(customer_id || message_id)`), so the expected outcome still comes from the
data and the written policy. A message about one account or one debit card still points to exactly one product: the
account is of the kind its words name (savings or checking), and without a number the customer has only one open
product of that kind. "1234" is replaced by the last four digits of the product the message is about (the
account, the debit card, the credit card, the account of the pending transfer, a card for the unknown charge); in the
other situations, such as the mother's account, it stays as written. In the transfer situation, the second turn is our
fixed "sí" ("sim"), which the code evaluates. The mother's-account situation is its own case type, judged on safety
only, since whose account it is cannot be checked in code. The case file goes in `eval/workload/`, which the public
export removes, because it carries customer ids of the dataset.

## Labels

Two people label every message on their own, before seeing any system output: it **matches** its situation, it is
**ambiguous** (asking back would be right), or it asks for **something else**. The agreement is reported as Cohen's
kappa before any disagreement is resolved; a third person settles the disagreements. Messages labeled "something
else" are dropped and counted, and "ambiguous" ones accept a clarifying question as a correct outcome. The judge counts
a case in scope for safe automated resolution only when answering is its single accepted outcome, so ambiguous messages
count for correct disposition and safety, not for that rate.

## What is reported

The pass/fail rules (G0 to G4) were fixed before any message was scored: [`docs/preregistration.md`](preregistration.md).
`eval/human_set/report.py` evaluates them in code, as its section 3 fixes the computation (the worst of the three live
runs decides).

The keyword bot and the live model (three runs) on the same cases, with the metrics of `EVALUATION.md`, the size
of the set, who wrote it (by country and language), the kappa and what was dropped. A few failing messages may be
quoted as written, as the consent allows; the files that carry every message stay out of the public export. The
results are reported whatever they are: they are not used to change the prompt, the rules or the classifier.

## The pipeline, in order

Every file below lives in `eval/workload/` (which the public export removes), except the reports.

1. **Export** (whoever holds the Cloudflare token file, `CLOUDFLARE_SECRETS`): `make human-set-export` writes
   `eval/workload/human_raw.jsonl`.
2. **Sheet** (whoever builds the set): `make human-set-sheet` writes `human_labeling_sheet.csv` with the messages of
   the people who never saw the system, shuffled with a fixed seed and without any output of the system.
3. **Pages** (same person): `make human-set-pages LABELERS="name1 name2"` writes one page per labeler,
   `human_labeling_<name>.html`: each message as text next to the Spanish situation its writer read, and three choices
   (Coincide, Ambiguo, Otra cosa). It opens from the file system, makes no network call, saves the progress in the
   browser when it can, and downloads `human_labels_<name>.csv` with the sheet's columns (or copies it, where a download
   fails). If a phone only previews the file and the choices do nothing, the labeler opens it on a computer.
4. **Send** (same person): each labeler gets only their own page, in private.
5. **Label** (the two labelers, each alone, without talking about it until both have sent their file): every message,
   then the CSV back to the sender, who puts it in `eval/workload/`.
6. **Agreement** (whoever builds the set): `make human-set-agreement A=... B=...` prints Cohen's kappa of the two
   **before** any disagreement is settled, writes the final labels (`human_labels_final.csv`) and lists the
   disagreements in `eval/reports/human_set_agreement.json`. A disagreement without a third opinion is left out and
   counted.
7. **Third person** (someone who is neither labeler): `make human-set-pages LABELERS=name DISAGREEMENTS=1` builds a
   page with only the disagreements, labeled blind; then step 6 again with `THIRD=human_labels_name.csv`.
8. **Cases** (whoever builds the set): `make human-set-cases` reads the full warehouse and writes `human_cases.jsonl`
   and its provenance, `human_cases_meta.json` (counts, what was dropped and why, message id to case id).
9. **Evaluation** (whoever holds the model key): `make human-set-eval`, the standard `run_system_eval --cases` run: the
   keyword bot once and the live model (Sonnet 5) three times on the same cases. It spends model credit, about USD 1
   to 2, and stops without the key.
10. **Report** (whoever builds the set): `make human-set-report` evaluates G0 to G4 in code and writes
    `eval/reports/HUMAN_SET.md` (and `human_set.json`). Below G0 it says NOT A RESULT.

On the same labels, `python -m eval.human_set.classifier_eval score` scores the **frozen** intent classifier and the
keyword baseline on what two people called `matches`. It refuses to run if the training data changed after the saved
model, says NOT A RESULT under 60 messages or 8 people, lists the guard's misses **without fixing them**, and declares
how many messages are near-identical to training phrases.
