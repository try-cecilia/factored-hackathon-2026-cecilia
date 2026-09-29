// Is this post from a page of ours? The operator forms are plain HTML posts, so nothing else vouches for them, and a
// login is exactly what a hostile page would want to force on a visitor (log the victim into the attacker's session).
// SameSite=Strict on the cookies does not help there: a login has no cookie yet.
//
// Rules, in order:
//  1. Fetch Metadata, when the browser sends it, must say `same-origin` (`same-site` is a sibling host, `none` is not a post).
//  2. Origin, when present, must be exactly our origin ("null" and every other origin fail); else Referer's origin must be.
//  3. With neither header there is no proof, so the post is refused. Every browser that can submit the form sends one.
// Our origin is the request's own host, so a proxy in front must pass the Host header through.

const ownOrigin = (requestUrl: string, headers: Headers) => {
  const url = new URL(requestUrl)
  const host = headers.get('host') ?? url.host
  return host.toLowerCase()
}

const hostOf = (value: string) => {
  try {
    return new URL(value).host.toLowerCase()
  } catch {
    return null
  }
}

export function isSameOrigin(request: Request): boolean {
  const headers = request.headers
  const site = headers.get('sec-fetch-site')
  if (site !== null && site !== 'same-origin') return false

  const host = ownOrigin(request.url, headers)
  const origin = headers.get('origin')
  if (origin !== null) return hostOf(origin) === host
  const referer = headers.get('referer')
  if (referer !== null) return hostOf(referer) === host
  return site === 'same-origin'
}
