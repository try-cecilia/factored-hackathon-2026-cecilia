import { translate, type Dictionary, type MessageKey, type Params } from './translate.ts'

/** For a route's `head()`: a title from the texts the root loader resolved for the page, in its language. */
export function headTitle(matches: ReadonlyArray<{ routeId: string; loaderData?: unknown }>, key: MessageKey, params?: Params) {
  const root = matches.find((match) => match.routeId === '__root__')?.loaderData as { messages?: Dictionary } | undefined
  return { meta: [{ title: translate(root?.messages ?? {}, key, params) }] }
}
