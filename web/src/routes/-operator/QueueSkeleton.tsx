import { useT } from '../../i18n/context'
import { DataTable, Sidebar, SidebarBrand, SidebarSkeleton, type Column } from '../../ui'

const columns: Column<never>[] = ['priority', 'ticket', 'queue', 'request', 'locale', 'age', 'status', 'operator'].map((id) => ({
  id,
  header: '',
  cell: () => null,
}))

/** What the console shows while its first read is slow: the same frame, with placeholder rows of the same height. */
export function QueueSkeleton() {
  const t = useT()
  return (
    <div className="op">
      <div className="op-shell">
        <div className="op-side">
          <Sidebar variant="operator" header={<SidebarBrand />}>
            <SidebarSkeleton />
          </Sidebar>
        </div>
        <main className="op-main" aria-busy="true" aria-label={t('operator.loading')}>
          <div className="op-split">
            <div className="op-list">
              <DataTable density="compact" rows={[]} columns={columns} getRowId={() => ''} caption={t('operator.queue.caption')} loading skeletonRows={10} />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
