/**
 * Smoke + behavioral tests for the bundled helper scripts under
 * plugins/session-handoff/scripts/.
 *
 * - Smoke: every script answers `--help` with exit 0 (argparse contract).
 * - label_audit.py: violating fixture blocks (exit 1) naming untagged rows;
 *   clean fixture passes (exit 0); frontmatter escape hatch skips (exit 2).
 * - session_metrics.py: streaming chunks sharing a message.id are deduped
 *   keeping the max-output chunk, and subagent transcripts (including nested
 *   workflow ones) are included.
 * - sessionstart_handoff_context.py: emits SessionStart additionalContext
 *   for the newest handoff prompt; silent + exit 0 when none exists.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, writeFileSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SCRIPTS = resolve(ROOT, "plugins/session-handoff/scripts");
const FIXTURES = resolve(__dirname, "fixtures");

const SCRIPT_NAMES = [
  "label_audit.py",
  "session_metrics.py",
  "skill_freshness_audit.py",
  "sessionstart_handoff_context.py",
];

function runPy(script, args = [], options = {}) {
  return spawnSync("python3", [resolve(SCRIPTS, script), ...args], {
    encoding: "utf-8",
    ...options,
  });
}

describe("bundled scripts", () => {
  describe("smoke: --help exits 0", () => {
    for (const name of SCRIPT_NAMES) {
      it(`${name} exists and answers --help`, () => {
        assert.ok(existsSync(resolve(SCRIPTS, name)), `${name} must exist`);
        const res = runPy(name, ["--help"]);
        assert.equal(res.status, 0, `--help must exit 0 (stderr: ${res.stderr})`);
        assert.ok(res.stdout.length > 0, "--help must print usage");
      });
    }
  });

  describe("label_audit.py", () => {
    it("blocks (exit 1) on untagged code->label rows and names them", () => {
      const res = runPy("label_audit.py", [
        resolve(FIXTURES, "label_audit_violating.md"),
      ]);
      assert.equal(res.status, 1, `expected exit 1, got ${res.status}`);
      assert.match(res.stdout, /BLOCKED/);
      assert.match(res.stdout, /Accepted Fully/, "must print the offending row");
      assert.match(res.stdout, /Rejected by underwriter/);
      // The tagged row is not a violation
      assert.doesNotMatch(res.stdout, /Withdrawn by applicant/);
    });

    it("passes (exit 0) when every row is tagged", () => {
      const res = runPy("label_audit.py", [
        resolve(FIXTURES, "label_audit_clean.md"),
      ]);
      assert.equal(res.status, 0, `expected exit 0 (stdout: ${res.stdout})`);
      assert.match(res.stdout, /CLEAN/);
    });

    it("honors the frontmatter escape hatch (exit 2)", () => {
      const res = runPy("label_audit.py", [
        resolve(FIXTURES, "label_audit_skipped.md"),
      ]);
      assert.equal(res.status, 2, `expected exit 2, got ${res.status}`);
      assert.match(res.stdout, /SKIPPED/);
      assert.match(res.stdout, /quoting the old fabricated table/);
    });

    it("--json reports violations with line numbers", () => {
      const res = runPy("label_audit.py", [
        "--json",
        resolve(FIXTURES, "label_audit_violating.md"),
      ]);
      assert.equal(res.status, 1);
      const parsed = JSON.parse(res.stdout);
      assert.equal(parsed.exit_code, 1);
      const violations = parsed.results[0].violations;
      assert.equal(violations.length, 2);
      assert.deepEqual(
        violations.map((v) => v.code).sort(),
        ["AD", "RJ"]
      );
      assert.ok(violations.every((v) => Number.isInteger(v.line) && v.line > 0));
    });
  });

  describe("session_metrics.py", () => {
    const args = [
      "--session-id", "abc123",
      "--projects-dir", resolve(FIXTURES, "projects"),
      "--json",
    ];

    it("dedupes streaming chunks by message.id keeping the max-output chunk", () => {
      const res = runPy("session_metrics.py", args);
      assert.equal(res.status, 0, `stderr: ${res.stderr}`);
      const parsed = JSON.parse(res.stdout);
      // msg_1 appears twice (output 1 then 80): dedup keeps 80, not 81.
      // Plus msg_2 (output 5) => main output = 85, main messages = 2.
      assert.equal(parsed.main.messages, 2);
      assert.equal(parsed.main.output_tokens, 85);
      assert.equal(parsed.main.input_tokens, 120);
      assert.equal(parsed.main.cache_read_input_tokens, 50);
      assert.equal(parsed.main.cache_creation_input_tokens, 10);
    });

    it("recurses into subagent transcripts, including workflow nesting", () => {
      const res = runPy("session_metrics.py", args);
      assert.equal(res.status, 0);
      const parsed = JSON.parse(res.stdout);
      assert.equal(parsed.subagent_transcripts.length, 2,
        "must find both subagents/agent-*.jsonl and subagents/workflows/wf_*/agent-*.jsonl");
      assert.equal(parsed.subagents.messages, 2);
      assert.equal(parsed.subagents.output_tokens, 16); // 7 + 9
      assert.equal(parsed.total.output_tokens, 101); // 85 + 16
      assert.ok(parsed.per_model["claude-haiku-4"], "per-model breakdown present");
    });

    it("prints no cost figures (tokens only)", () => {
      const res = runPy("session_metrics.py", [
        "--session-id", "abc123",
        "--projects-dir", resolve(FIXTURES, "projects"),
      ]);
      assert.equal(res.status, 0);
      assert.doesNotMatch(res.stdout, /\$\d/, "no dollar amounts in output");
    });
  });

  describe("sessionstart_handoff_context.py", () => {
    it("emits SessionStart additionalContext pointing at the newest prompt", () => {
      const proj = mkdtempSync(join(tmpdir(), "handoff-hook-"));
      mkdirSync(join(proj, "docs", "handoffs"), { recursive: true });
      const older = join(proj, "docs", "handoffs", "session_3_prompt.md");
      const newer = join(proj, "docs", "handoffs", "session_4_prompt.md");
      writeFileSync(older, "older");
      writeFileSync(newer, "newer");
      // Make mtimes deterministic: older is 1h behind newer
      const now = Date.now() / 1000;
      utimesSync(older, now - 3600, now - 3600);
      utimesSync(newer, now, now);

      const res = runPy("sessionstart_handoff_context.py", [], {
        input: JSON.stringify({ cwd: proj, hook_event_name: "SessionStart" }),
      });
      assert.equal(res.status, 0);
      const parsed = JSON.parse(res.stdout);
      assert.equal(parsed.hookSpecificOutput.hookEventName, "SessionStart");
      assert.match(
        parsed.hookSpecificOutput.additionalContext,
        /session_4_prompt\.md/
      );
    });

    it("is silent and exits 0 when no handoff prompt exists", () => {
      const proj = mkdtempSync(join(tmpdir(), "handoff-hook-empty-"));
      const res = runPy("sessionstart_handoff_context.py", [], {
        input: JSON.stringify({ cwd: proj }),
      });
      assert.equal(res.status, 0);
      assert.equal(res.stdout.trim(), "");
    });

    it("exits 0 even on a garbage payload", () => {
      const res = runPy("sessionstart_handoff_context.py", ["--project-dir", "/nonexistent"], {
        input: "not json at all",
      });
      assert.equal(res.status, 0);
      assert.equal(res.stdout.trim(), "");
    });
  });
});
