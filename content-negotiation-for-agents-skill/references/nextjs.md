# Next.js — content negotiation for AI agents

This reference is self-contained. It covers Next.js **App Router (server-rendered)**
and **static export**, including the negotiation mechanism, where the
HTML↔Markdown conversion belongs, how the two representations stay in sync,
the discovery routes, and the framework-specific caveats.

> Reminder: a negotiated Markdown route is a **distinct HTTP endpoint**. It does
> not inherit the auth middleware of the HTML page it mirrors. Never implement
> it on an authenticated route without adding the equivalent auth check on the
> Markdown route too. Only implement the routes the user confirmed in Step 2.

---

## 1. App Router, server-rendered — the mechanism

There are two viable mechanisms; pick one.

### Option A — config-level rewrite (PRD-default for App Router)

A rewrite in `next.config` inspects the `Accept` header and, when it contains
`text/markdown`, routes the request to a **parallel `markdown` route tree** that
returns Markdown. Browsers (which send `Accept: text/html,...`) are untouched.

> **Gotcha (validated on Next.js 16.2.7):** do **not** name the parallel tree
> with a leading underscore (e.g. `_md`). Next.js treats any folder whose name
> starts with `_` as a **private folder** and excludes it from routing, so the
> rewrite would resolve to a 404. Use a normal segment like `markdown`. Also, the
> destination's param token must **match the source's** — `:path` → `:path`, not
> `:path` → `:path*`.

```ts
// next.config.ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  async rewrites() {
    return {
      beforeFiles: [
        {
          // Match the confirmed section only. The negative lookahead keeps the
          // always-Markdown discovery files (sitemap.md) out of negotiation.
          source: '/blog/:path((?!sitemap\\.md$).*)',
          has: [
            // Next matches this value as a regex against the Accept header.
            { type: 'header', key: 'accept', value: '(.*[ ,])?text/markdown.*' },
          ],
          // Destination lives under a non-underscore prefix the `source` never
          // matches, so the rewrite cannot recursively re-trigger on its output.
          // (`markdown`, NOT `_md` — see the gotcha above. Param token matches
          // the source: `:path`.)
          destination: '/markdown/blog/:path',
        },
      ],
    }
  },
}

export default nextConfig
```

The matching route handler returns Markdown. Because the content here is
authored as Markdown/MDX, **serve the source directly** — never re-render HTML
and convert it back.

```ts
// app/markdown/blog/[...slug]/route.ts   (NOT app/_md/... — `_` = private folder)
import { notFound } from 'next/navigation'
import { getPostBySlug } from '@/lib/posts' // your existing content loader

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ slug: string[] }> },
) {
  const { slug } = await params
  const post = await getPostBySlug(slug.join('/'))
  if (!post) notFound()

  // post.body is the ORIGINAL Markdown/MDX source string.
  const markdown = `# ${post.title}\n\n${post.body}\n`

  return new Response(markdown, {
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
      // Always set Vary: Accept. Spec-wise the server SHOULD and caches MUST
      // honor it (RFC 9110 §12.5.5 / RFC 9111 §4.1); omitting it lets a CDN
      // serve the wrong representation to the wrong client.
      'Vary': 'Accept',
    },
  })
}
```

> **MDX-with-`export const meta`:** if you use `@next/mdx`, the `.mdx` source
> isn't pure Markdown — it carries metadata as `export const meta = {...}` plus
> possible `import`s. Strip those JS lines before returning, e.g.
> `raw.replace(/export\s+const\s+meta\s*=\s*\{[\s\S]*?\};\s*/, '').replace(/^\s*(import|export)\s.*$/gm, '')`,
> so the body is clean Markdown.

### Option B — middleware (cleaner when exclusions get complex)

`middleware.ts` gives full programmatic control — useful when you need to exclude
several discovery paths, add a recursion-guard header, or branch per section.

```ts
// middleware.ts
import { NextRequest, NextResponse } from 'next/server'

export const config = { matcher: ['/blog/:path*', '/docs/:path*'] }

export function middleware(req: NextRequest) {
  const accept = req.headers.get('accept') ?? ''
  const { pathname } = req.nextUrl

  const wantsMarkdown = /(^|[ ,])text\/markdown/.test(accept)
  const isDiscovery = pathname.endsWith('/sitemap.md')

  if (wantsMarkdown && !isDiscovery) {
    const url = req.nextUrl.clone()
    url.pathname = `/markdown${pathname}` // NOT `/_md` — `_` folders aren't routed
    return NextResponse.rewrite(url)
  }
  return NextResponse.next()
}
```

---

## 2. Where the conversion step belongs

| Source of truth | What to do | Why |
|---|---|---|
| **Markdown / MDX** (already structured) | Read the source file and return it as-is (Option A handler above). No conversion. | Lossless, fast, full control. Prefer the hand-rolled path here. |
| **CMS / rendered HTML** | Fetch the clean HTML, strip boilerplate (`@mozilla/readability`), convert (`turndown` or `mdream`). | Re-deriving Markdown from rendered HTML is non-trivial; lean on a package. |

For the CMS case, if you obtain HTML by **internally re-fetching your own page**,
tag the internal request so negotiation does not recurse:

```ts
// app/markdown/blog/[...slug]/route.ts  (CMS variant; NOT _md — private folder)
import { Readability } from '@mozilla/readability'
import { JSDOM } from 'jsdom'
import TurndownService from 'turndown'

export async function GET(req: Request, { params }: { params: Promise<{ slug: string[] }> }) {
  const { slug } = await params
  const htmlUrl = new URL(`/blog/${slug.join('/')}`, req.url)

  // The guard header prevents the rewrite from intercepting this fetch.
  const res = await fetch(htmlUrl, { headers: { 'x-md-skip': '1', accept: 'text/html' } })
  const html = await res.text()

  const dom = new JSDOM(html, { url: htmlUrl.toString() })
  const article = new Readability(dom.window.document).parse() // strips nav/footer/chrome
  const markdown = new TurndownService({ codeBlockStyle: 'fenced', headingStyle: 'atx' })
    .turndown(article?.content ?? '')

  return new Response(markdown, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8', 'Vary': 'Accept' },
  })
}
```

Then make the rewrite ignore guarded requests by adding a `missing` condition:

```ts
has: [{ type: 'header', key: 'accept', value: '(.*[ ,])?text/markdown.*' }],
missing: [{ type: 'header', key: 'x-md-skip', value: '1' }],
```

> **Lossy-conversion decision point (NG2):** tables, custom React/MDX components,
> and embeds may not survive HTML→Markdown cleanly. Surface this to the user as
> an explicit choice — do not silently drop or mangle them.

---

## 3. Keeping HTML and Markdown in sync

With Option A/B the Markdown is generated from the **same source** the HTML page
renders from (the content loader or the live HTML), at request time. There is no
second copy to drift. Preserve structure during conversion: fenced code blocks
keep their language hint, headings keep their hierarchy, links stay functional.

---

## 4. Discovery routes (Step 5)

```ts
// app/blog/sitemap.md/route.ts — always Markdown, for ALL clients
// (crawlers send Accept: text/html and still need this to resolve).
import { getAllPosts } from '@/lib/posts'

export async function GET() {
  const posts = await getAllPosts() // [{ title, slug, category }]
  const byCategory = new Map<string, typeof posts>()
  for (const p of posts) {
    const k = p.category ?? 'Uncategorized'
    byCategory.set(k, [...(byCategory.get(k) ?? []), p])
  }

  let md = '# Blog\n\n'
  for (const [cat, items] of byCategory) {
    md += `## ${cat}\n\n` // nest by category instead of a flat list
    for (const p of items) md += `- [${p.title}](/blog/${p.slug})\n`
    md += '\n'
  }
  return new Response(md, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  })
}
```

The site-wide `llms.txt` (`app/llms.txt/route.ts`) and `<link rel="alternate">`
tags are covered in `references/llms-txt-and-sitemaps.md`. Only link sections you
actually implemented this run — never a section without a working `.md` mirror.

---

## 5. Static export (`output: 'export'`) — the caveat

With `output: 'export'` there is **no server at request time** to read `Accept`,
so the request-time rewrite above does nothing. Use the **build-time sibling**
pattern instead: emit a `.md` next to every in-scope `.html`, sourced from the
original Markdown/MDX (not re-derived from rendered HTML).

```ts
// scripts/emit-markdown.ts — run after `next build && next export`
import { writeFile } from 'node:fs/promises'
import { getAllPosts } from '../lib/posts'

for (const post of await getAllPosts()) {
  await writeFile(`out/blog/${post.slug}.md`, `# ${post.title}\n\n${post.body}\n`)
}
```

Because static export cannot negotiate, the `<link rel="alternate"
type="text/markdown" href="/blog/<slug>.md">` tag in each page's `<head>` is
**mandatory** here, not optional — it is the only discovery path. See
`references/llms-txt-and-sitemaps.md` for the tag, the Markdown sitemap, and
`llms.txt`.

---

## 6. Verify (Step 6)

Run a live check against the dev/preview server — never report success on a
compile alone:

```sh
scripts/verify_negotiation.sh http://localhost:3000 /blog /blog/<a-real-slug> /docs
```

It must show `Content-Type: text/markdown` and `Vary: Accept` on the negotiated
response, and a **measured** byte-size reduction (not a copied percentage). For
static export, verify the emitted `.md` files and the `<link rel="alternate">`
tags instead, since there is no negotiated response to check.
