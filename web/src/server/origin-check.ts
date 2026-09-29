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

// One entry of WEB_PUBLIC_ORIGIN must already BE an origin as written: http(s), a host, an optional port. Checked on the text
// before anything is normalized, because normalizing first would quietly turn `https://trusted.example@attacker.invalid` into
// `https://attacker.invalid`, or drop a path or a query. A single trailing slash is the empty path and is accepted.
const PURE_ORIGIN = /^https?:\/\/[^\s/?#@*\\%]+$/i

/**
 * The exact origins a WEB_PUBLIC_ORIGIN value lists, or null unless EVERY entry is a pure origin (no wildcard, userinfo, path,
 * query, fragment or blank entry) and all share a scheme. One bad entry invalidates the whole value, so a typo refuses everything instead of opening something.
 */
export function publicOrigins(value: string | undefined): string[] | null {
  if (!value?.trim()) return null
  const origins: string[] = []
  for (const part of value.split(',')) {
    const entry = part.trim().replace(/\/$/, '')
    if (!PURE_ORIGIN.test(entry)) return null
    const origin = originOf(entry)
    if (origin === null) return null
    origins.push(origin)
  }
  // The origins share one scheme: the session cookies are Secure or not for the whole console (cookie-policy.ts), so a list that
  // mixes http and https would give a plain cookie to the https login, or a Secure one that the http origin never stores.
  return origins.every((origin) => origin.startsWith(origins[0].slice(0, origins[0].indexOf(':') + 1))) ? origins : null
}

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
