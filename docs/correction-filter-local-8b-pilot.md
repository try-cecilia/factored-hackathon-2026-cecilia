# Piloto local de modelos 8B: filtro de autocorrecciones

**Fecha:** 2026-10-03  
**Estado:** exploratorio; fixture pendiente de revisión humana.  
**Set:** 16 casos, dos por idioma y grupo; baseline y filtro con el mismo modelo.

Se probaron modelos ya instalados en Ollama, sin llamadas externas:

- `qwen3:8b` (Q4_K_M)
- `llama3-groq-tool-use:8b` (Q4_0)

El smoke test local de Qwen respondió en 19 s. No hubo errores del runtime en ninguno de los dos pilotos. El preflight del subconjunto encontró 3/4 frases de cambio de intención reescritas y 2/2 controles de fraude con escalación antes del modelo.

## Exactitud del resultado esperado

| Grupo (n=4) | Qwen 3 baseline | Qwen 3 filtro | Llama 3 Tool Use baseline | Llama 3 Tool Use filtro |
| --- | ---: | ---: | ---: | ---: |
| Cambio de intención | 1/4 | 3/4 | 0/4 | 0/4 |
| Corrección de cantidad | 4/4 | 3/4 | 3/4 | 3/4 |
| Mensaje imperfecto sin autocorrección | 2/4 | 2/4 | 0/4 | 0/4 |
| Sensible/ambiguo | 3/4 | 3/4 | 2/4 | 2/4 |

Los resultados apuntan a que el filtro ayuda a Qwen en estos pocos cambios de intención, pero no a Llama en este subconjunto: Llama pidió aclaración en todos los intentos de intención. Qwen añadió un `limit` no solicitado en una transferencia genérica y, en una corrección de cantidad en portugués, inventó un `product_id` que solo apareció con el filtro. Ambos escalaron los dos casos de fraude seleccionados sin llamadas al modelo o herramientas. Llama pidió aclaración en los dos controles benignos de movimientos pendientes; Qwen resolvió uno y también aclaró el otro.

## Lectura

Esto confirma que las 8B locales sirven para iterar sin cuota y detectar errores de herramientas/argumentos. No sustituyen la evaluación del modelo alojado: son modelos y capacidades distintos. El piloto es pequeño, asistido por IA y todavía no revisado por personas; no sirve para estimar el comportamiento de producción ni autoriza activar el filtro. Mantenerlo opt-in y desactivado por defecto.
