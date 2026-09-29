import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'

// A guard on the shape of the code, not a proof: the operator's keys are typed into plain HTML forms posted to the
// server, so no client file may read, hold or send them.
const root = new URL('..', import.meta.url).pathname

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}
const source = files(root).filter((f) => /\.(ts|tsx)$/.test(f) && !f.endsWith('.test.ts') && !f.endsWith('routeTree.gen.ts'))
// Only the operator console: the customer login (routes/login.tsx) is a different flow with its own PIN handling.
const client = source.filter((f) => /\/routes\/(operador|_operator|-operator)/.test(f) && f.endsWith('.tsx'))
const rel = (f: string) => f.slice(root.length)

test('a password input in a client component is uncontrolled', () => {
  for (const file of client) {
    for (const input of readFileSync(file, 'utf8').match(/<input[^>]*type="password"[^>]*>/gs) ?? []) {
      assert.doesNotMatch(input, /\bvalue=|\bonChange=|\bdefaultValue=/, `${rel(file)} controls a password input`)
    }
  }
})

test('no client file keeps a key in state or hands it to a server function', () => {
  for (const file of client) {
    const text = readFileSync(file, 'utf8')
    assert.doesNotMatch(text, /use(State|Reducer|Ref)\([^)]*\)[^\n]*(admin|operator)_?[kK]ey|(admin|operator)_?[kK]ey[^\n]*use(State|Reducer)/, rel(file))
    assert.doesNotMatch(text, /(admin|operator)Key\b/, `${rel(file)} mentions a key variable`)
    assert.doesNotMatch(text, /FormData|localStorage|sessionStorage/, `${rel(file)} reads form data or storage in the browser`)
  }
})

test('server functions never take a key as input', () => {
  const text = readFileSync(join(root, 'server/operator.functions.ts'), 'utf8')
  assert.doesNotMatch(text, /admin_key|operator_key|X-Admin-Key|X-Operator-Key/)
})

test('every password form posts to a server route', () => {
  for (const file of client) {
    const text = readFileSync(file, 'utf8')
    if (!text.includes('type="password"')) continue
    assert.match(text, /<form[^>]*method="post"[^>]*action="\/operador\/(sesion|clave)"/s, `${rel(file)}: password inputs need a native form post`)
  }
})
