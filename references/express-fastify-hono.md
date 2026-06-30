# Express / Fastify / Hono — content negotiation for AI agents

This reference is self-contained. It covers the generic Node-server pattern:
middleware that inspects the `Accept` header and serves clean Markdown from the
**same URL** when the client asks for `text/markdown`, while browsers continue
to get HTML.

> A negotiated Markdown route is a **distinct endpoint** and does **not** inherit
> the auth middleware of the HTML route. If a confirmed route is behind auth,
> apply the same `requireAuth` check to the Markdown branch. Only implement the
> routes the user confirmed in Step 2.

---

## 1. The mechanism (shared idea)

1. Read the `Accept` header.
2. If it prefers `text/markdown` **and** the path is in the confirmed scope:
   - **content already Markdown/MDX** → read the source file and send it
     directly, without invoking HTML rendering at all;
   - **content is rendered HTML** → strip boilerplate and convert (package or
     hand-rolled).
3. Otherwise call `next()` and let the normal HTML handler run.
4. Set `Content-Type: text/markdown; charset=utf-8` and `Vary: Accept`.

A small helper keeps the Accept test consistent:

```js
// prefers text/markdown, tolerating q-values and a list of types
function wantsMarkdown(accept = '') {
  return /(^|[ ,])text\/markdown/i.test(accept)
}
```

---

## 2. Express

```js
// markdown-negotiation.js
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const SCOPE = ['/blog', '/docs'] // confirmed sections only
const inScope = (p) => SCOPE.some((s) => p === s || p.startsWith(s + '/'))

export function markdownNegotiation(contentRoot) {
  return async function (req, res, next) {
    if (!wantsMarkdown(req.headers.accept) || !inScope(req.path)) return next()
    try {
      // Content already in Markdown: serve the source, skip HTML rendering.
      const file = path.join(contentRoot, req.path.replace(/\/$/, '') + '.md')
      const body = await readFile(file, 'utf8')
      res.set('Content-Type', 'text/markdown; charset=utf-8')
      res.set('Vary', 'Accept')
      return res.send(body)
    } catch {
      return next() // no .md source — fall through to HTML
    }
  }
}
```

```js
// app.js
import express from 'express'
import { markdownNegotiation } from './markdown-negotiation.js'

const app = express()
app.use(markdownNegotiation('./content'))
// ... your normal HTML routes follow ...
```

Mount the middleware **before** the HTML routes so the Markdown branch wins when
it applies.

---

## 3. Fastify

```js
// fastify-markdown.js
import { readFile } from 'node:fs/promises'
import path from 'node:path'

export default async function markdownPlugin(fastify, opts) {
  const SCOPE = opts.scope ?? ['/blog', '/docs']
  const inScope = (p) => SCOPE.some((s) => p === s || p.startsWith(s + '/'))

  fastify.addHook('onRequest', async (req, reply) => {
    if (!/(^|[ ,])text\/markdown/i.test(req.headers.accept ?? '')) return
    if (!inScope(req.url.split('?')[0])) return
    try {
      const rel = req.url.split('?')[0].replace(/\/$/, '') + '.md'
      const body = await readFile(path.join(opts.contentRoot, rel), 'utf8')
      reply
        .header('Content-Type', 'text/markdown; charset=utf-8')
        .header('Vary', 'Accept')
        .send(body)
    } catch {
      // no source file — let the normal route handle it
    }
  })
}
// fastify.register(markdownPlugin, { contentRoot: './content' })
```

---

## 4. Hono (also Workers / Deno / Bun)

```js
// hono-markdown.js
import { createMiddleware } from 'hono/factory'

export const markdownNegotiation = (opts) =>
  createMiddleware(async (c, next) => {
    const accept = c.req.header('accept') ?? ''
    const wants = /(^|[ ,])text\/markdown/i.test(accept)
    const inScope = (opts.scope ?? ['/blog', '/docs']).some(
      (s) => c.req.path === s || c.req.path.startsWith(s + '/'),
    )
    if (wants && inScope) {
      const md = await opts.load(c.req.path) // your loader returns source Markdown or null
      if (md != null) {
        return c.body(md, 200, {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Vary': 'Accept',
        })
      }
    }
    await next()
  })
// app.use('*', markdownNegotiation({ load: loadMarkdownForPath }))
```

---

## 5. When the source is rendered HTML, not Markdown

If you have no Markdown source and must convert from HTML, either delegate to a
package (see `references/packages-comparison.md` — `markdown-for-agents` has
Express/Fastify/Hono adapters) or hand-roll: strip non-content elements
(`nav`, `header`, `footer`, `aside`, `script`, `style`, cookie banners, ad slots)
with `@mozilla/readability`, then convert with `turndown` or `mdream`.

If you obtain the HTML by **re-fetching your own URL**, tag the internal request
so the middleware does not recurse:

```js
const res = await fetch(selfUrl, { headers: { 'x-md-skip': '1', accept: 'text/html' } })
// ...and at the top of the middleware: if (req.headers['x-md-skip']) return next()
```

> **Lossy-conversion decision point (NG2):** tables, embeds, and custom
> components may not convert cleanly. Surface this to the user rather than
> silently degrading the output.

---

## 6. Keeping the two representations in sync

Both branches derive from the same source (the `.md` file or the live HTML), per
request — there is no second copy to drift. Preserve structure when converting:
fenced code blocks keep language hints, headings keep hierarchy, links stay
functional.

---

## 7. Discovery routes (Step 5)

Serve the per-section sitemap and `llms.txt` as **always-Markdown** endpoints
(crawlers send `Accept: text/html` and still need them to resolve):

```js
// Express example — nested by category, not a flat list
app.get('/blog/sitemap.md', async (_req, res) => {
  const posts = await getAllPosts()
  let md = '# Blog\n\n'
  for (const [cat, items] of groupByCategory(posts)) {
    md += `## ${cat}\n\n`
    for (const p of items) md += `- [${p.title}](/blog/${p.slug})\n`
    md += '\n'
  }
  res.set('Content-Type', 'text/markdown; charset=utf-8').send(md)
})
```

See `references/llms-txt-and-sitemaps.md` for the root `llms.txt` and the
`<link rel="alternate">` tag. Only link sections you actually implemented.

---

## 8. Verify (Step 6)

```sh
scripts/verify_negotiation.sh http://localhost:3000 /blog /blog/<real-slug> /docs
```

Confirm `Content-Type: text/markdown`, `Vary: Accept`, and a **measured** byte
reduction on every confirmed path before reporting done. A failure is blocking —
fix it or flag the specific path; do not report success past a failing check.
