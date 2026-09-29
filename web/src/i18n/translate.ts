import type { Messages } from './types.ts'

/** Dotted path of every string in the dictionary: `common.close`, `loaders.thinking.label`... */
type Path<T, Prefix extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Path<T[K], `${Prefix}${K}.`>
}[keyof T & string]

export type MessageKey = Path<Messages>
export type Params = Record<string, string | number>
export type Translate = (key: MessageKey, params?: Params) => string

/** The texts a page has: the namespaces of its areas (`areas.ts`), in its language. */
export type Dictionary = Partial<Messages>

export function lookup(messages: Dictionary, key: string): string | undefined {
  let node: unknown = messages
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return undefined
    node = (node as Record<string, unknown>)[part]
  }
  return typeof node === 'string' ? node : undefined
}

/** `{name}` placeholders are replaced; a missing param stays visible instead of turning into "undefined". */
export function format(template: string, params?: Params): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole))
}

/** A key outside the loaded areas comes out as the key itself: visible, and caught by `areas.test.ts`. */
export function translate(messages: Dictionary, key: MessageKey, params?: Params): string {
  return format(lookup(messages, key) ?? key, params)
}

export function translator(messages: Dictionary): Translate {
  return (key, params) => translate(messages, key, params)
}
