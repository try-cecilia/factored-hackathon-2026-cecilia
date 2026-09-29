import type { DeskState, Ticket } from './operator.functions.ts'

/**
 * What the queue, its filters and the sidebar counts use of a ticket. The queue is read again every 30 seconds, up to 200
 * tickets each time: the evidence, the verified facts, the actions and the desk's history stay on the server and travel only
 * with the case that is opened (`loadTicket`).
 */
export type QueueRow = Pick<Ticket, 'ticket_id' | 'created_at' | 'category' | 'priority' | 'queue' | 'customer_id' | 'country' | 'language' | 'request'> & {
  desk: Pick<DeskState, 'status' | 'operator' | 'version'>
}

export const toQueueRow = (t: Ticket): QueueRow => ({
  ticket_id: t.ticket_id,
  created_at: t.created_at,
  category: t.category,
  priority: t.priority,
  queue: t.queue,
  customer_id: t.customer_id,
  country: t.country,
  language: t.language,
  request: t.request,
  desk: { status: t.desk.status, operator: t.desk.operator, version: t.desk.version },
})
