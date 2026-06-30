#!/usr/bin/env python3
"""detect_framework.py — read-only repo scanner for the
content-negotiation-for-agents skill (Step 1: Detect the project).

Identifies the web framework, routing/rendering mode, and candidate content
directories in a target repository, then prints a JSON report to stdout.

Design constraints (see PRD Section 8.3):
  * Standard library only — no third-party imports, so installing the skill
    never pulls in a dependency tree just to run its own tooling.
  * Read-only — this script must never create or modify a file in the target
    repo. It only reads.
  * Skips node_modules and .git (and other build/output dirs) when walking.
  * On an undetectable framework it reports {"framework": "unknown"} and still
    exits 0. The *caller* (the skill body) decides what to do with "unknown"
    (ask the user directly) — the script does not guess.

Usage:
    python3 scripts/detect_framework.py <path-to-repo>

Output (stdout): a single JSON object. Example:
    {
      "framework": "nextjs",
      "framework_family": "nextjs",
      "router": "app",
      "rendering_mode": "server",
      "recommended_reference": "references/nextjs.md",
      "detected_dependencies": ["next", "react"],
      "candidate_content_dirs": [
        {"path": "app/blog", "approx_page_count": 12,
         "likely_markdown_source": true, "markdown_files": 12, "html_files": 0}
      ],
      "notes": []
    }
"""

import json
import os
import re
import sys

# Directories we never descend into: dependency trees, VCS metadata, and build
# output. We want *source* content dirs, not generated ones.
SKIP_DIRS = {
    "node_modules", ".git", ".hg", ".svn", ".next", ".nuxt", ".svelte-kit",
    ".astro", ".vercel", ".netlify", ".cache", ".turbo", ".parcel-cache",
    "dist", "build", "out", "public", "coverage", "vendor", "target",
    "__pycache__", ".venv", "venv", ".idea", ".vscode", "tmp", ".tmp",
}

# Directory base-names that commonly hold public, high-information-density
# content — the good-fit candidates for content negotiation (PRD Section 6.1).
CONTENT_SECTION_NAMES = {
    "blog", "blogs", "docs", "doc", "documentation", "changelog", "changelogs",
    "help", "guides", "guide", "kb", "knowledge-base", "knowledgebase",
    "support", "faq", "faqs", "news", "articles", "posts", "_posts",
    "tutorials", "tutorial", "wiki",
}

# Base-names that hint at authenticated / sensitive areas. We surface these as a
# warning so the skill's mandatory scoping step (PRD Section 6.2 / 8.7) can flag
# them — content negotiation must NOT be applied to these without explicit,
# per-route confirmation.
SENSITIVE_SECTION_NAMES = {
    "dashboard", "dashboards", "admin", "account", "accounts", "settings",
    "billing", "checkout", "payment", "payments", "auth", "login", "signin",
    "signup", "register", "console", "portal", "profile", "user",
    "users", "members", "internal", "private",
}
# Note: "app" and "api" are deliberately excluded — they are normal framework
# directories (Next.js app/ router, api/ routes), so flagging them as sensitive
# is noise. Sensitive *content* routes (dashboard, account, billing, ...) are
# what Step 2 needs surfaced.

MARKDOWN_EXTS = {".md", ".mdx", ".markdown", ".mdoc"}
HTML_EXTS = {".html", ".htm"}
# Extensions we count toward an approximate "page count" for a content dir.
CONTENT_EXTS = MARKDOWN_EXTS | HTML_EXTS | {
    ".astro", ".njk", ".liquid", ".haml", ".erb", ".vue", ".svelte",
}


def read_text_safe(path):
    """Read a text file, returning '' on any error. Never raises."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, UnicodeError):
        return ""


def load_package_json(repo):
    """Return (dependency_names:set, raw_dict) or (set(), None) if absent/bad."""
    pkg_path = os.path.join(repo, "package.json")
    if not os.path.isfile(pkg_path):
        return set(), None
    raw = read_text_safe(pkg_path)
    if not raw.strip():
        return set(), None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return set(), None
    deps = set()
    for key in ("dependencies", "devDependencies", "peerDependencies",
                "optionalDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section.keys())
    return deps, data


def first_existing(repo, *relpaths):
    """Return the first relpath (from the args) that exists in repo, else None."""
    for rel in relpaths:
        if os.path.exists(os.path.join(repo, rel)):
            return rel
    return None


def find_next_config(repo):
    for name in ("next.config.ts", "next.config.js", "next.config.mjs",
                 "next.config.cjs"):
        p = os.path.join(repo, name)
        if os.path.isfile(p):
            return read_text_safe(p)
    return None


def detect_nextjs(repo, deps, notes):
    """Return (router, rendering_mode) for a Next.js repo."""
    # Router: App Router (app/) vs Pages Router (pages/). Either may sit under src/.
    has_app = first_existing(repo, "app", "src/app")
    has_pages = first_existing(repo, "pages", "src/pages")
    if has_app and has_pages:
        router = "app"  # App Router takes precedence when both exist
        notes.append("Both app/ and pages/ present; assuming App Router is primary.")
    elif has_app:
        router = "app"
    elif has_pages:
        router = "pages"
    else:
        router = None
        notes.append("Next.js detected but neither app/ nor pages/ found.")

    rendering_mode = "server"
    cfg = find_next_config(repo)
    if cfg:
        # Look for output: 'export' (single or double quotes, any spacing).
        if re.search(r"""output\s*:\s*['"]export['"]""", cfg):
            rendering_mode = "static_export"
    return router, rendering_mode


def detect_astro(repo, notes):
    """Return rendering_mode for an Astro repo (static unless output server/hybrid)."""
    for name in ("astro.config.ts", "astro.config.mjs", "astro.config.js",
                 "astro.config.cjs"):
        p = os.path.join(repo, name)
        if os.path.isfile(p):
            cfg = read_text_safe(p)
            if re.search(r"""output\s*:\s*['"](server|hybrid)['"]""", cfg):
                return "server"
            return "static"
    return "static"


def detect_framework(repo, notes):
    """Identify the framework. Returns a dict of framework facts (no content dirs)."""
    deps, _ = load_package_json(repo)

    # --- Next.js -------------------------------------------------------------
    if "next" in deps:
        router, rendering_mode = detect_nextjs(repo, deps, notes)
        return {
            "framework": "nextjs",
            "framework_family": "nextjs",
            "router": router,
            "rendering_mode": rendering_mode,
            "recommended_reference": "references/nextjs.md",
            "detected_dependencies": sorted(d for d in deps if d in {"next", "react"}),
        }

    # --- Astro ---------------------------------------------------------------
    astro_cfg = first_existing(
        repo, "astro.config.ts", "astro.config.mjs", "astro.config.js",
        "astro.config.cjs")
    if "astro" in deps or astro_cfg:
        return {
            "framework": "astro",
            "framework_family": "static-site",
            "router": None,
            "rendering_mode": detect_astro(repo, notes),
            "recommended_reference": "references/astro-and-static-sites.md",
            "detected_dependencies": sorted(d for d in deps if d == "astro"),
        }

    # --- Generic Node servers (Express / Fastify / Hono) ---------------------
    for server_dep, label in (("express", "express"), ("fastify", "fastify"),
                              ("hono", "hono")):
        if server_dep in deps:
            return {
                "framework": label,
                "framework_family": "node-server",
                "router": None,
                "rendering_mode": "server",
                "recommended_reference": "references/express-fastify-hono.md",
                "detected_dependencies": sorted(
                    d for d in deps if d in {"express", "fastify", "hono"}),
            }

    # --- Other JS static generators (mapped to the static-site reference) ----
    js_static = {
        "@11ty/eleventy": "eleventy",
        "gatsby": "gatsby",
        "@sveltejs/kit": "sveltekit",
        "vitepress": "vitepress",
        "nextra": "nextra",
    }
    for dep, label in js_static.items():
        if dep in deps:
            return {
                "framework": label,
                "framework_family": "static-site",
                "router": None,
                "rendering_mode": "static",
                "recommended_reference": "references/astro-and-static-sites.md",
                "detected_dependencies": [dep],
            }

    # --- Hugo (no package.json) ---------------------------------------------
    hugo_cfg = first_existing(repo, "hugo.toml", "hugo.yaml", "hugo.json",
                              "config.toml", "config/_default")
    if hugo_cfg and (os.path.isdir(os.path.join(repo, "content"))
                     or os.path.isdir(os.path.join(repo, "archetypes"))):
        return {
            "framework": "hugo",
            "framework_family": "static-site",
            "router": None,
            "rendering_mode": "static",
            "recommended_reference": "references/astro-and-static-sites.md",
            "detected_dependencies": [],
        }

    # --- Jekyll (no package.json) -------------------------------------------
    jekyll_cfg = first_existing(repo, "_config.yml", "_config.yaml")
    has_gemfile_jekyll = "jekyll" in read_text_safe(
        os.path.join(repo, "Gemfile")).lower()
    if (jekyll_cfg and os.path.isdir(os.path.join(repo, "_posts"))) \
            or has_gemfile_jekyll:
        return {
            "framework": "jekyll",
            "framework_family": "static-site",
            "router": None,
            "rendering_mode": "static",
            "recommended_reference": "references/astro-and-static-sites.md",
            "detected_dependencies": [],
        }

    # --- Unknown -------------------------------------------------------------
    notes.append(
        "No recognizable framework markers found. The skill must ask the user "
        "directly which framework and which pages to target.")
    return {
        "framework": "unknown",
        "framework_family": "unknown",
        "router": None,
        "rendering_mode": "unknown",
        "recommended_reference": None,
        "detected_dependencies": sorted(deps),
    }


def count_content(dir_path):
    """Walk a directory and tally content files. Returns (total, md, html)."""
    total = md = html = 0
    for root, dirnames, filenames in os.walk(dir_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in CONTENT_EXTS:
                total += 1
                if ext in MARKDOWN_EXTS:
                    md += 1
                elif ext in HTML_EXTS:
                    html += 1
    return total, md, html


def find_content_dirs(repo):
    """Walk the repo for directories matching known content-section names.

    Returns (candidates, sensitive_hits). Each candidate is a dict with path,
    approx_page_count, likely_markdown_source, markdown_files, html_files.
    sensitive_hits is a list of relative paths flagged as possibly auth/sensitive.
    """
    candidates = []
    sensitive_hits = []
    seen = set()
    for root, dirnames, _ in os.walk(repo):
        # Prune skip dirs in place so we never descend into them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in dirnames:
            base = d.lower()
            full = os.path.join(root, d)
            rel = os.path.relpath(full, repo)
            if base in SENSITIVE_SECTION_NAMES and rel not in sensitive_hits:
                sensitive_hits.append(rel)
            if base in CONTENT_SECTION_NAMES and rel not in seen:
                seen.add(rel)
                total, md, html = count_content(full)
                candidates.append({
                    "path": rel,
                    "approx_page_count": total,
                    "likely_markdown_source": md > 0 and md >= html,
                    "markdown_files": md,
                    "html_files": html,
                })
    candidates.sort(key=lambda c: c["path"])
    sensitive_hits.sort()
    return candidates, sensitive_hits


def main(argv):
    if len(argv) != 2:
        sys.stderr.write(
            "usage: python3 detect_framework.py <path-to-repo>\n")
        return 2
    repo = argv[1]
    if not os.path.isdir(repo):
        sys.stderr.write("error: not a directory: %s\n" % repo)
        return 2

    notes = []
    report = detect_framework(repo, notes)
    candidates, sensitive_hits = find_content_dirs(repo)
    report["candidate_content_dirs"] = candidates
    report["sensitive_dirs_flagged"] = sensitive_hits
    report["notes"] = notes

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
