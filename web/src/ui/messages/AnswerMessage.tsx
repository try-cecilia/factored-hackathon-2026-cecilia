import { useId, useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { IconButton } from '../Button'
import { CopyIcon } from '../icons'
import { InfoCircleIcon } from './icons'
import { AssistantFrame, AssistantText } from './MessageFrame'
import './AnswerMessage.css'

/** One verified fact behind the answer: the label and the value both come from the data, already in the customer's language. */
export type ExplanationRow = { label: string; value: string }

export type AnswerMessageProps = {
  /** The answer text (or paragraphs). Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** Data block under the text, e.g. <DataInAnswer />. */
  data?: ReactNode
  /** What "¿Por qué?" reveals. Without rows there is no disclosure. */
  explanation?: ExplanationRow[]
  defaultExplanationOpen?: boolean
  /** Shows the copy button. Copying is up to the caller. */
  onCopy?: () => void
  className?: string
}

/** Resolved answer: open text plus the "Why?" disclosure that shows the verified data behind it. */
export function AnswerMessage({ children, time, dateTime, data, explanation, defaultExplanationOpen = false, onCopy, className }: AnswerMessageProps) {
  const t = useT()
  const panelId = useId()
  const [open, setOpen] = useState(defaultExplanationOpen)
  const hasWhy = explanation !== undefined && explanation.length > 0
  return (
    <AssistantFrame time={time} dateTime={dateTime} tight={!data} className={className}>
      <AssistantText>{children}</AssistantText>
      {data}
      {(hasWhy || onCopy) && (
        <div className="ui-answer__actions">
          {hasWhy && (
            <button type="button" className="ui-answer__why" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((value) => !value)}>
              <InfoCircleIcon />
              <span>{t('chat.answer.why')}</span>
            </button>
          )}
          {onCopy && <IconButton className="ui-answer__copy" variant="ghost" size="xs" label={t('chat.answer.copy')} icon={<CopyIcon size={13} />} onClick={onCopy} />}
        </div>
      )}
      {hasWhy && (
        <dl id={panelId} className="ui-answer__panel" hidden={!open} aria-label={t('chat.answer.whyPanel')}>
          {explanation.map((row) => (
            <div key={row.label} className="ui-answer__fact">
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </AssistantFrame>
  )
}
