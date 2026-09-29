// What a first visit to /chat and to /operador/cola downloads, from a production build (`pnpm build`, then
// `node scripts/initial-assets.mjs`): the JS and CSS the TanStack Start manifest lists for each route and its parents, each file
// counted once, raw and gzipped (level 6, what a server sends by default). HTML, data, images and fonts are not counted.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'

const dist = process.argv[2] ?? 'dist'
const server = join(dist, 'server/assets')
const client = join(dist, 'client/assets')
const manifest = readdirSync(server).find((f) => f.startsWith('_tanstack-start-manifest'))
const source = readFileSync(join(server, manifest), 'utf8').replace(/export\s*\{[^}]*\};?/, '')
const { routes } = new Function(`${source}\nreturn tsrStartManifest()`)()

// Stylesheets linked from head() with `?url` are not in the manifest: the root's, and the operator's.
const built = readdirSync(client)
const linked = (name) => `/assets/${built.find((f) => f.startsWith(`${name}-`) && f.endsWith('.css'))}`

const pages = {
  '/chat': { routes: ['__root__', '/_authed', '/_authed/chat'], css: [linked('styles')] },
  '/operador/cola': { routes: ['__root__', '/_operator', '/_operator/operador/cola', '/_operator/operador/cola/'], css: [linked('styles'), linked('operator')] },
}

const kB = (bytes) => (bytes / 1000).toFixed(2).padStart(7)
for (const [page, { routes: chain, css: extra }] of Object.entries(pages)) {
  const js = new Set()
  const css = new Set(extra)
  for (const id of chain) {
    const route = routes[id]
    if (!route) throw new Error(`the manifest has no route ${id}`)
    for (const file of route.preloads ?? []) js.add(file)
    for (const script of route.scripts ?? []) if (script.attrs?.src) js.add(script.attrs.src)
    for (const file of route.css ?? []) css.add(file)
  }
  for (const [kind, files] of [['JS', js], ['CSS', css]]) {
    let raw = 0
    let gzip = 0
    for (const file of files) {
      const bytes = readFileSync(join(dist, 'client', file))
      raw += bytes.length
      gzip += gzipSync(bytes).length
    }
    console.log(`${page.padEnd(15)} ${kind.padEnd(3)} ${String(files.size).padStart(2)} files ${kB(raw)} kB  gzip ${kB(gzip)} kB`)
  }
}
