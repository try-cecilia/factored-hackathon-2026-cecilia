import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Group } from '../gallery/Section'
import { Spinner } from '../Spinner'
import { CheckingSteps } from './CheckingSteps'
import { DeliveryStatus } from './DeliveryStatus'
import { PageLoader } from './PageLoader'
import { Progress, ProgressSteps } from './Progress'
import { SkeletonCard, SkeletonMessage } from './Skeleton'
import { ThinkingDots } from './ThinkingDots'
import { Toast, ToastRegion } from './Toast'
import './LoadersGallery.css'

/** Everything of Paper's "UI · Loaders", in its order, plus the states Paper does not draw (failed step, error toast). */
export function LoadersGallery() {
  const t = useT()
  return (
    <div className="gal-loaders">
      <Block title={t('loaders.sample.spinner.title')} lead={t('loaders.sample.spinner.lead')}>
        <div className="gal-loaders__row">
          <Item caption="12"><Spinner size="xs" tone="ink" /></Item>
          <Item caption="16"><Spinner size="sm" tone="ink" /></Item>
          <Item caption="20"><Spinner size="md" tone="ink" /></Item>
          <Item caption="28"><Spinner size="lg" tone="ink" /></Item>
          <span className="gal-loaders__rule" />
          <Item caption={t('loaders.sample.spinner.brand')}><Spinner size="md" tone="brand" /></Item>
          <Item caption={t('loaders.sample.spinner.onDark')}>
            <span className="gal-loaders__tile"><Spinner size="sm" tone="onDark" /></span>
          </Item>
          <span className="gal-loaders__rule" />
          <Item caption="25%"><Spinner size="md" tone="brand" value={25} label="25%" /></Item>
          <Item caption="60%"><Spinner size="md" tone="brand" value={60} label="60%" /></Item>
          <Item caption={t('loaders.sample.spinner.done')}><Spinner size="md" tone="brand" value={100} label="100%" /></Item>
        </div>
      </Block>

      <Block title={t('loaders.sample.thinking.title')} lead={t('loaders.sample.thinking.lead')}>
        <div className="gal-loaders__row">
          {([1, 2, 3] as const).map((n) => (
            <Item key={n} caption={t('loaders.sample.thinking.frame', { n })} start><ThinkingDots frame={n} /></Item>
          ))}
          <span className="gal-loaders__rule" />
          <ThinkingDots withAvatar />
        </div>
      </Block>

      <Block title={t('loaders.sample.steps.title')} lead={t('loaders.sample.steps.lead')}>
        <div className="gal-loaders__stack">
          <CheckingSteps
            steps={[
              { id: 'accounts', label: t('loaders.sample.steps.accounts'), status: 'done' },
              { id: 'reading', label: t('loaders.sample.steps.reading'), status: 'active' },
              { id: 'preparing', label: t('loaders.sample.steps.preparing'), status: 'pending' },
            ]}
          />
          <CheckingSteps
            steps={[
              { id: 'accounts', label: t('loaders.sample.steps.accounts'), status: 'done' },
              { id: 'reading', label: t('loaders.sample.steps.failed'), status: 'failed' },
            ]}
          />
        </div>
      </Block>

      <Block title={t('loaders.sample.skeleton.title')} lead={t('loaders.sample.skeleton.lead')}>
        <div className="gal-loaders__stack gal-loaders__stack--wide">
          <SkeletonMessage />
          <div className="gal-loaders__cards">
            <SkeletonCard labelWidth={90} valueWidth={120} />
            <SkeletonCard labelWidth={70} valueWidth={100} />
          </div>
        </div>
      </Block>

      <Block title={t('loaders.sample.progress.title')} lead={t('loaders.sample.progress.lead')}>
        <div className="gal-loaders__stack gal-loaders__stack--wide">
          <Progress label={t('loaders.sample.progress.opening')} value={60} />
          <Progress label={t('loaders.sample.progress.loading')} />
          <ProgressSteps
            current={1}
            steps={[
              { id: 'verify', label: t('loaders.sample.progress.verify') },
              { id: 'confirm', label: t('loaders.sample.progress.confirm') },
              { id: 'done', label: t('loaders.sample.progress.done') },
            ]}
          />
        </div>
      </Block>

      <Block title={t('loaders.sample.delivery.title')} lead={t('loaders.sample.delivery.lead')}>
        <div className="gal-loaders__stack gal-loaders__stack--end">
          <Message><DeliveryStatus status="sending" /></Message>
          <Message><DeliveryStatus status="sent" time={t('loaders.sample.delivery.time')} /></Message>
          <Message failed><DeliveryStatus status="failed" onRetry={() => {}} /></Message>
        </div>
      </Block>

      <Block title={t('loaders.sample.page.title')} lead={t('loaders.sample.page.lead')}>
        <div className="gal-loaders__row gal-loaders__row--top">
          <PageLoader className="gal-loaders__page" label={t('loaders.sample.page.signingIn')} />
          <ToastRegion floating={false}>
            <Toast variant="loading">{t('loaders.sample.page.updating')}</Toast>
            <Toast variant="success">{t('loaders.sample.page.updated')}</Toast>
            <Toast variant="error" action={{ label: t('loaders.sample.page.retryAction'), onClick: () => {} }} onClose={() => {}}>
              {t('loaders.sample.page.failed')}
            </Toast>
          </ToastRegion>
        </div>
      </Block>
    </div>
  )
}

function Block({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  return (
    <Group title={title}>
      <p className="gal__caption">{lead}</p>
      {children}
    </Group>
  )
}

function Item({ caption, start, children }: { caption: string; start?: boolean; children: ReactNode }) {
  return (
    <div className={start ? 'gal-loaders__item gal-loaders__item--start' : 'gal-loaders__item'}>
      {children}
      <span className="gal-loaders__cap">{caption}</span>
    </div>
  )
}

/** The customer's bubble, drawn here only to give the delivery line its context. */
function Message({ failed, children }: { failed?: boolean; children: ReactNode }) {
  const t = useT()
  return (
    <div className="gal-loaders__message">
      <p className={failed ? 'gal-loaders__bubble gal-loaders__bubble--failed' : 'gal-loaders__bubble'}>{t('loaders.sample.delivery.message')}</p>
      {children}
    </div>
  )
}
