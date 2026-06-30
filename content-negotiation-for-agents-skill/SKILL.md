---
name: content-negotiation-for-agents-skill
description: >-
  Implements HTTP content negotiation so AI agents fetching a page get clean
  Markdown (via the Accept header) while browsers get normal HTML from the same
  URL. Use when the user wants to make a site, blog, docs, changelog, help
  center, or knowledge base "agent-readable", "AI-friendly", "readable by AI
  agents / LLMs", to "serve text/markdown", add an "llms.txt" or Markdown
  sitemaps, cut token cost for AI fetchers, or implement "Accept header content
  negotiation". Covers Next.js (App Router and static export),
  Express/Fastify/Hono, and static sites (Astro/Hugo/Jekyll). It ALWAYS asks
  which pages to target before changing anything, and verifies the result with a
  live HTTP request before reporting done.
license: MIT
compatibility: >-
  Needs read access to the target repo, file-editing tools, the ability to run
  python3 and a POSIX shell (curl), and ideally a running dev/preview server to
  verify against. Degrades gracefully where a capability is missing.
metadata:
  version: "1.0.0"
  author: shawnchee
  homepage: https://github.com/Shawnchee/content-negotiation-for-agents-skill
---

# Content negotiation for agents

Serve clean Markdown to AI agents and answer engines from the **same URL** that
serves HTML to browsers, using the HTTP `Accept` header. A negotiated Markdown
page is often a tiny fraction of the equivalent HTML (no nav, scripts, styles,
cookie banners), so agents spend far less context and cost on it.

This skill takes a developer from intent ("make our docs agent-friendly") to a
correctly **scoped**, working, **verified** implementation — across the
frameworks people actually use.

## When to use this

Trigger on requests like: "make my blog/docs readable by AI agents", "serve
markdown to LLMs", "add content negotiation", "add llms.txt", "make this
AI-friendly / agent-friendly", "reduce tokens for crawlers fetching my site".

## When NOT to use this

- Authenticated dashboards, account/billing/checkout, interactive tools — poor
  fit and a real security risk (see the non-negotiables below).
- "Make my whole site AI-optimized" — out of scope. This skill does **one**
  thing: content negotiation + its discovery files. `robots.txt` for AI
  crawlers, JSON-LD, general AEO/SEO are **not** owned here (mention, don't
  implement).

## Non-negotiable rules (do not optimize these away)

1. **Scope is mandatory and explicit (Step 2).** Never implement negotiation on
   a route the user did not confirm. Default to public, static, high-density
   content. If the user says "the whole site" or names an authenticated/sensitive
   route, reflect it back and require explicit per-route confirmation first.
   *Why this matters:* a negotiated Markdown route is a **distinct HTTP
   endpoint** — it does **not** inherit the auth middleware of the HTML page it
   mirrors. Blind site-wide application can expose gated content to anyone who
   sends `Accept: text/markdown`.
2. **Verify with a live request (Step 6).** Never report success because the code
   compiles. A failed verification is **blocking** — fix it or flag the specific
   failing path; do not declare done past a failure.
3. **Measure, don't assume.** Report real byte counts from the actual
   request/response, never a percentage copied from documentation.
4. **Detection and scoping are read-only.** Create or modify nothing in the
   target repo until scope is confirmed.
5. **Both implementation paths are first-class.** Hand-rolled (zero new deps) and
   drop-in package are both supported. Never hard-depend on a third-party
   package; the hand-rolled path must always work.

---

## The workflow (6 steps)

### Step 1 — Detect the project (read-only)

Run the bundled detector; it never writes to the repo and skips
`node_modules`/`.git`:

```sh
python3 scripts/detect_framework.py <path-to-repo>
```

It prints JSON: `framework`, `framework_family`, `router`, `rendering_mode`,
`recommended_reference`, `candidate_content_dirs` (each with an approximate page
count and a `likely_markdown_source` heuristic), and `sensitive_dirs_flagged`.

- For Next.js it distinguishes App Router vs Pages Router and server vs
  `output: 'export'` static export.
- If `framework` is `"unknown"`, do **not** guess — ask the user directly which
  framework and which pages.

Open the reference for the detected family and follow it:

- `references/nextjs.md` — Next.js App Router (server) and static export.
- `references/express-fastify-hono.md` — generic Node servers.
- `references/astro-and-static-sites.md` — Astro, Hugo, Jekyll, Next static
  export, and any build-time static generator.

### Step 2 — Ask which pages to target (mandatory, non-skippable)

Before creating or modifying **any** file, present the candidate sections from
Step 1 **with reasoning**, and ask the user to confirm, narrow, or redirect.

Say, in substance:

> Content negotiation is a good fit for **public, static, high-information
> content** — blogs, docs, changelogs, help centers. It is a poor fit and a
> potential security risk for **authenticated routes, dashboards/tools, and
> checkout/payment flows**, because the Markdown route is a separate endpoint
> that won't inherit the original page's auth.
>
> I found these candidate sections: `<list with page counts>`. I also flagged
> these as possibly authenticated/sensitive: `<sensitive_dirs_flagged>`.
> Which should I implement? (Default: the public content sections only.)

Rules for this step:

- If the user requests scope that includes a route the detector flagged as
  sensitive, or says "everything / the whole site", **reflect that back once and
  require explicit confirmation** for the sensitive routes specifically. Do not
  proceed silently.
- A clear, already-scoped request ("just `/blog`") may proceed with a lighter
  confirmation — but still **state what you are about to do before doing it**.
- This step cannot be bypassed by a "just do it all" instruction without the
  explicit-confirmation behavior above.

### Step 3 — Choose hand-rolled vs. a package

Present both paths with trade-offs (control/customizability vs. speed). Default
reasoning, absent a stated preference:

- Content **already Markdown/MDX** → **hand-rolled** (serve the source; full
  control is cheap, no conversion needed).
- Content is **CMS-rendered HTML** → **a package** (boilerplate-stripping +
  HTML→Markdown is non-trivial to hand-roll).
- User wants the **fastest path** → a package.

See `references/packages-comparison.md` for the current options. That list is a
**snapshot** — re-check a package's latest release / maintenance before making a
strong recommendation; do not treat the table as permanently accurate.

### Step 4 — Implement (per the framework reference)

Follow the matching reference. Constraints that apply regardless of framework:

- Set `Content-Type: text/markdown; charset=utf-8` on negotiated responses.
- Always set **`Vary: Accept`** on any response whose body depends on `Accept`,
  so CDNs/shared caches don't serve the wrong representation. (Server SHOULD,
  caches MUST honor it; always set it.)
- Preserve **structure**, not just text: fenced code blocks keep language hints,
  headings keep hierarchy, links stay functional.
- When content is already Markdown/MDX, serve the **source** directly — do not
  render HTML and convert it back.
- A negotiated route on an authenticated URL **must** carry the equivalent auth
  check — it does not inherit it.
- If you internally re-fetch your own URL to get clean HTML, **tag that request**
  (e.g. a custom header) so negotiation does not recurse.
- Static sites can't negotiate at request time → emit a build-time `.md` sibling
  for every in-scope `.html`, sourced from the original Markdown.
- **Lossy conversions are a user decision (NG2).** Tables, embeds, and custom
  components may not survive HTML→Markdown — surface this; never silently drop or
  mangle content.

### Step 5 — Add discovery

- A **Markdown sitemap** per scoped section at a predictable path
  (e.g. `/blog/sitemap.md`), with human-readable titles, **nested** for
  hierarchical content.
- A root **`llms.txt`** linking to the per-section sitemaps and key entry points
  — **only** to sections actually implemented this run (no dead links).
- A `<link rel="alternate" type="text/markdown" href="...">` in each in-scope
  page's `<head>` — **mandatory** for static output (its only discovery path),
  recommended everywhere.

Details and code: `references/llms-txt-and-sitemaps.md`. Remember most AI
**crawlers** don't negotiate — discovery files are how they reach your Markdown.

### Step 6 — Verify (blocking)

For every page in the confirmed scope, issue a real request and check the result:

```sh
scripts/verify_negotiation.sh <base-url> <path-1> [path-2] ...
# e.g. scripts/verify_negotiation.sh http://localhost:3000 /blog /blog/hello /docs
```

It checks the Markdown response's `Content-Type` (hard gate — `text/markdown`,
with or without charset), warns loudly if `Vary: Accept` is missing (not silently
ignored), and prints the **measured** byte-size difference between the HTML and
Markdown responses. It exits non-zero if any path fails, so it doubles as a CI
gate.

For **static** sites there is no negotiated response — verify the emitted `.md`
files resolve with `Content-Type: text/markdown` and that the
`<link rel="alternate">` tags are present instead.

Do not report the task complete while any scoped URL fails verification.

---

## Bundled files

- `scripts/detect_framework.py` — Step 1 detector (read-only, stdlib-only).
- `scripts/verify_negotiation.sh` — Step 6 live verifier (curl + POSIX shell).
- `scripts/validate_skill.py` — contributor/CI check for this skill's own
  structure (not used during a normal run).
- `references/nextjs.md` — Next.js (App Router server-rendered + static export).
- `references/express-fastify-hono.md` — Express, Fastify, Hono, generic Node.
- `references/astro-and-static-sites.md` — Astro, Hugo, Jekyll, static export.
- `references/packages-comparison.md` — hand-rolled vs. drop-in packages (living
  snapshot; verify currency before recommending).
- `references/llms-txt-and-sitemaps.md` — `llms.txt`, Markdown sitemaps,
  `rel=alternate`, and `Vary: Accept`.

## Portability note

This skill follows the open Agent Skills standard (only `name` and `description`
are required frontmatter). It targets Claude Code and Codex CLI; it avoids
agent-specific frontmatter so it degrades gracefully on any conformant agent. The
bundled scripts use only Python's standard library and POSIX `curl`/shell — no
extra dependency tree to install the skill's own tooling.
