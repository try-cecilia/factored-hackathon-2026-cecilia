import { createContext, use } from 'react'

export type ShellContextValue = {
  /** Brings a case into view: opens the sidebar (the drawer on a phone, the wide panel from the rail) and puts the focus on its row. */
  showCase: (ticketId: string) => void
}

const ShellContext = createContext<ShellContextValue>({ showCase: () => {} })

export const ShellProvider = ShellContext.Provider
export const useShell = (): ShellContextValue => use(ShellContext)
