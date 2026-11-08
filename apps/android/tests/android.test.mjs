// Offline tests: node --test apps/android/tests
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url)), root = join(here, "..");
const P = require("../lib/pcm.js"), X = require("../lib/protocol.js"), V = require("../lib/verdict.js");

test("floatToPcm16 clamps and maps full scale", () => {
  const o = P.floatToPcm16(Float32Array.from([0, 1, -1, 2, -2, 0.5, NaN]));
  assert.deepEqual([...o], [0, 32767, -32768, 32767, -32768, 16384, 0]);
});

test("resampler 48k -> 16k gives a third of the samples and keeps a tone's level", () => {
  const n = 48000, x = new Float32Array(n);
  for (let i = 0; i < n; i++) x[i] = 0.5 * Math.sin((2 * Math.PI * 440 * i) / 48000);
  const rs = new P.Resampler(48000, 16000), a = rs.push(x.subarray(0, 20000)), b = rs.push(x.subarray(20000));
  assert.equal(a.length + b.length, 16000);
  assert.ok(Math.abs(P.rms(Float32Array.from([...a, ...b])) - 0.5 / Math.SQRT2) < 0.02);
});

test("pipeline emits 100 ms frames: 1600 samples = 3200 bytes, even length, 16 kHz", () => {
  const frames = [];
  const p = P.createPipeline({ inRate: 48000, onFrame: (f) => frames.push(f), onLevel: () => {} });
  const chunk = new Float32Array(2048).fill(0.25);
  for (let i = 0; i < 40; i++) p.push(chunk);                     // 40 * 2048 / 48000 = 1.707 s
  assert.equal(frames.length, 17);
  for (const f of frames) { assert.equal(f.length, 1600); assert.equal(f.byteLength, 3200); assert.equal(f.byteLength % 2, 0); }
  assert.ok(frames[3].every((s) => s === 8192));
});

test("pipeline at 16 kHz passes samples straight through", () => {
  const frames = [];
  const p = P.createPipeline({ inRate: 16000, onFrame: (f) => frames.push(f) });
  p.push(new Float32Array(3200).fill(-0.5));
  assert.equal(frames.length, 2);
  assert.equal(frames[0][0], -16384);
});

test("frames stay under the engine's 128 KiB limit", () => {
  assert.ok(P.TARGET_RATE * 2 * (P.FRAME_MS / 1000) < 128 * 1024);
});

test("hello matches the engine handshake", () => {
  assert.deepEqual(X.hello("tok"), { type: "hello", token: "tok", sample_rate: 16000, format: "pcm_s16le", side: "mix", source: "android speaker" });
});

test("api override is honoured for loopback only", () => {
  assert.equal(X.loopbackApi("?api=http://127.0.0.1:8011", "http://localhost:8000"), "http://127.0.0.1:8011");
  assert.equal(X.loopbackApi("?api=http://192.168.1.5:8000", "http://localhost:8000"), "http://localhost:8000");
  assert.equal(X.loopbackApi("?api=https://evil.example", "http://localhost:8000"), "http://localhost:8000");
  assert.equal(X.wsUrl("http://localhost:8000", "/ws/stream"), "ws://localhost:8000/ws/stream");
});

test("verdict helpers", () => {
  const v = { tier: "scam", p_ai: 0.2, p_scam: 0.9, confidence: 0.7, tells: [] };
  assert.equal(V.scoresOf(v).level, "high");
  assert.equal(V.quadrantOf(v).combo, "human_scam");
  assert.equal(V.ringTicks({ scam: 100, ai_voice: 0 }, 48), 48);
  assert.equal(V.mmss(125), "2:05");
  const marks = V.buildMarks("Please send the money now", [{ name: "payment_rails", family: "intent", applicable: true, score: 0.9, evidence: 'Said "send the money"' }]);
  assert.equal(marks.length, 1);
  const st = V.stableView({ tier: "unsure", p_scam: 0.1 }, { tier: "scam", reasons: ["x"] });
  assert.equal(st.tier, "scam"); assert.ok(st.p_scam >= 0.6);
});

test("manifest is installable", () => {
  const m = JSON.parse(readFileSync(join(root, "manifest.webmanifest"), "utf8"));
  assert.equal(m.display, "standalone");
  assert.ok(m.name && m.short_name && m.start_url && m.theme_color && m.background_color);
  const sizes = m.icons.map((i) => i.sizes);
  assert.ok(sizes.includes("192x192") && sizes.includes("512x512"));
  assert.ok(m.icons.some((i) => i.purpose === "maskable"));
  for (const i of m.icons) assert.ok(existsSync(join(root, i.src)), i.src);
});

test("service worker caches only the app shell: no audio, no verdicts, no engine calls", () => {
  const sw = readFileSync(join(root, "sw.js"), "utf8");
  const shell = JSON.parse(sw.match(/const SHELL = (\[[^\]]*\])/s)[1]);
  for (const f of shell) {
    assert.ok(!/(^|\/)(live|session|ws|analyze|health|thresholds)(\/|$)|\.(wav|webm|opus|ogg|mp3|m4a|json)$/i.test(f), "not shell: " + f);
    if (f !== "./") assert.ok(existsSync(join(root, f)), "missing " + f);
  }
  assert.ok(!/\/live|\/session|\/ws|\/analyze/.test(sw.replace(/\/\*[\s\S]*?\*\//, "")), "sw must not name engine routes");
  assert.match(sw, /url\.origin !== self\.location\.origin\) return/);   // other origins (the engine) are never intercepted
  assert.match(sw, /req\.method !== "GET"/);
  assert.ok(!/caches\.[a-z]+\([^)]*(blob|arrayBuffer)/.test(sw));
});

test("app never uses the network beyond loopback and has no analytics", () => {
  const js = readFileSync(join(root, "app.js"), "utf8") + readFileSync(join(root, "index.html"), "utf8");
  assert.ok(!/https?:\/\/(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}/i.test(js.replace(/https?:\/\/www\.w3\.org[^"']*/g, "")));
  assert.ok(!/gtag|sentry|segment|mixpanel|google-analytics/i.test(js));
  assert.match(js, /echoCancellation: false, noiseSuppression: false, autoGainControl: false/);
});

test("consent wording is exact", () => {
  const h = readFileSync(join(root, "index.html"), "utf8");
  assert.ok(h.includes("Tell listens to this call through your microphone on your phone and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it."));
});
