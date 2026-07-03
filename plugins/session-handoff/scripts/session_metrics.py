#!/usr/bin/env python3
"""Session token-usage recompute (session-handoff step 24c fallback).

Locates a Claude Code session transcript (`<projects-dir>/**/<session-id>.jsonl`)
plus its subagent transcripts (`<session-id>/subagents/**/agent-*.jsonl`,
recursed so workflow fan-outs at `subagents/workflows/wf_<runid>/agent-*.jsonl`
are included) and prints token totals:

  - input_tokens / output_tokens / cache_read_input_tokens /
    cache_creation_input_tokens, split main-loop vs subagents
  - per-model breakdown
  - deduplicated assistant-message count

Dedup rules (mirrors the cctime fork's subagent accounting):
  - streaming chunks share a message.id (falling back to requestId) — each
    key is counted ONCE across the whole file, keeping the chunk with the
    HIGHEST output_tokens (the first chunk carries full input/cache but
    output_tokens ~= 0, so first-wins under-counts output ~8x).

TOKENS ONLY — this script does NO pricing/cost math. Hardcoded pricing goes
stale; cost estimation is delegated to token-torch / the cctime fork
(~/.claude/tools/cctime-fork), which remains the canonical generator of
usage-tracking records.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def parse_transcript(path):
    """Parse one JSONL transcript; return deduped assistant usage records.

    Returns a list of dicts: {model, input_tokens, output_tokens,
    cache_read_input_tokens, cache_creation_input_tokens}.
    """
    best = {}  # key -> record (whole-file dedup, keep max output_tokens)
    anon = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            role = message.get("role") or obj.get("type")
            if role != "assistant":
                continue
            key = message.get("id") or obj.get("requestId")
            if not key:
                anon += 1
                key = f"__anon_{anon}"
            record = {
                "model": message.get("model") or "unknown",
            }
            for f in USAGE_FIELDS:
                v = usage.get(f)
                record[f] = int(v) if isinstance(v, (int, float)) else 0
            prev = best.get(key)
            if prev is None or record["output_tokens"] > prev["output_tokens"]:
                best[key] = record
    return list(best.values())


def sum_records(records):
    totals = {f: 0 for f in USAGE_FIELDS}
    totals["messages"] = len(records)
    for r in records:
        for f in USAGE_FIELDS:
            totals[f] += r[f]
    return totals


def find_main_transcripts(projects_dir, session_id, project_filter=None):
    """Find <projects-dir>/**/<session-id>.jsonl (usually exactly one)."""
    matches = sorted(projects_dir.rglob(f"{session_id}.jsonl"))
    if project_filter:
        matches = [m for m in matches if project_filter in m.parent.name]
    return matches


def find_subagent_transcripts(main_transcript):
    """Recursive glob under the sibling <session-id>/subagents/ dir.

    Catches both foreground `subagents/agent-*.jsonl` and nested workflow
    `subagents/workflows/wf_<runid>/agent-*.jsonl` transcripts.
    """
    session_dir = main_transcript.parent / main_transcript.stem
    subagents_dir = session_dir / "subagents"
    if not subagents_dir.is_dir():
        return []
    return sorted(subagents_dir.rglob("agent-*.jsonl"))


def fmt(n):
    return f"{n:,}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Recompute a Claude Code session's token usage (main loop + "
            "subagent transcripts) with per-message.id dedup. "
            "Fallback for session-handoff step 24c when the cctime fork "
            "is not installed."
        ),
        epilog=(
            "Tokens only — no cost math. Pricing tables go stale; cost "
            "estimation is delegated to token-torch / the cctime fork."
        ),
    )
    parser.add_argument(
        "--session-id", "--session", dest="session_id",
        default=os.environ.get("CLAUDE_CODE_SESSION_ID"),
        help="session id (default: $CLAUDE_CODE_SESSION_ID)",
    )
    parser.add_argument(
        "--projects-dir", type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Claude Code projects dir (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--project", default=None, metavar="SLUG",
        help="optional project-dir slug filter (e.g. -home-user-myproj), "
             "used to disambiguate when the session id matches in several "
             "project dirs",
    )
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of text")
    parser.add_argument(
        "--print-summary", action="store_true",
        help="print the human-readable summary (default behavior; flag kept "
             "for compatibility with the skill's documented invocation)",
    )
    args = parser.parse_args(argv)

    if not args.session_id:
        parser.error("--session-id required (or set $CLAUDE_CODE_SESSION_ID)")

    if not args.projects_dir.is_dir():
        print(f"session_metrics: projects dir not found: {args.projects_dir}",
              file=sys.stderr)
        return 1

    mains = find_main_transcripts(args.projects_dir, args.session_id, args.project)
    if not mains:
        # Per skill wire behavior: transcripts missing => skip, don't hard-fail.
        print(f"session_metrics: no transcript found for session "
              f"{args.session_id} under {args.projects_dir} — skipping",
              file=sys.stderr)
        return 0
    if len(mains) > 1:
        print(f"session_metrics: {len(mains)} transcripts matched; using "
              f"{mains[0]} (disambiguate with --project)", file=sys.stderr)
    main_transcript = mains[0]

    main_records = parse_transcript(main_transcript)
    subagent_files = find_subagent_transcripts(main_transcript)
    subagent_records = []
    for sf in subagent_files:
        subagent_records.extend(parse_transcript(sf))

    per_model = defaultdict(lambda: dict({f: 0 for f in USAGE_FIELDS}, messages=0))
    for r in main_records + subagent_records:
        bucket = per_model[r["model"]]
        bucket["messages"] += 1
        for f in USAGE_FIELDS:
            bucket[f] += r[f]

    result = {
        "session_id": args.session_id,
        "main_transcript": str(main_transcript),
        "subagent_transcripts": [str(p) for p in subagent_files],
        "main": sum_records(main_records),
        "subagents": sum_records(subagent_records),
        "total": sum_records(main_records + subagent_records),
        "per_model": dict(sorted(per_model.items())),
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Session {args.session_id}")
    print(f"  main transcript:      {main_transcript}")
    print(f"  subagent transcripts: {len(subagent_files)}")
    print()
    header = f"  {'':<12}{'messages':>10}{'input':>14}{'output':>12}{'cache_read':>14}{'cache_create':>14}"
    print(header)
    for label, t in (("main", result["main"]),
                     ("subagents", result["subagents"]),
                     ("TOTAL", result["total"])):
        print(f"  {label:<12}{fmt(t['messages']):>10}{fmt(t['input_tokens']):>14}"
              f"{fmt(t['output_tokens']):>12}{fmt(t['cache_read_input_tokens']):>14}"
              f"{fmt(t['cache_creation_input_tokens']):>14}")
    print()
    print("  per model:")
    for model, t in result["per_model"].items():
        print(f"    {model:<32}{fmt(t['messages']):>8} msgs"
              f"{fmt(t['input_tokens']):>14} in{fmt(t['output_tokens']):>12} out"
              f"{fmt(t['cache_read_input_tokens']):>14} cr"
              f"{fmt(t['cache_creation_input_tokens']):>14} cc")
    print()
    print("  (tokens only — cost estimation delegated to token-torch / cctime fork)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
