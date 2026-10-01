// The conversation as plain text for the clipboard: what the customer sees on screen, in order, and nothing the screen does not show.
// Pure, so it is tested without a DOM. Internal data of a reply (trace id, disposition, scores, the "why") is never read here.
import { htmlLang, type Locale } from '../i18n/locales.ts'
import type { Translate } from '../i18n/translate.ts'
import { caseCategoryKey, caseStatusText, classifyReply, proposalState, splitCaseNews, type Entry } from './conversation.ts'
import type { CaseRow } from './ConversationProvider.tsx'
import { toBlocks } from './format.ts'

export type TranscriptOptions = {
  locale: Locale
  t: Translate
  /** The cases the handoff messages read their status from. */
  cases: readonly CaseRow[]
  /** The zone the hours are told in; the browser's own when absent. */
  timeZone?: string
}

type Message = Exclude<Entry, { role: 'note' }>

const messagesOf = (entries: readonly Entry[]): Message[] => entries.filter((e): e is Message => e.role !== 'note')

/** There is something to copy: at least one message of the customer or of Cecilia (the "conversation resumed" note is not one). */
export const hasMessages = (entries: readonly Entry[]): boolean => messagesOf(entries).length > 0

/** The API's text as the screen draws it: paragraphs as lines, dash lists as dash lines. */
function lines(text: string): string[] {
  return toBlocks(text).flatMap((block) => (block.type === 'ul' ? block.items.map((item) => `- ${item}`) : [block.text]))
}

/**
 * What a reply says on screen, line by line: the case news above it, its text, and what its card adds (the options of a question,
 * the title of an opened trace, the outcome of a proposal, the case and where it stands). Buttons (yes, no, retry, view the case,
 * the suggestions of a refusal) are not text of the conversation and are left out.
 */
function assistantLines(entries: readonly Entry[], index: number, { t, cases }: Pick<TranscriptOptions, 't' | 'cases'>): string[] {
  const entry = entries[index]
  if (entry.role !== 'assistant') return []
  const { reply } = entry
  const kind = classifyReply(reply, entries.slice(0, index))
  const { news, body } = splitCaseNews(reply.response_text)
  const out = [...news]
  switch (kind.kind) {
    case 'clarify':
      if (kind.options) out.push(...lines(kind.options.lead), ...kind.options.options.map((option) => `- ${option}`), ...lines(kind.options.tail))
      else out.push(...lines(body))
      break
    case 'actionResult':
      out.push(t('chat.actionResult.okTitle'), ...lines(body))
      break
    case 'confirmTrace': {
      out.push(...lines(body))
      const state = proposalState(entries, index, false)
      if (state === 'sent') out.push(t('chat.confirm.sent'))
      if (state === 'declined') out.push(t('chat.confirm.declined'))
      break
    }
    case 'handoff': {
      const row = cases.find((c) => c.ref.ticketId === kind.ticketId)
      const title = t(`cases.category.${caseCategoryKey(kind.category)}` as 'cases.category.other')
      out.push(...lines(body), `${title} · ${caseStatusText(t, row)} · #${kind.ticketId}`)
      break
    }
    default:
      out.push(...lines(body))
  }
  return out
}

/**
 * The text the "copy conversation" button puts on the clipboard:
 *
 *     Conversación con Cecilia · 01/10/2026
 *     [15:38] Tú: ¿Cuál es mi saldo?
 *     [15:38] Cecilia: Tu saldo es 10 USD.
 *
 * The date is the one of the first message; the hours are in the same format as the ones on screen. An empty conversation is "".
 */
export function conversationTranscript(entries: readonly Entry[], { locale, t, cases, timeZone }: TranscriptOptions): string {
  const shown = messagesOf(entries)
  if (shown.length === 0) return ''
  const hour = new Intl.DateTimeFormat(htmlLang[locale], { hour: '2-digit', minute: '2-digit', timeZone })
  const day = new Intl.DateTimeFormat(htmlLang[locale], { day: '2-digit', month: '2-digit', year: 'numeric', timeZone })
  const out = [`${t('conversation.copy.title')} · ${day.format(shown[0].at)}`]
  entries.forEach((entry, index) => {
    if (entry.role === 'note') return
    // What the customer typed goes as typed.
    const body = entry.role === 'user' ? entry.text.trim().split('\n') : assistantLines(entries, index, { t, cases })
    if (body.join('') === '') return
    const who = entry.role === 'user' ? t('chat.you') : t('chat.assistant')
    const head = `[${hour.format(entry.at)}] ${who}:`
    // A reply that opens with a list keeps its heading apart: "Cecilia: - Cuenta..." reads as a dash in the middle of a sentence.
    if (entry.role === 'assistant' && body[0].startsWith('- ')) out.push(head, ...body)
    else out.push(`${head} ${body[0]}`, ...body.slice(1))
  })
  return out.join('\n')
}
