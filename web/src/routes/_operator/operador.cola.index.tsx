import { createFileRoute } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { Empty } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/cola/')({
  component: NoTicket,
})

function NoTicket() {
  const t = useT()
  return <Empty title={t('operator.ticket.chooseTitle')}>{t('operator.ticket.chooseBody')}</Empty>
}
