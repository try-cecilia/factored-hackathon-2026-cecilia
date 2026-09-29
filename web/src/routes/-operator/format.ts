import type { DeskStatus } from '../../server/operator.functions'

export const PRIORITY_ORDER = ['Critical', 'High', 'Medium', 'Low']
export const priorityLabel: Record<string, string> = { Critical: 'Crítica', High: 'Alta', Medium: 'Media', Low: 'Baja' }

export const statusLabel: Record<DeskStatus, string> = {
  open: 'Sin tomar',
  claimed: 'Tomado',
  approved: 'Aprobado',
  rejected: 'Rechazado',
  handed_back: 'Devuelto',
  stale: 'Ya no aplica',
}
export const CLOSED: DeskStatus[] = ['approved', 'rejected', 'handed_back', 'stale']

export const categoryLabel: Record<string, string> = {
  fraud: 'Fraude',
  theft: 'Robo',
  account_takeover: 'Toma de cuenta',
  safety: 'Cliente vulnerable',
  legal_or_regulator: 'Legal o regulador',
  classifier_escalation: 'Posible fraude (clasificador)',
  compliance_hold: 'Cuenta suspendida',
  security: 'Seguridad',
  data_unavailable: 'Dato no disponible',
  tool_failure: 'Falla de herramienta',
  llm_unavailable: 'Asistente caído',
  trace_unmatched: 'Rastreo sin coincidencia',
  trace_unverified: 'Rastreo sin confirmar',
  trace_review: 'Revisión de rastreo',
}
export const label = (map: Record<string, string>, key: string | null | undefined) => (key ? map[key] ?? key : '—')

export const dispositionLabel: Record<string, string> = {
  AUTO_RESOLVE: 'Resuelto',
  CLARIFY: 'Aclaración',
  ABSTAIN: 'Sin respuesta',
  ESCALATE: 'Derivado',
}

const rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })
export function ago(ts: number | null | undefined, now = Date.now()) {
  if (!ts) return '—'
  const seconds = Math.round((ts * 1000 - now) / 1000)
  const abs = Math.abs(seconds)
  if (abs < 60) return 'hace instantes'
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), 'hour')
  return rtf.format(Math.round(seconds / 86400), 'day')
}

const dateTime = new Intl.DateTimeFormat('es', { dateStyle: 'medium', timeStyle: 'short' })
export const when = (ts: number | null | undefined) => (ts ? dateTime.format(ts * 1000) : '—')

export const usd = (n: number | null | undefined, digits = 4) => (n == null ? '—' : `USD ${n.toFixed(digits)}`)
export const ms = (n: number | null | undefined) => (n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${Math.round(n)} ms`)
export const short = (id: string | null | undefined) => (id ? id.slice(0, 8) : '—')

/** What the operator reads when the BFF or API said no. `acting` = the failed call was an action, not a read. */
export function explain(status: number, acting = false) {
  switch (status) {
    case 0:
    case 401:
      return acting
        ? 'La clave de operador ya no es válida. Ingresala de nuevo para actuar.'
        : 'La sesión venció o la clave de lectura ya no es válida. Ingresá de nuevo.'
    case 403:
      return 'Tu sesión es de solo lectura. Agregá una clave de operador para actuar.'
    case 404:
      return acting ? 'El caso ya no existe.' : 'No hay datos para mostrar.'
    case 409:
      return 'Otra persona movió este caso antes. Recargamos su estado; revisalo y volvé a decidir.'
    case 429:
      return 'Demasiados intentos fallidos desde este origen. Esperá un minuto.'
    case 503:
      return 'El servicio no está disponible en este momento (o falta configurar las claves).'
    default:
      return 'No se pudo completar la operación.'
  }
}
