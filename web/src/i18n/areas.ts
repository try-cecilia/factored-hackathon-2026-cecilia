import type { Locale } from './locales.ts'
import type { Dictionary } from './translate.ts'
import type { Messages } from './types.ts'

type Namespace = keyof Messages

/**
 * The texts are split by area and by language: a page downloads the namespaces its area uses (its own and the kit's), in its
 * language, and never the others'. The root loader resolves them (`routes/__root.tsx`), so the server's HTML and the hydration
 * use the very same dictionary. A new namespace goes in the list of every area whose screens use it: `areas.test.ts` follows the
 * imports of each area's routes and fails on a key outside them.
 */
export type Area = 'customer' | 'operator' | 'monitor' | 'gallery'

export const areaNamespaces: Record<Area, readonly Namespace[]> = {
  customer: ['common', 'shell', 'home', 'login', 'loaders', 'sidebar', 'chat', 'cases', 'conversation', 'demo'],
  operator: ['common', 'loaders', 'sidebar', 'table', 'operator'],
  // Only the monitor and the traces, inside the console: the operator's own texts come with the operator area.
  monitor: ['monitor'],
  // The gallery draws the whole kit in both languages with the full dictionaries of its own chunk (`ui/gallery/GalleryPage.tsx`).
  gallery: ['common', 'gallery'],
}

/** The areas a page needs, from its path. */
export function areasOf(pathname: string): Area[] {
  if (/^\/dev\/ui(\/|$)/.test(pathname)) return ['gallery']
  if (/^\/operador\/(monitoreo|trazas)(\/|$)/.test(pathname)) return ['operator', 'monitor']
  if (/^\/operador(\/|$)/.test(pathname)) return ['operator']
  return ['customer']
}

/** Whether what is loaded already has every area a page needs (a page of fewer areas keeps the loaded ones). */
export function covers(loaded: readonly Area[] | undefined, needed: readonly Area[]): boolean {
  return !!loaded && needed.every((area) => loaded.includes(area))
}

type Sources = { [N in Namespace]: () => Promise<Messages[N]> }

// One chunk per namespace and language, fetched only when a page of its area opens in that language.
const sources: Record<Locale, Sources> = {
  es: {
    common: () => import('./dict/es/common.ts').then((m) => m.common),
    shell: () => import('./dict/es/shell.ts').then((m) => m.shell),
    home: () => import('./dict/es/auth.ts').then((m) => m.home),
    login: () => import('./dict/es/auth.ts').then((m) => m.login),
    gallery: () => import('./dict/es/gallery.ts').then((m) => m.gallery),
    loaders: () => import('./dict/es/loaders.ts').then((m) => m.loaders),
    sidebar: () => import('./dict/es/sidebar.ts').then((m) => m.sidebar),
    table: () => import('./dict/es/table.ts').then((m) => m.table),
    chat: () => import('./dict/es/chat.ts').then((m) => m.chat),
    cases: () => import('./dict/es/cases.ts').then((m) => m.cases),
    conversation: () => import('./dict/es/conversation.ts').then((m) => m.conversation),
    demo: () => import('./dict/es/demo.ts').then((m) => m.demo),
    operator: () => import('./dict/es/operator.ts').then((m) => m.operator),
    monitor: () => import('./dict/es/monitor.ts').then((m) => m.monitor),
  },
  pt: {
    common: () => import('./dict/pt/common.ts').then((m) => m.common),
    shell: () => import('./dict/pt/shell.ts').then((m) => m.shell),
    home: () => import('./dict/pt/auth.ts').then((m) => m.home),
    login: () => import('./dict/pt/auth.ts').then((m) => m.login),
    gallery: () => import('./dict/pt/gallery.ts').then((m) => m.gallery),
    loaders: () => import('./dict/pt/loaders.ts').then((m) => m.loaders),
    sidebar: () => import('./dict/pt/sidebar.ts').then((m) => m.sidebar),
    table: () => import('./dict/pt/table.ts').then((m) => m.table),
    chat: () => import('./dict/pt/chat.ts').then((m) => m.chat),
    cases: () => import('./dict/pt/cases.ts').then((m) => m.cases),
    conversation: () => import('./dict/pt/conversation.ts').then((m) => m.conversation),
    demo: () => import('./dict/pt/demo.ts').then((m) => m.demo),
    operator: () => import('./dict/pt/operator.ts').then((m) => m.operator),
    monitor: () => import('./dict/pt/monitor.ts').then((m) => m.monitor),
  },
}

/**
 * What the demo panel's bank view reads beyond the customer area: the console's texts (`table` for the priority, `operator` for the
 * codes of a ticket). The panel asks for them when it is drawn, only in the demo; the customer's page never carries them.
 */
export const demoPanelNamespaces = ['table', 'operator'] as const satisfies readonly Namespace[]

/** Some namespaces by name, in a language: for what a page needs beyond its areas (the demo panel's bank view reads the console's texts). */
export async function loadNamespaces(wanted: readonly Namespace[], locale: Locale): Promise<Dictionary> {
  const texts = await Promise.all(wanted.map((namespace) => sources[locale][namespace]()))
  return Object.fromEntries(wanted.map((namespace, i) => [namespace, texts[i]]))
}

export async function loadMessages(areas: readonly Area[], locale: Locale): Promise<Dictionary> {
  return loadNamespaces([...new Set(areas.flatMap((area) => areaNamespaces[area]))], locale)
}
