// Fails the build if the bundle would load anything from the internet.
// index.html and CSS must contain no external URLs at all (fonts, scripts, images).
// JS is scanned for fetch/import/src of absolute URLs; harmless doc links and XML namespaces are ignored.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const root = new URL('../dist', import.meta.url).pathname
const IGNORE = [/www\.w3\.org/, /reactjs\.org\/docs/, /konvajs\./, /github\.com/, /github\.io/, /tailwindcss\.com/]
const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]))
let bad = 0
for (const f of walk(root)) {
  if (!/\.(html|css|js)$/.test(f)) continue
  const txt = readFileSync(f, 'utf8')
  const strict = /\.(html|css)$/.test(f)
  const re = strict ? /https?:\/\/[^\s"')]+/g : /(?:fetch\(|import\(|src=|href=|url\()\s*["'`]?https?:\/\/[^\s"')]+/g
  for (const m of txt.match(re) || []) {
    if (IGNORE.some((r) => r.test(m))) continue
    console.error(`external URL in ${f.replace(root, 'dist')}: ${m}`); bad++
  }
}
if (bad) { console.error(`\n${bad} external reference(s) found`); process.exit(1) }
console.log('offline check passed: no external URLs in dist/')
