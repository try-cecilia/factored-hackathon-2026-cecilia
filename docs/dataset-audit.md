# Auditoría del dataset y consecuencias para el diseño

Auditoría realizada el 28 de septiembre de 2026 sobre el dataset de S3 identificado en el diccionario provisto por la organización. Las recomendaciones incorporan la lectura completa de la [consigna oficial](https://docs.google.com/document/d/18AwONT8hQupRcfNPLFrPo6fHOJ_OUn1nBf-3jMnla2c/edit).

## Recomendación

Las consultas de saldo quedan descartadas como problema a resolver. Su presencia en todas las transcripciones se explica por la repetición de plantillas y no permite justificar su prioridad por demanda. Conservamos ese hallazgo como limitación del corpus.

Quedan como alternativas pagos y reclamos. Las transacciones permiten construir consultas verificadas de estado y las categorías de reclamos documentan problemas registrados en este dataset sintético. No permiten demostrar que las transferencias no recibidas sean un motivo de contacto frecuente. El flujo principal todavía no está elegido. Debe incluir una persona visible en la conversación, una acción de negocio aprobada y verificada en el simulador, y casos persistentes. La reversión es una posible acción, todavía pendiente de elección.

Mantenemos la decisión original de no entrenar un modelo propio. La consigna permite modelos preentrenados y no exige entrenar uno nuevo. Hay que evaluar un componente como Jev contra un baseline determinista, con labels revisados y un workload held-out compartido. Data engineering y evaluación con métricas siguen siendo obligatorios.

El hallazgo técnico principal es que un registro puede cumplir el schema y aun así ser inadecuado para un uso concreto. Antes de confiar en un join, la app y el evaluador deben verificar ownership, consistencia temporal, evidencia disponible y significado de los labels.

## Cobertura y reproducibilidad

La auditoría inventarió las 13 tablas. Procesó todos los archivos de 11 tablas y una muestra por fechas de las otras dos tablas de eventos. En total analizó 6.311.493 filas de 5.516 archivos, equivalentes a 1.309.213.022 bytes. Son conteos obtenidos al parsear los archivos, no estimaciones del PDF.

| Tabla | Filas analizadas | Cobertura |
| --- | ---: | --- |
| Clientes | 150.000 | Completa |
| Productos | 400.000 | Completa |
| Sucursales | 350 | Completa |
| Agentes de atención | 1.200 | Completa |
| Campañas de marketing | 200 | Completa |
| Tipos de cambio diarios | 13.164 | Completa |
| Interacciones de call center | 686.296 | Los 1.097 archivos diarios |
| Transcripciones | 171.321 | Los 1.097 archivos diarios |
| Reclamos | 67.095 | Los 1.097 archivos diarios |
| Encuestas de satisfacción | 212.759 | Los 1.097 archivos diarios |
| Transacciones | 4.425.008 | Los 1.097 archivos diarios |
| Eventos digitales | 164.857 | 13 fechas, día 17 de marzo, junio, septiembre y diciembre cuando está disponible |
| Envíos de campañas | 19.243 | 12 fechas con la misma regla de selección |

Las muestras de eventos no son aleatorias ni se diseñaron para ser representativas. Sus tasas no deben extrapolarse a la población completa. La cobertura de archivos diarios llega al 17 de junio de 2026, aunque algunos timestamps de eventos llegan al 18 de junio. Process day y event day son distintos. Esa diferencia por sí sola no demuestra late ingestion.

Cada archivo tiene metadata del objeto, SHA256 local, conteo de filas y lineage por registro en la base local de auditoría. Una segunda implementación, con el parser CSV de la biblioteca estándar de Python, volvió a leer todos los archivos y coincidió en los conteos y SHA256. Hubo cero diferencias. La auditoría usó scripts exploratorios locales en TypeScript y SQL. Esos scripts quedan excluidos del control de versiones y no fijan la tecnología del proyecto.

Un rebuild completo también reprodujo los hashes y conteos de los 5.516 archivos y los hashes de ambos datasets de evaluación. Esto verifica reproducibilidad en el entorno local con los mismos bytes de origen. Falta publicar la implementación y los comandos en el lenguaje que elija el equipo para poder repetir el proceso desde un checkout limpio. Los manifests y resultados por sí solos no reemplazan esa entrega. Tampoco demuestran que los registros sean correctos para cualquier uso.

Los artefactos de evidencia permanecen en el entorno local, bajo `reports/data-audit/`. Esta entrega incluye solo documentación Markdown. Los scripts, reportes y datasets no están incluidos y no estarán disponibles en un checkout nuevo.

- `source-manifest.json`, con objetos seleccionados, cobertura y bytes.
- `ingestion.json`, con hashes, conteos, variantes de schema, nulos y duplicados.
- `metrics.json` y `queries.sql`, con hallazgos agregados y consultas usadas en la auditoría.
- `independent-verification.json`, con resultados del segundo parser.
- `reproducibility.json`, con la comparación del rebuild completo.
- `quality-gates.json`, con fallos vinculados al uso afectado.

## Qué respaldan los contactos

| Categoría de origen | Contactos | Proporción | Tasa registrada de casos sin resolver |
| --- | ---: | ---: | ---: |
| Transaccional | 240.056 | 34,98% | 8,49% |
| Producto | 150.863 | 21,98% | 10,37% |
| Queja | 117.021 | 17,05% | 56,40% |
| Técnico | 102.899 | 14,99% | 30,07% |
| Comercial | 54.879 | 8,00% | 34,79% |
| Retención | 20.578 | 3,00% | 39,84% |

El denominador son las 686.296 interacciones. Estas categorías son metadata descriptiva del origen. `contact_reason` coincide con `reason_category` en todas las filas. No hay un label independiente con un motivo más específico.

Los 171.321 textos de clientes mencionan un saldo. Los checks léxicos documentados no encontraron menciones de transferencias, cargos no reconocidos, comisiones ni pagos. La revisión de los 42 textos distintos encontró dos preguntas iniciales, una sobre saldo de caja de ahorro y otra sobre saldo de tarjeta de crédito. A estas se agregan frases conversacionales genéricas. Hay solo 546 transcripciones completas distintas y 42 textos distintos del agente.

Cada una de las 42 variantes aparece bajo varias categorías de motivo. `detected_intents` contiene `consulta_general` cuando no es nulo. Esto limita las conclusiones:

- Las consultas de saldo están presentes, pero su repetición no permite medir su demanda ni justificar su prioridad como producto.
- Las proporciones por categoría no equivalen a proporciones de intención semántica validadas.
- El conteo de transcripciones no representa 171.321 ejemplos lingüísticos distintos ni demanda real de mercado.
- No se puede medir la prevalencia de consultas por transferencias no recibidas a partir de estas transcripciones.

La tabla de transacciones contiene 896.438 transferencias. Incluye 17.841 Pending, 44.979 Declined y 8.942 Reversed. Estos registros permiten consultar estados y construir escenarios controlados. No prueban que haya existido una consulta, una demora ni recepción por el beneficiario. No hay una secuencia de liquidación ni un ledger vinculado del beneficiario.

Los reclamos incluyen 12.297 casos en la subcategoría Cargo no reconocido y 12.194 en Cobro indebido. Sin embargo, toda la tabla usa solo cinco descripciones genéricas. Las categorías permiten describir volumen de reclamos, pero las descripciones ofrecen poca variedad para evaluar lenguaje natural.

## Defectos de calidad que cambian el diseño

| Hallazgo | Resultado medido | Consecuencia |
| --- | --- | --- |
| Ownership entre reclamo y producto | Las 44.570 referencias no nulas apuntan a un producto de otro cliente. | Bloquear ese join en serving y labeling. No cambiar silenciosamente ninguno de los propietarios. |
| Vínculo entre reclamo e interacción | `origin_interaction_id` es nulo en los 67.095 reclamos. | No se pueden usar como resultados vinculados a conversaciones. |
| Sucursal de registro del cliente | 149.995 de 150.000 referencias apuntan a sucursales inexistentes. | Excluir features y atribuciones basadas en esa sucursal. |
| Sucursal del agente | 831 de las 833 referencias no nulas apuntan a sucursales inexistentes. | No usar esa relación para routing de agentes por sucursal. |
| Contacto anterior al registro | 128.453 de 686.296 contactos, un 18,72%. | Excluir cronologías imposibles de la cohorte histórica candidata. |
| Cronología de pagos | 1.451.309 de 4.425.008 transacciones, un 32,80%, son anteriores al registro del cliente, la apertura del producto o ambos. | Solo 2.973.699 pasan los dos controles. |
| Duración obligatoria de transcripción | 24.029 duraciones nulas, aunque el diccionario exige el campo. | Registrar la violación del contrato. No imputar duración para evaluar resultados. |
| Dimensiones históricas | Clientes y productos son archivos únicos. No se exponen snapshots mensuales. Algunos `last_updated` llegan a junio de 2027. | No usar saldos y estados actuales como features históricas al inicio de una consulta ni como observaciones en vivo. |
| Cobertura de moneda | No hay transacciones MXN. Las 2.216.431 transacciones de clientes de México están en USD. | Documentar la cobertura real. Estos registros no respaldan una demo en MXN. |
| Conciliación de conversión a USD | 749.769 filas ARS y 1.031.847 COP con importe USD informado difieren en más de un centavo de la conversión con el tipo de cambio de ese día calendario. | No usar `amount_usd` como evidencia financiera verificada hasta resolver la convención de conversión. |

Verificar solo la existencia de foreign keys no detectaría el defecto de ownership de los reclamos. La cadena transacción → producto → cliente, en cambio, tiene cero discrepancias de ownership en las 4.425.008 transacciones. También coincide el cliente entre transcripción e interacción, y entre encuesta e interacción. Estas relaciones son utilizables después de aplicar controles temporales y específicos del propósito.

El origen no incluye saldo de apertura, asientos con signo de débito o crédito ni un historial completo de saldos. Todos los importes observados son positivos. Sumarlos no permite conciliar `current_balance`. Aunque las consultas de saldo quedaron fuera del alcance, esta limitación sigue afectando cualquier reversión opcional. Para verificarla se necesita el ledger independiente del simulador.

Todos los archivos seleccionados pudieron parsearse, cada tabla presentó un único header schema y no aparecieron business keys duplicadas en las entradas analizadas. Esto difiere de la tasa aproximada de duplicados que describe el diccionario. No descarta defectos en archivos digitales o de campañas no muestreados ni en futuras entregas. El pipeline exploratorio local incluye fixtures controlados de duplicación, conflictos, truncamiento y cambios de schema para probar esos comportamientos. Esos fixtures no están incluidos en esta entrega de documentación.

Un vínculo inválido con un producto no obliga a descartar todo el reclamo. Se puede conservar para análisis agregado por categoría y prohibir el join inseguro. La decisión de calidad depende del uso.

## Labels y leakage

`was_escalated` ronda el 10% en las seis categorías. Un clasificador que siempre predice que no habrá escalación obtiene 90,03% de accuracy en la partición exploratoria de 2026. Esto muestra el riesgo de usar accuracy como única métrica. La auditoría no demuestra que la escalación sea impredecible, pero un predictor de ese resultado necesita más justificación.

`was_resolved` varía entre categorías, aunque estas contradicen el texto visible y no está probado que estén disponibles al inicio de la consulta. `requires_followup` es verdadero en todos los casos registrados como no resueltos, por lo que introduce riesgo de leakage del resultado. Las transcripciones completas, respuestas del agente, duración, satisfacción, fechas de resolución y compensaciones no deben convertirse en features de entrada.

En un split temporal simple con 2026 como holdout diagnóstico:

- 74.303 de los 75.981 clientes held-out ya aparecen antes, un 97,79%.
- Las 26.620 transcripciones held-out repiten texto de clientes visto antes.
- Cada una de las 42 variantes se asocia con varios resultados de escalación y varias categorías de motivo.

Un split aleatorio por filas ocultaría estos problemas. Dos familias de preguntas iniciales no alcanzan para un benchmark lingüístico amplio con separación estricta por plantilla. Hay que crear o transformar lenguaje ES/PT bajo un protocolo documentado, revisarlo y mantenerlo separado del desarrollo de prompts. Las traducciones siguen vinculadas al caso original.

## Artefactos de evaluación construidos

El archivo local `reports/data-audit/evaluation-manifest.json` registra splits reproducibles por hash de cliente y fecha. Después de excluir contactos anteriores al registro, quedan estas cohortes estructuradas:

| Partición | Casos | Clientes únicos |
| --- | ---: | ---: |
| Train/development | 245.074 | 81.202 |
| Validation | 15.839 | 11.050 |
| Test candidato | 15.675 | 11.229 |

No hay clientes compartidos entre las particiones retenidas. Otros 281.255 contactos con cronología válida quedan fuera de las combinaciones seleccionadas de cliente y período. Esa exclusión está registrada. Son datasets históricos candidatos y no obligan a entrenar un modelo. Sus resultados agregados se inspeccionaron durante la auditoría, por lo que no constituyen un benchmark ciego ya ejecutado.

El pipeline también seleccionó 200 clientes distintos, con 50 contextos de pagos por estado, y creó 3.600 fixtures estructurados. Surgen de 200 contextos × dos idiomas × nueve variantes. Cubren consulta normal, propietario incorrecto, estado faltante, sesión vencida, prompt injection, fallo de tool, ambigüedad multilingüe, moneda inconsistente y observación vencida.

Estos fixtures sirven para verificación determinista y desarrollo del runner. La cantidad de contextos independientes es 200. Las 3.600 variantes no son conversaciones independientes. Los prompts son sintéticos, falta revisión lingüística y todavía no se evaluó ningún agente. No reemplazan un workload held-out diverso y revisado ni una comparación real contra el baseline. Cubren consultas de estado de pagos y no fijan el alcance. Faltan escenarios de la acción aprobada, participación humana y persistencia, además de cualquier adaptación necesaria si se eligen reclamos.

## Próxima implementación recomendada

1. Elegir un flujo entre pagos y reclamos a partir de su evidencia y limitaciones, sin usar la repetición de consultas de saldo como señal de demanda. Mantener aclaraciones, participación humana visible, una acción de negocio aprobada y verificada y casos persistentes. Identificar las mutaciones financieras como trabajo del simulador.
2. Publicar hechos permitidos con lineage y flags explícitos de calidad. Ownership inválido, evidencia faltante y fallos de freshness deben activar gates deterministas antes de enviar datos al modelo.
3. Comparar un baseline ES/PT de reglas de intención y ambigüedad con Jev usando labels revisados de forma independiente. Ambos deben compartir tools, permisos y verificación. No usar `reason_category` como ground truth semántico de estas transcripciones.
4. Ejecutar los sistemas completos sobre el mismo workload held-out y reportar resultados, escalación, seguridad, latencia, costo y diferencias entre grupos según la consigna. Seguir el [protocolo de evaluación](evaluation-protocol.md).

La auditoría está completa con la cobertura declarada. Quedan pendientes el pipeline compartido en el stack elegido, las mediciones del baseline y del modelo, la revisión lingüística humana y la verificación en runtime de la aplicación bancaria.
