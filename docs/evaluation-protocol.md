# Evaluación y verificación mediante data engineering

Este protocolo aplica la [consigna de Factored AI & Data Hackathon 2026](https://docs.google.com/document/d/18AwONT8hQupRcfNPLFrPo6fHOJ_OUn1nBf-3jMnla2c/edit), leída completa el 28 de septiembre de 2026. La consigna no fija un mínimo de casos de prueba y permite cumplir el requisito de componente aprendido sin entrenar un modelo nuevo.

Los contratos, splits y métricas de este documento no dependen del lenguaje. El stack sigue abierto y puede incluir Python. Los scripts exploratorios de la auditoría son locales y están excluidos del control de versiones. Falta entregar una implementación compartida reproducible en el stack elegido.

Además de la consigna, el producto mantiene tres requisitos acordados con el equipo. El cliente debe ver y conversar con la persona que interviene. La demo debe ejecutar una acción de negocio con aprobación humana y verificación independiente en el simulador. Los casos deben persistir entre sesiones y reinicios. Estos recorridos necesitan evidencia end-to-end propia. Un flujo con aprobación humana no cuenta como resolución automática.

## Cuatro tipos de evidencia

| Evidencia | Pregunta que responde | Fuente de verdad |
| --- | --- | --- |
| Calidad de datos | ¿Este registro o relación sirve para este uso? | Contratos, registros de origen, ownership, timestamps y lineage. |
| Evaluación del componente aprendido | ¿Jev mejora la clasificación de intención y ambigüedad frente a las reglas? | Labels independientes y revisados sobre consultas held-out. |
| Evaluación end-to-end del servicio | ¿El sistema alcanza el resultado correcto y permitido? | Resultados esperados revisados y observaciones confiables de tools y estado. |
| Verificación en runtime | ¿Esta acción concreta produjo el resultado que se afirma? | Registro de operaciones y lectura independiente del estado y ledger. |

Cumplir un schema CSV no prueba ownership. Clasificar bien no demuestra que una acción bancaria haya tenido éxito. Una demo exitosa no establece una mejora held-out.

## 1. Publicar datos con contratos y lineage

Usar ingesta batch para los archivos estáticos provistos. La auditoría implementada incluye fetch, carga estructural, profiling semántico, construcción de datasets de evaluación y quality gates. El pipeline de la app deberá conservar un manifest inmutable por release publicado. Fijar versiones de objetos o usar lecturas condicionales cuando estén disponibles. Conservar SHA256 local y lineage por registro.

Clasificar los defectos por uso. Por ejemplo, el vínculo roto entre reclamo y producto impide recuperar el producto para ese cliente, pero permite contar el reclamo en un informe por categoría. Nunca reparar la relación asignando el reclamo al otro cliente. Conservar registros inválidos y motivos en quarantine o en un manifest de usos rechazados.

El contrato de serving debe incluir identidad autenticada del cliente, propietario del registro, referencia al origen, importe y moneda cuando correspondan, estado observado, timestamp de observación, clasificación de freshness y estado de calidad. Separar event time, process day, ingestion time y observation time del simulador. Los CSV históricos no representan el estado actual de un banco.

Publicar un nuevo snapshot de serving solo cuando pasen sus gates obligatorios. Los rebuilds batch completos alcanzan para este hackathon. Un fixture de actualización identificado como tal debe demostrar late arrival, replay sin cambios, correcciones en conflicto, entrada malformada y una columna nueva. Los tests locales del loader exploratorio cubren esos comportamientos estructurales. No están incluidos en esta entrega de documentación. Falta implementar el servicio de publicación del snapshot de serving.

Definir y documentar un límite sintético de antigüedad para las observaciones del simulador. Una observación vencida dispara un refresh acotado. Si falla, el caso queda explícitamente sin resolver o se deriva a una persona. Un ingestion timestamp reciente no convierte un saldo antiguo en actual.

## 2. Elegir el componente aprendido sin entrenar un modelo nuevo

El experimento principal propuesto usa Jev para clasificar intención y determinar si la consulta identifica una operación o reclamo permitido de forma unívoca o necesita aclaración. El LLM conversacional lleva el diálogo. Sus respuestas no definen permisos.

Cerrar primero el flujo del cliente y después una taxonomía pequeña para esa tarea. Si se eligen pagos, puede incluir consulta de estado, solicitud de investigación y solicitud fuera de alcance. Si se eligen reclamos, debe reflejar las tareas de recepción, seguimiento y solicitud de acción que se implementen. La política determina qué acción se permite y cuándo requiere aprobación. Estas opciones no implican construir ambos flujos. Las consultas de saldo quedan fuera del alcance. La ambigüedad puede representarse como un boolean separado si no es una clase excluyente. Congelar esa representación antes de evaluar.

El baseline usa reglas explícitas de keywords ES/PT y selección de entidades, con abstención. El candidato usa Jev con los mismos campos permitidos y el mismo output schema. Ninguno recibe labels esperados ocultos, resultados futuros ni registros de otro cliente. Ambos alimentan los mismos controles deterministas de políticas y tools.

Los labels deben surgir de una revisión independiente de la consulta y el contexto disponible. Los campos de intención y categoría del origen no son labels semánticos suficientemente específicos para esta tarea. Un reviewer anota intención esperada, ambigüedad, tools permitidas, necesidad de handoff y evidencia requerida. Otro revisa los casos en disputa y los críticos para seguridad. Registrar desacuerdos y su resolución. Las clasificaciones del propio candidato no pueden ser su ground truth.

Reportar precision y recall por clase, macro-F1, confusion matrix, cobertura de abstención y categorías de error por idioma. Si Jev expone probabilidades utilizables, evaluar calibración y elegir thresholds de abstención con validation. Un valor de confianza sin validar no equivale a la probabilidad de que una acción sea segura.

Si las reglas igualan o superan a Jev, reportar ese resultado y evaluar si existe otra tarea aprendida que tenga una justificación concreta. La comparación debe permitir elegir a partir de evidencia.

## 3. Congelar un workload held-out compartido

El corpus de origen tiene dos familias de preguntas iniciales y ningún ejemplo nativo en PT. Los fixtures derivados de los datos necesitan casos lingüísticos adicionales revisados de forma independiente. Identificar el contenido sintético de la organización, el generado por el equipo, las traducciones y los textos escritos por personas.

Particionar los grupos de clientes y escenarios antes de generar paráfrasis o traducciones. Mantener todas las variantes e idiomas de un caso en el mismo split. Reservar familias de redacción y prompts de autoría para test. No usarlos como ejemplos para ajustar los system prompts. Evitar que development y test compartan customer IDs, registros de origen o textos casi idénticos cuando esa separación forme parte de la generalización que se quiere medir.

Usar los manifests de splits estructurados para análisis históricos cuando corresponda. Su volumen no reemplaza un benchmark lingüístico. Los 3.600 fixtures existentes forman una matriz de stress de 200 clientes. Sus prompts repetidos siguen pendientes de revisión humana.

Antes de ejecutar test, congelar:

- Case IDs, provenance, pertenencia a splits, labels de calidad y estado de revisión.
- Identificadores de modelos, prompts, parámetros de temperatura y decoding cuando apliquen, reglas y thresholds.
- Contratos de tools, versión de políticas, presupuesto de retries, release del dataset y seed y estado inicial del simulador.
- Configuraciones de baseline y candidato, composición del workload, plan de repeticiones y supuestos de costo.

Ejecutar ambos sistemas sobre los mismos casos, restaurando por separado estados equivalentes del sandbox. Alternar o aleatorizar el orden al comparar latencia contra proveedores. Repetir un subconjunto declarado, o todos los casos si el presupuesto alcanza, para medir variación estocástica. Conservar llamadas fallidas y timeouts en los resultados.

Elegir el tamaño del workload según cobertura, incertidumbre, capacidad de anotación y presupuesto de ejecución. Reportar tanto grupos independientes como ejecuciones expandidas. Estimar incertidumbre por grupo cuando haya traducciones o variantes correlacionadas. Agregar filas no agrega necesariamente evidencia independiente. La consigna no prescribe una cantidad.

## 4. Verificar resultados con evidencia confiable

Para una consulta read-only, el verifier comprueba ownership, campos permitidos, freshness y coincidencia exacta del estado o del importe y moneda. El estado Approved no prueba que el beneficiario haya recibido los fondos. Un registro faltante o inconsistente no respalda una respuesta afirmativa.

La acción de negocio elegida debe cambiar un estado autoritativo del simulador y dejar un registro consultable. Verificar ese estado mediante una lectura independiente y comprobar que corresponde a la operación aprobada. La creación de un ticket, una propuesta de acción o un mensaje de éxito no alcanzan como prueba de ejecución.

Si la acción afecta fondos, el saldo de origen no alcanza como prueba. Es un campo de snapshot y faltan el saldo de apertura y los asientos con signo necesarios para reconstruirlo a partir de transacciones. Verificar esas mutaciones con el ledger propio del simulador. Esto no incorpora consultas de saldo al alcance del producto.

Para una reversión simulada opcional, exigir sesión válida del empleado, aprobación vinculada a la acción exacta y a la versión actual del registro, elegibilidad vigente, idempotency key estable y lectura independiente de la operación y el ledger. Los CSV no prueban que la reversión ocurrió. Tampoco alcanza una respuesta exitosa del transporte o que el modelo diga "listo". Un resultado incierto mantiene abierto el caso mientras se consulta la operación existente. Los retries no deben crear un segundo crédito.

El control de aprobación, versión, elegibilidad e idempotencia también aplica si se elige otra acción de negocio. La acción concreta queda pendiente, pero su ejecución aprobada y verificada es obligatoria en la demo.

Verificar que el cliente vea nombre y rol del empleado, sus mensajes y quién tiene el control de la conversación. Durante takeover, la IA debe dejar de enviar respuestas al cliente hasta que el empleado le devuelva el control explícitamente. Después de refresh, reconexión y reinicio del worker, comprobar que se recuperen el mismo caso, historial, responsable, aprobación y operación. Probar interrupciones antes de aprobar, después de aprobar y después de ejecutar cuando se pierde la respuesta de la tool. Reanudar un caso no puede reutilizar una aprobación desactualizada ni duplicar una acción.

Capturar un trace estructurado con case ID y run ID, actor, decisión de autorización, referencias de origen, política y versión, requests y resultados de tools, cantidad de retries, transiciones de estado, aprobación, hallazgos de verificación y handoff final. No incluir chain-of-thought privado en los artefactos de auditoría.

El oracle experimental local compara decisión, estado, mutaciones prohibidas y afirmaciones sobre recepción de fondos con los fixtures. El conteo de acciones debe venir del executor confiable. Las anotaciones sobre afirmaciones de la respuesta necesitan revisión independiente. Lo que el modelo dice haber ejecutado no es telemetría. Faltan la implementación compartida del oracle, el runner de la app, el checker completo de handoff y el verifier del ledger.

## 5. Matriz de fallos y comportamientos

| Caso | Comportamiento esperado | Evidencia de verificación |
| --- | --- | --- |
| Consulta normal elegible | Respuesta correcta y respaldada, sin intervención humana. | Registro autorizado y vigente, con hechos exactos en la respuesta. |
| Solicitud ambigua o fuera de alcance | Pedir aclaración o derivar según la política de referencia. | Sin selección inventada de entidades, políticas ni datos de cuenta. |
| Caso que requiere una persona | Handoff con contexto útil, empleado visible y conversación con el cliente. | Solicitud, hechos verificados, acciones, evidencia, preguntas pendientes y autoría de mensajes. |
| Acción de negocio aprobada | Ejecutar la acción elegida solo tras una aprobación válida y verificar el cambio de estado. | Identidad del aprobador, parámetros y versión aprobados, operación persistida y lectura independiente del resultado. |
| Acción rechazada o aprobación desactualizada | No ejecutar. Mantener el caso y explicar el siguiente paso. | Rechazo o versión en conflicto, con ausencia de ejecución. |
| Reanudación del caso | Recuperar contexto y estado tras refresh, reconexión o reinicio del worker. | Mismo case ID, historial, responsable, aprobación y operación, sin efectos duplicados. |
| Datos incorrectos | Rechazar la relación inválida o el hecho en conflicto. | Gate de ownership, tipo, moneda o cronología y motivo explícito de rechazo. |
| Datos faltantes | Pedir información o hacer handoff. | Evidencia del campo faltante, sin valores inventados. |
| Sesión vencida | Exigir nueva autenticación antes de revelar datos o actuar. | Check de sesión confiable anterior al request de la tool. |
| Acceso no autorizado | Rechazar sin revelar registros de otro cliente. | Trace de autorización en servidor o tool, además de la respuesta al cliente. |
| Prompt injection | Tratar el texto del cliente y de tools como no confiable y mantener los permisos. | Sin divulgación adicional ni ejecución no autorizada. |
| Fallo de tool | Retries acotados, fallback seguro y estado sin resolver cuando corresponda. | Intentos, deadlines, error final y handoff. |
| Ambigüedad multilingüe | Mantener contexto y pedir aclaraciones coherentes en ES/PT. | Expectativas bilingües revisadas y tratamiento consistente de entidades e importes. |
| Observación vencida | Hacer refresh según la política o abstenerse de afirmar un dato actual. | Timestamps de origen y observación, más resultado del refresh. |
| Mutación repetida o incierta | Verificar la operación existente y evitar efectos duplicados. | Clave estable de operación y evidencia independiente del ledger y estado. |

## 6. Métricas exigidas por la consigna

N representa todos los casos held-out dentro del alcance. Conservar por separado la elegibilidad de referencia, si se intentó automatizar y si el caso terminó sin derivación.

| Métrica | Definición y regla de reporte |
| --- | --- |
| Resolución automática segura | Casos elegibles resueltos correctamente, dentro de las políticas, verificados y sin intervención humana, divididos por N. Reportar también sobre qué proporción de N se intentó automatizar. |
| Containment | Casos que terminan sin derivación divididos por N. No equivale a resolución. |
| Calidad de escalación | Derivaciones correctas, necesarias pero omitidas e innecesarias, comparadas con labels revisados. Incluir precision y recall cuando estén definidos y completitud del handoff. |
| Resultados inseguros | Casos con divulgación o acción no autorizada, o resultados materialmente incorrectos, con conteos y denominadores. Separar fallos observados, casos no ejecutados y evaluaciones sin resolver. |
| Latencia | p50/p95 end-to-end, con llamadas a tools y retries. Incluir tratamiento de timeouts y tamaño de muestra. Reportar por separado la espera humana. |
| Costo por caso intentado | Costo total medido o estimado del workload dividido por los intentos ejecutados. Declarar supuestos de modelos, tools e infraestructura y qué costos faltan. |
| Costo por resolución automática exitosa | Costo total del workload intentado dividido por las resoluciones automáticas seguras. Usar "no definido" si no hay ninguna. |

Reportar diferencias entre baseline y candidato sobre el mismo workload, variación entre ejecuciones e incertidumbre. Cero resultados inseguros observados no significa riesgo cero. Una consulta sin respuesta no es exitosa por haber quedado contenida.

Para los requisitos propios del producto, reportar también resolución asistida, ejecución y verificación de acciones aprobadas, y recuperación de casos persistentes. Usar los casos correspondientes como denominador y declararlo. Los resultados con aprobación o takeover humano quedan fuera del numerador de resolución automática segura.

Desglosar resultados por ES/PT y segmentos de clientes autorizados cuando existan suficientes casos independientes. Aclarar si los atributos de segmento vienen de snapshots actuales o de hechos históricos. Investigar diferencias sin afirmar fairness a partir de una muestra pequeña o repetitiva. Conservar solo la información de segmento necesaria y no revelarla a otros clientes.

Para texto libre, priorizar checks factuales deterministas y una rúbrica revisada. Si un modelo evalúa respuestas, registrar modelo, prompt, versión y rúbrica. Validar una muestra contra juicios humanos o deterministas y reportar desacuerdos.

Los resultados son offline o simulados hasta probarse en operación. Los ahorros calculados con volúmenes de contacto y reducciones supuestas de tiempo de atención son proyecciones. No son mejoras medidas en producción.

## 7. Evidencia de entrega y trabajo pendiente

| Requisito oficial | Artefacto existente | Pendiente |
| --- | --- | --- |
| Problema respaldado por datos | Auditoría completa de tablas centrales y análisis de contactos. | Decisión del equipo sobre el flujo respaldado por evidencia. |
| Contratos, checks, lineage y freshness | Resultados de auditoría batch local, provenance por archivo y fila, gates por uso, tests locales de actualización y replay, política documentada. | Pipeline y tests compartidos reproducibles en el stack elegido, publicación para serving y control de freshness en la app. |
| Componente aprendido contra baseline | Componente y comparación propuestos, protocolo documentado. | Tarea y taxonomía vinculadas al flujo elegido, labels independientes revisados, ejecuciones reales de baseline y Jev, análisis de errores. |
| Evaluación held-out de fallos | Splits estructurados candidatos y fixtures de stress ES/PT derivados del origen. | Casos lingüísticos diversos y revisados, ejecución del sistema completo. |
| Automatización controlada | Contratos de permisos y verificación, oracle estructurado experimental local. | Oracle compartido, tools con autenticación, handoff a empleado, retries acotados y verifier de acciones funcionando. |
| Requisitos de producto acordados | Humano visible, acción aprobada y verificada, y casos persistentes documentados. | UI del empleado dentro del recorrido del cliente, acción ejecutable en sandbox y pruebas de reanudación e idempotencia. |
| Paso a operación | Límites del origen y runtime, responsabilidades de arquitectura. | Captura de traces, monitoreo, capacidad y costo medidos, política de retención y ensayo de deployment. |

Antes de entregar, exportar el workload manifest congelado, la guía de labels, resultados por caso incluidos los fallos, versiones de modelos, prompts y reglas, tablas de métricas, análisis de errores y comandos reproducibles. Excluir credenciales y datos privados o restringidos de archivos públicos y requests externos. Enviar a los modelos solo los campos autorizados que necesita la tarea.
