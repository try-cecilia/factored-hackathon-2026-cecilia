import { createContext, use } from 'react'
import type { CopyState } from '../chat/CopyConversation'

export type ShellContextValue = {
  /** Brings a case into view: opens the sidebar (the drawer on a phone, the wide panel from the rail) and puts the focus on its row. */
  showCase: (ticketId: string) => void
  /** How the last "copy conversation" went (the bar's and the demo panel's button share it): the chat says it by its composer. */
  copied?: CopyState
}

const ShellContext = createContext<ShellContextValue>({ showCase: () => {} })

export const ShellProvider = ShellContext.Provider
export const useShell = (): ShellContextValue => use(ShellContext)
