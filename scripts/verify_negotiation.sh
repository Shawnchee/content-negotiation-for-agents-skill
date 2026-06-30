#!/bin/sh
# verify_negotiation.sh — live HTTP verification for the
# content-negotiation-for-agents skill (Step 6: Verify).
#
# For each path, issues two real requests against a running server — one with
# `Accept: text/html` and one with `Accept: text/markdown` — and checks the
# Markdown response:
#   * Content-Type contains `text/markdown`  (HARD gate — failure exits non-zero)
#   * Vary contains `Accept`                 (soft — missing is WARNED, not fatal)
# It also measures and prints the actual byte-size difference between the two
# responses (never an assumed or copied percentage).
#
# Design constraints (PRD Section 8.4):
#   * curl + POSIX shell only. No framework assumptions. No extra dependencies.
#   * Exit code is non-zero if ANY path fails the Content-Type check, so this
#     can gate CI/automation, not just produce a human-readable report.
#
# Usage:
#   verify_negotiation.sh <base-url> <path-1> [path-2] ...
#
# Example:
#   verify_negotiation.sh http://localhost:3000 /blog /blog/hello-world /docs
#
# Environment:
#   MD_ACCEPT   Override the Markdown Accept header (default: text/markdown).
#   ACCEPT_HTML Override the HTML Accept header (default: text/html).

set -u

MD_ACCEPT="${MD_ACCEPT:-text/markdown}"
ACCEPT_HTML="${ACCEPT_HTML:-text/html}"
UA="content-negotiation-verify/1.0"

if ! command -v curl >/dev/null 2>&1; then
    echo "error: curl is required but was not found on PATH" >&2
    exit 2
fi

if [ "$#" -lt 2 ]; then
    echo "usage: verify_negotiation.sh <base-url> <path-1> [path-2] ..." >&2
    exit 2
fi

BASE_URL="$1"
shift

# Strip a single trailing slash from the base URL so joining is predictable.
case "$BASE_URL" in
    */) BASE_URL="${BASE_URL%/}" ;;
esac

TMPDIR_VN="$(mktemp -d 2>/dev/null || mktemp -d -t cnv)"
# Best-effort cleanup of temp files on any exit.
trap 'rm -rf "$TMPDIR_VN"' EXIT INT TERM

fail_count=0
warn_count=0
pass_count=0

# header_value <headers-file> <header-name>
# Prints the value of the LAST occurrence of the named header (last wins after
# redirects), with CR stripped and leading spaces trimmed.
header_value() {
    grep -i "^$2:" "$1" 2>/dev/null \
        | tail -n 1 \
        | cut -d: -f2- \
        | tr -d '\r' \
        | sed 's/^[[:space:]]*//'
}

# byte_size <file> — prints the byte count of a file (0 if missing).
byte_size() {
    if [ -f "$1" ]; then
        wc -c < "$1" | tr -d '[:space:]'
    else
        echo 0
    fi
}

echo "Content negotiation verification"
echo "Base URL: $BASE_URL"
echo "Markdown Accept: $MD_ACCEPT"
echo "--------------------------------------------------------------------"

for path in "$@"; do
    # Normalize the path so it has exactly one leading slash.
    case "$path" in
        /*) url="$BASE_URL$path" ;;
        *)  url="$BASE_URL/$path" ;;
    esac

    html_headers="$TMPDIR_VN/html.h"
    html_body="$TMPDIR_VN/html.b"
    md_headers="$TMPDIR_VN/md.h"
    md_body="$TMPDIR_VN/md.b"

    # --- HTML request ----------------------------------------------------
    curl -sS -L -A "$UA" -H "Accept: $ACCEPT_HTML" \
        -D "$html_headers" -o "$html_body" "$url" 2>"$TMPDIR_VN/html.err"
    html_curl_rc=$?

    # --- Markdown request ------------------------------------------------
    curl -sS -L -A "$UA" -H "Accept: $MD_ACCEPT" \
        -D "$md_headers" -o "$md_body" "$url" 2>"$TMPDIR_VN/md.err"
    md_curl_rc=$?

    if [ "$md_curl_rc" -ne 0 ]; then
        echo "[FAIL] $path"
        echo "       request error: $(cat "$TMPDIR_VN/md.err")"
        fail_count=$((fail_count + 1))
        echo
        continue
    fi

    md_ctype="$(header_value "$md_headers" "content-type")"
    md_vary="$(header_value "$md_headers" "vary")"
    md_status="$(grep -i '^HTTP/' "$md_headers" | tail -n 1 | tr -d '\r')"

    html_bytes="$(byte_size "$html_body")"
    md_bytes="$(byte_size "$md_body")"

    # --- Content-Type: the hard gate -------------------------------------
    if echo "$md_ctype" | grep -iq 'text/markdown'; then
        ctype_ok=1
    else
        ctype_ok=0
    fi

    # --- Vary: Accept: soft check ----------------------------------------
    if echo "$md_vary" | grep -iq 'accept'; then
        vary_ok=1
    else
        vary_ok=0
    fi

    # --- Byte-size delta from ACTUAL response bodies ---------------------
    reduction="$(awk -v h="$html_bytes" -v m="$md_bytes" 'BEGIN{
        if (h > 0) printf "%.1f", ((h - m) / h) * 100; else printf "n/a"
    }')"

    if [ "$ctype_ok" -eq 1 ]; then
        status_label="[OK]"
        pass_count=$((pass_count + 1))
    else
        status_label="[FAIL]"
        fail_count=$((fail_count + 1))
    fi

    echo "$status_label $path"
    echo "       status:        ${md_status:-<none>}"
    echo "       Content-Type:  ${md_ctype:-<missing>}"
    if [ "$ctype_ok" -ne 1 ]; then
        echo "       -> expected Content-Type to contain 'text/markdown'"
    fi
    if [ "$vary_ok" -eq 1 ]; then
        echo "       Vary:          ${md_vary}"
    else
        echo "       Vary:          <missing 'Accept'>  (WARNING: caches may serve the wrong representation)"
        warn_count=$((warn_count + 1))
    fi
    echo "       HTML bytes:    $html_bytes"
    echo "       Markdown bytes:$md_bytes"
    if [ "$reduction" != "n/a" ]; then
        echo "       Size reduction:${reduction}% (measured, $((html_bytes - md_bytes)) bytes saved)"
    else
        echo "       Size reduction:n/a (HTML response was empty)"
    fi
    echo
done

echo "--------------------------------------------------------------------"
echo "Passed: $pass_count   Failed: $fail_count   Warnings: $warn_count"

if [ "$fail_count" -gt 0 ]; then
    echo "RESULT: FAILED — at least one path did not return text/markdown." >&2
    exit 1
fi

echo "RESULT: PASSED — all paths negotiated text/markdown."
exit 0
