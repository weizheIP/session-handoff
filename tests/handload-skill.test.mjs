import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const HANDLOAD = resolve(ROOT, "plugins/session-handoff/skills/handload/SKILL.md");

function selectRecovery(files) {
  const handoffs = new Set();
  const prompts = new Set();
  const parallel = new Map();
  const handoff = /^session_(\d+)_handoff\.md$/;
  const prompt = /^session_(\d+)_prompt\.md$/;
  const branch = /^session_(\d+)b_[^/]+_prompt\.md$/;

  for (const name of files) {
    let match = name.match(handoff);
    if (match) handoffs.add(Number(match[1]));
    else if ((match = name.match(prompt))) prompts.add(Number(match[1]));
    else if ((match = name.match(branch))) {
      const number = Number(match[1]);
      parallel.set(number, [...(parallel.get(number) || []), name]);
    }
  }

  if (prompts.size === 0) return { error: "no handoff prompt exists" };
  const promptSession = Math.max(...prompts);
  const handoffSession = promptSession - 1;
  if (handoffSession < 1 || !handoffs.has(handoffSession)) {
    return { error: `missing session_${handoffSession}_handoff.md` };
  }
  return {
    promptSession,
    handoff: `session_${handoffSession}_handoff.md`,
    prompt: `session_${promptSession}_prompt.md`,
    parallel: parallel.get(promptSession) || [],
  };
}

describe("handload skill", () => {
  it("is shipped inside the plugin", () => {
    assert.ok(existsSync(HANDLOAD));
  });

  it("documents explicit, read-only recovery of summary and prompt", () => {
    const skill = readFileSync(HANDLOAD, "utf-8");
    assert.match(skill, /^name: handload$/m);
    const plugin = JSON.parse(readFileSync(resolve(ROOT, "plugins/session-handoff/.claude-plugin/plugin.json"), "utf-8"));
    assert.match(skill, new RegExp(`^version: ${plugin.version.replaceAll(".", "\\.")}$`, "m"));
    assert.match(skill, /explicit `\/session-handoff:handload` or `\/handload` request/);
    assert.match(skill, /session_<P-1>_handoff\.md/);
    assert.match(skill, /session_<P>_prompt\.md/);
    assert.match(skill, /Do not create, edit, move, delete, commit/);
  });

  it("selects the largest primary prompt and its preceding handoff", () => {
    assert.deepEqual(selectRecovery([
      "session_2_handoff.md",
      "session_3_prompt.md",
      "session_11_handoff.md",
      "session_12_prompt.md",
    ]), {
      promptSession: 12,
      handoff: "session_11_handoff.md",
      prompt: "session_12_prompt.md",
      parallel: [],
    });
  });

  it("refuses a newest prompt whose preceding handoff is missing", () => {
    assert.deepEqual(selectRecovery([
      "session_2_handoff.md",
      "session_3_prompt.md",
      "session_4_prompt.md",
    ]), { error: "missing session_3_handoff.md" });
  });

  it("lists same-prompt-session parallel prompts without using them as recovery input", () => {
    assert.deepEqual(selectRecovery([
      "session_7_handoff.md",
      "session_8_prompt.md",
      "session_8b_api_prompt.md",
      "session_8b_ui_prompt.md",
    ]), {
      promptSession: 8,
      handoff: "session_7_handoff.md",
      prompt: "session_8_prompt.md",
      parallel: ["session_8b_api_prompt.md", "session_8b_ui_prompt.md"],
    });
  });

  it("ignores unrelated and parallel-only filenames", () => {
    assert.deepEqual(selectRecovery(["notes.md", "session_2b_api_prompt.md"]), {
      error: "no handoff prompt exists",
    });
  });
});
