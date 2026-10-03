import { useNavigate, useRouterState } from '@tanstack/react-router'
import type { DemoEntry } from '../../server/demo-entry'
import { EnterDemoDialog } from './EnterDemoDialog'

export { DEMO_ENTRY_HREF } from './DemoBar'

type Props = {
  /** The test customers the kit offers (demoEntries): none, and there is no dialog. */
  entries: DemoEntry[]
  /** The address asks for it: the home page with `?demo=entrar` (DEMO_ENTRY_HREF, the landing's "Probar la demo"). */
  open: boolean
}

/**
 * The one-click demo's dialog on the home page, opened by its address: every "Probar la demo" of the landing is a link to
 * DEMO_ENTRY_HREF, so it opens from the same page, from another one, or from a link shared. Only with the demo console on.
 */
export function EnterDemoHost({ entries, open }: Props) {
  const navigate = useNavigate()
  // Read at the moment of closing, not when drawn: the dialog may close after the visitor has already left this page.
  const onEntryLink = useRouterState({ select: (s) => s.location.pathname === '/' && (s.location.search as { demo?: string }).demo === 'entrar' })
  if (entries.length === 0) return null
  // Cancelled on the entry link: the link leaves the address (going back does not open it again), and that closes the dialog.
  // Anywhere else (the chat, after entering) the address is left alone.
  const close = () => {
    if (onEntryLink) void navigate({ to: '/', search: {} as never, replace: true })
  }
  return <EnterDemoDialog open={open} entries={entries} onClose={close} />
}
