#!/usr/bin/env python3
"""validate_skill.py — contributor/CI validator for the SKILL.md structure
(PRD Section 8.5).

Checks performed:
  HARD ERRORS (exit non-zero):
    * SKILL.md exists and frontmatter is delimited by `---` ... `---`.
    * `name` present, 1–64 chars, lowercase-hyphenated (no leading/trailing or
      consecutive hyphens).
    * `description` present and non-empty.
    * Every file under references/ is referenced somewhere in SKILL.md
      (an orphaned reference file is never loaded by the agent — a silent bug).

  WARNINGS (printed, do not fail the build):
    * `name` does not match the containing folder. NOTE: this is intentionally a
      warning, not a hard error, because the local dev checkout may be named
      differently from the skill (e.g. while the GitHub repo is renamed at
      publish time). The published repo/skill folder SHOULD be named exactly the
      `name` value so the layout is spec-clean.
    * `description` suspiciously short (< 40 chars) or over the 1024-char spec cap.
    * SKILL.md exceeds the ~500-line progressive-disclosure guideline.
    * `name` contains a reserved word ("anthropic"/"claude") — rejected by some
      agents (Anthropic's), so avoid for portability.

Standard library only.

Usage:
    python3 scripts/validate_skill.py [path-to-skill-dir]   # defaults to cwd
"""

import os
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MIN_DESCRIPTION = 40
MAX_BODY_LINES = 500
RESERVED_WORDS = ("anthropic", "claude")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.oks = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def ok(self, msg):
        self.oks.append(msg)


def parse_frontmatter(text):
    """Return (frontmatter_dict, error_or_None).

    Minimal YAML-ish parser: handles top-level `key: value` and block scalars
    (`>`, `>-`, `|`, `|-`, or an empty value followed by an indented block).
    Sufficient for validating `name` and `description`; not a full YAML parser.
    """
    # Tolerate a leading BOM / blank lines before the opening fence.
    stripped = text.lstrip("﻿")
    lines = stripped.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, "SKILL.md does not start with a '---' frontmatter fence."

    # Find the closing fence.
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, "SKILL.md frontmatter is not closed with a '---' fence."

    body = lines[1:end]
    data = {}
    i = 0
    while i < len(body):
        line = body[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):(.*)$", line)
        if not m or line[0] in " \t":
            i += 1
            continue
        key = m.group(1)
        rest = m.group(2).strip()
        if rest in (">", ">-", "|", "|-", ">+", "|+", ""):
            # Block scalar (or nested mapping). Gather indented continuation.
            collected = []
            j = i + 1
            while j < len(body):
                nxt = body[j]
                if nxt.strip() == "":
                    collected.append("")
                    j += 1
                    continue
                if nxt[0] in " \t":
                    collected.append(nxt.strip())
                    j += 1
                else:
                    break
            data[key] = " ".join(c for c in collected if c).strip()
            i = j
        else:
            data[key] = rest.strip().strip("'\"")
            i += 1
    return data, None


def referenced_files(skill_dir, rep):
    """Hard-error on any references/*.md not mentioned in SKILL.md."""
    ref_dir = os.path.join(skill_dir, "references")
    if not os.path.isdir(ref_dir):
        rep.ok("No references/ directory (nothing to cross-check).")
        return
    skill_text = ""
    skill_path = os.path.join(skill_dir, "SKILL.md")
    if os.path.isfile(skill_path):
        with open(skill_path, "r", encoding="utf-8", errors="replace") as fh:
            skill_text = fh.read()
    ref_files = sorted(
        f for f in os.listdir(ref_dir) if f.endswith(".md"))
    if not ref_files:
        rep.ok("references/ exists but contains no .md files.")
        return
    for fname in ref_files:
        # A reference is "linked" if its filename or relative path appears.
        if fname in skill_text or ("references/" + fname) in skill_text:
            rep.ok("references/%s is linked from SKILL.md." % fname)
        else:
            rep.error(
                "references/%s is NOT referenced anywhere in SKILL.md — it "
                "will never be loaded (orphaned reference)." % fname)


def main(argv):
    skill_dir = argv[1] if len(argv) > 1 else "."
    skill_dir = os.path.abspath(skill_dir)
    rep = Report()

    skill_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_path):
        sys.stderr.write("error: no SKILL.md found in %s\n" % skill_dir)
        return 1

    with open(skill_path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    fm, err = parse_frontmatter(text)
    if err:
        rep.error(err)
        fm = {}
    else:
        rep.ok("Frontmatter is fenced correctly.")

    # --- name ----------------------------------------------------------------
    name = fm.get("name", "")
    if not name:
        rep.error("Frontmatter is missing the required `name` field.")
    else:
        if len(name) > MAX_NAME:
            rep.error("`name` is %d chars; max is %d." % (len(name), MAX_NAME))
        if not NAME_RE.match(name):
            rep.error(
                "`name` '%s' is not lowercase-hyphenated (a-z, 0-9, single "
                "hyphens, no leading/trailing hyphen)." % name)
        else:
            rep.ok("`name` '%s' is well-formed." % name)
        for word in RESERVED_WORDS:
            if word in name:
                rep.warn(
                    "`name` contains reserved word '%s' — rejected by some "
                    "agents; avoid for portability." % word)
        folder = os.path.basename(skill_dir)
        if name != folder:
            rep.warn(
                "`name` '%s' does not match the containing folder '%s'. The "
                "published skill folder/repo should be named '%s' to be "
                "spec-clean." % (name, folder, name))
        else:
            rep.ok("`name` matches the containing folder.")

    # --- description ---------------------------------------------------------
    desc = fm.get("description", "")
    if not desc:
        rep.error("Frontmatter is missing the required `description` field.")
    else:
        if len(desc) < MIN_DESCRIPTION:
            rep.warn(
                "`description` is only %d chars — too short to convey what the "
                "skill does AND when to trigger it." % len(desc))
        elif len(desc) > MAX_DESCRIPTION:
            rep.warn(
                "`description` is %d chars, over the %d-char spec cap; it may "
                "be truncated by some agents." % (len(desc), MAX_DESCRIPTION))
        else:
            rep.ok("`description` present (%d chars)." % len(desc))

    # --- body line count -----------------------------------------------------
    line_count = text.count("\n") + 1
    if line_count > MAX_BODY_LINES:
        rep.warn(
            "SKILL.md is %d lines, over the ~%d-line progressive-disclosure "
            "guideline. Move detail into references/." % (line_count, MAX_BODY_LINES))
    else:
        rep.ok("SKILL.md is %d lines (within the ~%d-line guideline)."
               % (line_count, MAX_BODY_LINES))

    # --- orphaned references -------------------------------------------------
    referenced_files(skill_dir, rep)

    # --- output --------------------------------------------------------------
    for msg in rep.oks:
        print("  ok    %s" % msg)
    for msg in rep.warnings:
        print("  WARN  %s" % msg)
    for msg in rep.errors:
        print("  ERROR %s" % msg)

    print("\n%d ok, %d warning(s), %d error(s)"
          % (len(rep.oks), len(rep.warnings), len(rep.errors)))

    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
