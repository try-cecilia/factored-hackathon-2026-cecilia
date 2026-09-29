// Is this post from a page of ours? The operator forms are plain HTML posts, so nothing else vouches for them, and a
// login is exactly what a hostile page would want to force on a visitor (log the victim into the attacker's session).
// SameSite=Strict on the cookies does not help there: a login has no cookie yet.
//
// "Ours" is one origin, scheme + host + port, taken from configuration, because behind a TLS-terminating proxy the
// request URL says http while the browser is on https, and a proxy header is only as trustworthy as the proxy:
//  - production: WEB_PUBLIC_ORIGIN is required (for example https://console.bank.example). Without it, or with a value that
//    is not an http(s) origin, every form post is refused and the server logs why.
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

export function originConfigFromEnv(env: Record<string, string | undefined> = process.env): OriginConfig {
  return { production: env.NODE_ENV === 'production', publicOrigin: env.WEB_PUBLIC_ORIGIN }
}

export function checkOrigin(request: Request, config: OriginConfig): OriginVerdict {
  const configured = config.publicOrigin?.trim()
  let ours: string | null
  if (configured) ours = originOf(configured)
  else ours = config.production ? null : originOf(request.url)
  if (ours === null) return { ok: false, reason: 'misconfigured' }

  const headers = request.headers
  const site = headers.get('sec-fetch-site')
  if (site !== null && site !== 'same-origin') return { ok: false, reason: 'cross-site' }

  const origin = headers.get('origin')
  if (origin !== null) return origin === ours || originOf(origin) === ours ? { ok: true } : { ok: false, reason: 'cross-site' }
  const referer = headers.get('referer')
  if (referer !== null) return originOf(referer) === ours ? { ok: true } : { ok: false, reason: 'cross-site' }
  return site === 'same-origin' ? { ok: true } : { ok: false, reason: 'cross-site' }
}
