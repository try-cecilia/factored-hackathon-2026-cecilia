# Errores del dataset y contrato de validación de ingesta

Revisión del 28 de septiembre de 2026 contra el [diccionario oficial](https://drive.google.com/file/d/***REMOVED***/view). La copia descargada nuevamente coincide con la usada en la auditoría. Su SHA256 es `65cc2bd37d525fc0c7812ea442d56fdfb8152f1b937e5a8995bb98bfd7dea513`.

Este documento define validaciones a partir de defectos observados. No implementa el pipeline definitivo ni elige Python o TypeScript. Los scripts de comprobación y reportes detallados permanecen locales. Esta entrega contiene solo Markdown.

## Cobertura y criterio

Se contrastaron las definiciones de 260 columnas, incluidas 136 restricciones `NOT NULL`, contra las 13 tablas analizadas. La cobertura sigue siendo 11 tablas completas y muestras por fecha de eventos digitales y envíos de campañas. Son 6.311.493 filas de 5.516 archivos. Los resultados de tablas muestreadas no se extrapolan al resto del origen.

Se verificaron presencia de columnas, nulos, longitudes `VARCHAR`, representación de tipos, precisión decimal y los cuatro campos adicionales declarados `UNIQUE`. La auditoría previa cubre primary keys, relaciones y cronología. También se comprobaron rangos seleccionados descritos en el diccionario, no toda posible regla de negocio.

Clasificamos cada hallazgo por su fundamento:

- **Contrato explícito:** incumple `NOT NULL`, `UNIQUE` o una foreign key declarada.
- **Consistencia semántica:** las filas son válidas por separado, pero su combinación no sirve para el uso previsto.
- **Evidencia insuficiente:** el diccionario permite el dato faltante, pero la aplicación no puede realizar cierta afirmación o acción sin él.
- **Diferencia de representación o documentación:** necesita una política de parsing o un contrato acordado. No justifica descartar filas automáticamente.

Los conteos de reglas distintas pueden incluir las mismas filas. No deben sumarse para obtener una cantidad total de registros defectuosos.

## 1. Incumplimientos explícitos del diccionario

| ID | Contrato y referencia | Resultado observado | Validación y tratamiento |
| --- | --- | --- | --- |
| DQ-001 | `products.product_number`, `NOT NULL, UNIQUE`, página 5. | 6 números repetidos, 12 productos afectados de 400.000. Cada número corresponde a dos `product_id` y dos clientes distintos. Son 6 filas excedentes respecto de la unicidad. | Agrupar por número y exigir una sola identidad dentro del snapshot. Bloquear la resolución de identidad por ese número. Conservar las filas raw; no fusionar productos ni propietarios. |
| DQ-002 | `service_agents.employee_code`, `NOT NULL, UNIQUE`, página 6. | 13 códigos repetidos, 26 agentes afectados de 1.200. Cada código aparece dos veces. | Bloquear identificación, asignación o autenticación basadas solo en ese código. Usar `agent_id` validado y una sesión confiable. No fusionar agentes automáticamente. |
| DQ-003 | `customers.registration_branch_id`, `FK, NOT NULL`, páginas 4 y 15. | 149.995 de 150.000 referencias no existen en `branches`. Ninguna es nula. | Comprobar existencia mediante anti-join. Bloquear atribución y routing por sucursal de registro. Conservar otros usos válidos del cliente. |
| DQ-004 | `service_agents.assigned_branch_id`, `FK`, páginas 6 y 15. | 831 referencias huérfanas entre 833 no nulas. Los otros 367 agentes tienen un nulo permitido. | Verificar solo referencias no nulas. Bloquear routing o contexto de sucursal basado en las huérfanas. No tratar los 367 nulos como violaciones de `NOT NULL`. |
| DQ-005 | `call_transcripts.duration_seconds`, `INTEGER, NOT NULL`, página 10. | 24.029 valores nulos de 171.321 transcripciones. | Registrar incumplimiento. Excluir esas filas de usos que requieren duración y de una publicación que prometa ese contrato estricto. No sustituir por cero ni por la duración de otra tabla sin una regla justificada. |

La auditoría anterior verificaba duplicados de primary keys. Esta revisión agrega los campos alternativos `UNIQUE`. Por eso pueden coexistir cero primary keys duplicadas y números de producto o códigos de empleado repetidos.

Los campos `customers.document_number` y `branches.branch_code`, también declarados `UNIQUE`, no presentaron repeticiones no nulas en las tablas completas analizadas.

## 2. Inconsistencias entre registros

Estas reglas combinan la semántica de los campos y las necesidades del producto. No todas aparecen como un `CHECK` literal en el diccionario.

| ID | Regla | Resultado observado | Tratamiento |
| --- | --- | --- | --- |
| DQ-006 | Un reclamo solo puede vincularse con un producto del mismo cliente. | Las 44.570 referencias no nulas de `complaints.affected_product_id` existen, pero todas apuntan a productos de otro cliente. | Bloquear ese join para serving, permisos y labels. El reclamo puede conservarse para consulta por su cliente y análisis agregado. No cambiar su propietario. |
| DQ-007 | Para la cohorte histórica de pagos, la transacción debe ser posterior o igual al registro del cliente y la apertura del producto. | 1.451.309 de 4.425.008 transacciones incumplen al menos una condición. Solo 2.973.699 pasan ambas. | Excluirlas de esa cohorte y de contextos que afirmen esa historia. Registrar el motivo por fila. Validar fechas antes de compararlas. |
| DQ-008 | Una interacción histórica no puede preceder al registro del cliente bajo el contrato adoptado para la cohorte. | 128.453 de 686.296 interacciones son anteriores al registro. | Excluirlas de la cohorte histórica y reportar la reducción de cobertura. No reemplazar fechas. |

Las fechas de registro representan el alta según el diccionario. Si la organización aclara que en realidad son fechas de migración, habrá que revisar las reglas temporales. No se aplicará esa explicación por suposición.

La cadena transacción → producto → cliente sí tiene ownership consistente en las 4.425.008 transacciones. Esto no elimina la necesidad de comprobar cronología ni de autorizar al usuario en runtime.

## 3. Datos opcionales que no alcanzan para determinados usos

| ID | Hallazgo | Resultado observado | Gate de uso propuesto |
| --- | --- | --- | --- |
| DQ-009 | Importe reclamado sin moneda. El diccionario permite nulos en ambos campos, página 12. | 1.040 de los 21.751 reclamos con `claimed_amount` informado carecen de `currency`. Los 1.040 importes son positivos. La tabla completa tiene 67.095 filas. | No proponer ni ejecutar una acción monetaria a partir de ese importe. Solicitar o recuperar la moneda con evidencia autorizada. No inferirla del país ni del producto mal vinculado. |
| DQ-010 | Estado de resolución sin evidencia suficiente. `resolution_date` y `resolution` son opcionales, página 12. | Entre 16.121 reclamos `Resolved` o `Closed`, 772 no tienen fecha de resolución y 811 no tienen descripción. La unión es 1.549 reclamos. | Se puede informar el estado registrado como tal. No afirmar qué acción ocurrió ni cuándo se verificó sin evidencia adicional. No contar esos estados por sí solos como resoluciones verificadas. |
| DQ-011 | Reclamos sin interacción de origen. `origin_interaction_id` es una FK opcional, páginas 12 y 16. | Nulo en los 67.095 reclamos. | Deshabilitar el vínculo reclamo → conversación y su uso como ground truth de resultado conversacional. No inventar un join por proximidad de fechas o cliente. |
| DQ-012 | Falta de versiones históricas de dimensiones. El diccionario anuncia `monthly_snapshot`, páginas 4 y 5. | La entrega inventariada contiene un archivo de clientes y uno de productos, sin los snapshots mensuales anunciados. Algunos `last_updated` llegan a junio de 2027. | No tratar atributos del snapshot como features disponibles en una fecha anterior. Declarar la versión disponible y separar event time, ingestion time y observation time. |

La columna `complaints.currency` se describe como moneda del importe reclamado. El diccionario no define explícitamente la moneda de `compensation_granted`. No asumir que son iguales ni ejecutar compensaciones desde ese campo sin completar el contrato del simulador.

Una reingesta reciente no vuelve actuales los datos históricos. El límite de antigüedad aceptable se define por caso de uso y se aplica a observaciones del simulador. No se deduce un SLA bancario real de estos CSV.

## 4. Diferencias de formato y documentación

### INTEGER serializados como decimales

Hay 13 columnas `INTEGER` con valores no nulos representados con formato decimal, como `700.0`. La comprobación adicional confirmó cero valores no integrales o inválidos en esas columnas. Son diferencias de representación, no números que deban redondearse.

| Campo | Valores con representación no canónica |
| --- | ---: |
| `customers.credit_score` | 127.508 |
| `products.days_past_due` | 125.350 |
| `service_agents.total_monthly_interactions` | 1.089 |
| `call_center_interactions.duration_seconds` | 590.062 |
| `call_center_interactions.wait_time_seconds` | 480.678 |
| `call_transcripts.duration_seconds` | 147.292 |
| `satisfaction_surveys.question_1_response` | 121.370 |
| `satisfaction_surveys.question_2_response` | 81.496 |
| `satisfaction_surveys.question_3_response` | 40.103 |
| `digital_events.duration_seconds` | 60.060, solo muestra |
| `complaints.resolution_days` | 15.363 |
| `complaints.resolution_satisfaction` | 2.484 |
| `campaign_sends.click_count` | 1.130, solo muestra |

El parser debe comprobar con aritmética decimal que el valor sea finito, integral y representable por el tipo destino. Puede convertir `700.0` a `700` sin pérdida. Debe rechazar `700.5` en un campo entero y evitar conversiones que trunquen silenciosamente. Estos ejemplos ilustran la regla y no son identificadores del origen. Conservar el texto raw.

Esto no requiere normalizar nuevamente el modelo relacional. Es parsing explícito del CSV.

### Categorías descritas en inglés y valores entregados en español

El diccionario describe `products.product_type` con nombres en inglés. Los 400.000 productos usan ocho categorías en español, como `Cuenta Ahorro` y `Tarjeta Crédito`.

`call_center_interactions.reason_category` contiene categorías en español en las 686.296 filas. Además, 20.578 contienen `Retención`, que no figura en la lista de cinco categorías de la página 9.

No construir un enum cerrado copiando esas descripciones sin contrastarlo con los datos. Conservar el valor original y acordar un catálogo versionado de valores aceptados. Si la aplicación necesita códigos canónicos, usar un mapping explícito y revisado. Una categoría desconocida debe generar un evento de schema/domain drift, no una traducción improvisada por el LLM.

### Conversión monetaria y cobertura

La comparación exploratoria de `amount_usd` con el tipo de cambio del mismo día difiere por más de un centavo en 749.769 filas ARS y 1.031.847 COP. El diccionario no define qué tasa, instante o convención de redondeo produjo `amount_usd`. Es un diagnóstico pendiente de aclaración, no un error financiero confirmado.

La ausencia de transacciones MXN y el uso de USD por clientes mexicanos describen la cobertura del dataset. El país del cliente no obliga a una moneda de transacción.

## 5. Controles que pasaron y límites de la revisión

En las entradas analizadas:

- No faltan columnas del diccionario y no se encontraron registros malformados ni primary keys ausentes o duplicadas según la auditoría estructural.
- No se detectaron excesos de longitud `VARCHAR` ni importes fuera de la precisión y escala `DECIMAL` declaradas. El parsing usó aritmética decimal, sin redondear para hacer pasar los controles.
- La única columna `NOT NULL` con nulos encontrada al contrastar las 136 restricciones fue `call_transcripts.duration_seconds`.
- Los booleanos no nulos usan `True` o `False`. Es la representación observada; el contrato de ingesta debe declarar qué representaciones admite.
- Las fechas y horas no nulas verificadas pudieron parsearse. Esto no demuestra cronología correcta ni establece una zona horaria ausente del origen.
- Los rangos revisados de `credit_score`, `avg_csat`, `fraud_score`, `sentiment_score`, `accent_confidence`, `resolution_satisfaction` y `main_score` para CSAT y NPS no presentaron valores fuera de rango. No se aplicó al CES un rango que el diccionario no especifica.
- Los 154.157 valores no nulos de `mentioned_entities` son JSON sintácticamente válido. Su semántica sigue requiriendo checks si se usa para actuar.

Las proporciones aproximadas de duplicados o nulos del PDF no son una especificación de conteo exacto. Tampoco se puede concluir que faltó una descarga porque el conteo observado difiera del aproximado. La completitud de ingesta se comprueba contra el inventario de objetos seleccionado.

Los 42 textos distintos del cliente son un problema de diversidad y de evaluación, no primary keys duplicadas. Deben bloquear afirmaciones de generalización lingüística basadas en un split aleatorio, sin eliminar registros de negocio por compartir texto.

## 6. Comportamiento requerido del pipeline

La secuencia propuesta es ingesta raw → parsing y checks → publicación por uso. No hace falta rediseñar las tablas ni reparar automáticamente el origen.

1. Registrar objeto, tamaño, hash, versión disponible, timestamp de ingesta y línea de origen. Conservar raw sin modificar.
2. Validar schema y convertir tipos sin pérdida. Una clave ausente o un valor no parseable pasa a quarantine con motivo.
3. Comprobar primary keys y los campos alternativos `UNIQUE`. Separar duplicados exactos de identidades en conflicto. DQ-001 y DQ-002 son conflictos, no filas idénticas que se puedan consolidar.
4. Ejecutar foreign keys, ownership, cronología y gates de evidencia sobre los joins que utilizará el producto.
5. Publicar una vista o snapshot con un contrato explícito por uso. Un cliente puede ser utilizable aunque su sucursal de registro no lo sea. El serving no debe exponer el join bloqueado.
6. Publicar de forma atómica. Un lote incompleto no reemplaza al anterior. Reprocesar los mismos bytes no duplica efectos.
7. Generar un reporte de calidad por release. Si no queda un conjunto válido para un uso, deshabilitar ese uso y mostrar la causa.

Los snapshots mensuales futuros deben tener una clave que incluya su versión o período. La misma identidad en dos snapshots no es un duplicado por sí sola. Las reglas `UNIQUE` se aplican dentro de la versión pertinente, no sobre toda la historia sin distinguir snapshots.

El reporte mínimo de cada regla debe incluir `rule_id`, versión, tipo de fundamento, tabla y campos, dataset version, filas evaluadas, nulos no aplicables, grupos afectados cuando corresponda, filas fallidas, uso bloqueado y decisión. Los ejemplos por registro deben conservarse con acceso restringido y lineage; la documentación compartida usa conteos agregados.

### Prioridad para el hackathon

Primero implementar schema, parsing, PK, `UNIQUE`, ownership, cronología y moneda para el flujo seleccionado. Aplicar freshness al estado del simulador. Las relaciones de sucursal pueden quedar deshabilitadas y documentadas si no participan del producto; no hace falta repararlas para seguir.

Los checks de ingesta no reemplazan autorización, aprobación ni verificación en runtime. Antes de ejecutar una acción, volver a comprobar sesión, ownership, versión y elegibilidad. Después, leer de forma independiente el resultado. El estado `Resolved` de una fila histórica no sustituye esa verificación.

## 7. Consultas de referencia y resultados esperados

Estas consultas documentan el criterio y pueden adaptarse al motor elegido. Se ejecutan sobre la versión analizada, con campos vacíos representados como NULL. No son un pipeline compartido completo. No se incluyen filas del origen ni credenciales.

### DQ-001 y DQ-002: unicidad fuera de la primary key

```sql
SELECT COUNT(*) AS conflicting_values,
       SUM(n) AS affected_rows,
       SUM(n - 1) AS excess_rows
FROM (
  SELECT product_number, COUNT(*) AS n
  FROM products
  WHERE product_number IS NOT NULL
  GROUP BY product_number
  HAVING COUNT(*) > 1
) conflicts;
-- Esperado: 6 valores, 12 filas afectadas, 6 excedentes.
-- Repetir para service_agents.employee_code:
-- 13 valores, 26 filas afectadas, 13 excedentes.
```

### DQ-003 y DQ-004: referencias inexistentes

```sql
SELECT COUNT(*) AS failed_rows
FROM customers c
LEFT JOIN branches b ON b.branch_id = c.registration_branch_id
WHERE c.registration_branch_id IS NOT NULL AND b.branch_id IS NULL;
-- Esperado: 149995.
-- Repetir para service_agents.assigned_branch_id: 831.
```

### DQ-005: campo obligatorio vacío

```sql
SELECT COUNT(*) AS failed_rows
FROM call_transcripts
WHERE duration_seconds IS NULL;
-- Esperado: 24029.
```

### DQ-006: la foreign key existe, pero el cliente es otro

```sql
SELECT COUNT(*) AS failed_rows
FROM complaints c
JOIN products p ON p.product_id = c.affected_product_id
WHERE c.customer_id <> p.customer_id;
-- Esperado: 44570. Verificar referencias faltantes por separado.
```

### DQ-009 y DQ-010: evidencia insuficiente

```sql
SELECT COUNT(*) AS failed_rows
FROM complaints
WHERE claimed_amount IS NOT NULL AND currency IS NULL;
-- Esperado: 1040.

SELECT COUNT(*) AS insufficient_evidence
FROM complaints
WHERE status IN ('Resolved', 'Closed')
  AND (resolution_date IS NULL OR resolution IS NULL);
-- Esperado: 1549, sin sumar dos veces los registros con ambos campos vacíos.
```

Las reglas temporales comparan fechas ya parseadas, no strings con formatos arbitrarios. Para transacciones se requiere `transaction_date >= registration_date` y que su fecha calendario no preceda `opening_date`, que el diccionario define como DATE. No inferir una hora de apertura intradía ni una zona horaria que no existe en el origen.

## 8. Pruebas de aceptación para la implementación futura

- Detectar los 6 números de producto y 13 códigos de empleado en conflicto sin fusionar identidades.
- Bloquear los 44.570 joins reclamo-producto con ownership incorrecto, conservando usos independientes del reclamo.
- Distinguir los 24.029 nulos obligatorios de los nulos permitidos en referencias opcionales.
- Convertir enteros con sufijo `.0` sin pérdida y rechazar fracciones reales en columnas INTEGER.
- Bloquear decisiones monetarias basadas en los 1.040 importes reclamados sin moneda.
- No declarar verificadas las resoluciones de los 1.549 reclamos con evidencia incompleta a partir del estado histórico solamente.
- Probar con fixtures identificados el replay, un archivo truncado, una corrección conflictiva y una columna nueva. Mantener la publicación válida anterior ante fallo.
- Si cambia el origen, comparar conteos con un baseline versionado y explicar la variación. Los conteos de este informe son un resultado de auditoría, no umbrales permanentes de aceptación.
