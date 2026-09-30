import { useT } from '../i18n/context'
import type { CaseRow } from '../chat/ConversationProvider'
import { caseCategoryKey, caseTone, isOpenCase, shortCaseId } from '../chat/conversation'
import { SidebarCasesIcon, SidebarEmpty, SidebarRow, SidebarSection } from '../ui'

type Translate = ReturnType<typeof useT>

const STATUSES = ['open', 'claimed', 'approved', 'rejected', 'handed_back', 'stale', 'resolved'] as const

export function statusLabel(t: Translate, row: CaseRow): string {
  if (row.state.state === 'loading') return t('cases.loading')
  if (row.state.state === 'error') return t('cases.unavailable')
  if (row.state.state === 'not_found') return t('cases.notFound')
  const status = row.state.status
  return t(`cases.status.${(STATUSES as readonly string[]).includes(status) ? (status as (typeof STATUSES)[number]) : 'unknown'}`)
}

/** "Cases": the handoffs of this conversation and where each stands. In the rail it is one icon, with a dot while any case is open. */
export function CasesSection({ cases, collapsed, onOpen, onExpand }: {
  cases: CaseRow[]
  collapsed: boolean
  /** A case row was chosen: bring its message into view. */
  onOpen: (ticketId: string) => void
  onExpand: () => void
}) {
  const t = useT()
  const open = cases.filter((c) => c.state.state === 'ready' && isOpenCase(c.state.status)).length

  if (collapsed) {
    return (
      <SidebarSection title={t('cases.title')}>
        <SidebarRow icon={<SidebarCasesIcon />} label={t('cases.title')} status={open > 0 ? 'unread' : undefined} onClick={onExpand} />
      </SidebarSection>
    )
  }

  return (
    <SidebarSection title={t('cases.title')} meta={open > 0 ? t(open === 1 ? 'cases.openOne' : 'cases.openMany', { n: open }) : undefined}>
      {cases.length === 0 ? (
        <li><SidebarEmpty title={t('cases.empty.title')} description={t('cases.empty.description')} /></li>
      ) : (
        cases.map((row) => (
          <SidebarRow
            key={row.ref.ticketId}
            id={`case-row-${row.ref.ticketId}`}
            dot={row.state.state === 'ready' ? caseTone(row.state.status) : 'accent'}
            label={t(`cases.category.${caseCategoryKey(row.ref.category)}` as 'cases.category.other')}
            description={`${statusLabel(t, row)} · #${shortCaseId(row.ref.ticketId)}`}
            onClick={() => onOpen(row.ref.ticketId)}
          />
        ))
      )}
    </SidebarSection>
  )
}
