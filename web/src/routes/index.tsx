import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { headTitle } from '../i18n/head'
import { DemoEntryProvider } from '../landing/demo-entry'
import { Landing } from '../landing/Landing'
import type { DemoEntry } from '../server/demo-entry'
import { demoEntries } from '../server/demo-entry'
import { getDemoKit, type DemoKit } from '../server/demo.functions'
import { EnterDemoHost } from './-demo/EnterDemo'

export const Route = createFileRoute('/')({
  // `?demo=entrar` (DEMO_ENTRY_HREF) opens the one-click demo's dialog.
  validateSearch: (search: Record<string, unknown>): { demo?: 'entrar' } => (search.demo === 'entrar' ? { demo: 'entrar' } : {}),
  // Not awaited: the landing never waits for the API. Until the kit answers (or without the sandbox) "Probar la demo" is the sign-in.
  loader: () => ({ kit: getDemoKit().catch((): DemoKit => ({ enabled: false })) }),
  head: ({ matches }) => headTitle(matches, 'landing.pageTitle'),
  component: Home,
})

function Home() {
  const { kit } = Route.useLoaderData()
  const { demo } = Route.useSearch()
  const [entries, setEntries] = useState<DemoEntry[]>([])
  useEffect(() => {
    let live = true
    void kit.then((resolved) => live && setEntries(demoEntries(resolved)))
    return () => void (live = false)
  }, [kit])
  return (
    <DemoEntryProvider value={entries.length > 0}>
      <Landing />
      <EnterDemoHost entries={entries} open={demo === 'entrar'} />
    </DemoEntryProvider>
  )
}
