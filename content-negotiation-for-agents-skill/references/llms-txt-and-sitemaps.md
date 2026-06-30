# Discovery: `llms.txt`, Markdown sitemaps, `rel=alternate`, and `Vary`

This reference is self-contained. It covers how agents *find* your Markdown:
the `llms.txt` index, per-section Markdown sitemaps, the `<link rel="alternate">`
tag, and the `Vary: Accept` header that keeps caches honest.

> **Why discovery matters even with negotiation.** Only some *interactive coding
> agents* (Claude Code, Cursor, OpenCode, and Anthropic's Claude fetch path) send
> `Accept: text/markdown` and get your negotiated response. The major background
> **crawlers** (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot) do **not**
> content-negotiate — they request `text/html` and then look for separate `.md`
> URLs. Discovery is how those crawlers (and link-followers) reach your Markdown.
> Do not claim "AI crawlers negotiate for Markdown" — they don't.

---

## 1. `llms.txt`

A community convention (llmstxt.org, Jeremy Howard, Sept 2024) for a root-level
Markdown file that gives agents a curated index of a site's key content. It is
about **content discovery, not crawl permission** — orthogonal to `robots.txt`,
which governs access. It is **not** an IETF standard.

**Location:** site root, `/llms.txt`.

**Structure** (from the spec):

```markdown
# Title

> Optional one-line summary in a blockquote

Optional free-form detail (any Markdown except headings).

## Docs

- [Quickstart](https://example.com/docs/quickstart.md): how to get started
- [API reference](https://example.com/docs/api.md): endpoints and types

## Optional

- [Changelog](https://example.com/changelog.md): release history
```

The H1 title is the only required element. An `## Optional` section has special
meaning: its links **may be skipped** when a shorter context is needed.

**Only list sections you actually implemented this run.** Every link in
`llms.txt` must resolve to a real, working Markdown response — no dead links to
unbuilt sections (Step 5 acceptance criterion).

**`llms-full.txt`** — a *de facto* community/tooling convention (popularized by
Mintlify), **not** in the official spec: where `llms.txt` is an index of links,
`llms-full.txt` inlines the full page content into one large file. Offer it only
if the user wants it, and label it as a convention, not a standard.

**Adopters** (confirmed): Anthropic, Stripe, Vercel, Cloudflare, Hugging Face,
Perplexity, Svelte, and hundreds more (directory.llmstxt.cloud).

### Generating it

Server route (Next.js / Node):

```ts
// app/llms.txt/route.ts — always plain Markdown text, for all clients
export async function GET() {
  const body = [
    '# Example Docs',
    '',
    '> Product documentation, agent-readable.',
    '',
    '## Docs',
    '- [Docs sitemap](https://example.com/docs/sitemap.md): all docs pages',
    '',
    '## Blog',
    '- [Blog sitemap](https://example.com/blog/sitemap.md): all posts',
    '',
  ].join('\n')
  return new Response(body, { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } })
}
```

Static site: write `llms.txt` into the build output root at build time, listing
only the sections you generated `.md` mirrors for.

---

## 2. Markdown sitemaps

A per-section, human-and-agent-readable table of contents — Markdown links with
real titles, **nested** to show hierarchy (not a flat list). Predictable path,
e.g. `/blog/sitemap.md`, `/docs/sitemap.md`.

```markdown
# Docs

## Getting started
- [Installation](/docs/install.md)
- [Quickstart](/docs/quickstart.md)

## Guides
- [Authentication](/docs/guides/auth.md)
- [Deployment](/docs/guides/deploy.md)
```

For categorized/hierarchical content, render recursively so parent/child
relationships are visible. Serve it as an **always-Markdown** route (crawlers
send `text/html` and still need it to resolve) — see the per-framework
references for the route/build-step code.

---

## 3. `<link rel="alternate" type="text/markdown">`

Advertises the Markdown alternate of an HTML page in its `<head>`:

```html
<link rel="alternate" type="text/markdown" href="/blog/my-post.md" title="Markdown version" />
```

The plumbing is fully standardized — `rel="alternate"` + `type` (WHATWG HTML,
RFC 4287, IANA link relations) and `text/markdown` (RFC 7763). Using it
*specifically* to point at a Markdown alternate is an **emerging 2025–2026
convention**, not a mandated standard, but it is spec-valid and recommended
(Vercel, WordPress/Roots, Eleventy implementations).

- **Mandatory on static sites** — with no server-side negotiation, this tag is
  the primary discovery path. Not optional there.
- **`href` target:** point at the **per-page `.md`** for true
  "alternate-of-this-document" semantics (recommended), or at the site-wide
  `/llms.txt` (Vercel's choice) — pick one convention and be consistent.

The HTTP `Link` header is the equivalent for non-HTML responses (RFC 8288):

```
Link: </blog/my-post.md>; rel="alternate"; type="text/markdown"
```

---

## 4. `Vary: Accept`

When the body returned for a URL depends on the `Accept` header, set
`Vary: Accept` on the response.

```
Content-Type: text/markdown; charset=utf-8
Vary: Accept
```

Spec nuance (state it accurately): per RFC 9110 §12.5.5 the origin server
**SHOULD** send `Vary` for content-negotiated, cacheable responses, and per RFC
9111 §4.1 **caches MUST** honor it. Practically: **always set it.** If you omit
it, a shared cache/CDN keys by URL alone, stores whichever representation it saw
first, and serves that to everyone — so a Markdown-requesting agent can receive
cached HTML, or a browser can receive cached Markdown. Use the **same** `Vary`
value on all responses for the URL, including `304 Not Modified`.

`Content-Type` for Markdown is `text/markdown` (RFC 7763); include
`; charset=utf-8`. The verifier accepts the type with or without the charset
parameter.

---

## 5. Out of scope for this skill

`robots.txt` directives for AI crawlers, JSON-LD/structured data, and general
AEO/SEO intersect with discovery but are **not owned** by this skill (PRD NG3).
Mention them as adjacent if relevant; point the user to a dedicated tool rather
than implementing them here.
