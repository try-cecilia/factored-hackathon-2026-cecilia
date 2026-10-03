import { Link } from '@tanstack/react-router'
import { createContext, use, type MouseEvent, type ReactNode } from 'react'
import { useT } from '../i18n/context'
import { entryFailureText, useEnterDemo } from '../routes/-demo/useEnterDemo'
import { demoEntry } from './links'

// Whether the one-click demo is on for this page (getDemoKit with console: true and test customers to offer). Off by default:
// without it, "Probar la demo" stays the sign-in.
const DemoEntryContext = createContext(false)

export const DemoEntryProvider = DemoEntryContext.Provider

/**
 * "Probar la demo" and "Entrar a la demo": with the demo console on, one click enters the demo as the default test customer and
 * lands in the chat, where the welcome says what to try. It stays a link to the sign-in, so a click with a modifier, or the page
 * before its script runs, still goes somewhere useful. With the console off it is only that link.
 */
export function DemoEntryCta({ className, children }: { className: string; children: ReactNode }) {
  const t = useT()
  const on = use(DemoEntryContext)
  const entry = useEnterDemo()
  if (!on) return <Link className={className} {...demoEntry}>{children}</Link>
  const enter = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    void entry.enter()
  }
  return (
    <>
      <a className={className} href={demoEntry.to} onClick={enter} aria-busy={entry.pending || undefined} data-entry="one-click">
        {entry.pending ? <span>{t('demoMode.entry.entering')}</span> : children}
      </a>
      {entry.failure && <p className="land-cta__error" role="alert">{entryFailureText(t, entry.failure)}</p>}
    </>
  )
}
