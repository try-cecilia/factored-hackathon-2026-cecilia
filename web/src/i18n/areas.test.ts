import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { test } from 'node:test'
import { areaNamespaces, areasOf, covers, loadMessages, type Area } from './areas.ts'
import { es } from './es.ts'
import { pt } from './pt.ts'

const src = resolve(import.meta.dirname, '..')
const namespaces = Object.keys(es)

// Each page with the files of its route: whatever they import, the keys they use must be in the areas of the page's path.
const pages: Record<string, string[]> = {
  '/': ['routes/index.tsx'],
  '/login': ['routes/login.tsx'],
  '/chat': ['routes/_authed.tsx', 'routes/_authed/chat.tsx'],
  '/operador/login': ['routes/operador.login.tsx'],
  '/operador/cola': ['routes/_operator.tsx', 'routes/_operator/operador.index.tsx', 'routes/_operator/operador.cola.tsx', 'routes/_operator/operador.cola.index.tsx'],
  '/operador/cola/T-1': ['routes/_operator.tsx', 'routes/_operator/operador.cola.tsx', 'routes/_operator/operador.cola.$ticketId.tsx'],
  '/operador/monitoreo': ['routes/_operator.tsx', 'routes/_operator/operador.monitoreo.tsx'],
  '/operador/trazas/abc': ['routes/_operator.tsx', 'routes/_operator/operador.trazas.tsx', 'routes/_operator/operador.trazas.index.tsx', 'routes/_operator/operador.trazas.$traceId.tsx'],
  '/dev/ui': ['routes/dev.ui.tsx'],
}

const read = (file: string) => readFileSync(file, 'utf8')

function resolveSpec(from: string, spec: string): string | undefined {
  const base = resolve(dirname(from), spec)
  return [base, `${base}.ts`, `${base}.tsx`, join(base, 'index.ts')].find((path) => /\.tsx?$/.test(path) && existsSync(path))
}

/** The module a barrel (`index.ts`) takes `name` from: importing a name from the kit pulls in that component, not the whole kit. */
function origin(barrel: string, name: string): string | undefined {
  for (const [, names, spec] of read(barrel).matchAll(/export\s+(?:\*|\{([^}]*)\})\s+from\s+'(\.[^']+)'/g)) {
    const target = resolveSpec(barrel, spec)
    if (!target) continue
    if (names !== undefined) {
      if (names.split(',').some((n) => n.replace(/^\s*type\s+/, '').trim() === name)) return target
    } else if (target.endsWith('index.ts')) {
      const found = origin(target, name)
      if (found) return found
    } else if (new RegExp(`export\\s+(?:function|const|class)\\s+${name}\\b`).test(read(target))) return target
  }
  return undefined
}

/** The source files a route pulls in, following relative imports (the i18n itself, the server functions and the gallery aside). */
function closure(entries: string[]): Set<string> {
  const seen = new Set<string>()
  const queue = entries.map((entry) => join(src, entry))
  while (queue.length) {
    const file = queue.pop() as string
    if (seen.has(file)) continue
    seen.add(file)
    for (const [, typeOnly, names, imported, loaded] of read(file).matchAll(/import\s+(type\s+)?(?:\{([^}]*)\}\s+from\s+)?'(\.[^']+)'|import\('(\.[^']+)'\)/g)) {
      const spec = imported ?? loaded
      if (typeOnly || !spec) continue
      const target = resolveSpec(file, spec)
      if (!target || /\/(i18n|server|ui\/gallery)\//.test(target.replaceAll('\\', '/'))) continue
      if (!target.endsWith('index.ts') || names === undefined) {
        queue.push(target)
        continue
      }
      for (const name of names.split(',').map((n) => n.trim()).filter((n) => n && !n.startsWith('type '))) {
        const found = origin(target, name.split(/\s+as\s+/)[0])
        assert.ok(found, `${file}: ${name} not found through ${target}`)
        queue.push(found)
      }
    }
  }
  return seen
}

test('every key a page uses is in the namespaces of its areas', () => {
  const key = new RegExp(`['\`](${namespaces.join('|')})\\.[a-zA-Z]`, 'g')
  for (const [path, entries] of Object.entries(pages)) {
    const allowed = new Set(areasOf(path).flatMap((area) => areaNamespaces[area]))
    for (const file of closure(entries)) {
      for (const [, namespace] of readFileSync(file, 'utf8').matchAll(key)) {
        assert.ok(allowed.has(namespace as never), `${path}: ${file.slice(src.length + 1)} uses '${namespace}.', not in ${areasOf(path).join(' + ')}`)
      }
    }
  }
})

test('each page is in its own area, and the customer never loads the console, the monitor or the gallery', () => {
  assert.deepEqual(areasOf('/chat'), ['customer'])
  assert.deepEqual(areasOf('/'), ['customer'])
  assert.deepEqual(areasOf('/operador/cola/abc'), ['operator'])
  assert.deepEqual(areasOf('/operador/trazas/abc'), ['operator', 'monitor'])
  assert.deepEqual(areasOf('/operadora'), ['customer'])
  assert.deepEqual(areasOf('/dev/ui'), ['gallery'])
  const customer = new Set(areaNamespaces.customer)
  for (const namespace of ['operator', 'monitor', 'gallery', 'table'] as const) assert.ok(!customer.has(namespace), namespace)
})

test('from the queue to the monitor the texts reload; back to the queue they do not', () => {
  const queue: Area[] = ['operator']
  assert.equal(covers(queue, areasOf('/operador/monitoreo')), false)
  assert.equal(covers(['operator', 'monitor'], areasOf('/operador/cola')), true)
  assert.equal(covers(undefined, areasOf('/chat')), false)
})

test('a page loads its namespaces in its language, and only those', async () => {
  const chat = await loadMessages(areasOf('/chat'), 'pt')
  assert.deepEqual(Object.keys(chat).sort(), [...areaNamespaces.customer].sort())
  assert.deepEqual(chat.conversation, pt.conversation)
  const monitor = await loadMessages(areasOf('/operador/monitoreo'), 'es')
  assert.deepEqual(Object.keys(monitor).sort(), [...new Set([...areaNamespaces.operator, ...areaNamespaces.monitor])].sort())
  assert.deepEqual(monitor.monitor, es.monitor)
})
