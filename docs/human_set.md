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

`python -m eval.human_set.cloud export` downloads the answers to `eval/workload/human_raw.jsonl`. Each message becomes
one case of the workload format, with the case type of its situation and a synthetic customer chosen the way
`eval/workload.py` chooses one for that type, so the expected outcome still comes from the data and the written
policy. "1234" is replaced by the last four digits of the chosen customer's product. In the transfer situation, the
second turn is our fixed "sí", which the code evaluates. The case file goes in `eval/workload/`, which the public
export removes, because it carries customer ids of the dataset.

## Labels

Two people label every message on their own, before seeing any system output: it **matches** its situation, it is
**ambiguous** (asking back would be right), or it asks for **something else**. The agreement is reported as Cohen's
kappa before any disagreement is resolved; a third person settles the disagreements. Messages labeled "something
else" are dropped and counted, and "ambiguous" ones accept a clarifying question as a correct outcome.

## What is reported

The pass/fail rules (G0 to G4) were fixed before any message was scored: [`docs/preregistration.md`](preregistration.md).

The keyword bot and the live model (three runs) on the same cases, with the metrics of `EVALUATION.md`, the size
of the set, who wrote it (by country and language) and the kappa. The results are reported whatever they are:
they are not used to change the prompt, the rules or the classifier.

## Herramienta (`eval/human_set/classifier_eval.py`)

1. `python -m eval.human_set.classifier_eval sheet` genera la hoja para etiquetar (`eval/workload/human_labeling_sheet.csv`)
   con los mensajes de quienes no vieron el sistema, en orden mezclado y sin ninguna salida del sistema. Cada anotador la
   completa por su cuenta con `matches`, `ambiguous` o `something_else` en la columna `label`.
2. `... agreement A.csv B.csv [--third C.csv]` calcula el kappa de Cohen **antes** de resolver desacuerdos y escribe las
   etiquetas finales. Un desacuerdo sin tercera opinión queda fuera y contado.
3. `... score` puntúa el clasificador **congelado** y la línea base sobre lo que dos personas llamaron `matches`. Se niega a
   correr si el entrenamiento cambió respecto del modelo guardado, marca "NOT A RESULT" por debajo de 60 mensajes o de
   8 personas, lista los fallos de la guarda **sin corregirlos**, y declara cuántos mensajes son casi idénticos a frases de
   entrenamiento. Los resultados no se usan para ajustar el clasificador ni el léxico: un hueco se prueba en mensajes nuevos.
