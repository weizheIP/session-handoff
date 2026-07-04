#!/usr/bin/env python3
"""Label audit (session-handoff Phase 0) — loose mode, blocking with escape hatch.

Scans markdown file(s) for code -> human-label mapping tables (e.g. Salesforce
status codes, HTTP-status legends, enum descriptions) and flags every table row
that does not carry one of the inline provenance tags:

  [verified: <repo-relative-path>:<line>]   label confirmed against an
                                            authoritative source
  [HYPOTHESIS]                              label is a guess; receiving session
                                            must re-probe

This is the author-side gate that prevents the "predecessor handoff fabricates
semantic labels" failure mode: untagged rows BLOCK the handoff until tagged.

Escape hatch: a document may set frontmatter `label-audit-skipped: <reason>`
to bypass the audit for that file (e.g. a retrospective reference quoting an
old fabricated table). The skip reason is printed so the receiving session
knows to treat ALL labels in that doc as unverified.

Exit codes:
  0  clean — no code-legend rows detected, or every flagged row is tagged
  1  blocking — at least one untagged row (offending rows are printed)
  2  skipped via frontmatter (and no violations in non-skipped files)

The table detector is a deliberately loose heuristic (false positives cost a
30-second frontmatter ack; false negatives cost a fabricated label shipping to
a client — the asymmetry is by design).
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Inline provenance tags
VERIFIED_RE = re.compile(r"\[verified:\s*[^\]\s][^\]]*:\d+\s*\]")
HYPOTHESIS_RE = re.compile(r"\[HYPOTHESIS\]", re.IGNORECASE)

# A "code-like" cell: short identifier, no spaces — e.g. `AD`, `404`,
# `IN_PROGRESS`, `ERR-42`. Backticks are stripped before matching.
CODE_CELL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,23}$")
# Pure small integers (1-2 digits) are usually ordinals (numbered lists,
# priority columns), not status codes. HTTP codes (3 digits) still match.
# Pure numeric ranges ("1-4", "19-25") are step/line ranges, not codes.
ORDINAL_RE = re.compile(r"^(\d{1,2}|\d+[-–]\d+)$")

# Header words that suggest a code -> label legend
HEADER_HINTS = re.compile(
    r"\b(code|status|value|enum|label|abbrev|abbreviation|meaning|legend|symbol|flag)\b",
    re.IGNORECASE,
)

FRONTMATTER_SKIP_RE = re.compile(
    r"^label-audit-skipped:\s*(.+)$", re.MULTILINE
)


def split_row(line):
    """Split a markdown table row into stripped cells."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator_row(line):
    s = line.strip().strip("|").strip()
    return bool(s) and bool(re.fullmatch(r"[:\-| ]+", s)) and "-" in s


def is_code_cell(cell):
    """True if the cell looks like a machine code / identifier."""
    stripped = cell.strip()
    backticked = stripped.startswith("`") and stripped.endswith("`") and len(stripped) > 2
    if backticked:
        stripped = stripped[1:-1].strip()
    if not stripped or " " in stripped:
        return False
    if not CODE_CELL_RE.match(stripped):
        return False
    if ORDINAL_RE.match(stripped):
        return False
    # Require some "code" signal: uppercase, digit, underscore/dot/dash,
    # or explicit backticks — a plain lowercase word ("yes", "done") is prose.
    if backticked:
        return True
    return bool(re.search(r"[A-Z0-9_.\-]", stripped))


def is_label_cell(cell):
    """True if the cell looks like a human-facing label/description."""
    words = [w for w in re.split(r"\s+", cell.strip()) if re.search(r"[A-Za-z]", w)]
    return len(words) >= 2


def extract_frontmatter_skip(text):
    """Return the skip reason if frontmatter sets label-audit-skipped."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = text[3:end]
    m = FRONTMATTER_SKIP_RE.search(fm)
    return m.group(1).strip() if m else None


def find_tables(lines):
    """Yield (header_idx, [body_row_indices]) for each markdown table."""
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < n and is_separator_row(lines[i + 1]):
            header_idx = i
            body = []
            j = i + 2
            while j < n and lines[j].lstrip().startswith("|"):
                body.append(j)
                j += 1
            yield header_idx, body
            i = j
        else:
            i += 1


def audit_table(lines, header_idx, body_idxs):
    """Return untagged-row violations if this table is a code->label legend."""
    header_cells = split_row(lines[header_idx])
    rows = [(idx, split_row(lines[idx])) for idx in body_idxs]
    if not rows:
        return []

    ncols = max(len(header_cells), max(len(c) for _, c in rows))
    # Find a column that is code-like in a majority of rows, with a
    # human-label cell present somewhere else in the same rows.
    best_col = None
    best_hits = 0
    for col in range(ncols):
        hits = 0
        for _, cells in rows:
            if col < len(cells) and is_code_cell(cells[col]) and any(
                is_label_cell(c) for k, c in enumerate(cells) if k != col
            ):
                hits += 1
        if hits > best_hits:
            best_hits, best_col = hits, col

    header_hint = any(HEADER_HINTS.search(h) for h in header_cells)
    majority = best_hits >= max(2, (len(rows) + 1) // 2)
    # A hinted header (Code/Status/...) lowers the bar, but a single code-like
    # row in an otherwise prose table is noise — require at least 2 either way.
    hinted = header_hint and best_hits >= 2
    if best_col is None or not (majority or hinted):
        return []  # not a code->label legend

    violations = []
    for idx, cells in rows:
        if best_col >= len(cells) or not is_code_cell(cells[best_col]):
            continue  # not a mapping row (spanning note, blank code, etc.)
        row_text = lines[idx]
        if VERIFIED_RE.search(row_text) or HYPOTHESIS_RE.search(row_text):
            continue
        violations.append({
            "line": idx + 1,
            "code": cells[best_col],
            "row": row_text.rstrip(),
        })
    return violations


def audit_file(path):
    """Audit one markdown file. Returns a result dict."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    skip_reason = extract_frontmatter_skip(text)
    if skip_reason is not None:
        return {"path": str(path), "status": "skipped",
                "skip_reason": skip_reason, "violations": []}
    lines = text.splitlines()
    violations = []
    for header_idx, body_idxs in find_tables(lines):
        violations.extend(audit_table(lines, header_idx, body_idxs))
    status = "violations" if violations else "clean"
    return {"path": str(path), "status": status, "violations": violations}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Audit markdown file(s) for code->human-label tables whose rows "
            "lack [verified: path:line] / [HYPOTHESIS] provenance tags "
            "(session-handoff Phase 0)."
        ),
        epilog=(
            "Exit codes: 0 clean, 1 untagged rows found (blocking), "
            "2 skipped via `label-audit-skipped:` frontmatter."
        ),
    )
    parser.add_argument("files", nargs="+", metavar="FILE.md",
                        help="markdown file(s) to audit")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of text")
    args = parser.parse_args(argv)

    results = []
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"label_audit: file not found: {f}", file=sys.stderr)
            return 1
        results.append(audit_file(p))

    any_violations = any(r["status"] == "violations" for r in results)
    any_skipped = any(r["status"] == "skipped" for r in results)
    exit_code = 1 if any_violations else (2 if any_skipped else 0)

    if args.json:
        print(json.dumps({"results": results, "exit_code": exit_code}, indent=2))
        return exit_code

    for r in results:
        if r["status"] == "skipped":
            print(f"SKIPPED  {r['path']} — label-audit-skipped: {r['skip_reason']}")
            print("         (receiving session must treat ALL labels in this doc as unverified)")
        elif r["status"] == "clean":
            print(f"CLEAN    {r['path']}")
        else:
            print(f"BLOCKED  {r['path']} — {len(r['violations'])} untagged label row(s):")
            for v in r["violations"]:
                print(f"  line {v['line']}: {v['row']}")
            print(
                "  Fix: append [verified: <path>:<line>] to rows confirmed against an\n"
                "  authoritative source, [HYPOTHESIS] to guessed rows, or set frontmatter\n"
                "  `label-audit-skipped: <reason>` for retrospective references."
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
