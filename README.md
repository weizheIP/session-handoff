# session-handoff

End-of-session handoff that captures all knowledge, **dispatches session output across the canonical 7-bucket `docs/` taxonomy** (aligned with [memory-hygiene v3.3](https://github.com/wan-huiyan/memory-hygiene)), and prepares paste-ready prompts for the next session. Includes a built-in **label audit** (Phase 0), cross-session consolidation when multiple handoffs accumulate, a mandatory **doc-freshness reverse-lint + skill-freshness audit** that catches stale normative guidance, **future-to-do GitHub issue emission**, and a closing **user-facing live-dashboard recap** for the chat.

**v1.9** is the current release — aligned with the 7-bucket taxonomy, with skill-freshness audit and future-to-do issue emission layered on top of the bucket-aware dispatch introduced in v1.4.

## Quick Start

```
You: /session-handoff
Claude: [scans git log, writes handoff doc, updates memory, creates next-session prompt]

You: wrap up this session
Claude: [same — triggers on natural language too]

You: consolidate handoffs
Claude: [merges 3+ handoff docs into a single source-of-truth plan]

You: /handload
Claude: [loads the latest complete handoff summary and next-session prompt for this project]
```

### Recovering a session

After `/session-handoff`, run `/handload` in the same Git project whenever you need
to restore its context. It reads the newest primary prompt with its preceding session
summary in `docs/handoffs/`: `session_<P-1>_handoff.md` and
`session_<P>_prompt.md`. Selection uses the largest primary-prompt number rather than
file modification time, requires both files, and never falls back to an earlier prompt
if the newest pair is incomplete. Same-prompt-session parallel prompts are listed but
not loaded unless explicitly selected. `/handload` is read-only and project-scoped, so
separate projects keep separate recovery context.

The bundled plugin exposes this as `/session-handoff:handload`. This repository also
ships a matching standalone global `/handload` Skill for the shorter command.

## Installation

**Claude Code（插件安装，推荐）：**

在任意设备上执行：

```bash
claude plugin marketplace add weizheIP/session-handoff
claude plugin install session-handoff@weizheIP-session-handoff
```

重启 Claude Code 后可使用：

```text
/session-handoff
/session-handoff:handload
```

**可选：启用裸 `/handload`：**

插件命令是 `/session-handoff:handload`。若需要更短的裸命令 `/handload`，在每台设备额外安装全局 Skill：

```bash
git clone https://github.com/weizheIP/session-handoff.git /tmp/session-handoff
install -Dm644 /tmp/session-handoff/plugins/session-handoff/skills/handload/SKILL.md \
  ~/.claude/skills/handload/SKILL.md
rm -rf /tmp/session-handoff
```

重启 Claude Code 后即可使用 `/handload`。该命令仅读取当前 Git 项目中的 `docs/handoffs/`，不会修改任何交接文件。

## What You Get

Every handoff dispatches session output across the 7 canonical buckets (rich sessions touch 3-5 of them):

| Bucket | Populated when the session... |
|---|---|
| **`docs/decisions/`** | Made an architectural or methodological choice (ADRs) |
| **`docs/runbooks/`** | Created/updated an operational procedure (retrain, rerun, QA) |
| **`docs/analysis/`** | Produced findings, investigations, diagnostics |
| **`docs/references/`** | Updated schemas, data dictionaries, project conventions |
| **`docs/reviews/`** | Produced review-panel or audit output |
| **`docs/handoffs/`** | **Always** — the session handoff doc + next-session prompt (+ parallel prompts) |
| **`docs/deliverables/`** | Produced an external-facing artifact (client draft, published output, slides) |

Plus:

| Artifact | Description |
|---|---|
| **Label audit (Phase 0)** | Blocks the handoff if it ships code→human label tables (Salesforce statuses, HTTP codes, enums) without inline `[verified: path:line]` or `[HYPOTHESIS]` tags — prevents fabricated semantic labels from propagating to the next session |
| **Lessons update** | Non-obvious debugging patterns and user corrections captured |
| **Memory files** | New feedback/reference files created or updated |
| **Future plan** | Updated with completed items and newly discovered work |
| **Sessions archive** | Running log of all sessions with dates, outcomes, and bucket footprint |
| **PR (committed + pushed)** | All session work committed to a feature branch, pushed, and a PR created (optionally merged) |
| **Next session prompt** | Paste-ready prompt with full context to resume immediately |
| **Doc-freshness reverse-lint** | Invokes [doc-freshness-reverse-lint](https://github.com/wan-huiyan/claude-ecosystem-hygiene/tree/main/plugins/doc-freshness-reverse-lint) against lessons/feedback touched this session and surfaces candidate stale docs in the handoff |
| **Skill-freshness audit** | When a `SKILL.md` is edited this session, runs an audit against project docs/CLAUDE.md to surface guidance that contradicts the new skill behavior |
| **Future-to-do GitHub issues** | Each follow-up item in the future-to-do plan is drafted as a `gh issue create` payload, shown for review, then filed — so action doesn't depend on a future session re-reading the handoff |
| **Live-dashboard recap (Phase 6)** | Chat-only, user-facing summary translating shipped PRs into what the user will *see* in the product next time they open it — grouped by venue, not by PR |
| **Consolidated plan** | *(when 3+ handoffs exist)* Single source of truth with decision supersession, gap analysis, and PR reconciliation |

## Typical Ad-Hoc vs With Skill

| | Ad-hoc wrap-up | With session-handoff |
|---|---|---|
| Knowledge capture | Mental notes, maybe a quick message | Structured handoff doc with decisions table |
| Lessons learned | Lost when context window resets | Written to persistent memory files |
| Next session start | Re-read code, reconstruct context | Paste the prompt, start immediately |
| Parallel streams | Forgotten | Separate prompts for each work stream |
| Git workflow | Uncommitted changes left behind | Committed, pushed, PR created and optionally merged |
| Memory hygiene | Skipped | Automatic check for orphaned files |
| Stale project docs after a lesson update | No one notices for weeks | Reverse-lint surfaces candidates in the handoff |
| Follow-up items | Trapped inside a doc no one reads | Filed as GitHub issues with full context |
| User-visible impact | "We shipped 4 PRs" | Per-venue before/after the user will actually see |
| After 5 parallel sessions | Cross-reference 5 handoff docs manually | One consolidated plan with superseded decisions resolved |

## How It Works

| Phase | Steps | What happens |
|---|---|---|
| **0. Label audit** | — | Block the handoff if it contains code→human label tables without `[verified: path:line]` or `[HYPOTHESIS]` tags. Escape hatch via frontmatter for retrospective references. |
| **1. Capture** | 1-4 | Scan git log, capture lessons, collect session artifacts for bucket triage |
| **2. Dispatch** | 5-16 | Route session output to the 7 canonical buckets (decisions/runbooks/analysis/references/reviews/handoffs/deliverables), then propagate to future plan, sessions archive, MEMORY.md |
| **3. Prepare** | 17-18 | Write next-session prompt(s) for all work streams |
| **4. Commit, PR, verify** | 19-25 | Commit code + docs, push branch, create PR, optionally merge, memory hygiene check, **doc-freshness reverse-lint**, **skill-freshness audit**, **emit future-to-do items as GitHub issues** |
| **5. Consolidate** | 26-30 | *(conditional)* Merge handoffs into single plan, track decision supersession, identify gaps |
| **6. Live-dashboard recap** | 31-35 | *(chat output, not a file)* User-facing "what you'll see in the product" summary grouped by venue |

### When does consolidation run?

Phase 5 triggers automatically when 3+ handoff docs exist in `docs/handoffs/`, or when you explicitly ask to consolidate. It:

- **Tracks decision supersession** — marks decisions as OPEN, RESOLVED, or SUPERSEDED across sessions
- **Validates claims** — checks every PR/branch reference against actual git/GitHub state
- **Identifies gaps** — cross-checks "what needs to happen next" against what actually happened
- **Produces one plan** — `docs/plans/future_sessions_plan.md` that a cold-start session can read without touching any other handoff doc

### Why Phase 6 (live-dashboard recap)?

Handoff docs are written for *Claude in a future session* — dense, technical, complete. The user reading the chat needs a different register: what changed, where they'll notice it, what to verify themselves. Without Phase 6, the user has to read the handoff doc or click through 4-8 PRs to know what changed in their product. Phase 6 closes that loop in conversational chat output.

## Key Design Decisions

| Decision | Rationale |
|---|---|
| 7-phase sequential checklist | Ensures nothing is skipped; each phase builds on the previous |
| Phase 0 label audit (blocking with escape hatch) | Author-side gate — false positives cost 30s of human ack, false negatives cost a fabricated label shipping to a client. The asymmetry is by design. |
| Consolidation as Phase 5 (not separate skill) | Reduces cognitive overhead — one skill handles the full handoff lifecycle |
| Conditional consolidation (3+ threshold) | Avoids unnecessary overhead for simple linear session sequences |
| Phase 6 as chat-only (no file) | The recap's audience is the *human* closing the session — it's release-notes register, not handoff register |
| GitHub issues for future-to-do items | Filing each follow-up closes the loop on "will the next session actually act on this?" — issues persist outside the handoff doc |
| Strikethrough for resolved decisions | Visual scanning — instantly see what's decided vs open |
| Paste-ready next-session prompts | Eliminates "see above" references that break across context windows |

## Limitations

- Context usage is visible in Claude Code (`/context`, the statusline's context indicator), but the plugin never triggers automatically. Invoke `/session-handoff` when the session is ready to close, then explicitly invoke `/session-handoff:handload` or `/handload` when recovery is needed.
- Assumes `docs/` and `memory/` directory structure — creates them if missing, but works best when pre-existing
- Git-dependent for commit scanning and branch status (gracefully degrades without git)
- Requires `gh` CLI for PR status validation during consolidation and for future-to-do issue emission (skips those checks without it)
- Helper scripts (`label_audit.py`, `session_metrics.py`, `skill_freshness_audit.py`) ship with the plugin in `plugins/session-handoff/scripts/`. The checklist resolves them from `${CLAUDE_PLUGIN_ROOT}/scripts/` (plugin install) first, then `~/.claude/skills/session-handoff/scripts/` (git-clone install); if a script is missing at both locations, that step logs and continues

<details>
<summary>Quality Checklist</summary>

The skill guarantees:
- [ ] Phase 0 label audit passed (or skipped via documented frontmatter)
- [ ] All commits since session start are accounted for
- [ ] Handoff doc has all 6 sections (completed, remaining, blockers, decisions, files, branch)
- [ ] Lessons scanned for non-obvious debugging patterns
- [ ] MEMORY.md index is consistent with memory files on disk
- [ ] All changes committed, pushed, and PR created
- [ ] Doc-freshness reverse-lint ran against this session's lesson/feedback edits
- [ ] Skill-freshness audit ran if any SKILL.md was edited
- [ ] Future-to-do follow-ups filed as GitHub issues
- [ ] Next-session prompt is paste-ready (no "see above" references)
- [ ] ADR numbers checked for duplicates
- [ ] Live-dashboard recap delivered in chat (or "internal-only" note)
- [ ] (If consolidating) Every PR/branch claim verified against current state
- [ ] (If consolidating) Decision supersession timeline is complete

</details>

## Development

Run the test suite (validates manifest/version consistency across `plugin.json`,
`marketplace.json`, `package.json`, and `SKILL.md` frontmatter):

```bash
npm test
```

`main` is **branch-protected**: changes land via pull request only, and the
`test-gate` status check must pass before merge (enforced for admins too — no direct
pushes). Solo flow:

```bash
git checkout -b fix/something
# …edit…
git push -u origin fix/something          # hook runs npm test first (see below)
gh pr create --fill
gh pr merge --squash --delete-branch --auto   # merges once test-gate is green
```

**Enable the local pre-push guard (recommended, once per clone):**

```bash
git config core.hooksPath .githooks
```

This makes `git push` run `npm test` first and **abort the push if it fails** — so a
malformed version (e.g. a `.1.9.1` leading-dot semver typo) or a cross-file version
drift fails fast on your machine instead of after you've opened a PR. It's the fast
local layer; branch protection is the authoritative server-side gate. Override the
hook in a genuine emergency with `git push --no-verify` (the server gate still applies).

## Related Skills

- **[memory-hygiene](https://github.com/wan-huiyan/memory-hygiene)** v3.3+ — Source of truth for the 7-bucket `docs/` taxonomy. Deep memory cleanup + `docs/` taxonomy audit/migration beyond what session-handoff does in-line.
- **[doc-freshness-reverse-lint](https://github.com/wan-huiyan/claude-ecosystem-hygiene/tree/main/plugins/doc-freshness-reverse-lint)** — Invoked automatically in Phase 4. Catches stale normative guidance in project docs after lessons/feedback updates and ships the skill-freshness audit script used in step 24b. Falls back gracefully if not installed.

## Version History

- **1.9.1** — Added a session usage-metrics step (step 24c): archives the session's `cctime` output as a structured record so handoffs carry token/cost accounting. Invokes the cctime fork by absolute path to avoid the upstream name-collision. Falls back gracefully if the fork isn't installed.
- **1.9.0** — Skill-freshness audit step (runs when any SKILL.md edited this session) + future-to-do GitHub issue emission (each follow-up filed via `gh issue create`) + memory-hygiene v3.3 alignment in the lead.
- **1.8.0** — Added the skill-freshness audit script wiring and tightened v3.3 references throughout the checklist.
- **1.7.0** — Phase 6: user-facing live-dashboard recap delivered as chat output (not a file). Translates shipped PRs into per-venue "what you'll see next time" summaries.
- **1.4.0** — Aligned with [memory-hygiene v3.1+](https://github.com/wan-huiyan/memory-hygiene/pull/3) 7-bucket `docs/` taxonomy. New Phase 2 dispatches session output across `decisions/runbooks/analysis/references/reviews/handoffs/deliverables` instead of a single handoff file. Phase 4 adds a mandatory doc-freshness reverse-lint verify step.
- **1.3.0** — Phase 4 now includes explicit commit, push, PR creation, and optional merge steps. Previously just said "commit and push any stragglers" which was too vague.
- **1.2.0** — Plugin packaging fix: restructured to canonical `plugins/<name>/` layout.
- **1.1.0** — Merged session-handoff-consolidator as Phase 5 (conditional consolidation). Added edge case handling, anti-patterns section, improved triggers.
- **1.0.0** — Initial release. 4-phase checklist with 15 steps.

## License

MIT
