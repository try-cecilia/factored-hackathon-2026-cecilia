import { createContext, use, type ReactNode } from 'react'
import type { CopyState } from '../chat/CopyConversation'

export type ShellContextValue = {
  /** Brings a case into view: opens the sidebar (the drawer on a phone, the wide panel from the rail) and puts the focus on its row. */
  showCase: (ticketId: string) => void
  /** How the last "copy conversation" went (the bar's and the demo panel's button share it): the chat says it by its composer. */
  copied?: CopyState
  /** The one-click demo's card to the bank's side ("Tu caso ya llegó al banco"), drawn by the chat over its composer; only in that demo. */
  bridge?: ReactNode
  /** The one-click demo's welcome, drawn by the chat in place of its own empty state (and of its suggestions); only in that demo. */
  welcome?: ReactNode
}

const ShellContext = createContext<ShellContextValue>({ showCase: () => {} })

export const ShellProvider = ShellContext.Provider
export const useShell = (): ShellContextValue => use(ShellContext)
