// Whether the session cookies are `Secure` with the `__Host-` prefix is decided by the origin the browser really sees
// (WEB_PUBLIC_ORIGIN), not by NODE_ENV: the Docker image runs in production mode, but on http://127.0.0.1 a browser like
// Safari refuses a `Secure` cookie and the login would be lost without a word.
//  - WEB_PUBLIC_ORIGIN is https: `Secure` and `__Host-` (the prefix makes the browser require Secure, Path=/ and no Domain).
//  - WEB_PUBLIC_ORIGIN is http (a local run): neither, because the browser would drop them.
//  - not set, or not an http(s) origin: production keeps `Secure` and `__Host-`; development, which has no https, does not.
// Read on every call, not once at import, so the choice follows the environment the process was started with.

export type CookiePolicy = { secure: boolean; name: (base: string) => string }

const protocolOf = (value: string | undefined) => {
  try {
    return value?.trim() ? new URL(value.trim()).protocol : null
  } catch {
    return null
  }
}

export function cookiePolicy(env: Record<string, string | undefined> = process.env): CookiePolicy {
  const protocol = protocolOf(env.WEB_PUBLIC_ORIGIN)
  const secure = protocol === 'https:' ? true : protocol === 'http:' ? false : env.NODE_ENV === 'production'
  return { secure, name: (base) => (secure ? `__Host-${base}` : base) }
}
