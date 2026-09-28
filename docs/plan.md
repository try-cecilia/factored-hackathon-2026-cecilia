# Plan para el hackathon de Factored AI

Actualizado el 28 de septiembre de 2026, después de leer completa la [consigna oficial](https://docs.google.com/document/d/18AwONT8hQupRcfNPLFrPo6fHOJ_OUn1nBf-3jMnla2c/edit) y auditar el dataset provisto.

## Objetivo y respaldo en los datos

Construir un servicio bancario con IA que siga el ciclo Understand → Decide → Act → Verify → Escalate. El sistema debe entender la consulta, elegir una acción permitida, ejecutarla mediante tools, verificar el resultado y escalar cuando corresponda. La entrega incluye una app para clientes y una consola para empleados, conectadas mediante casos persistentes.

La demo original era "Mi transferencia no llegó", con una reversión simulada aprobada por una persona. La auditoría no permite demostrar demanda por ese motivo de contacto. Las 171.321 transcripciones de clientes hablan de saldos y ninguna menciona transferencias. El dataset contiene estados de pagos, pero no tiene una secuencia de liquidación ni un ledger del beneficiario.

Descartamos las consultas de saldo como problema a resolver en esta entrega. Las transcripciones repiten solo 42 textos de cliente derivados de dos preguntas iniciales. Esa repetición no justifica priorizar saldos por demanda.

El caso principal queda pendiente de elección entre pagos y reclamos. Las transacciones permiten verificar estados; las categorías de reclamos aportan evidencia de problemas registrados en el corpus sintético. Sus limitaciones están documentadas en la auditoría. El flujo elegido debe incluir participación humana visible, una acción de negocio aprobada y verificada, y persistencia del caso. La reversión es una acción candidata del simulador. Podemos elegir otra, pero una consulta de estado o la creación de un ticket por sí solas no completan el alcance acordado.

## Requisitos de producto que mantenemos

- El cliente ve a la persona que interviene, su nombre y rol, y sus mensajes dentro de la conversación. El handoff conserva el contexto. La consola permite al empleado tomar el caso, conversar, aprobar o rechazar y devolver el control a la automatización.
- La demo ejecuta al menos una acción de negocio que cambia el estado de una operación o producto en el simulador bancario. Requiere aprobación humana explícita y verificación independiente del resultado. Mostrar una propuesta o registrar un ticket no cuenta como ejecución de esa acción.
- Los casos persisten entre sesiones y sobreviven a refresh, reconexión y reinicio del worker. Se conservan conversación, responsable, aprobaciones, operación, evidencia y timeline. La reanudación no puede duplicar efectos.

Estos requisitos se mantienen aunque cambien el caso de uso y las tecnologías. El recorrido con intervención humana y acción aprobada se evalúa por separado de la resolución automática, porque requiere una persona.

Los resultados y sus límites están en [dataset-audit.md](dataset-audit.md). El proceso de evaluación está en [evaluation-protocol.md](evaluation-protocol.md).

## Qué exige la consigna

- Un flujo coherente de atención bancaria respaldado por datos, con resolución normal, ambigüedad o solicitudes fuera de alcance e intervención humana.
- Interacciones en español y portugués, con sus limitaciones de cobertura documentadas. Inglés no es obligatorio y se propone quitarlo del alcance comprometido.
- Preparación reproducible de datos, contratos, quality checks, lineage y una política de actualización y freshness.
- Al menos un componente aprendido evaluado contra un baseline apropiado. Entrenar un modelo nuevo es opcional. Mantenemos la decisión original de usar un componente preentrenado.
- Baseline y candidato sobre el mismo workload held-out, con datos incorrectos o faltantes, sesiones vencidas, accesos no autorizados, prompt injection, fallos de tools y ambigüedad multilingüe.
- Resultados correctos e inseguros, calidad del handoff, latencia, costo, tamaño de muestra y limitaciones. Hay que distinguir containment de resolución segura.
- Traces, retries acotados, fallback seguro, setup reproducible, controles de acceso y un plan concreto para operar la solución.

La consigna no fija una cantidad mínima de casos de prueba. Hay que justificar el tamaño y la cobertura del workload. Tampoco exige streaming, múltiples agentes, dashboards ni integración bancaria real. Permite tools de sandbox y una sesión de prueba confiable.

## Restricciones, arquitectura y tecnologías pendientes

El stack sigue abierto. TypeScript, Turborepo y TanStack Start fueron propuestas iniciales. Python también es una opción para backend, data engineering y evaluación. La auditoría exploratoria no define el lenguaje del producto ni el del pipeline definitivo.

| Área | Decisión |
| --- | --- |
| Plazo | Diez días, previstos del 28 de septiembre al 7 de octubre de 2026. Falta confirmar la hora oficial de entrega. |
| Capacidad | Tres personas, dos horas por día hábil y entre cuatro y seis horas por persona cada día del fin de semana. Entre 72 y 84 horas-persona. |
| Frontend | Web chat dentro de la app bancaria simulada. TanStack Start es una opción inicial, pendiente de confirmación. |
| Repositorio y lenguajes | Organización y herramientas por definir. Evaluar TypeScript, Python o una combinación según el trabajo de cada componente. Turborepo queda como candidato si encaja con el stack elegido. |
| Arquitectura | Monolito modular con vertical slices y ports/adapters donde aporten aislamiento. |
| Comportamiento del agente | Híbrido. Investigación acotada con IA y reglas explícitas persistidas para transiciones con consecuencias. |
| Casos | Asíncronos y reanudables, con timeline y actualizaciones dentro de la app. |
| Control humano | Aprobar o rechazar acciones, tomar la conversación y devolver el control a la automatización de forma explícita. |
| Identidad | Cuentas precreadas, sesiones confiables y autorización en servidor y tools. Sin registro ni onboarding. |
| Autoridad financiera | La investigación rutinaria puede ser automática. Las mutaciones financieras requieren aprobación humana y son simuladas. |
| IA | Jev vía OpenRouter como clasificador candidato y un LLM conversacional para el diálogo. Falta verificar la integración, el schema y los modelos concretos. |
| Hosting | Cloudflare y Vercel son candidatos iniciales. Revisar la elección junto con los lenguajes, jobs y runtime antes del deployment. No hay créditos disponibles. |
| Base de datos | PostgreSQL o MySQL. Elegir acceso a datos y ORM después del lenguaje. Drizzle fue una propuesta para TypeScript. |

## Comportamiento del producto

El cliente inicia sesión y consulta en ES o PT sobre una operación o reclamo, según el flujo que se elija. El sistema recupera solo los datos permitidos, pide aclaraciones cuando la selección es ambigua y muestra avances respaldados por eventos registrados. Debe indicar si el dato corresponde a un snapshot histórico o al simulador. No puede afirmar que un pago se liquidó o un reclamo se resolvió sin evidencia.

El cliente ve quién tiene el caso, cuándo un empleado toma la conversación y qué mensajes provienen de esa persona. Las intervenciones quedan en el mismo historial y continúan disponibles al volver a la app. Los estados de espera de aprobación, ejecución, verificación y resolución deben reflejar eventos persistidos.

El empleado ve la solicitud, los hechos verificados, las acciones realizadas, la evidencia y las preguntas pendientes. Durante el takeover, la IA deja de responder al cliente, aunque puede preparar resúmenes internos. La aprobación de acciones y el control de la conversación son permisos distintos.

La acción elegida debe ejecutarse en el servicio bancario del sandbox y cambiar su estado autoritativo. La aprobación queda vinculada a la acción, sus parámetros y la versión del registro. Incluye importe y moneda cuando corresponda. El executor vuelve a verificar la elegibilidad, usa una idempotency key estable y consulta de forma independiente el resultado. Para una reversión, verifica la operación y el ledger. Si el resultado es incierto, el caso sigue abierto con verificación pendiente. Antes de reintentar, debe consultar la operación existente.

Persistir el caso antes de despachar trabajo asíncrono. Al reanudar, recuperar el estado, la asignación humana, la aprobación vigente y el identificador de operación. La demo debe mostrar que un caso abierto puede retomarse y que una acción ya ejecutada no vuelve a aplicarse por un refresh o retry.

El texto generado por un modelo no puede conceder acceso, cambiar políticas ni declarar exitosa una acción sin verificarla.

## Data engineering como entrega central

La auditoría inicial se ejecutó con scripts exploratorios locales, excluidos del control de versiones. Sus resultados están documentados en [dataset-audit.md](dataset-audit.md). Inventarió las 13 tablas y procesó 6.311.493 filas de 5.516 archivos. Incluye 11 tablas completas y muestras explícitas de eventos digitales y envíos de campañas. Una lectura independiente coincidió en el conteo de filas y el SHA256 de cada archivo analizado.

El [catálogo de validaciones](data-validation-catalog.md) contrasta el diccionario con los errores observados y define controles de ingesta por uso. Incluye primary keys, restricciones `UNIQUE` adicionales, ownership, cronología, parsing sin pérdida y evidencia faltante para operar con importes.

El pipeline definitivo debe cubrir estas etapas, con el lenguaje que elija el equipo:

1. Inventariar y descargar un conjunto declarado de objetos de origen.
2. Parsear y validar archivos, con registros de schema, claves, conteos, hashes y lineage.
3. Separar duplicados exactos, claves en conflicto, registros malformados y relaciones que no se pueden usar.
4. Verificar ownership, cronología, significado de labels, evidencia faltante y límites de los snapshots.
5. Publicar datasets de serving y evaluación con un propósito explícito y sus manifests.
6. Verificar replay, actualizaciones, aislamiento entre cohortes y quality gates por uso.

Los scripts locales permitieron validar este proceso, pero todavía falta incorporar al repositorio una implementación que el equipo pueda ejecutar desde un checkout limpio. Conservamos manifests, consultas SQL y resultados de la auditoría en el entorno local. Esta entrega incluye solo documentación Markdown. La implementación compartida y sus comandos se definirán al cerrar el stack.

Hallazgos que afectan el diseño:

- Las 44.570 referencias no nulas de reclamos a productos apuntan a productos de otro cliente. Ese join debe bloquearse.
- Los 67.095 reclamos tienen vacía la referencia a la interacción de origen. No sirven como labels vinculados a conversaciones.
- Hay 128.453 interacciones anteriores al registro del cliente. Se excluyen de las cohortes históricas candidatas.
- Solo 2.973.699 transacciones pasan ambos controles de cronología, registro del cliente y apertura del producto.
- La cadena de ownership transacción → producto → cliente sí es consistente en las 4.425.008 transacciones.
- Clientes y productos son snapshots únicos. Sus saldos y estados actuales no pueden usarse como features históricas al inicio de una consulta.
- Todas las transcripciones están en español y repiten 42 variantes de texto del cliente, derivadas de dos preguntas iniciales. Las categorías generales del origen no representan de forma confiable las intenciones visibles.

Conservar los registros raw para diagnóstico y bloquear el uso afectado. Un reclamo con un producto mal vinculado puede seguir contando en un informe de volumen, pero no puede autorizar la consulta de ese producto.

Usar procesamiento batch para este origen estático. Cada release publicado necesita un source manifest y una versión del dataset. Probar late arrivals, conflictos, columnas nuevas, truncamientos y replay mediante fixtures identificados como tales. Mantener separados event time, ingestion time y observation time del simulador. Una nueva importación no vuelve actual un saldo antiguo.

## Arquitectura y motivos

Organizar el código por casos de uso y aislar los sistemas externos mediante interfaces. Las [vertical slices](https://www.jimmybogard.com/vertical-slice-architecture/) mantienen juntos los cambios de una funcionalidad. Los [ports and adapters](https://alistair.cockburn.us/hexagonal-architecture) permiten probar reglas bancarias sin depender de proveedores, persistencia o UI.

La separación lógica propuesta no depende del lenguaje ni fija todavía la estructura de carpetas:

| Componente | Responsabilidad |
| --- | --- |
| Web | Interfaces de cliente y empleado. |
| Aplicación y dominio | Casos de uso, invariantes, permisos y transiciones. |
| Worker | Ejecución en background y reanudación de casos. |
| Ports y adapters | Integraciones de persistencia, proveedor de IA y simulador bancario. |
| Contratos | Validación de requests, eventos, evidencia y resultados. |
| Pipeline de datos | Ingesta, calidad, lineage y publicación de snapshots. |
| Evaluación | Workloads revisados, oracles, métricas y manifests. |

Web y worker deben usar las mismas reglas de negocio mediante los handlers o contratos que permita el stack elegido. Si combinamos lenguajes, hay que definir cómo se validan los contratos entre ellos. Las reglas bancarias no dependen del framework web, ORM, proveedor de IA ni SDK del hosting. Las interfaces tienen propósitos concretos, como recuperar registros autorizados, persistir casos o ejecutar operaciones bancarias. Los helpers comunes de UI no necesitan una capa de adapters.

| Elección | Motivo | Costo o limitación |
| --- | --- | --- |
| Monolito modular | Contratos compartidos y menos deployments para tres personas. | Hay que controlar imports y responsabilidades al crecer el código. |
| Vertical slices | Cada integrante puede implementar un comportamiento completo. | Las invariantes compartidas necesitan una única implementación. |
| Adapters selectivos | Permiten sustituir proveedores externos por implementaciones controladas de prueba. | Agregan algunas interfaces y contract tests. |
| Workflow persistido | Las esperas humanas y los reinicios no pierden casos. | Hay que manejar concurrencia, retries y aprobaciones desactualizadas. |
| Calidad antes de serving | Impide que joins inválidos y hechos sin respaldo lleguen al modelo. | Algunos registros o features quedan fuera de uso. |
| Verificación independiente | Cada afirmación de éxito requiere un resultado observado. | El fallo de verificación debe ser un estado explícito del caso. |

El worker define una responsabilidad lógica. Elegir el mecanismo de jobs o workflow junto con el lenguaje y hosting, y separar su orquestación de los handlers de negocio. El despacho de tareas debe ser confiable respecto de las transiciones persistidas. No construir un motor de workflows genérico.

SQLite es almacenamiento analítico local para la auditoría. No define la base de datos de la app. Registrar las decisiones relevantes en ADRs breves que expliquen el problema, la elección, las alternativas y su verificación.

## Componente aprendido y baseline

La tarea propuesta para Jev es clasificar intención y ambigüedad. Usar consultas ES/PT revisadas de forma independiente y una taxonomía pequeña vinculada al flujo elegido. No entrenar ni evaluar intención semántica usando `reason_category` como ground truth de las transcripciones repetitivas.

Comparar:

- Un baseline determinista de keywords y selección de entidades, con abstención explícita.
- Jev con el mismo contexto permitido y el mismo contrato de salida.

Ambos usan la misma capa de políticas, tools y verifier. La autoridad financiera queda fuera de los clasificadores. Elegir thresholds de confianza o abstención con validation y reportar la relación entre cobertura, errores y handoffs.

Una salida estructurada no demuestra que el modelo acertó. Reportar errores por clase e idioma. Medir calibración solo si el proveedor expone probabilidades con una semántica utilizable. No prometer mejoras antes de medirlas.

El alcance comprometido no necesita un modelo tabular entrenado por el equipo. Los datasets históricos sirven para análisis descriptivo y un posible experimento futuro. No vamos a consumir el presupuesto de diez días solo para demostrar entrenamiento.

## Evaluación held-out y verificación en runtime

Seguir [evaluation-protocol.md](evaluation-protocol.md). Separar la evidencia de calidad de datos, clasificación, resultados del servicio y verificación de cada acción.

Artefactos producidos durante la auditoría local:

- Particiones estructuradas sin clientes compartidos, con 245.074 interacciones de development, 15.839 de validation y 15.675 candidatas a test.
- 200 contextos de pagos derivados del origen, expandidos a 3.600 fixtures ES/PT con nueve variantes. Son exploratorios y deben adaptarse o sustituirse si el flujo elegido requiere otra evidencia.
- Un oracle experimental local para decisiones estructuradas, divulgación de estados permitidos, mutaciones prohibidas y afirmaciones sin respaldo sobre recepción de fondos.

Estos artefactos todavía no son resultados de evaluación de modelos. Los 3.600 fixtures corresponden a 200 contextos independientes, usan lenguaje de plantillas y esperan revisión lingüística. No reemplazan consultas held-out diversas ni prueban generalización lingüística.

Crear casos de lenguaje revisados de forma independiente. Separar grupos de clientes, escenarios y familias de redacción antes de producir variantes. Mantener juntas las traducciones de un mismo caso. Congelar dataset, labels, políticas, prompts, versiones de modelos, thresholds, presupuesto de retries y seeds antes de comparar. Ejecutar ambos sistemas sobre los mismos casos y con estados iniciales equivalentes del sandbox. Incluir fallos y repeticiones declaradas.

La matriz debe cubrir resolución normal, ambigüedad, intervención humana visible, datos incorrectos o faltantes, sesiones vencidas, accesos no autorizados, prompt injection, fallos de tools, ambigüedad ES/PT y observaciones vencidas. Para la acción acordada, probar aprobación, rechazo, aprobación desactualizada, ejecución, verificación incierta y retries sin efectos duplicados. Para persistencia, probar refresh, reconexión y reinicio del worker sin pérdida de contexto ni permisos.

Reportar:

- Resolución automática segura sobre todos los casos dentro del alcance y cobertura de intentos de automatización.
- Containment separado de resolución.
- Escalaciones correctas, omitidas e innecesarias, junto con la utilidad del contexto del handoff.
- Divulgaciones o acciones no autorizadas y resultados materialmente incorrectos, con conteos y denominadores.
- Latencia end-to-end p50/p95, incluidos retries y fallos de tools.
- Costo por caso intentado y por resolución automática exitosa. Si no hay resoluciones exitosas, el segundo costo queda como "no definido".
- Tamaño de muestra, cantidad de casos independientes, variación entre ejecuciones y diferencias por idioma y segmentos autorizados.

Usar checks deterministas de tools y estado para verificar hechos y acciones. Si un modelo evalúa texto libre, validar una muestra contra juicios humanos independientes o checks deterministas y reportar desacuerdos. Cero fallos observados no significa riesgo cero. Los resultados offline y del simulador no son mejoras medidas en producción.

## Responsabilidades y cronograma de diez días

Reservar entre 18 y 21 de las 72 a 84 horas-persona para evaluación, integración, correcciones y ensayo. Distribución propuesta:

| Responsable | Trabajo principal |
| --- | --- |
| A | Pipeline de datos, contratos de calidad y freshness, labels, workloads held-out e informes de evaluación. |
| B | Workflow, adapters de IA y tools, autorización, aprobaciones, verificación y deployment. |
| C | Ambas interfaces mínimas, ES/PT, handoff de conversación, timeline y demo. |

Los tres revisan labels y errores. Reutilizar componentes de UI y limitar la consola del empleado a una cola y el detalle del caso. Asignar nombres y ajustar tareas según la experiencia de cada integrante.

| Día | Capacidad del equipo | Entrega |
| --- | ---: | --- |
| Lunes 28 de septiembre | 6 horas | Revisar auditoría y consigna, elegir el flujo respaldado por datos, evaluar lenguajes, hosting, base de datos y Jev, definir contratos. |
| Martes 29 de septiembre | 6 horas | Incorporar el pipeline reproducible en el stack elegido, preparar snapshot y quality gates, sesiones precreadas y estructura mínima de UI. |
| Miércoles 30 de septiembre | 6 horas | Baseline determinista y primer flujo acotado de investigación con IA y captura de evidencia. |
| Jueves 1 de octubre | 6 horas | Flujo inicial de cliente → empleado visible → aprobación → acción ejecutada → resultado verificado. |
| Viernes 2 de octubre | 6 horas | Casos asíncronos persistentes, takeover, retries y comportamiento de actualización y freshness. |
| Sábado 3 de octubre | 12 a 18 horas | Completar ES/PT, labels de referencia, flujos normal, ambiguo y humano, y matriz de fallos. |
| Domingo 4 de octubre | 12 a 18 horas | Integrar traces y evaluadores. Congelar alcance, workloads, prompts y reglas. |
| Lunes 5 de octubre | 6 horas | Ejecutar baseline y candidato sobre el mismo held-out y probar autorización. |
| Martes 6 de octubre | 6 horas | Analizar fallos y diferencias entre grupos, probar recuperación y cerrar arquitectura y limitaciones. |
| Miércoles 7 de octubre | 6 horas | Reproducir artefactos, ensayar, verificar deployment y preparar la entrega. |

La auditoría ya está terminada con la cobertura documentada. Faltan el pipeline compartido reproducible, la app, la comparación de modelos y el benchmark lingüístico final. Si no alcanza el tiempo, recortar inglés, detalles visuales, dashboards, comparaciones adicionales de proveedores y acciones adicionales. Mantener el humano visible, una acción aprobada y verificada, los casos persistentes y el trabajo de datos y evaluación exigido por la consigna.

## Privacidad y paso a operación

Usar solo datos autorizados por la organización y recursos externos permitidos. El corpus provisto es sintético. Identificar por separado el lenguaje generado por el equipo, los fixtures con defectos introducidos y el estado del sandbox. No incluir credenciales, registros privados ni datos restringidos en entregas públicas o requests a modelos.

Reducir los inputs del proveedor a la consulta y los hechos permitidos. Verificar identidad y ownership en servicios y tools. Un customer ID no autentica a una persona. Registrar retries acotados, motivos de rechazo, fallos de verificación y resultados del handoff. Definir retención, borrado, acceso y redacción de traces antes del deployment.

Medir concurrencia, límites del proveedor, recuperación de jobs, latencia y costo sobre el workload declarado. Documentar monitoreo y trabajo pendiente para un banco real, como integración de identidad, responsables de políticas, datos actualizados confiables, revisión de seguridad, operación humana y una evaluación más amplia. La consigna no exige ni autoriza movimientos de dinero real.

## Exclusiones y decisiones pendientes

Quedan fuera las consultas de saldo como caso de uso, el registro de usuarios, onboarding, recuperación de contraseña, voz, WhatsApp, email, fine-tuning de LLMs, mutaciones bancarias reales, decisiones crediticias, otros flujos bancarios, analítica empresarial y microservicios. Las actualizaciones batch son suficientes. Streaming no aporta puntaje por sí mismo.

Falta cerrar el flujo respaldado por evidencia, la acción de negocio concreta, lenguajes y frameworks, herramientas del repositorio, base de datos, hosting, runtime, modelo conversacional, taxonomía revisada, tamaño del workload, presupuesto de inferencia, responsables con nombre, política de retención y hora oficial de entrega. La consigna ya resolvió las dudas sobre idiomas, entrenamiento, escenarios de fallo y métricas obligatorias.
