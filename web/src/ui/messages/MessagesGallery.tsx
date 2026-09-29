import { useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Group } from '../gallery/Section'
import { ActionResultMessage } from './ActionResultMessage'
import { AnswerMessage } from './AnswerMessage'
import { ClarifyMessage } from './ClarifyMessage'
import { ConfirmTraceMessage, type ConfirmTraceState } from './ConfirmTraceMessage'
import { CouldNotVerifyMessage } from './CouldNotVerifyMessage'
import { DataInAnswer } from './DataInAnswer'
import { DeclineMessage } from './DeclineMessage'
import { HandoffMessage } from './HandoffMessage'
import { LimitedModeBanner } from './LimitedModeBanner'
import { MessageList } from './MessageList'
import { SignInAgainMessage } from './SignInAgainMessage'
import { SystemDivider, SystemNote } from './SystemNote'
import { UserMessage } from './UserMessage'
import './MessagesGallery.css'

/** A titled block as in Paper: title, one line of what it is for, then the messages at 600px. */
function Block({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  return (
    <Group title={title}>
      <p className="gal__caption">{lead}</p>
      <div className="gal-msg__stage">{children}</div>
    </Group>
  )
}

function State({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="gal-msg__state">
      <span className="gal__caption">{caption}</span>
      {children}
    </div>
  )
}

const noop = () => {}

export function MessagesGallery() {
  const t = useT()
  const [picked, setPicked] = useState<string | undefined>()
  const confirmStates: { state: ConfirmTraceState; caption: string }[] = [
    { state: 'idle', caption: t('chat.sample.confirm.idle') },
    { state: 'loading', caption: t('chat.sample.confirm.loading') },
    { state: 'sent', caption: t('chat.sample.confirm.sent') },
    { state: 'declined', caption: t('chat.sample.confirm.declined') },
  ]
  const explanation = [
    { label: t('chat.sample.answer.sourceLabel'), value: t('chat.sample.answer.sourceValue') },
    { label: t('chat.sample.answer.accountLabel'), value: t('chat.sample.answer.accountValue') },
    { label: t('chat.sample.answer.checkedLabel'), value: t('chat.sample.answer.checkedValue') },
  ]
  const clarifyOptions = [
    { value: 'checking', label: t('chat.sample.clarify.checking') },
    { value: 'savings', label: t('chat.sample.clarify.savings') },
    { value: 'card', label: t('chat.sample.clarify.card') },
  ]
  const rows = [
    { leading: t('chat.sample.data.rows.first.date'), label: t('chat.sample.data.rows.first.label'), value: t('chat.sample.data.rows.first.value') },
    { leading: t('chat.sample.data.rows.second.date'), label: t('chat.sample.data.rows.second.label'), value: t('chat.sample.data.rows.second.value') },
    { leading: t('chat.sample.data.rows.third.date'), label: t('chat.sample.data.rows.third.label'), value: t('chat.sample.data.rows.third.value') },
  ]
  const balances = [
    { label: t('chat.sample.data.checking'), value: '$4.286,12' },
    { label: t('chat.sample.data.savings'), value: '$12.940,00' },
  ]
  const declineSuggestions = [
    { value: 'balance', label: t('chat.sample.decline.balance') },
    { value: 'recent', label: t('chat.sample.decline.recent') },
  ]
  const item = {
    title: t('chat.sample.confirm.itemTitle'),
    amount: t('chat.sample.confirm.itemAmount'),
    detail: t('chat.sample.confirm.itemDetail'),
  }

  return (
    <div className="gal-msg">
      <Block title={t('chat.sample.user.title')} lead={t('chat.sample.user.lead')}>
        <State caption={t('chat.sample.user.rest')}>
          <UserMessage time={t('chat.sample.time')}>{t('chat.sample.user.text')}</UserMessage>
        </State>
        <State caption={t('chat.sample.user.hover')}>
          <UserMessage time={t('chat.sample.time')} forceState="hover">{t('chat.sample.user.text')}</UserMessage>
        </State>
      </Block>

      <Block title={t('chat.sample.answer.title')} lead={t('chat.sample.answer.lead')}>
        <State caption={t('chat.sample.answer.closed')}>
          <AnswerMessage time={t('chat.sample.time')} explanation={explanation} onCopy={noop}>{t('chat.sample.answer.text')}</AnswerMessage>
        </State>
        <State caption={t('chat.sample.answer.open')}>
          <AnswerMessage time={t('chat.sample.time')} explanation={explanation} defaultExplanationOpen onCopy={noop}>{t('chat.sample.answer.text')}</AnswerMessage>
        </State>
      </Block>

      <Block title={t('chat.sample.clarify.title')} lead={t('chat.sample.clarify.lead')}>
        <State caption={t('chat.sample.clarify.states')}>
          <ClarifyMessage
            time={t('chat.sample.clarify.time')}
            options={[
              { ...clarifyOptions[0], forceState: 'hover' },
              { ...clarifyOptions[1], forceState: 'focus' },
              clarifyOptions[2],
            ]}
            onSelect={noop}
          >
            {t('chat.sample.clarify.text')}
          </ClarifyMessage>
        </State>
        <ClarifyMessage time={t('chat.sample.clarify.time')} options={clarifyOptions} selectedValue={picked} onSelect={setPicked}>
          {t('chat.sample.clarify.text')}
        </ClarifyMessage>
      </Block>

      <Block title={t('chat.sample.decline.title')} lead={t('chat.sample.decline.lead')}>
        <DeclineMessage time={t('chat.sample.decline.time')} suggestions={declineSuggestions} onSelect={noop}>{t('chat.sample.decline.text')}</DeclineMessage>
      </Block>

      <Block title={t('chat.sample.handoff.title')} lead={t('chat.sample.handoff.lead')}>
        <HandoffMessage
          time={t('chat.sample.handoff.time')}
          title={t('chat.sample.handoff.caseTitle')}
          status={t('chat.sample.handoff.status')}
          caseId="4f21a9"
          onViewCase={noop}
        >
          {t('chat.sample.handoff.text')}
        </HandoffMessage>
      </Block>

      <Block title={t('chat.sample.signIn.title')} lead={t('chat.sample.signIn.lead')}>
        <SignInAgainMessage time={t('chat.sample.signIn.time')} onSignIn={noop}>{t('chat.sample.signIn.text')}</SignInAgainMessage>
        <State caption={t('chat.sample.signIn.loading')}>
          <SignInAgainMessage time={t('chat.sample.signIn.time')} onSignIn={noop} loading>{t('chat.sample.signIn.text')}</SignInAgainMessage>
        </State>
      </Block>

      <Block title={t('chat.sample.confirm.title')} lead={t('chat.sample.confirm.lead')}>
        {confirmStates.map(({ state, caption }) => (
          <State key={state} caption={caption}>
            <ConfirmTraceMessage time={t('chat.sample.confirm.time')} item={item} state={state} onConfirm={noop} onDecline={noop}>
              {t('chat.sample.confirm.text')}
            </ConfirmTraceMessage>
          </State>
        ))}
      </Block>

      <Block title={t('chat.sample.actionResult.title')} lead={t('chat.sample.actionResult.lead')}>
        <State caption={t('chat.sample.actionResult.ok')}>
          <ActionResultMessage status="ok" reference={t('chat.sample.actionResult.reference')} time={t('chat.sample.actionResult.time')}>
            {t('chat.sample.actionResult.okDetail')}
          </ActionResultMessage>
        </State>
        <State caption={t('chat.sample.actionResult.failed')}>
          <ActionResultMessage status="failed" time={t('chat.sample.actionResult.time')}>{t('chat.sample.actionResult.failedDetail')}</ActionResultMessage>
        </State>
      </Block>

      <Block title={t('chat.sample.limited.title')} lead={t('chat.sample.limited.lead')}>
        <LimitedModeBanner>{t('chat.sample.limited.banner')}</LimitedModeBanner>
        <AnswerMessage time={t('chat.sample.limited.time')}>{t('chat.sample.limited.text')}</AnswerMessage>
      </Block>

      <Block title={t('chat.sample.couldNotVerify.title')} lead={t('chat.sample.couldNotVerify.lead')}>
        <CouldNotVerifyMessage time={t('chat.sample.couldNotVerify.time')} onRetry={noop}>{t('chat.sample.couldNotVerify.text')}</CouldNotVerifyMessage>
        <State caption={t('chat.sample.couldNotVerify.retrying')}>
          <CouldNotVerifyMessage time={t('chat.sample.couldNotVerify.time')} onRetry={noop} retrying>{t('chat.sample.couldNotVerify.text')}</CouldNotVerifyMessage>
        </State>
      </Block>

      <Block title={t('chat.sample.system.title')} lead={t('chat.sample.system.lead')}>
        <SystemDivider>{t('chat.sample.system.today')}</SystemDivider>
        <SystemNote tone="info" time={t('chat.sample.system.pickedTime')}>{t('chat.sample.system.picked')}</SystemNote>
        <SystemNote tone="success" time={t('chat.sample.system.traceTime')}>{t('chat.sample.system.trace')}</SystemNote>
        <SystemNote tone="neutral" time={t('chat.sample.system.signedInTime')}>{t('chat.sample.system.signedIn')}</SystemNote>
        <SystemNote>{t('chat.sample.system.expiring')}</SystemNote>
        <SystemNote>{t('chat.sample.system.reset')}</SystemNote>
      </Block>

      <Block title={t('chat.sample.data.title')} lead={t('chat.sample.data.lead')}>
        <AnswerMessage time={t('chat.sample.time')} data={<DataInAnswer label={t('chat.sample.data.label')} rows={rows} />}>
          {t('chat.sample.data.text')}
        </AnswerMessage>
        <State caption={t('chat.sample.data.balances')}>
          <DataInAnswer label={t('chat.sample.data.balances')} rows={balances} />
        </State>
      </Block>

      <Block title={t('chat.sample.list.title')} lead={t('chat.sample.list.lead')}>
        <MessageList>
          <SystemDivider>{t('chat.sample.system.today')}</SystemDivider>
          <UserMessage time={t('chat.sample.time')}>{t('chat.sample.user.text')}</UserMessage>
          <AnswerMessage time={t('chat.sample.time')} explanation={explanation} onCopy={noop}>{t('chat.sample.answer.text')}</AnswerMessage>
          <SystemNote tone="success" time={t('chat.sample.system.traceTime')}>{t('chat.sample.system.trace')}</SystemNote>
        </MessageList>
      </Block>
    </div>
  )
}
