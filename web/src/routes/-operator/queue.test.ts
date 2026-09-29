import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { DeskStatus, Ticket } from '../../server/operator.functions.ts'
import { countryCode, countryOptions, defaultOrder, pageSlice, filterTickets, filtersOf, inScope, localeOf, orderTickets, sidebarCounts, tabCounts, validateSearch, type QueueFilters } from './queue.ts'

let n = 0
function ticket(over: Partial<Ticket> & { status?: DeskStatus; operator?: string | null } = {}): Ticket {
  const { status = 'open', operator = null, ...rest } = over
  n += 1
  return {
    ticket_id: `t${n.toString().padStart(3, '0')}`, trace_id: null, created_at: 1000 + n, category: 'fraud', priority: 'Low', queue: 'fraud_ops',
    customer_id: 'C-1', session_ref: 's', segment: 'Retail', country: 'MX', language: 'es', request: 'Pedido', prior_requests: [], reason: 'r',
    policy_rule: 'rule', verified_facts: [], evidence: [], actions_taken: [], open_questions: [], suggested_next_step: 's', pending_action: null,
    desk: { ticket_id: `t${n}`, status, operator, trace_id: null, version: 1, history: [] },
    ...rest,
  }
}
const all: QueueFilters = { view: 'all', tab: 'all' }

const crit = ticket({ priority: 'Critical', status: 'claimed', operator: 'ana.ruiz', queue: 'fraud_ops' })
const high = ticket({ priority: 'High', queue: 'payments_ops', country: 'AR', language: 'pt' })
const medOld = ticket({ priority: 'Medium', queue: 'payments_ops', created_at: 10 })
const medNew = ticket({ priority: 'Medium', queue: 'complaints', created_at: 500 })
const done = ticket({ priority: 'Critical', status: 'approved', operator: 'lucia.g', created_at: 900 })
const stale = ticket({ priority: 'Low', status: 'stale', operator: 'ana.ruiz', created_at: 950 })
const rows = [medNew, done, high, crit, stale, medOld]

test('the default order is pending first, by priority and then oldest, with closed work last and latest first', () => {
  assert.deepEqual(defaultOrder(rows).map((t) => t.ticket_id), [crit, high, medOld, medNew, stale, done].map((t) => t.ticket_id))
})

test('ordering by a column is stable and puts age ascending as youngest first', () => {
  const byAge = orderTickets(rows, { key: 'age', direction: 'asc' }).map((t) => t.created_at)
  assert.deepEqual(byAge, [...byAge].sort((a, b) => b - a))
  assert.deepEqual(orderTickets(rows, { key: 'priority', direction: 'desc' }).at(0)?.priority, 'Low')
  assert.equal(orderTickets(rows, null).length, rows.length)
})

test('views: mine is only what I hold, unassigned is only open', () => {
  assert.deepEqual(filterTickets(rows, { ...all, view: 'mine' }, 'ana.ruiz').map((t) => t.ticket_id), [crit.ticket_id])
  assert.deepEqual(filterTickets(rows, { ...all, view: 'mine' }, null), [])
  const open = filterTickets(rows, { ...all, view: 'unassigned' }, 'ana.ruiz').map((t) => t.ticket_id).sort()
  assert.deepEqual(open, [high, medNew, medOld].map((t) => t.ticket_id).sort())
})

test('queue, priority, country and language filters combine', () => {
  assert.deepEqual(filterTickets(rows, { ...all, queue: 'payments_ops' }, null).length, 2)
  assert.deepEqual(filterTickets(rows, { ...all, queue: 'payments_ops', priority: 'High' }, null), [high])
  assert.deepEqual(filterTickets(rows, { ...all, country: 'AR', language: 'pt' }, null), [high])
  assert.deepEqual(filterTickets(rows, { ...all, language: 'fr' }, null), [])
})

test('search matches the id, the request, the queue and the operator, ignoring case', () => {
  assert.deepEqual(filterTickets(rows, { ...all, q: crit.ticket_id.toUpperCase() }, null), [crit])
  assert.equal(filterTickets(rows, { ...all, q: 'COMPLAINTS' }, null)[0], medNew)
  assert.equal(filterTickets(rows, { ...all, q: 'lucia' }, null)[0], done)
})

test('status tabs and their counts, taken from the scope before the tab', () => {
  const scope = inScope(rows, { ...all, queue: 'payments_ops' }, null)
  assert.deepEqual(tabCounts(scope), { all: 2, open: 2, claimed: 0, decided: 0 })
  assert.deepEqual(tabCounts(rows), { all: 6, open: 3, claimed: 1, decided: 2 })
  assert.equal(filterTickets(rows, { ...all, tab: 'decided' }, null).length, 2)
  assert.equal(filterTickets(rows, { ...all, tab: 'claimed' }, null)[0], crit)
})

test('sidebar counts count pending work, list the seven queues and add unknown ones', () => {
  const extra = ticket({ queue: 'new_queue' })
  const counts = sidebarCounts([...rows, extra], 'ana.ruiz')
  assert.equal(counts.allOpen, 5)
  assert.equal(counts.mine, 1)
  assert.equal(counts.unassigned, 4)
  assert.deepEqual(counts.queues.map((q) => q.name), ['fraud_ops', 'priority_care', 'complaints', 'security_review', 'compliance', 'payments_ops', 'account_payments_l2', 'new_queue'])
  assert.equal(counts.queues.find((q) => q.name === 'payments_ops')?.count, 2)
  assert.equal(counts.queues.find((q) => q.name === 'priority_care')?.count, 0)
})

test('search params drop what is not known and map to filters', () => {
  assert.deepEqual(validateSearch({ vista: 'x', cola: '<script>', estado: 'tomados', prioridad: 'Urgent', pais: 'MX' }), {
    vista: undefined, cola: undefined, estado: 'tomados', prioridad: undefined, pais: 'MX', idioma: undefined,
  })
  assert.deepEqual(filtersOf({ vista: 'mias', estado: 'decididos', cola: 'fraud_ops' }, '  hola '), {
    view: 'mine', queue: 'fraud_ops', tab: 'decided', priority: undefined, country: undefined, language: undefined, q: 'hola',
  })
})

test('the locale column shows the country code and the language', () => {
  assert.equal(countryCode('México'), 'MX')
  assert.equal(countryCode('Argentina'), 'AR')
  assert.equal(countryCode('Atlántida'), 'Atlántida')
  assert.equal(countryCode(null), null)
  assert.equal(localeOf(ticket({ country: 'Colombia', language: 'es' })), 'CO·ES')
  assert.equal(localeOf(ticket({ country: null, language: 'pt' })), 'PT')
})

test('the country filter survives the URL for every country of the dataset and for names with accents', () => {
  for (const name of ['México', 'Colombia', 'Argentina', 'Perú', 'Brasil', 'Chile', 'Uruguay', 'Atlántida']) {
    const t = ticket({ country: name })
    const other = ticket({ country: name === 'Colombia' ? 'Chile' : 'Colombia' })
    const code = countryCode(name)!
    // What the filter writes to the URL, read back the way the router reads it.
    const search = validateSearch({ pais: code })
    assert.equal(search.pais, code, name)
    assert.deepEqual(filterTickets([t, other], filtersOf(search, ''), null), [t], name)
  }
  // A link written by hand with the country's name still works.
  const mx = ticket({ country: 'México' })
  assert.deepEqual(filterTickets([mx, ticket({ country: 'Chile' })], filtersOf(validateSearch({ pais: 'México' }), ''), null), [mx])
  assert.equal(validateSearch({ pais: '<script>' }).pais, undefined)
})

test('the country options are the codes with the name next to them, once each', () => {
  const options = countryOptions([ticket({ country: 'México' }), ticket({ country: 'México' }), ticket({ country: 'Perú' }), ticket({ country: null })])
  assert.deepEqual(options, [{ value: 'MX', label: 'MX · México' }, { value: 'PE', label: 'PE · Perú' }])
})

test('a page past the end is brought back to the last one, with its rows', () => {
  const rows = Array.from({ length: 26 }, (_, i) => i)
  assert.deepEqual(pageSlice(rows, 2, 25), { page: 2, rows: [25] })
  // The poll leaves 25 cases while the operator is on page 2.
  const fewer = rows.slice(0, 25)
  const back = pageSlice(fewer, 2, 25)
  assert.equal(back.page, 1)
  assert.equal(back.rows.length, 25)
  assert.deepEqual(pageSlice([], 3, 25), { page: 1, rows: [] })
  assert.equal(pageSlice(rows, 0, 25).page, 1)
})
