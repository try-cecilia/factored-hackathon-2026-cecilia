import { createFileRoute } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { Empty } from '../-operator/ui'

export const Route = createFileRoute('/_demobanco/demo/banco/')({
  component: NoTicket,
})

function NoTicket() {
  const t = useT()
  return <Empty title={t('demoMode.desk.choose.title')}>{t('demoMode.desk.choose.body')}</Empty>
}
