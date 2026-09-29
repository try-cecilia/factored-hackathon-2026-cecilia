// One id per message the customer sends, kept across retries: the API answers the same key with the same reply, so
// a retry after a lost answer cannot run the turn twice. Must match KEY_PATTERN in server/chat-core.ts.
export function newMessageKey(): string {
  const c = globalThis.crypto
  if (typeof c?.randomUUID === 'function') return c.randomUUID()
  // randomUUID needs a secure context; over plain http on a LAN address it is missing.
  const bytes = c.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}
