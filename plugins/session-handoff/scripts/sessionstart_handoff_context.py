#!/usr/bin/env python3
"""SessionStart hook: auto-surface the latest next-session handoff prompt.

Opt-in Claude Code SessionStart hook (see README "Automating the loop with
hooks"). Reads the hook JSON payload from stdin, looks for the newest
`docs/handoffs/session_*_prompt.md` under the project cwd, and — if one
exists — emits:

  {"hookSpecificOutput": {"hookEventName": "SessionStart",
                          "additionalContext": "<pointer to the prompt>"}}

so the new session starts knowing a paste-ready handoff prompt is waiting.
Prints nothing when no prompt exists.

Deliberately fail-open: any error (bad payload, unreadable dir, ...) results
in empty output and exit 0 — a broken hook must never block session startup.
"""

import argparse
import json
import os
import sys


def find_latest_prompt(project_dir):
    """Return the newest docs/handoffs/session_*_prompt.md, or None."""
    handoffs = os.path.join(project_dir, "docs", "handoffs")
    if not os.path.isdir(handoffs):
        return None
    candidates = []
    for name in os.listdir(handoffs):
        if name.startswith("session_") and name.endswith("_prompt.md"):
            path = os.path.join(handoffs, name)
            if os.path.isfile(path):
                candidates.append((os.path.getmtime(path), path))
    if not candidates:
        return None
    return max(candidates)[1]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Claude Code SessionStart hook: reads the hook JSON payload from "
            "stdin and, if the project has a docs/handoffs/session_*_prompt.md, "
            "emits hookSpecificOutput.additionalContext pointing the new "
            "session at the newest one. Never fails (exit 0 always)."
        ),
    )
    parser.add_argument(
        "--project-dir", default=None,
        help="project directory to scan (default: 'cwd' from the hook "
             "payload, falling back to the process cwd)",
    )
    args = parser.parse_args(argv)

    try:
        payload = {}
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                payload = json.loads(raw)

        project_dir = (
            args.project_dir
            or payload.get("cwd")
            or os.getcwd()
        )

        prompt_path = find_latest_prompt(project_dir)
        if prompt_path:
            rel = os.path.relpath(prompt_path, project_dir)
            context = (
                f"A next-session handoff prompt from a previous session exists "
                f"at {rel} (newest of docs/handoffs/session_*_prompt.md). "
                f"Read it before starting work — it contains the prior "
                f"session's context, priorities, and start files."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }))
    except Exception:
        # Fail open: a hook error must never block session startup.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
