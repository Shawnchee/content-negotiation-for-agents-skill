# Astro / Hugo / Jekyll and other static sites — content negotiation for AI agents

This reference is self-contained. It covers static-site generators (Astro, Hugo,
Jekyll, Eleventy, etc.) and any **Next.js static export** build. The defining
constraint: **there is no server at request time to read the `Accept` header**,
so true request-time content negotiation is impossible. The correct pattern is a
**build-time sibling**: emit a `.md` file next to every in-scope `.html`,
sourced from the original Markdown — plus mandatory `<link rel="alternate">`
discovery tags.

> Only generate `.md` mirrors for the sections the user confirmed in Step 2.
> Static `.md` files are world-readable by anyone who knows the URL — the same
> "distinct endpoint, no inherited auth" rule applies: never mirror gated content.

---

## 1. The mechanism: build-time `.md` siblings

For every in-scope page, write `page.md` alongside `page/index.html`, sourced
from the **original Markdown/MDX** (not re-derived from rendered HTML — that loses
fidelity and re-introduces the boilerplate you are trying to strip).

Why siblings and not negotiation: the major AI **crawlers** (GPTBot,
OAI-SearchBot, ClaudeBot, PerplexityBot) do **not** content-negotiate — they
request `text/html` and then look for a separate `.md` URL. Even on servers that
*do* negotiate, today's Markdown traffic comes mostly from interactive coding
agents. On a static host you serve everyone via discoverable `.md` URLs.

---

## 2. Astro

### Static (default) — a Markdown endpoint per page

Astro endpoints can emit non-HTML files at build time. Pair `getStaticPaths`
with the content collection so each post produces a `.md` sibling from its
**source body**:

```ts
// src/pages/blog/[...slug].md.ts
import type { APIRoute, GetStaticPaths } from 'astro'
import { getCollection } from 'astro:content'

export const getStaticPaths: GetStaticPaths = async () => {
  const posts = await getCollection('blog')
  return posts.map((post) => ({ params: { slug: post.slug }, props: { post } }))
}

export const GET: APIRoute = ({ props }) => {
  const { post } = props
  // post.body is the raw Markdown source.
  return new Response(`# ${post.data.title}\n\n${post.body}\n`, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  })
}
```

This generates `/blog/<slug>.md` for every post at build. Advertise it with the
`<link rel="alternate">` tag (Section 5).

### Astro SSR / hybrid (`output: 'server'` | `'hybrid'`) — request-time negotiation is possible

If the site is server-rendered, you *can* negotiate at request time in
middleware (read `Accept`, rewrite to the `.md` endpoint). Treat this like the
generic Node pattern in `references/express-fastify-hono.md`. For purely static
builds, stay with the sibling pattern above.

### Packages (Astro)

- **starlight-llms-txt** — for Starlight docs; generates `llms.txt` /
  `llms-full.txt` at build. The most established option in this niche.
- **astro-llms-md** — generates `llms.txt` plus per-page `.md` files.

See `references/packages-comparison.md` for currency/maintenance notes.

---

## 3. Hugo — custom output format

Hugo content is already Markdown in `content/`. Define a custom `text/markdown`
output format and a one-line template that emits the **raw** content
(`.RawContent`, not the rendered `.Content`):

```toml
# hugo.toml
[mediaTypes."text/markdown"]
suffixes = ["md"]

[outputFormats.MarkdownAgent]
mediaType = "text/markdown"
isPlainText = true
baseName = "index"

[outputs]
section = ["HTML", "MarkdownAgent"]
page = ["HTML", "MarkdownAgent"]
```

```go-html-template
{{/* layouts/_default/single.md (the MarkdownAgent template) */}}
# {{ .Title }}

{{ .RawContent }}
```

Scope it to the confirmed sections only (e.g. set `outputs` per section via
front matter or a section-specific config) rather than site-wide.

---

## 4. Jekyll and other generators — universal post-build emitter

Jekyll exposes rendered HTML (`page.content`), not raw Markdown, in Liquid, so
the cleanest cross-generator approach is a **post-build script** that copies the
**source** Markdown into sibling `.md` files in the output directory. This works
for Jekyll, Eleventy, Hugo, and Next.js static export alike:

```python
# scripts/emit_md_siblings.py — run AFTER the static build
# Copies source Markdown for in-scope sections into the build output as .md siblings.
import pathlib, shutil, re

SRC = pathlib.Path("_posts")        # Jekyll source (adjust per generator)
OUT = pathlib.Path("_site/blog")    # build output dir for the section
OUT.mkdir(parents=True, exist_ok=True)

for md in SRC.glob("*.md"):
    text = md.read_text(encoding="utf-8")
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)  # drop front matter
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", md.stem)                  # Jekyll date prefix
    (OUT / f"{slug}.md").write_text(text, encoding="utf-8")
```

Adjust `SRC`/`OUT` and the slug rule per generator. The key invariant: **source
Markdown in, sibling `.md` out** — never convert from rendered HTML on a static
site if the original Markdown exists.

> If a section's source is **not** Markdown (CMS export, HTML templates), this is
> the NG2 lossy-conversion decision point: tell the user it needs HTML→Markdown
> conversion (readability + turndown) and that tables/embeds/components may not
> survive — let them decide, don't silently degrade.

---

## 5. Discovery is mandatory here (Step 5)

With no server-side fallback, discovery tags are the **only** way an agent finds
the Markdown. These are required, not nice-to-have:

```html
<!-- in each in-scope page's <head> -->
<link rel="alternate" type="text/markdown" href="/blog/my-post.md" title="Markdown version" />
```

Also generate, at build time:

- a per-section `sitemap.md` (nested by category, human-readable titles), and
- a root `llms.txt` linking to the per-section sitemaps and key `.md` entry
  points — only for sections actually built this run.

Both are covered in detail in `references/llms-txt-and-sitemaps.md`.

---

## 6. Keeping HTML and Markdown in sync

The `.md` siblings are regenerated from the source on **every build**, so they
cannot drift from the HTML as long as both come from the same source content. If
you ever hand-author a `.md` separately from its `.html`, you have created a
second source of truth that *will* drift — don't.

---

## 7. Verify (Step 6)

A static host has no negotiated response, so verify the **emitted files and
tags** rather than an `Accept`-driven response:

```sh
# After build + local preview (e.g. `astro preview`, `hugo server`, `jekyll serve`):
curl -sI http://localhost:4321/blog/my-post.md | grep -i content-type   # text/markdown
curl -s  http://localhost:4321/blog/my-post.md | head                    # real Markdown body
grep -l 'rel="alternate".*text/markdown' _site/blog/my-post/index.html   # tag present
```

Confirm every `.md` link in `llms.txt` and the sitemaps resolves to a real
Markdown file — no dead links to unbuilt sections. Report the **measured** byte
difference between the `.html` and `.md` files, not an assumed percentage.
