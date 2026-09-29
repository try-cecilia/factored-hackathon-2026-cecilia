import { createContext, use } from 'react'

export type SidebarVariant = 'client' | 'operator'

export type SidebarContextValue = {
  variant: SidebarVariant
  collapsed: boolean
  /** Present when the parent handles collapsing; the brand shows the toggle only then. */
  toggle?: () => void
}

const SidebarContext = createContext<SidebarContextValue>({ variant: 'client', collapsed: false })

export const SidebarProvider = SidebarContext.Provider

/** Rows, sections and the footer adapt to the sidebar they sit in. Outside one they draw as the expanded client sidebar. */
export const useSidebar = (): SidebarContextValue => use(SidebarContext)
