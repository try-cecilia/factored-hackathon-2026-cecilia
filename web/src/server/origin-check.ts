// Is this post from a page of ours? The operator forms are plain HTML posts, so nothing else vouches for them, and a
// login is exactly what a hostile page would want to force on a visitor (log the victim into the attacker's session).
// SameSite=Strict on the cookies does not help there: a login has no cookie yet.
//
// "Ours" is an origin, scheme + host + port, taken from configuration, because behind a TLS-terminating proxy the
// request URL says http while the browser is on https, and a proxy header is only as trustworthy as the proxy:
//  - production: WEB_PUBLIC_ORIGIN is required (for example https://console.bank.example). Without it, or with a value that
//    is not an http(s) origin, every form post is refused and the server logs why.
//  - WEB_PUBLIC_ORIGIN may list several origins separated by commas, each one exact (a local run answers on both
//    http://127.0.0.1:3000 and http://localhost:3000). Every entry must be a pure origin (no wildcard, userinfo, path, query or
//    fragment): one entry that is not makes the whole value invalid, so a typo refuses everything instead of opening something.
//  - development: without WEB_PUBLIC_ORIGIN, the origin of the request URL (Vite serves http://127.0.0.1:<port>).
// X-Forwarded-* and Forwarded are never read.
//
// Rules, in order:
//  1. Fetch Metadata, when the browser sends it, must say `same-origin` (`same-site` is a sibling host, `none` is not a post).
//  2. Origin, when present, must equal our origin; else the Referer's origin must ("null" and every other origin fail).
//  3. With neither header there is no proof, so the post is refused unless Fetch Metadata already said same-origin.

import { publicOrigins } from '../../public-origins.mjs'

export { publicOrigins }

export type OriginConfig = { production: boolean; publicOrigin?: string }
export type OriginVerdict = { ok: true } | { ok: false; reason: 'cross-site' | 'misconfigured' }

const originOf = (value: string) => {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null
  } catch {
    return null
  }
}

// WEB_PUBLIC_ORIGIN is parsed by public-origins.mjs at the root of web/, shared with the production server's HSTS decision.

export function originConfigFromEnv(env: Record<string, string | undefined> = process.env): OriginConfig {
  return { production: env.NODE_ENV === 'production', publicOrigin: env.WEB_PUBLIC_ORIGIN }
}

export function checkOrigin(request: Request, config: OriginConfig): OriginVerdict {
  const configured = config.publicOrigin?.trim()
  const own = originOf(request.url)
  const ours = configured ? publicOrigins(configured) : config.production || own === null ? null : [own]
  if (ours === null) return { ok: false, reason: 'misconfigured' }

  const headers = request.headers
  const site = headers.get('sec-fetch-site')
  if (site !== null && site !== 'same-origin') return { ok: false, reason: 'cross-site' }

  const origin = headers.get('origin')
  const isOurs = (value: string | null) => value !== null && ours.includes(value)
  if (origin !== null) return isOurs(origin) || isOurs(originOf(origin)) ? { ok: true } : { ok: false, reason: 'cross-site' }
  const referer = headers.get('referer')
  if (referer !== null) return isOurs(originOf(referer)) ? { ok: true } : { ok: false, reason: 'cross-site' }
  return site === 'same-origin' ? { ok: true } : { ok: false, reason: 'cross-site' }
}
