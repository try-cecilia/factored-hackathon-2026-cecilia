# Estado de la evaluación del filtro de autocorrecciones

Actualizado: 2026-10-03.

## Hecho

- El piloto exploratorio de modelos locales 8B ya fue ejecutado por el usuario. Los resultados de Qwen 3 8B y Llama 3 Tool Use 8B, junto con sus límites, están en [el informe del piloto](correction-filter-local-8b-pilot.md).
- Se agregan los fixtures de cuentas y pagos y su política esperada de argumentos en `ops/fixtures/correction_filter_review_*_v4_accounts_payments.jsonl`.
- La evaluación con Groq quedó interrumpida por límites `429`. No hay métricas completas válidas; el detalle está en [el informe exploratorio v4](correction-filter-v4-accounts-payments-exploratory-run.md).

## Qué hay en el repositorio

Solo estos informes y los dos fixtures. La implementación del filtro y el runner de la comparación pareada (baseline y filtro con el mismo modelo) no están en este repositorio: las corridas descritas se hicieron en local. Hasta que se agreguen, ninguno de estos resultados se puede reproducir desde el repositorio.

## Pendiente

- Agregar al repositorio el filtro y el runner, apagados por defecto.
- Probar Sonnet 5 (`claude-sonnet-5`, el modelo configurado primero en producción según `render.yaml` y ADR-004) con el fixture de cuentas y pagos.
- Subir los resultados completos de los benchmarks una vez que la corrida termine. Los resultados locales 8B ya están documentados, pero son exploratorios y no sustituyen la evaluación de Sonnet.
- Revisar y congelar el fixture con revisión humana antes de tratarlo como holdout o usar sus métricas para decidir sobre producción.

El filtro sigue opt-in y desactivado por defecto. Ninguno de estos resultados autoriza activarlo en producción.
