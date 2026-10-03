import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { headTitle } from '../i18n/head'
import { DemoEntryProvider } from '../landing/demo-entry'
import { Landing } from '../landing/Landing'
import { demoEntries } from '../server/demo-entry'
import { getDemoKit, type DemoKit } from '../server/demo.functions'

export const Route = createFileRoute('/')({
  // Not awaited: the landing never waits for the API. Until the kit answers (or without the sandbox) "Probar la demo" is the sign-in.
  loader: () => ({ kit: getDemoKit().catch((): DemoKit => ({ enabled: false })) }),
  head: ({ matches }) => headTitle(matches, 'landing.pageTitle'),
  component: Home,
})

function Home() {
  const { kit } = Route.useLoaderData()
  // The one-click entry is offered once the kit says the demo console is on (DemoEntryCta).
  const [oneClick, setOneClick] = useState(false)
  useEffect(() => {
    let live = true
    void kit.then((resolved) => live && setOneClick(demoEntries(resolved).length > 0))
    return () => void (live = false)
  }, [kit])
  return (
    <DemoEntryProvider value={oneClick}>
      <Landing />
    </DemoEntryProvider>
  )
}
