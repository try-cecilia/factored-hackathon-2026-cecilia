import assert from 'node:assert/strict'
import { test } from 'node:test'
import { GENERIC_ERROR, PublicError, toClientError } from './rpc-guard.ts'

const quiet = <T,>(run: () => T) => {
  const log = console.error
  const lines: unknown[][] = []
  console.error = (...args: unknown[]) => void lines.push(args)
  try {
    return { lines, value: run() }
  } finally {
    console.error = log
  }
}

test('an unexpected error becomes a generic one: no message, no cause, no stack of the original', () => {
  const boom = new SyntaxError('Unexpected token < in JSON at position 0: <html>CANARY</html>', { cause: new Error('CANARY cause') })
  const { value: error, lines } = quiet(() => toClientError(boom) as Error)
  assert.ok(error instanceof Error)
  assert.equal(error.message, GENERIC_ERROR)
  assert.equal(error.cause, undefined)
  assert.ok(!String(error.stack).includes('CANARY'))
  // The diagnosis stays on the server: the kind of failure, never the message or the body.
  assert.equal(lines.length, 1)
  assert.ok(String(lines[0]).includes('SyntaxError'))
  assert.ok(!JSON.stringify(lines).includes('CANARY'))
})

test('what is thrown that is not an Error is generic too', () => {
  assert.equal((quiet(() => toClientError('CANARY text')).value as Error).message, GENERIC_ERROR)
  assert.equal((quiet(() => toClientError({ message: 'CANARY' })).value as Error).message, GENERIC_ERROR)
})

test('a deliberate public error keeps its message', () => {
  const error = new PublicError('ticket_id is not valid')
  assert.equal(quiet(() => toClientError(error)).value, error)
})

test('what the framework throws to steer (a Response, a redirect, a not-found) goes through untouched', () => {
  const redirect = new Response(null, { status: 307, headers: { Location: '/login' } })
  const notFound = { isNotFound: true }
  assert.equal(quiet(() => toClientError(redirect)).value, redirect)
  assert.equal(quiet(() => toClientError(notFound)).value, notFound)
})
