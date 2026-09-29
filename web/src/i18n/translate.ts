import type { Locale } from './locales.ts'
import { es } from './es.ts'
import { pt } from './pt.ts'
import type { Messages } from './types.ts'

const dictionaries: Record<Locale, Messages> = { es, pt }

/** Dotted path of every string in the dictionary: `common.close`, `loaders.thinking.label`... */
type Path<T, Prefix extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Path<T[K], `${Prefix}${K}.`>
}[keyof T & string]

export type MessageKey = Path<Messages>
export type Params = Record<string, string | number>
export type Translate = (key: MessageKey, params?: Params) => string

export function lookup(locale: Locale, key: string): string | undefined {
  let node: unknown = dictionaries[locale]
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

export function translate(locale: Locale, key: MessageKey, params?: Params): string {
  return format(lookup(locale, key) ?? lookup('es', key) ?? key, params)
}

export function translator(locale: Locale): Translate {
  return (key, params) => translate(locale, key, params)
}
