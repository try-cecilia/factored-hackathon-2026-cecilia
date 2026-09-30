import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { DeskStatus } from '../../server/operator.functions.ts'
import type { QueueRow } from '../../server/queue-row.ts'
import { countryCode, countryOptions, defaultOrder, pageSlice, filterTickets, filtersOf, inScope, localeOf, orderTickets, sidebarCounts, tabCounts, validateSearch, type QueueFilters } from './queue.ts'

let n = 0
function ticket(over: Partial<QueueRow> & { status?: DeskStatus; operator?: string | null } = {}): QueueRow {
  const { status = 'open', operator = null, ...rest } = over
  n += 1
  return {
    ticket_id: `t${n.toString().padStart(3, '0')}`, created_at: 1000 + n, category: 'fraud', priority: 'Low', queue: 'fraud_ops',
    customer_id: 'C-1', country: 'MX', language: 'es', request: 'Pedido',
    desk: { status, operator, version: 1 },
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

test('an old open case among many newer closed ones still counts as pending work and stays in the unassigned view', () => {
  const oldOpen = ticket({ created_at: 1, priority: 'Low' })
  const history = Array.from({ length: 250 }, () => ticket({ status: 'approved', operator: 'ana.ruiz' }))
  const queue = [oldOpen, ...history]
  assert.equal(sidebarCounts(queue, 'ana.ruiz').unassigned, 1)
  assert.deepEqual(filterTickets(queue, { view: 'unassigned', tab: 'all' }, 'ana.ruiz').map((t) => t.ticket_id), [oldOpen.ticket_id])
  assert.equal(defaultOrder(queue)[0].ticket_id, oldOpen.ticket_id)
})

// A case that reached the console without a priority or a language (an old or incomplete record) is still drawn: it says so, it does
// not take down the ordering or the rendering of the whole queue, and it does not pass for a priority it does not have.
const noPriority = ticket({ priority: undefined, created_at: 20 })
const nullPriority = ticket({ priority: null, created_at: 30 })
const noLanguage = ticket({ priority: 'High', language: undefined, country: null })

test('a case without priority does not break the default order and goes after the ones that have one', () => {
  const sorted = defaultOrder([noPriority, medNew, nullPriority, crit, done])
  assert.deepEqual(sorted.map((t) => t.ticket_id), [crit, medNew, noPriority, nullPriority, done].map((t) => t.ticket_id))
})

test('ordering by priority or by locale tolerates the missing values, and the case keeps its (missing) priority', () => {
  for (const direction of ['asc', 'desc'] as const) {
    assert.equal(orderTickets([noPriority, crit, noLanguage], { key: 'priority', direction }).length, 3)
    assert.equal(orderTickets([noPriority, crit, noLanguage], { key: 'locale', direction }).length, 3)
  }
  assert.equal(noPriority.priority, undefined)
})

test('the locale of a case without language is marked, not hidden and not made up', () => {
  assert.equal(localeOf(noLanguage), '?')
  assert.equal(localeOf(ticket({ country: 'México', language: null })), 'MX·?')
  assert.equal(localeOf(noLanguage, 'Desconocido'), 'Desconocido')
})

test('the filters and the counts do not fail on a case without priority or language', () => {
  const mixed = [noPriority, noLanguage, crit]
  assert.deepEqual(filterTickets(mixed, { ...all, priority: 'Critical' }, null), [crit])
  assert.deepEqual(filterTickets(mixed, { ...all, language: 'es' }, null), [noPriority, crit])
  assert.equal(tabCounts(inScope(mixed, all, null)).all, 3)
})
