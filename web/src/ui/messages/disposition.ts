// Which message component draws each outcome of a turn. Pure so the mapping is tested without a DOM.

/** The API dispositions plus REAUTH_REQUIRED, which the chat raises when the session is gone. */
export type MessageDisposition = 'AUTO_RESOLVE' | 'CLARIFY' | 'ABSTAIN' | 'ESCALATE' | 'REAUTH_REQUIRED'

export type MessageVariant = 'answer' | 'clarify' | 'decline' | 'handoff' | 'signInAgain' | 'couldNotVerify'

const VARIANTS: Record<MessageDisposition, MessageVariant> = {
  AUTO_RESOLVE: 'answer',
  CLARIFY: 'clarify',
  ABSTAIN: 'decline',
  ESCALATE: 'handoff',
  REAUTH_REQUIRED: 'signInAgain',
}

export function isMessageDisposition(value: string): value is MessageDisposition {
  return Object.hasOwn(VARIANTS, value)
}

/** A disposition this build does not know never renders as an answer: it says the reply could not be verified. */
export function variantForDisposition(disposition: string): MessageVariant {
  return isMessageDisposition(disposition) ? VARIANTS[disposition] : 'couldNotVerify'
}

/** Degraded mode is not a message: it adds the limited-mode banner above whatever the disposition draws. */
export function resolveMessage(input: { disposition: string; degraded?: boolean }): { variant: MessageVariant; limitedBanner: boolean } {
  return { variant: variantForDisposition(input.disposition), limitedBanner: input.degraded === true }
}
