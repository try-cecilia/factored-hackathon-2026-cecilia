// The exact origins a WEB_PUBLIC_ORIGIN value lists. One parser for both readers of that setting: the origin check on form
// posts (src/server/origin-check.ts) and the production server's HSTS decision (serve.mjs, which cannot import the app's
// TypeScript, so this is plain JavaScript beside it and the image copies it with serve.mjs).

// One entry must already BE an origin as written: http(s), an ASCII host and an optional port. Checked on the text before
// anything is normalized, because normalizing first would quietly turn `https://trusted.example@attacker.invalid` into
// `https://attacker.invalid`, drop a path or a query, or map a Unicode look-alike (a fullwidth asterisk U+FF0A, an ideographic
// full stop) onto `*` or `.`. An internationalized host is written in punycode (xn--...). A single trailing slash is the empty
// path and is accepted.
const LABEL = '[a-z0-9](?:[a-z0-9-]*[a-z0-9])?'
const PURE_ORIGIN = new RegExp(`^(https?)://(${LABEL}(?:\\.${LABEL})*|\\[[0-9a-f:.]+\\])(?::([0-9]{1,5}))?$`, 'i')

/**
 * The exact origins a WEB_PUBLIC_ORIGIN value lists, or null unless EVERY entry is a pure origin (no wildcard, userinfo, path,
 * query, fragment or blank entry) and all share a scheme. One bad entry invalidates the whole value, so a typo refuses everything
 * instead of opening something.
 * @param {string | undefined} value
 * @returns {string[] | null}
 */
export function publicOrigins(value) {
  if (!value?.trim()) return null
  const origins = []
  for (const part of value.split(',')) {
    const entry = part.trim().replace(/\/$/, '')
    const match = PURE_ORIGIN.exec(entry)
    if (!match) return null
    // The parser must agree with the text: the host it reports is the host that was written (an odd IPv4 form or an IDNA mapping is not).
    let url
    try {
      url = new URL(entry)
    } catch {
      return null
    }
    if (url.hostname !== match[2].toLowerCase() || url.username || url.password || url.search || url.hash) return null
    origins.push(url.origin)
  }
  // The origins share one scheme: the session cookies are Secure or not for the whole console (cookie-policy.ts), so a list that
  // mixes http and https would give a plain cookie to the https login, or a Secure one that the http origin never stores.
  return origins.every((origin) => origin.startsWith(origins[0].slice(0, origins[0].indexOf(':') + 1))) ? origins : null
}
