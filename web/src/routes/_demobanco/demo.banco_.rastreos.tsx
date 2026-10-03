import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { headTitle } from '../../i18n/head'
import { DemoTracesView } from '../-demo/DemoTracesView'

export const Route = createFileRoute('/_demobanco/demo/banco_/rastreos')({
  head: ({ matches }) => headTitle(matches, 'demoMode.desk.pageTitle.traces'),
  component: DemoTraces,
})

const layout = getRouteApi('/_demobanco')

/** "Rastreos": the trace requests this visitor's session opened in the sandbox's tracing service (the bank's side of a trace). */
function DemoTraces() {
  const { traces } = layout.useLoaderData({ structuralSharing: true })
  return <DemoTracesView traces={traces} />
}
