# Packages comparison — hand-rolled vs. drop-in

This is a **living, snapshot-in-time** document. It is deliberately kept separate
from `SKILL.md` because the package ecosystem moves faster than the rest of the
skill.

> **Snapshot date: 2026-06-30.** Versions, adoption, and maintenance status below
> were verified against the npm registry and GitHub on that date.
>
> **Verify before recommending (mandatory).** Before you recommend any package
> here to a user, re-check its current state — latest publish date, open-issue
> health, whether the repo is archived. A package that was healthy at snapshot
> time may be abandoned now. Treat anything not touched in ~12 months as suspect
> and say so. Do **not** present this table as currently-accurate without that
> check.

---

## Choosing a path: hand-rolled vs. package (Step 3)

Both paths are first-class. The skill must work end-to-end on the **hand-rolled
path with zero new dependencies** — never hard-depend on a third-party package.

Default reasoning, absent a stated user preference:

- **Content is already Markdown/MDX** → prefer **hand-rolled**. No conversion is
  needed, you just serve the source, and full control is cheap. (See the
  framework references.)
- **Content is CMS-rendered HTML** → prefer a **package**. Stripping boilerplate
  and converting HTML→Markdown correctly is non-trivial to hand-roll.
- **User wants the fastest path to a working result** → prefer a package.

Always present both options and let the user (or the default above) decide.

---

## HTML → Markdown conversion (for the CMS / rendered-HTML case)

| Package | Scope | What it automates | Snapshot status (2026-06-30) | Best fit |
|---|---|---|---|---|
| **turndown** | Generic JS | DOM-based HTML→Markdown with pluggable rules | v7.2.4 (2026-04-03), ~5.97M dl/wk, MIT — mature, ubiquitous | The default converter for the actual HTML→MD step. |
| **@mozilla/readability** | Generic JS | Firefox Reader-View extraction; strips nav/header/footer/chrome, returns clean article HTML (not a converter) | v0.6.0 (2025-03-03), ~3.47M dl/wk, Apache-2.0 | The **boilerplate-stripping stage before** turndown. Pair them: readability → turndown. Run DOMPurify first on untrusted input. |
| **node-html-markdown** | Generic JS | Fast HTML→Markdown cross-compiler | v2.0.0 (2025-11-14), ~627k dl/wk, MIT | When raw conversion throughput matters more than turndown's extensibility. Lower bus factor. |
| **mdream** | Generic JS / LLM-oriented | HTML→Markdown tuned for LLMs; also produces `llms.txt` artifacts | v1.4.1 (2026-06-16), ~6.8k dl/wk, 914★ | Modern single-purpose alternative; bundles LLM cleanup. Newer/smaller than turndown but active. |

---

## Accept-header negotiation middleware (drop-in)

| Package | Ecosystem | What it automates | Snapshot status | Notes |
|---|---|---|---|---|
| **@markdown-for-agents/nextjs** (part of the `markdown-for-agents` family) | Next.js | Inspects `Accept`; on `text/markdown` converts the response to Markdown, strips nav/footer/ads/cookie banners, sets `Content-Type: text/markdown` + `Vary: Accept`; browsers pass through | v1.3.4 (2026-03-30) | **Emerging / low-adoption** — solo project, ~23★, tiny download counts. Does exactly what this skill describes, but flag it as early-stage, not a default. NOTE: `@markdown-for-agents/core` does **not** exist — only the umbrella + per-framework scoped packages. |

---

## Build-time `llms.txt` / `.md` sibling generators (Next.js)

| Package | Ecosystem | What it automates | Snapshot status | Notes |
|---|---|---|---|---|
| **fumadocs** (`fumadocs-core`, `fumadocs-mdx`) | Next.js docs framework | Built-in `llms()` source helper + `getLLMText`; documented `llms.txt`/`llms-full.txt`, raw `.mdx` serving, and Accept-header negotiation | core v16.10.7 (2026-06-29), ~755k dl/wk | Very active. The llms.txt support is a **feature of the framework**, not a separate package. If the project already uses Fumadocs, prefer its built-in support. |
| **next-llms-txt** | Next.js (16+) | Proxy plugin that generates `llms.txt` | v1.0.2 (2025-12-03) | Real, new, small. |
| **nextra** | Next.js | MDX site generator; serves raw Markdown to agents via Next config rewrites + header matching; ships a docs `llms.txt` | v4.6.1 (2025-12-04) | Active, large. The MD-serving is a config rewrite, not a dedicated API. |

---

## Next.js / Vercel: a pattern, not a package

Vercel's official content-negotiation approach for Next.js is documented as a
**code pattern** — a rewrite rule in `next.config` matching the `Accept` header
plus a route handler returning Markdown (see `references/nextjs.md`). There is no
official `@vercel/*` negotiation package. Cite the Vercel blog/KB as the source,
implement the pattern directly.

---

## Do NOT cite these (verified absent or abandoned at snapshot time)

These names appear in casual writeups but were **not** real, maintained packages
on 2026-06-30. Don't recommend them:

- `@markdown-for-agents/core` — does not exist (only the umbrella + scoped pkgs).
- bare `llms-txt`, `generate-llms-txt` — not found on npm.
- `@vercel/llms-txt`, `@vercel/agent`, `@vercel/markdown`,
  `@vercel/content-negotiation`, `next-content-negotiation` — no such packages.
- `showdown` — exists but converts **Markdown→HTML** (wrong direction).

---

## Honest default read

For a Next.js production build, the battle-tested pieces are **@mozilla/readability
→ turndown** (extract, then convert) for the CMS/HTML case, and **fumadocs**'
built-in support if the project is already a Fumadocs site. The dedicated
Accept-negotiation package (`@markdown-for-agents/nextjs`) does exactly what this
skill is about but is early-stage as of the snapshot — list it as "purpose-built,
emerging," not a default. When the content is already Markdown/MDX, no package
beats just serving the source via the hand-rolled rewrite in `references/nextjs.md`.

*Open question for maintainers (PRD §14.1): whether to add a periodic CI job that
checks each listed package's latest release date. v1 relies on the
verify-before-recommending instruction above; revisit if the table grows.*
