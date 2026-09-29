import { createFileRoute } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { Empty } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/trazas/')({
  component: NoTrace,
})

function NoTrace() {
  const t = useT()
  return <Empty title={t('monitor.traces.chooseTitle')}>{t('monitor.traces.chooseBody')}</Empty>
}
