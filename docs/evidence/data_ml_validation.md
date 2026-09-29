# Validación de buenas prácticas de datos y ML (auto-generado)

Generado por `make evidence` (`python -m eval.validate_data_ml --out-dir docs/evidence`) el 2026-09-29T15:44:26Z sobre el código `0d71649`.
Rúbrica: «Buena práctica de datos y ML: contratos, calidad, linaje, política de frescura, y al menos un componente aprendido
contra una línea base, sin fuga de datos». Resultado global: **PASS**. pytest: 43 passed in 9.69s.

Cada fila es una prueba de `tests/test_data_ml_validation.py`: hermética (warehouse de prueba de `tests/fixtures`, sin S3 ni claves), y falla si la
frase del documento que cita deja de ser cierta. Las cifras de la evidencia salen de la propia prueba, no se escriben a mano.

| Criterio | Resultado | Pruebas | Comando |
|---|---|---|---|
| Contratos | **PASS** | 11/11 | `python -m pytest tests/test_data_ml_validation.py -k test_contracts_ -q` |
| Calidad | **PASS** | 2/2 | `python -m pytest tests/test_data_ml_validation.py -k test_quality_ -q` |
| Linaje | **PASS** | 13/13 | `python -m pytest tests/test_data_ml_validation.py -k test_lineage_ -q` |
| Política de frescura | **PASS** | 4/4 | `python -m pytest tests/test_data_ml_validation.py -k test_freshness_ -q` |
| Componente aprendido contra una línea base | **PASS** | 5/5 | `python -m pytest tests/test_data_ml_validation.py -k test_learned_ -q` |
| Sin fuga de datos | **PASS** | 8/8 | `python -m pytest tests/test_data_ml_validation.py -k test_leakage_ -q` |

### Contratos: PASS

Afirma: docs/data_quality.md (Pipeline, pasos 2-5), data/contracts.py.

| Prueba | Resultado | Evidencia |
|---|---|---|
| every table has types key row model and they agree | PASS | 9 tablas: tipos, clave, NOT NULL y modelo pydantic coherentes; contrato 2.1.0 |
| the served tables have the dictionary types and keys | PASS | 95 columnas de 5 tablas servidas con el tipo del diccionario; sin claves repetidas |
| a violating row is quarantined with its reason and appears in the report | PASS | 2 de 5 filas del lote malo en _quarantine_transactions con motivo (rule:status_enum, cast:amount); checks de error fallidos en el reporte JSON y en _dq_results; las 3 válidas se cargaron |
| over the quarantine threshold the load stops and the previous state stays | PASS | lote con 40% en cuarentena (umbral 1%): PipelineError, tabla servida idéntica (mismo md5), carga 'failed' en _ingestion_log, `python -m data.pipeline` sale con error y el reporte dice status=failed |
| a missing required column fails the load | PASS | sin la columna obligatoria `amount` la carga falla ('missing required columns') y la tabla no cambia |
| a value that would be rounded to fit its type is quarantined not stored rounded | PASS | amount='200000.005' en un CSV real: error type_cast:amount, fila en cuarentena y no se guarda como 200000.01; '54.500' se acepta |
| valid amounts of any magnitude are stored exactly and only a rounding one is rejected | PASS | 523 importes válidos de 0.01 a 9999999999999.99 (incluido 8995304.28) cargados exactos; 200000.005 rechazado con cast:amount; una sola fila en cuarentena |
| the fixture warehouse loads without a single cast error | PASS | la carga del fixture sin ningún type_cast ni fila en cuarentena (38 filas leídas) |
| a truncated file cannot replace the rows it cuts off | PASS | un archivo cortado a mitad de la última fila: con el umbral por defecto la carga se detiene; aun tolerando todo, sus 5 filas van a cuarentena (con su archivo de origen) y la tabla servida queda idéntica |
| the documented severities are the ones the code assigns | PASS | tabla de severidades de docs/data_quality.md == severidades que asignan measure/pydantic_sample/quarantine; muestra pydantic = 1000 |
| each documented deviation is still measured as a warning | PASS | 2 desvíos del contrato: cada uno es una regla `warn` medida en cada carga y está en docs/data_quality.md |

### Calidad: PASS

Afirma: docs/data_quality.md (Pipeline paso 4, Findings).

| Prueba | Resultado | Evidencia |
|---|---|---|
| every check is persisted and the report counts them | PASS | 161 checks de la corrida del fixture: los 161 en _dq_results y en el JSON; conteos del resumen recalculados |
| the committed full run report is the one the doc quotes | PASS | quality_report.json (20260928T204248Z-31184c): 246 checks, 0 errores, 12 advertencias, 6,058,898 filas; 10 conteos del doc == los del reporte |

### Linaje: PASS

Afirma: docs/data_quality.md (Pipeline paso 8), data/lineage.py.

| Prueba | Resultado | Evidencia |
|---|---|---|
| every served row traces to a run a file and its hash | PASS | 5 tablas servidas: fila -> run -> contrato/código -> archivo -> SHA-256 (recalculado del disco, 7 archivos); `python -m data.lineage --verify` sin problemas |
| a broken chain is detected | PASS | se rompe la cadena de 5 maneras (fila sin run, run no exitoso, archivo sin hash, bytes cambiados, archivo borrado) y verify() lo dice; sin raw_dir, además, exige sha256 hex de 64, tamaño, URI, versión de contrato y de código, modo y horas no vacíos (10 casos negativos) |
| an incomplete record fails verification even without the raw files[UPDATE  source files SET sha256 = NULL WHERE table name = 'customers'-malformed sha256] | PASS | sha256 = NULL -> verify() sin raw_dir: customers: customers.csv in run 20260929T154420Z-5d067d has a missing or malformed sha256 |
| an incomplete record fails verification even without the raw files[UPDATE  source files SET sha256 = 'abc123' WHERE table name = 'customers'-malformed sha256] | PASS | sha256 = 'abc123' -> verify() sin raw_dir: customers: customers.csv in run 20260929T154420Z-f2ccfa has a missing or malformed sha256 |
| an incomplete record fails verification even without the raw files[UPDATE  source files SET sha256 = upper(sha256) WHERE table name = 'customers'-malformed sha256] | PASS | sha256 = upper(sha256) -> verify() sin raw_dir: customers: customers.csv in run 20260929T154420Z-a218cc has a missing or malformed sha256 |
| an incomplete record fails verification even without the raw files[UPDATE  source files SET n bytes = NULL WHERE table name = 'customers'-n bytes] | PASS | n_bytes = NULL -> verify() sin raw_dir: customers: customers.csv in run 20260929T154420Z-9755ff has a missing or malformed n_bytes |
| an incomplete record fails verification even without the raw files[UPDATE  source files SET source uri = '' WHERE table name = 'customers'-source uri] | PASS | source_uri = '' -> verify() sin raw_dir: customers: customers.csv in run 20260929T154421Z-0a0b6c has a missing or malformed source_uri |
| an incomplete record fails verification even without the raw files[UPDATE  ingestion log SET contract version = NULL WHERE table name = 'customers'-contract version] | PASS | contract_version = NULL -> verify() sin raw_dir: customers: run 20260929T154421Z-406244 does not record contract_version |
| an incomplete record fails verification even without the raw files[UPDATE  ingestion log SET contract version = '  ' WHERE table name = 'customers'-contract version] | PASS | contract_version = '  ' -> verify() sin raw_dir: customers: run 20260929T154421Z-4a7c79 does not record contract_version |
| an incomplete record fails verification even without the raw files[UPDATE  ingestion log SET code version = NULL WHERE table name = 'customers'-code version] | PASS | code_version = NULL -> verify() sin raw_dir: customers: run 20260929T154421Z-a3152d does not record code_version |
| an incomplete record fails verification even without the raw files[UPDATE  ingestion log SET finished at = NULL WHERE table name = 'customers'-finished at] | PASS | finished_at = NULL -> verify() sin raw_dir: customers: run 20260929T154421Z-714f9a does not record finished_at |
| an incomplete record fails verification even without the raw files[UPDATE  ingestion log SET mode = NULL WHERE table name = 'customers'-mode] | PASS | mode = NULL -> verify() sin raw_dir: customers: run 20260929T154422Z-264de6 does not record mode |
| a corrected partition shows which file and hash each row came from | PASS | tras una partición corregida, la fila corregida apunta al run y al hash de raw_late y las demás a los del primer run |

### Política de frescura: PASS

Afirma: docs/data_quality.md (Update and freshness policy).

| Prueba | Resultado | Evidencia |
|---|---|---|
| the documented defaults and the as of date | PASS | sin FRESHNESS_ENFORCE se sirve el dato de 2024 con as_of=2024-01-16; SLO por defecto 36 h; lookback 3 días |
| stale data is unavailable on the gated tools and only on them | PASS | FRESHNESS_ENFORCE=1: saldo, movimientos y estado de pago -> DataUnavailable(as_of); perfil y tipo de cambio siguen |
| the limit is the slo in hours measured from the data date | PASS | as_of 2024-01-16: hoy+1 día (24 h) sirve; hoy+2 (48 h) bloquea con SLO 36; con SLO 48 sirve; sin fecha bloquea |
| a stale warehouse ends in an escalation not an answer | PASS | misma pregunta: sin política AUTO_RESOLVE con 'al 16/01/2024'; con dato vencido ESCALATE/data_unavailable con ticket y sin la cifra |

### Componente aprendido contra una línea base: PASS

Afirma: EVALUATION.md §2, eval/reports/intent_classifier.md.

| Prueba | Resultado | Evidencia |
|---|---|---|
| beats the keyword baseline on the same test split with intervals | PASS | test n=85: aprendido 84.7% [75.6–90.8] vs palabras clave 62.4% [51.7–71.9]; diferencia pareada +22.4 pts [+9.4, +35.3], McNemar p=0.001878; piso mayoritaria 17.6% [11.0–27.1] |
| the committed report is what the code and data produce | PASS | build_report() sobre los CSV del repo reproduce las 1148 cifras del reporte JSON versionado y el texto completo del Markdown (solo se excluyen la hora de generación y la versión de sklearn); hashes de datos == los de los archivos |
| altering any published metric makes the comparison fail | PASS | cada una de las 1148 cifras del reporte (incluidos macro-F1 aprendido, exactitud PT y exactitud sin frases de plantilla), alterada de a una, hace que la comparación falle en exactamente esa ruta |
| the deployed model is the one that was selected and reported | PASS | eval/models/intent_clf.joblib da las mismas probabilidades que el modelo reentrenado (356 frases, tol 1e-9); meta: char+word, τ=0.55, mismo hash de entrenamiento |
| the paired statistics agree with a hand worked case | PASS | diferencia pareada y McNemar exacto comprobados a mano en un caso de 10 ítems (4 a favor, 1 en contra, p = 12/32); el bootstrap es reproducible con semilla |

### Sin fuga de datos: PASS

Afirma: EVALUATION.md §2, eval/leakage.py, LIMITATIONS.md (Data and ML).

| Prueba | Resultado | Evidencia |
|---|---|---|
| nothing chosen moves when the test split changes | PASS | con las etiquetas del test rotadas: variante (char+word), τ (0.55), F1 de dev y barrido idénticos y la exactitud de test cambia; rotando dev sí cambia la selección (control positivo) |
| near duplicates between train dev and test | PASS | similitud máxima de trigramas de caracteres (excluye ≥ 0.9): {'dev↔train': 0.647, 'test↔train': 0.679, 'test↔dev': 0.826}; frases excluidas del puntaje: 1 de 174 |
| the check catches a copy of a training phrase and keeps it out of the scores | PASS | una copia de una frase de entrenamiento (otra capitalización, puntuación y espacios) se detecta y no entra al puntaje |
| the only input of the learned component is the customers words | PASS | features = texto del cliente: train() solo lee `utterance` e `intent`; reentrenar con columnas basura da las mismas probabilidades; ni el clasificador ni la guarda importan duckdb, herramientas ni el warehouse (sin info posterior al resultado) |
| the two datasets are the ones frozen before measuring and the workloads do not share cases | PASS | hashes de entrenamiento y held-out == los del reporte y del modelo desplegado; workloads dev/test sin (plantilla, cliente) compartidos; similitud máxima de los turnos del workload con el entrenamiento: {'dev': 0.787, 'test': 0.787} |
| the workload generator rejects a training phrase with other punctuation | PASS | el generador de workloads rechaza un turno que es una frase de entrenamiento con otra capitalización o puntuación (antes solo comparaba strip().lower()) |
| the test misses were reported not tuned away | PASS | 1 escalación(es) omitida(s) en test, ['vou processar o banco']: siguen fuera del léxico y bajo τ=0.55; están declaradas en EVALUATION.md y LIMITATIONS.md |
| evaluation doc section 2 quotes the committed report | PASS | 26 cifras de EVALUATION.md §2 == eval/reports/intent_classifier.json; el titular coincide en README, slides_outline y LIMITATIONS |

## Lo que esto no cierra (declarado)

- Los textos de entrenamiento y de held-out los escribió el mismo equipo (LIMITATIONS.md, «No usable text»): la diferencia con la línea base es real en este held-out, no una medida sobre clientes reales.
- El orden cronológico (entrenamiento y línea base congelados antes de escribir el held-out) no se puede probar con el historial de git, que empieza en una sola importación; lo que sí se prueba es que los archivos no cambiaron desde que se midieron (hashes).
- Los cortes de similitud (0.90 y 0.60) se fijaron mirando la distribución de todo el held-out, dev y test juntos; una frase se dejó fuera (LIMITATIONS.md).
- La decisión de no reentrenar el clasificador con ejemplos de rastreo se tomó viendo el split de test (LIMITATIONS.md, «The action»).
- Una similitud de caracteres no ve una paráfrasis con otras palabras (eval/leakage.py).
- El reporte de calidad de la corrida completa (`data/reports/quality_report.json`) sale del bucket del organizador y no se regenera aquí; estas pruebas comprueban que el documento lo cita bien, no que los datos sigan siendo esos.
