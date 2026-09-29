import { useState } from 'react'
import { useT } from '../../i18n/context'
import { Button } from '../Button'
import { Group } from '../gallery/Section'
import type { BulkAction } from './BulkActionBar'
import { DataTable, RowIdentity } from './DataTable'
import { PriorityChip, StatusIndicator } from './PriorityChip'
import { Pagination } from './Pagination'
import { priorities, type StatusTone } from './priority'
import { SortButton } from './SortButton'
import type { SortState } from './sort'
import { sortRows } from './sort'
import type { Column } from './types'
import './TableGallery.css'

type Status = 'resolved' | 'pending' | 'scheduled'
type Comfortable = { id: string; key: 'contact' | 'access' | 'movement' | 'language' | 'card' | 'billing'; status: Status; messages: number }

const comfortableRows: Comfortable[] = [
  { id: 'r1', key: 'contact', status: 'resolved', messages: 4 },
  { id: 'r2', key: 'access', status: 'resolved', messages: 6 },
  { id: 'r3', key: 'movement', status: 'resolved', messages: 3 },
  { id: 'r4', key: 'language', status: 'resolved', messages: 2 },
  { id: 'r5', key: 'card', status: 'pending', messages: 5 },
  { id: 'r6', key: 'billing', status: 'scheduled', messages: 1 },
]
const comfortableTone: Record<Status, StatusTone> = { resolved: 'neutral', pending: 'caution', scheduled: 'info' }

type QueueStatus = 'claimed' | 'open' | 'approved' | 'stale'
type Ticket = {
  id: string
  priority: (typeof priorities)[number]
  queue: string
  /** Text written by the customer: it is data, so it keeps its own language. */
  request: string
  locale: string
  age: string
  status: QueueStatus
  operator: string
}
const queueTone: Record<QueueStatus, StatusTone> = { claimed: 'info', open: 'open', approved: 'success', stale: 'caution' }

const tickets: Ticket[] = [
  { id: '4f21a9', priority: 'critical', queue: 'fraud_ops', request: 'No reconozco un cargo en mi tarjeta', locale: 'MX·ES', age: '4m', status: 'claimed', operator: 'ana.ruiz' },
  { id: '7b03c2', priority: 'critical', queue: 'fraud_ops', request: 'Alguien cambió mi contraseña y entró a mi cuenta', locale: 'CO·ES', age: '11m', status: 'claimed', operator: 'diego.m' },
  { id: 'a91f3c', priority: 'high', queue: 'payments_ops', request: 'Mi pago sigue pendiente', locale: 'MX·ES', age: '26m', status: 'open', operator: '—' },
  { id: '9c14b5', priority: 'medium', queue: 'payments_ops', request: 'Mi tarjeta nueva no ha llegado', locale: 'CO·ES', age: '1h', status: 'open', operator: '—' },
  { id: 'b7720e', priority: 'low', queue: 'account_payments_l2', request: 'Quero entender por que meu saldo mudou', locale: 'AR·PT', age: '2h', status: 'approved', operator: 'lucia.g' },
  { id: '18b2d7', priority: 'low', queue: 'payments_ops', request: 'Pago pendiente de la tarjeta', locale: 'CO·ES', age: '6h', status: 'stale', operator: 'ana.ruiz' },
]
const ageMinutes: Record<string, number> = { '4m': 4, '11m': 11, '26m': 26, '1h': 60, '2h': 120, '6h': 360 }

/** One numbered block of the Paper artboard: its title as the group, its one-line description under it. */
function Block({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="gal-table__cell">
      <Group title={title}>
        <p className="gal__caption">{description}</p>
        <div className="gal-table__block">{children}</div>
      </Group>
    </div>
  )
}

export function TableGallery() {
  const t = useT()
  const [selected, setSelected] = useState<string[]>(['4f21a9', '7b03c2'])
  const [sort, setSort] = useState<SortState>({ key: 'age', direction: 'asc' })
  const [page, setPage] = useState(1)

  const statusText = (status: Status | QueueStatus) => t(`table.sample.status.${status}`)

  const comfortableColumns: Column<Comfortable>[] = [
    { id: 'date', header: t('table.sample.columns.date'), width: 96, muted: true, cell: (row) => t(`table.sample.comfortable.rows.${row.key}.date`) },
    {
      id: 'topic',
      header: t('table.sample.columns.topic'),
      rowHeader: true,
      cell: (row) => <RowIdentity mark={t(`table.sample.comfortable.rows.${row.key}.topic`).charAt(0)}>{t(`table.sample.comfortable.rows.${row.key}.topic`)}</RowIdentity>,
    },
    { id: 'category', header: t('table.sample.columns.category'), width: 150, cell: (row) => t(`table.sample.comfortable.rows.${row.key}.category`) },
    { id: 'status', header: t('table.sample.columns.status'), width: 120, cell: (row) => <StatusIndicator tone={comfortableTone[row.status]}>{statusText(row.status)}</StatusIndicator> },
    { id: 'messages', header: t('table.sample.columns.messages'), width: 140, align: 'end', strong: true, cell: (row) => row.messages },
  ]

  const ticketColumn = { id: 'ticket', header: t('table.sample.columns.ticket'), rowHeader: true, mono: true, width: 68, cell: (row: Ticket) => row.id } satisfies Column<Ticket>
  const requestColumn = { id: 'request', header: t('table.sample.columns.request'), truncate: true, cell: (row: Ticket) => row.request } satisfies Column<Ticket>
  const statusColumn = { id: 'status', header: t('table.sample.columns.status'), width: 96, cell: (row: Ticket) => <StatusIndicator tone={queueTone[row.status]}>{statusText(row.status)}</StatusIndicator> } satisfies Column<Ticket>

  const compactColumns: Column<Ticket>[] = [
    { id: 'priority', header: t('table.sample.columns.priority'), width: 64, cell: (row) => <PriorityChip priority={row.priority} /> },
    ticketColumn,
    { id: 'queue', header: t('table.sample.columns.queue'), width: 148, mono: true, muted: true, cell: (row) => row.queue },
    requestColumn,
    { id: 'locale', header: t('table.sample.columns.locale'), width: 64, mono: true, muted: true, cell: (row) => row.locale },
    { id: 'age', header: t('table.sample.columns.age'), width: 44, align: 'end', mono: true, muted: true, cell: (row) => row.age },
    statusColumn,
    { id: 'operator', header: t('table.sample.columns.operator'), width: 84, mono: true, cell: (row) => row.operator },
  ]

  const selectionColumns: Column<Ticket>[] = [
    { ...ticketColumn },
    requestColumn,
    { ...statusColumn, width: 84 },
  ]
  const bulkActions: BulkAction[] = [
    { id: 'claim', label: t('table.sample.actions.claim'), onAction: () => setSelected([]), primary: true },
    { id: 'release', label: t('table.sample.actions.release'), onAction: () => setSelected([]), muted: true },
  ]

  const sortStates = [
    { key: 'unsorted', direction: null, forceState: undefined },
    { key: 'hover', direction: null, forceState: 'hover' },
    { key: 'ascending', direction: 'asc', forceState: undefined },
    { key: 'descending', direction: 'desc', forceState: undefined },
    { key: 'focus', direction: 'desc', forceState: 'focus' },
  ] as const

  const sorted = sortRows(tickets, sort, (row, key) => (key === 'age' ? ageMinutes[row.age] : (row as Record<string, unknown>)[key] as string))
  const sortColumns: Column<Ticket>[] = [
    { ...ticketColumn },
    requestColumn,
    { id: 'age', header: t('table.sample.columns.age'), width: 96, align: 'end', mono: true, muted: true, sortable: true, cell: (row) => row.age },
  ]

  return (
    <div className="gal-table">
        <Block title={t('table.sample.titles.comfortable')} description={t('table.sample.descriptions.comfortable')}>
          <DataTable rows={comfortableRows} columns={comfortableColumns} getRowId={(row) => row.id} caption={t('table.sample.caption.comfortable')} forceHoverId="r2" />
        </Block>

        <Block title={t('table.sample.titles.compact')} description={t('table.sample.descriptions.compact')}>
          <DataTable
            density="compact"
            rows={tickets}
            columns={compactColumns}
            getRowId={(row) => row.id}
            caption={t('table.sample.caption.compact')}
            selectedIds={['4f21a9', '7b03c2']}
            forceHoverId="a91f3c"
          />
        </Block>

        <div className="gal-table__pair">
          <Block title={t('table.sample.titles.selection')} description={t('table.sample.descriptions.selection')}>
            <DataTable
              density="compact"
              rows={tickets.slice(0, 4)}
              columns={selectionColumns}
              getRowId={(row) => row.id}
              getRowLabel={(row) => row.id}
              caption={t('table.sample.caption.selection')}
              selectedIds={selected}
              onSelectionChange={setSelected}
              bulkActions={bulkActions}
            />
          </Block>

          <Block title={t('table.sample.titles.sorting')} description={t('table.sample.descriptions.sorting')}>
            <div className="gal-table__sort">
              {sortStates.map((state) => (
                <div key={state.key} className="gal__cell">
                  <SortButton label={t('table.sample.columns.age')} direction={state.direction} forceState={state.forceState} onClick={() => {}} />
                  <span className="gal__caption">{t(`table.sample.sortStates.${state.key}`)}</span>
                </div>
              ))}
            </div>
            <DataTable
              density="compact"
              rows={sorted.slice(0, 3)}
              columns={sortColumns}
              getRowId={(row) => row.id}
              caption={t('table.sample.caption.sorting')}
              sort={sort}
              onSortChange={setSort}
            />
            <Pagination page={page} pageSize={25} total={138} onPageChange={setPage} />
          </Block>

          <Block title={t('table.sample.titles.loading')} description={t('table.sample.descriptions.loading')}>
            <DataTable loading rows={[]} columns={comfortableColumns} getRowId={(row: Comfortable) => row.id} caption={t('table.sample.caption.loading')} />
          </Block>

          <Block title={t('table.sample.titles.empty')} description={t('table.sample.descriptions.empty')}>
            <DataTable
              rows={[]}
              columns={comfortableColumns}
              getRowId={(row: Comfortable) => row.id}
              caption={t('table.sample.caption.empty')}
              empty={{
                title: t('table.sample.empty.title'),
                description: t('table.sample.empty.description'),
                action: <Button variant="ghost" tinted size="sm">{t('table.sample.empty.action')}</Button>,
              }}
            />
          </Block>
        </div>

        <Block title={t('table.sample.titles.chips')} description={t('table.sample.descriptions.chips')}>
          <div className="gal-table__chips">
            {priorities.map((priority) => <PriorityChip key={priority} priority={priority} />)}
            <div className="gal-table__chip-row">
              {(['neutral', 'info', 'success', 'caution', 'open'] as const).map((tone) => (
                <StatusIndicator key={tone} tone={tone}>{tone}</StatusIndicator>
              ))}
            </div>
          </div>
        </Block>
    </div>
  )
}
