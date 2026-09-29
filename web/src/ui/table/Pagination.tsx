import { useT } from '../../i18n/context'
import { Button } from '../Button'
import './Pagination.css'
import { clampPage, hasNext, hasPrevious, pageCount, pageItems, pageRange } from './paging'

type Props = {
  /** 1-based. An out-of-range page is drawn as the nearest valid one. */
  page: number
  pageSize: number
  /** Rows across all pages. */
  total: number
  onPageChange: (page: number) => void
  className?: string
}

/** Table footer: the range on the left ("Showing 1–25 of 138"), previous, page numbers and next on the right. */
export function Pagination({ page, pageSize, total, onPageChange, className }: Props) {
  const t = useT()
  const current = clampPage(page, total, pageSize)
  const { from, to } = pageRange(current, total, pageSize)
  const items = pageItems(current, pageCount(total, pageSize))

  return (
    <nav className={className ? `ui-pager ${className}` : 'ui-pager'} aria-label={t('table.pagination.label')}>
      <p className="ui-pager__range" aria-live="polite">
        {total > 0 ? t('table.pagination.showing', { from, to, total }) : t('table.pagination.none')}
      </p>
      <div className="ui-pager__controls">
        <Button variant="ghost" size="sm" disabled={!hasPrevious(current)} onClick={() => onPageChange(current - 1)}>
          {t('table.pagination.previous')}
        </Button>
        {items.map((item) =>
          typeof item === 'number' ? (
            <button
              key={item}
              type="button"
              className="ui-pager__page"
              aria-current={item === current ? 'page' : undefined}
              aria-label={t('table.pagination.goTo', { page: item })}
              onClick={() => item !== current && onPageChange(item)}
            >
              {item}
            </button>
          ) : (
            <span key={item} className="ui-pager__gap" aria-hidden="true">…</span>
          ),
        )}
        <Button variant="ghost" size="sm" disabled={!hasNext(current, total, pageSize)} onClick={() => onPageChange(current + 1)}>
          {t('table.pagination.next')}
        </Button>
      </div>
    </nav>
  )
}
