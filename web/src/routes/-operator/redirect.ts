/** A path on this site, or nothing: the login must never send an operator to another origin. */
export function sameOriginPath(value: unknown) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return undefined
  const base = 'http://cecilai.invalid'
  try {
    const url = new URL(value, base)
    return url.origin === base ? url.pathname + url.search + url.hash : undefined
  } catch {
    return undefined
  }
}
