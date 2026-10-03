import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useT } from '../../i18n/context'
import type { DemoEntry } from '../../server/demo-entry'
import { Button, type ButtonSize, type ButtonVariant } from '../../ui'
import { EnterDemoDialog } from './EnterDemoDialog'

export { DEMO_ENTRY_HREF } from './DemoBar'

type Props = {
  /** The test customers the kit offers (demoEntries): none, and there is no button. */
  entries: DemoEntry[]
  /** Opened from the start: the home page reached through DEMO_ENTRY_HREF (`/?demo=entrar`). */
  initiallyOpen?: boolean
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
}

/**
 * "Entrar a la demo": the button and the dialog it opens. Only with the one-click demo on (DEMO_CONSOLE=1); without it nothing is
 * drawn. A page links to the entry with DEMO_ENTRY_HREF, or mounts this where its button goes.
 */
export function EnterDemoButton({ entries, initiallyOpen = false, variant = 'outline', size = 'lg', className }: Props) {
  const t = useT()
  const navigate = useNavigate()
  const [open, setOpen] = useState(initiallyOpen)
  if (entries.length === 0) return null
  const close = () => {
    setOpen(false)
    // The link that opened it is not kept in the address: going back does not open it again.
    if (initiallyOpen) void navigate({ to: '/', search: {} as never, replace: true })
  }
  return (
    <>
      <Button variant={variant} size={size} className={className} aria-haspopup="dialog" onClick={() => setOpen(true)}>{t('demoMode.entry.open')}</Button>
      <EnterDemoDialog open={open} entries={entries} onClose={close} />
    </>
  )
}
