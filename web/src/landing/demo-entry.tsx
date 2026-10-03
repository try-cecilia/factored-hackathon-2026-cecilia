import { createContext, use } from 'react'
import { demoEntry, signInEntry } from './links'

// Whether the one-click demo is on for this page (getDemoKit with console: true and test customers to offer). Off by default:
// without it, "Probar la demo" stays the sign-in.
const DemoEntryContext = createContext(false)

export const DemoEntryProvider = DemoEntryContext.Provider

/** Where "Probar la demo" goes: the one-click entry's dialog with the demo console on, the sign-in otherwise. */
export function useDemoEntry(): typeof demoEntry | typeof signInEntry {
  return use(DemoEntryContext) ? demoEntry : signInEntry
}
