import type { Ref } from 'react'
import { useT } from '../../i18n/context'

/**
 * The queue's search box. It has a stable `id` and `name` (a browser's form-field checks and its autofill want them), and keeps
 * its accessible name in the hidden label.
 */
export function SearchBox({ value, onChange, inputRef }: { value: string; onChange: (value: string) => void; inputRef?: Ref<HTMLInputElement> }) {
  const t = useT()
  return (
    <label className="op-search" htmlFor="op-search">
      <svg viewBox="0 0 20 20" width="12" height="12" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.7" /><path d="M13.2 13.2 17 17" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
      <span className="sr-only">{t('operator.queue.search')}</span>
      <input ref={inputRef} id="op-search" name="q" type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={t('operator.queue.searchPlaceholder')} autoComplete="off" spellCheck={false} />
      <kbd aria-hidden="true">{t('operator.queue.searchHint')}</kbd>
    </label>
  )
}

/**
 * A filter that looks like the pills of the design and is a native select underneath: keyboard and screen readers get it for free.
 * `field` is the filter's own word in the URL (`prioridad`, `pais`, `idioma`) and gives the select its `id` and `name`.
 */
export function FilterSelect({ field, name, value, onChange, options }: {
  field: string
  name: string
  value: string | undefined
  onChange: (value: string | undefined) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="op-select" data-set={value ? '' : undefined}>
      <select id={`op-filter-${field}`} name={field} aria-label={name} value={value ?? ''} onChange={(e) => onChange(e.target.value || undefined)}>
        <option value="">{name}</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <svg viewBox="0 0 20 20" width="10" height="10" aria-hidden="true" focusable="false"><path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </label>
  )
}
