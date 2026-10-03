import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

// A guard on the shape of the code, like keys-stay-on-server.test.ts: the demo's bank side has no credential but the customer's
// session cookie. None of its files may reach the operator's session, its store or its API client (where the keys live), even by a
// value import of operator.functions (which imports them); types are erased and allowed.
const root = fileURLToPath(new URL('..', import.meta.url)).replaceAll('\\', '/')

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name).replaceAll('\\', '/')
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}
const demo = files(root).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f) &&
  (/\/server\/(demo-desk|demo-entry|demo-gate|demo-limit)/.test(f) || /\/routes\/(-demo\/|_demobanco)/.test(f)))
const rel = (f: string) => f.slice(root.length)

test('the demo files are found', () => {
  assert.ok(demo.some((f) => f.endsWith('server/demo-desk.functions.ts')))
  assert.ok(demo.some((f) => f.endsWith('routes/_demobanco.tsx')))
  assert.ok(demo.some((f) => f.endsWith('routes/-demo/DemoBar.tsx')))
})

test('no file of the demo imports the operator\'s session, store or API client', () => {
  for (const file of demo) {
    const text = readFileSync(file, 'utf8')
    assert.doesNotMatch(text, /from '[^']*operator-(session|store|api|login|forms)(\.ts)?'/, `${rel(file)} imports the operator's credentials`)
    for (const [line] of text.matchAll(/^import (?!type ).*from '[^']*operator\.functions(\.ts)?'.*$/gm)) assert.fail(`${rel(file)}: ${line}`)
  }
})

test('no file of the demo names an operator key or the operator\'s calls', () => {
  for (const file of demo) {
    assert.doesNotMatch(readFileSync(file, 'utf8'), /X-Admin-Key|X-Operator-Key|adminRead|operatorAct|admin_key|operator_key/, rel(file))
  }
})
