const BASE = 'http://cecilai.invalid'
// Control characters (tab and newline are dropped by URL parsers, which turns "/\t/host" into "//host") and backslashes
// (browsers read "\" as "/").
const FORBIDDEN = /[\u0000-\u001f\u007f\\]/

/**
 * A path on this site, normalised, or nothing: the login must never send an operator to another origin.
 * The value is decoded (up to three levels), normalised the way a browser would, and the normalised form is what
 * comes back, so `/a/..//evil.example` cannot survive as `//evil.example` in a Location header.
 * In doubt it answers nothing and the caller uses its default destination.
 */
export function sameOriginPath(value: unknown) {
  if (typeof value !== 'string' || value.length > 2000 || !value.startsWith('/') || FORBIDDEN.test(value)) return undefined
  try {
    const url = new URL(value, BASE)
    if (url.origin !== BASE) return undefined
    let seen = url.pathname
    for (let level = 0; level < 3; level++) {
      if (seen.startsWith('//') || FORBIDDEN.test(seen)) return undefined
      const decoded = decodeURIComponent(seen)
      if (decoded === seen) break
      seen = decoded
    }
    if (seen.startsWith('//') || FORBIDDEN.test(seen)) return undefined
    return url.pathname + url.search + url.hash
  } catch {
    return undefined
  }
}

// The pages behind the customer's session (src/routes/_authed): the only places a customer is sent on to after signing in.
// A path of this site that is no page ("/@host", "/nada", the operator console's) would end on a "Not Found".
export const CUSTOMER_DESTINATIONS: ReadonlySet<string> = new Set(['/chat'])

/** `sameOriginPath`, and a page the customer can open: anything else is nothing, and the caller goes to its default destination. */
export function customerDestination(value: unknown) {
  const path = sameOriginPath(value)
  if (!path) return undefined
  const { pathname, search, hash } = new URL(path, BASE)
  const page = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
  return CUSTOMER_DESTINATIONS.has(page) ? page + search + hash : undefined
}
