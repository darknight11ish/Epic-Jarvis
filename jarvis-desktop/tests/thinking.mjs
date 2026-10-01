/**
 * Tests for Desktop Thinking levels module (Section 5.5).
 */
import assert from "node:assert/strict";
import {
  DEFAULT,
  DETAIL,
  LEVEL_LABELS,
  LEVELS,
  MISSING,
  NOTICE,
  readThinking,
  TITLE,
  WHY,
} from "../src/thinking-module.js";

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

await check("thinking constants match specification", async () => {
  assert.deepEqual(LEVELS, ["off", "quick", "deep", "auto"]);
  assert.equal(DEFAULT, "off");
  assert.equal(TITLE, "Thinking levels");
  assert.ok(NOTICE.includes("conversation room"));
  for (const lvl of LEVELS) {
    assert.ok(LEVEL_LABELS[lvl]);
    assert.ok(WHY[lvl]);
  }
});

await check("readThinking parses valid status payload", async () => {
  const raw = {
    title: "Thinking levels",
    detail: "Lets Jarvis think",
    notice: "Spends conversation room",
    models: [
      {
        role: "everyday",
        name: "Everyday chat",
        model: "jarvis-primary",
        level: "quick",
        supported: ["off", "quick", "deep", "auto"],
        why: "Quick thinking.",
      },
      {
        role: "second",
        name: "Second card lane",
        model: "plain-model",
        level: "off",
        supported: ["off"],
        why: "Off.",
      },
    ],
  };

  const parsed = readThinking(raw);
  assert.equal(parsed.available, true);
  assert.equal(parsed.title, "Thinking levels");
  assert.equal(parsed.models.length, 2);

  const m1 = parsed.models[0];
  assert.equal(m1.role, "everyday");
  assert.equal(m1.level, "quick");
  assert.deepEqual(m1.supported, ["off", "quick", "deep", "auto"]);

  const m2 = parsed.models[1];
  assert.equal(m2.role, "second");
  assert.equal(m2.level, "off");
  assert.deepEqual(m2.supported, ["off"]);
});

await check("readThinking handles unavailable and malformed payload", async () => {
  const unavail = readThinking({ available: false, why: "Not installed" });
  assert.equal(unavail.available, false);
  assert.equal(unavail.why, "Not installed");

  const malformed = readThinking(null);
  assert.equal(malformed.available, true);
  assert.deepEqual(malformed.models, []);
});

if (fails.length > 0) {
  process.exit(1);
}
