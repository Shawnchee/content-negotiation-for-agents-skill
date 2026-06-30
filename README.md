# content-negotiation-for-agents

An [Agent Skill](https://agentskills.io) that takes you from *"I want AI agents
to read my site efficiently"* to a working, **verified** implementation of HTTP
**content negotiation** — serving clean Markdown to agents via the `Accept`
header, while browsers keep getting normal HTML from the **same URL**.

A negotiated Markdown page drops the nav, scripts, styles, and cookie banners an
agent never wanted, so it costs a fraction of the context and tokens of the
equivalent HTML page.

> **What it touches, before you install it sight-unseen:** this skill **never**
> edits a route you didn't explicitly confirm. It detects your project read-only,
> asks which pages to mirror (defaulting to public docs/blog/changelog content,
> never authenticated routes), and verifies its own work with a live HTTP request
> before reporting done. See [Why scoping is mandatory](#why-scoping-is-mandatory).

## What it does

- Detects your framework (Next.js, Express/Fastify/Hono, Astro/Hugo/Jekyll) and
  your content sections — **read-only**.
- Asks which pages to target, and pushes back if you ask for authenticated or
  whole-site scope.
- Implements negotiation the right way for your framework (request-time rewrite,
  middleware, or build-time `.md` siblings).
- Adds discovery: `llms.txt`, per-section Markdown sitemaps, and
  `<link rel="alternate" type="text/markdown">` tags.
- Verifies every scoped URL with a real request and reports **measured** byte
  savings — not a number copied from a blog post.

## What it does NOT do

- It does not touch authenticated/dashboard/checkout routes without explicit,
  per-route confirmation.
- It is not a "make my whole site AI-optimized" tool. `robots.txt` for AI
  crawlers, JSON-LD, and general AEO/SEO are out of scope.
- It does not lock you into a third-party package — the hand-rolled, zero-new-deps
  path is fully supported.

## Install

This skill installs straight from this public GitHub repo — no registry
submission:

```sh
# Project scope (./.claude/skills/, ./.agents/skills/, etc.)
npx skills add Shawnchee/content-negotiation-for-agents-skill

# Personal/global scope (~/.claude/skills/, ~/.agents/skills/)
npx skills add -g Shawnchee/content-negotiation-for-agents-skill
```

The `npx skills` CLI installs to each target agent's skills directory:
`.claude/skills/` for Claude Code, `.agents/skills/` for Codex CLI (Codex's
official convention; the third-party CLI path is still settling — verify with
`npx skills add ... -a codex --list` if you rely on it). The skill's frontmatter
`name` matches the repo, so it installs as `content-negotiation-for-agents-skill`.

## Use

Once installed, just describe your intent to your agent:

> "Make my blog readable by AI agents."
> "Add `text/markdown` content negotiation to my docs."
> "Generate an `llms.txt` and markdown versions of my changelog."

The skill activates on those triggers and walks the six-step workflow below,
stopping to confirm scope before it changes anything.

## The workflow

1. **Detect** the framework and content sections (`scripts/detect_framework.py`,
   read-only).
2. **Ask** which pages to target — mandatory, with reasoning. Defaults to public
   content; flags sensitive routes.
3. **Choose** hand-rolled vs. a drop-in package (trade-offs presented).
4. **Implement** per your framework, always setting `Content-Type: text/markdown`
   and `Vary: Accept`, preserving structure.
5. **Add discovery** — `llms.txt`, Markdown sitemaps, `rel=alternate` tags.
6. **Verify** with a live request (`scripts/verify_negotiation.sh`); a failure is
   blocking.

## Why scoping is mandatory

A negotiated Markdown route is a **distinct HTTP endpoint**. It does **not**
inherit the authentication middleware of the HTML page it mirrors. A skill that
blindly applied negotiation site-wide could expose authenticated content to
anyone who sends `Accept: text/markdown`. So Step 2 is non-skippable: the skill
defaults to public content and requires explicit, per-route confirmation for
anything flagged sensitive — even if you say "just do the whole site."

## Supported frameworks (v1)

| Framework | Pattern |
|---|---|
| Next.js — App Router, server-rendered | `Accept`-header rewrite → Markdown route handler |
| Next.js — static export (`output: 'export'`) | Build-time `.md` siblings + `rel=alternate` |
| Express / Fastify / Hono / generic Node | Middleware on `Accept` |
| Astro / Hugo / Jekyll / static generators | Build-time `.md` siblings + `rel=alternate` |

Likely next: SvelteKit, Django, Rails.

## Repository layout

```
content-negotiation-for-agents-skill/
├── SKILL.md                     # the skill (loaded by the agent)
├── README.md                    # this file
├── LICENSE                      # MIT
├── references/                  # loaded on demand by the skill
│   ├── nextjs.md
│   ├── express-fastify-hono.md
│   ├── astro-and-static-sites.md
│   ├── packages-comparison.md   # living snapshot — verify before recommending
│   └── llms-txt-and-sitemaps.md
├── scripts/
│   ├── detect_framework.py      # Step 1 — read-only, stdlib only
│   ├── verify_negotiation.sh    # Step 6 — curl + POSIX shell only
│   └── validate_skill.py        # contributor/CI validator
├── evals/
│   └── evals.json               # happy-path + scoping-judgment test prompts
└── .github/workflows/
    └── validate-skill.yml       # CI: validate + JSON + shell syntax checks
```

## Cross-agent portability

Written and tested against **Claude Code** and **Codex CLI**. The frontmatter
uses only standard fields (`name`, `description`, `license`, `compatibility`,
`metadata`) so it degrades gracefully on any conformant agent. Bundled tooling
uses only the Python standard library and POSIX `curl`/shell — installing the
skill pulls in no dependency tree of its own.

## Tooling

```sh
python3 scripts/detect_framework.py <path-to-repo>     # JSON report, read-only
scripts/verify_negotiation.sh <base-url> <path> [...]  # live check, non-zero on failure
python3 scripts/validate_skill.py .                    # validate this skill's structure
```

## Distribution

- **GitHub** is canonical (this repo, MIT).
- **skills.sh** indexes public repos automatically via the `npx skills` install
  telemetry — no manual submission. *(Re-verify these mechanics before a release;
  this ecosystem moves quickly.)*
- **Secondary directories**: skills.sh and LobeHub auto-index (topic-tag the repo
  `agent-skills`, `claude-skills`, `codex-skills`); Awesome Claude Skills takes a
  manual PR.

## Contributing

CI (`.github/workflows/validate-skill.yml`) runs on every push/PR and checks:
`validate_skill.py` passes, `evals/evals.json` is valid JSON, shell scripts pass
`sh -n`, Python scripts compile, and the detector smoke-test passes. Add a
happy-path **and** a scoping-judgment eval for any new framework.

## License

MIT — see [LICENSE](LICENSE).
