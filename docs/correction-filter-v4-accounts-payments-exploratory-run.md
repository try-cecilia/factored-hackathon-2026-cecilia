# Corrida exploratoria v4: cuentas y pagos

**Fecha:** 2026-10-02  
**Estado:** interrumpida; no producir métricas.  
**Fixture:** borrador v4 de cuentas/pagos, todavía pendiente de revisión humana.  
**Proveedor/modelo:** Groq `openai/gpt-oss-120b`, sin fallback previsto, intervalo configurado de 14 segundos.

## Preflight local

- 120 casos: 60 ES y 60 PT, 15 por idioma en cada uno de cuatro grupos.
- 120 IDs únicos y políticas de argumentos para los 120 casos.
- Ninguna etiqueta de cotización de moneda ni mención de moneda fuera del alcance cuentas/pagos.
- El filtro reescribió 25/30 cambios de intención y dejó intactos los otros tres grupos.
- Los 10 casos de posible fraude activaron la escalación pre-LLM en el preflight local.

## Corrida del modelo

La comparación pareada comenzó con frases del fixture anterior; se detuvo, esas frases se sustituyeron y la primera corrida se descartó. La segunda corrida comenzó con el fixture de cuentas/pagos. Groq devolvió `429 rate_limit_exceeded` al llegar al bloque portugués. El runner no detectó inicialmente el error y continuó registrando filas `llm_unavailable`; se detuvo en cuanto se observó el problema.

No hay una comparación completa ni un resumen válido. No interpretar las filas parciales como puntuación del filtro. Se corrigió el runner para abortar inmediatamente si la categoría es `llm_unavailable`.

## Reintento (2026-10-03)

El preflight repitió los mismos conteos. Groq volvió a limitar la cuenta al comenzar el segundo caso; algunas respuestas de contingencia conservaron una disposición normal, así que el runner aún no las detectaba. Se detuvo al reconocer la interrupción. Se reforzó la detección para abortar ante cualquier resultado degradado, aunque tenga otra categoría; no se volverá a consultar al proveedor hasta que el límite se libere.

## Reintento con clave nueva

La clave se autenticó en un smoke test de una sola llamada y se mantuvo solo en memoria del proceso. La comparación consiguió completar el primer par y recibió `429 rate_limit_exceeded` en la llamada filtrada del segundo caso. El runner fail-fast detectó el resultado degradado y abortó; no hay métricas completas ni parciales que deban puntuarse.

Como el borrador fue parcialmente expuesto al modelo y sus frases fueron generadas por IA, no es un holdout ciego. Tras revisión humana se debe congelar un corpus nuevo para la decisión final, con modelo, presupuesto de llamadas y manejo de errores preregistrados.
