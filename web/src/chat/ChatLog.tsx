import { memo, useEffect, useState, type ReactNode } from 'react'
import { useI18n, useT } from '../i18n/context'
import {
  ActionResultMessage,
  AnswerMessage,
  AssistantFrame,
  AssistantText,
  CheckingSteps,
  ClarifyMessage,
  ConfirmTraceMessage,
  CouldNotVerifyMessage,
  DeclineMessage,
  DeliveryStatus,
  HandoffMessage,
  LimitedModeBanner,
  MessageList,
  SignInAgainMessage,
  SystemNote,
  ThinkingDots,
  UserMessage,
  type ExplanationRow,
} from '../ui'
import { Blocks } from './Blocks'
import { useTimeParts } from './clock'
import type { CaseRow } from './ConversationProvider'
import {
  caseCategoryKey,
  caseStatusText,
  chosenOption,
  classifyReply,
  deliveryDetailKey,
  deliveryOf,
  proposalState,
  splitCaseNews,
  type AssistantEntry,
  type Entry,
  type UserEntry,
} from './conversation'
import { optionAnswer } from './format'
import type { Why } from './types'

// What the customer sends when they tap a suggestion, in the language of the reply: the API reads plain Spanish and Portuguese.
const YES = { es: 'Sí', pt: 'Sim' } as const
const NO = { es: 'No', pt: 'Não' } as const

export type ChatLogProps = {
  entries: Entry[]
  cases: CaseRow[]
  /** A message is on its way. */
  sending: boolean
  /** The customer can answer: online, session alive. */
  live: boolean
  /** The session is over: the log ends with the message that asks to sign in again. */
  ended: boolean
  onSend: (text: string) => void
  onRetry: (id: number) => void
  onReload: () => void
  onViewCase: (ticketId: string) => void
  onSignIn: () => void
}

/**
 * The conversation: each entry drawn by the kit component its disposition asks for, then what is in flight, then the sign-in message
 * if the session ended. Memoized: the page around it (the session's countdown, the composer) changes without touching it.
 */
export const ChatLog = memo(function ChatLog({ entries, cases, sending, live, ended, onSend, onRetry, onReload, onViewCase, onSignIn }: ChatLogProps) {
  const t = useT()
  const timeOf = useTimeParts()
  const lastIndex = entries.reduce((last, e, i) => (e.role === 'note' ? last : i), -1)

  return (
    <MessageList className="chat-log">
      {entries.map((entry, index) => {
        if (entry.role === 'note') return <SystemNote key={entry.id}>{t('conversation.history.restored')}</SystemNote>
        if (entry.role === 'user') {
          return <UserView key={entry.id} entry={entry} time={timeOf(entry.at)} onRetry={onRetry} onReload={onReload} canRetry={live && !sending && !ended} />
        }
        return (
          <AssistantView
            key={entry.id}
            entry={entry}
            entries={entries}
            index={index}
            cases={cases}
            time={timeOf(entry.at)}
            active={index === lastIndex && live && !sending && !ended}
            sending={sending}
            onSend={onSend}
            onViewCase={onViewCase}
          />
        )
      })}
      {sending && <Working />}
      {ended && (
        <SignInAgainMessage onSignIn={onSignIn}>{t('conversation.session.reauth')}</SignInAgainMessage>
      )}
    </MessageList>
  )
})

function UserView({ entry, time, canRetry, onRetry, onReload }: {
  entry: UserEntry
  time: ReturnType<ReturnType<typeof useTimeParts>>
  canRetry: boolean
  onRetry: (id: number) => void
  onReload: () => void
}) {
  const t = useT()
  const failed = entry.delivery !== 'sent' && entry.delivery !== 'sending'
  const detail = entry.failure ? t(`conversation.delivery.${deliveryDetailKey(entry.failure)}`) : undefined
  const footer =
    entry.delivery === 'sending' ? (
      <DeliveryStatus status="sending" />
    ) : failed ? (
      <DeliveryStatus
        status={entry.delivery}
        detail={detail}
        onRetry={canRetry ? () => onRetry(entry.id) : undefined}
        onReload={entry.failure === 'answer_gone' ? undefined : onReload}
      />
    ) : undefined
  const tone = entry.delivery === 'failed' ? 'failed' : entry.delivery === 'uncertain' ? 'uncertain' : undefined
  return (
    <UserMessage time={time?.time} dateTime={time?.dateTime} footer={footer} tone={tone}>
      {entry.text}
    </UserMessage>
  )
}

function AssistantView({ entry, entries, index, cases, time, active, sending, onSend, onViewCase }: {
  entry: AssistantEntry
  entries: Entry[]
  index: number
  cases: CaseRow[]
  time: ReturnType<ReturnType<typeof useTimeParts>>
  active: boolean
  sending: boolean
  onSend: (text: string) => void
  onViewCase: (ticketId: string) => void
}) {
  const t = useT()
  const { locale } = useI18n()
  const { reply } = entry
  const lang = reply.language === 'pt' ? 'pt' : 'es'
  const kind = classifyReply(reply, entries.slice(0, index))
  const { news, body } = splitCaseNews(reply.response_text)
  const frame = { time: time?.time, dateTime: time?.dateTime }
  const text = <Blocks text={body} />

  let message: ReactNode
  switch (kind.kind) {
    case 'clarify': {
      const { options } = kind
      if (!options) {
        message = <AssistantFrame {...frame}><AssistantText>{text}</AssistantText></AssistantFrame>
        break
      }
      const chosen = chosenOption(options, (i) => optionAnswer(options, i), entries.slice(index + 1).find((e) => e.role === 'user'))
      message = (
        <ClarifyMessage
          {...frame}
          options={options.options.map((label, i) => ({ value: String(i), label }))}
          selectedValue={chosen === undefined ? undefined : String(chosen)}
          disabled={!active || sending}
          onSelect={(value) => onSend(optionAnswer(options, Number(value)))}
        >
          <Blocks text={options.lead} />
          {options.tail && <Blocks text={options.tail} />}
        </ClarifyMessage>
      )
      break
    }
    case 'confirmTrace':
      message = (
        <ConfirmTraceMessage
          {...frame}
          state={proposalState(entries, index, sending)}
          disabled={!active || sending}
          onConfirm={() => onSend(YES[lang])}
          onDecline={() => onSend(NO[lang])}
        >
          {text}
        </ConfirmTraceMessage>
      )
      break
    case 'actionResult':
      message = <ActionResultMessage {...frame} status="ok">{body}</ActionResultMessage>
      break
    case 'decline':
      message = (
        <DeclineMessage
          {...frame}
          disabled={!active || sending}
          suggestions={(['balance', 'recent', 'fx'] as const).map((key) => ({ value: key, label: t(`conversation.suggestions.${key}`) }))}
          onSelect={(key) => onSend(t(`conversation.suggestions.${key as 'balance' | 'recent' | 'fx'}`))}
        >
          {text}
        </DeclineMessage>
      )
      break
    case 'handoff': {
      const row = cases.find((c) => c.ref.ticketId === kind.ticketId)
      message = (
        <div id={`case-msg-${kind.ticketId}`} className="chat-case" tabIndex={-1}>
        <HandoffMessage
          {...frame}
          title={t(`cases.category.${caseCategoryKey(kind.category)}` as 'cases.category.other')}
          status={caseStatusText(t, row)}
          caseId={kind.ticketId}
          onViewCase={() => onViewCase(kind.ticketId)}
        >
          {text}
        </HandoffMessage>
        </div>
      )
      break
    }
    case 'couldNotVerify': {
      const previous = entries.slice(0, index).reverse().find((e) => e.role === 'user')
      message = (
        <CouldNotVerifyMessage
          {...frame}
          retrying={sending}
          onRetry={active && previous?.role === 'user' ? () => onSend(previous.text) : undefined}
        >
          {body}
        </CouldNotVerifyMessage>
      )
      break
    }
    default:
      message = (
        <AnswerMessage {...frame} explanation={reply.why ? whyRows(reply.why, t, locale) : undefined}>
          {text}
        </AnswerMessage>
      )
  }

  return (
    <>
      {news.map((line, i) => <SystemNote key={i} tone="info">{line}</SystemNote>)}
      {reply.degraded && <LimitedModeBanner>{t('conversation.limited')}</LimitedModeBanner>}
      {message}
    </>
  )
}

type Translate = ReturnType<typeof useT>

/** DEMO_MODE only: what the API says about how this reply was made. The demo texts come in Spanish and English. */
function whyRows(why: Why, t: Translate, locale: 'es' | 'pt'): ExplanationRow[] {
  const none = t('conversation.why.noLookups')
  return [
    { label: t('conversation.why.reason'), value: (locale === 'pt' ? why.because.pt : undefined) ?? why.because.es },
    { label: t('conversation.why.rule'), value: why.rule },
    { label: t('conversation.why.modelSaw'), value: why.model.called ? (why.model.saw ?? '') : t('conversation.why.noModel') },
    { label: t('conversation.why.modelChose'), value: why.model.chose.length ? why.model.chose.map((c) => `${c.tool}(${JSON.stringify(c.args)})`).join('\n') : none },
    {
      label: t('conversation.why.codeChecked'),
      value: why.checks.length ? why.checks.map((c) => `${c.ok ? '✓' : '✗'} ${c.tool}${c.product ? ` · ${c.product}` : ''} · ${c.outcome}`).join('\n') : none,
    },
    {
      label: t('conversation.why.cost'),
      value: t(why.llm_calls === 1 ? 'conversation.why.callsOne' : 'conversation.why.callsMany', { n: why.llm_calls, ms: Math.round(why.latency_ms) }),
    },
  ]
}

const SLOW_MS = 6_000

/** The wait for a reply: three dots, and after a few seconds the one step Cecilia is really on. No text arrives piece by piece. */
function Working() {
  const t = useT()
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_MS)
    return () => clearTimeout(timer)
  }, [])
  return slow ? (
    <CheckingSteps
      label={t('conversation.steps.label')}
      steps={[
        { id: 'sent', label: t('conversation.steps.sent'), status: 'done' },
        { id: 'checking', label: t('conversation.steps.checking'), status: 'active' },
      ]}
    />
  ) : (
    <ThinkingDots withAvatar />
  )
}
