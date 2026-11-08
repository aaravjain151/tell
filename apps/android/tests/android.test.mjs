// Offline tests: node --test apps/android/tests
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url)), root = join(here, "..");
const P = require("../lib/pcm.js"), X = require("../lib/protocol.js"), V = require("../lib/verdict.js"), DM = require("../lib/demo.js");

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

// ---------- auto-listen (start when a call is answered) ----------
const AL = require("../lib/autolisten.js");
const NATIVE_SRC = join(root, "native", "android", "app", "src", "main");
const javaSrc = () => {
  const dir = join(NATIVE_SRC, "java", "dev", "doublespeak", "app");
  const files = [...readdirSync(dir).map((f) => join(dir, f)), ...readdirSync(join(dir, "call")).map((f) => join(dir, "call", f))];
  return files.filter((f) => f.endsWith(".java")).map((f) => readFileSync(f, "utf8")).join("\n");
};

test("auto-listen consent wording is exact in the page, the lib and the native strings", () => {
  const exact = "When you answer a call, Tell listens through your microphone in speaker mode and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it.";
  assert.equal(AL.CONSENT, exact);
  assert.ok(readFileSync(join(root, "index.html"), "utf8").includes(exact));
  assert.ok(javaSrc().includes(exact));
});

test("auto-listen status line", () => {
  assert.equal(AL.status(null).line, "Auto-listen needs the installed Tell app");
  assert.equal(AL.status({ available: true, enabled: false, missing: [] }).line, "Auto-listen is off");
  const on = AL.status({ available: true, enabled: true, missing: [], state: "idle", background: "tap" });
  assert.equal(on.line, "Auto-listen is on: Tell starts when you answer");
  assert.match(on.sub, /tap Listen/);
  assert.equal(AL.status({ available: true, enabled: true, missing: [], state: "idle", background: "direct" }).sub, "Put the call on speaker after you answer.");
  assert.equal(AL.status({ available: true, enabled: true, missing: ["phone"] }).line, "Auto-listen is paused");
  assert.equal(AL.status({ available: true, enabled: true, missing: [], state: "listening" }).line, "Listening to this call");
  assert.equal(AL.status({ available: true, enabled: true, missing: [], state: "silent" }).tone, "warn");
});

test("auto-listen end reasons: the not-connected path says plug in the cable", () => {
  assert.equal(AL.endedText("ended:not_connected"), "Tell could not reach your computer; plug in the USB cable.");
  assert.match(AL.endedText("ended:refused"), /make api-android/);
  assert.equal(AL.endedText("ended:stopped"), "");
  assert.equal(AL.endedText("ended:dropped"), "");                 // engine reachable, clean end: never blame the cable
});

test("silenced mic has its own honest message, separate from the cable message", () => {
  assert.equal(AL.MIC_BLOCKED.line, "Your phone is blocking the microphone during the call. On this phone, apps can't hear a call even on speaker.");
  assert.equal(AL.MIC_BLOCKED.sub, "Use Tell on your Mac for live calls (answer the call on your Mac).");
  assert.equal(AL.endedText("ended:mic_silenced"), AL.MIC_BLOCKED.line);
  assert.equal(AL.outcome("ended:mic_silenced"), "mic_silenced");
  // the two failure messages must not be confused with each other
  assert.ok(!/cable|USB/i.test(AL.MIC_BLOCKED.line));
  assert.ok(!/microphone|mic\b/i.test(AL.endedText("ended:lost")));
  // the page separates the states in code: a /health probe gates the cable message, and a distinct blocked card exists
  const js = readFileSync(join(root, "app.js"), "utf8");
  assert.match(js, /function reachable\(/);
  assert.match(js, /function micBlocked\(/);
  assert.match(js, /function endConnection\(/);
  assert.match(js, /card err blocked/);
});

test("app.js no longer blames the USB cable on a mere SSE drop, and clears the teardown rejection", () => {
  const js = readFileSync(join(root, "app.js"), "utf8");
  assert.ok(!/function lostNote/.test(js), "the unconditional 'check the USB cable' SSE note is gone");
  assert.ok(!/es\.onerror = function \(\) \{ es\.close\(\); if \(S\.mode === "listening"\) lostNote/.test(js));
  assert.match(js, /release\(\);.*catch/s);                         // wake release promise rejection is swallowed
});

test("auto-listen stays within Play policy: no hidden APIs, accessibility, overlays, call log, recording to storage", () => {
  const m = readFileSync(join(NATIVE_SRC, "AndroidManifest.xml"), "utf8"), j = javaSrc();
  for (const p of ["SYSTEM_ALERT_WINDOW", "MODIFY_PHONE_STATE", "READ_CALL_LOG", "PROCESS_OUTGOING_CALLS", "CAPTURE_AUDIO_OUTPUT",
    "BIND_ACCESSIBILITY_SERVICE", "USE_FULL_SCREEN_INTENT", "READ_CONTACTS", "ANSWER_PHONE_CALLS", "MANAGE_OWN_CALLS", "BIND_INCALL_SERVICE"])
    assert.ok(!m.includes(p), "manifest must not use " + p);
  const code = j.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");   // comments may name what is NOT used
  assert.ok(!/AccessibilityService|getDeclaredMethod|setAccessible|Class\.forName|setSpeakerphoneOn|setCommunicationDevice/.test(code), "no reflection / route switching");
  assert.ok(!/FileOutputStream|openFileOutput|MediaRecorder\(|getExternal|RandomAccessFile/.test(code), "never writes audio to storage");
  assert.ok(!/EXTRA_INCOMING_NUMBER|getLine1Number/.test(code), "never reads numbers");
  // the receiver starts disabled (setting off by default) and only listens for PHONE_STATE
  assert.match(m, /android:name="\.CallStateReceiver"\s+android:enabled="false"/);
  assert.match(m, /<action android:name="android\.intent\.action\.PHONE_STATE" \/>/);
  // native capture only ever connects to 127.0.0.1
  assert.match(code, /new byte\[\]\{127, 0, 0, 1\}/);
  assert.ok(!/new Socket\("|InetAddress\.getByName\(/.test(code));
});

test("consent wording is exact", () => {
  const h = readFileSync(join(root, "index.html"), "utf8");
  assert.ok(h.includes("Tell listens to this call through your microphone on your phone and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it."));
});

test("engine key: only well-formed tokens are kept; the fragment is read; header and feed URL carry it", () => {
  const tok = "A".repeat(20) + "b_c-" + "9".repeat(19);
  assert.equal(X.cleanToken("  " + tok + "\n"), tok);
  for (const bad of ["", "short", tok + " x", "a".repeat(129), null, undefined, "x".repeat(31)]) assert.equal(X.cleanToken(bad), "");
  assert.equal(X.tokenFromHash("#token=" + tok), tok);
  assert.equal(X.tokenFromHash("#/home"), "");
  assert.equal(X.tokenFromHash("#token=nope"), "");
  assert.deepEqual(X.authHeaders(tok), { "X-Tell-Token": tok });
  assert.deepEqual(X.authHeaders("", { a: "1" }), { a: "1" });
  assert.equal(X.feedUrl("http://localhost:8000", tok), "http://localhost:8000/live/events?token=" + tok);
  assert.equal(X.feedUrl("http://localhost:8000", ""), "http://localhost:8000/live/events");
});

test("app sends the engine key on every engine call that needs it", () => {
  const js = readFileSync(join(root, "app.js"), "utf8");
  assert.match(js, /fetch\(API \+ "\/session", \{ method: "POST", headers: X\.authHeaders\(TOKEN\) \}\)/);
  assert.match(js, /fetch\(API \+ "\/live\/dismiss", \{ method: "POST", headers: X\.authHeaders\(TOKEN\) \}\)/);
  assert.match(js, /new EventSource\(X\.feedUrl\(API, TOKEN\)\)/);
  assert.ok(!/new EventSource\(API \+/.test(js), "the feed must not be opened without the key");
});

// ---------- Demo mode (stage): a bundled recorded clip -> the REAL engine, honestly labelled ----------
import vm from "node:vm";

test("demo streamer frames a clip into 100 ms PCM16 frames (even bytes, clip size preserved)", () => {
  assert.equal(DM.FRAME_BYTES, 3200);                       // 100 ms of PCM16 mono 16 kHz, same as the mic path
  const buf = new ArrayBuffer(3200 * 3 + 338);              // 3 whole frames + a short tail
  const frames = DM.frameClip(buf);
  assert.equal(frames.length, 4);
  for (const f of frames) assert.equal(f.byteLength % 2, 0, "frames are whole samples");
  assert.equal(frames.slice(0, 3).every((f) => f.byteLength === 3200), true);
  assert.equal(frames[3].byteLength, 338);
  assert.equal(frames.reduce((n, f) => n + f.byteLength, 0), buf.byteLength);   // nothing invented, nothing lost
  const odd = DM.frameClip(new ArrayBuffer(5));             // trailing odd byte dropped (never half a sample)
  assert.equal(odd.reduce((n, f) => n + f.byteLength, 0), 4);
});

test("demo streamer paces frames one per tick to a fake WS and stops cleanly", () => {
  const frames = [0, 1, 2, 3].map((i) => new Int16Array([i, i]).buffer);
  const sent = [], queue = []; let done = false;
  const s = DM.createStreamer({
    frames, intervalMs: 100,
    send: (f) => sent.push(f),                              // the fake WS
    setTimer: (fn) => { queue.push(fn); return queue.length; },
    clearTimer: () => {},
    onDone: () => { done = true; },
  });
  s.start();                                                // sends frame 0 immediately, schedules the next
  assert.equal(sent.length, 1);
  assert.equal(s.running(), true);
  while (queue.length) queue.shift()();                     // drive the fake clock to completion
  assert.deepEqual(sent, frames);                           // every frame sent, in order, exactly once
  assert.equal(done, true);
  assert.equal(s.sent(), 4);
  assert.equal(s.running(), false);
});

test("demo streamer stop() halts before the clip finishes and sends no more", () => {
  const frames = [0, 1, 2, 3].map((i) => new Int16Array([i]).buffer);
  const sent = []; let next = null;
  const s = DM.createStreamer({ frames, send: (f) => sent.push(f), setTimer: (fn) => { next = fn; return 1; }, clearTimer: () => { next = null; } });
  s.start();                                                // frame 0
  next();                                                   // frame 1
  s.stop();
  assert.equal(s.running(), false);
  assert.equal(sent.length, 2);
  if (next) next();                                         // a stray timer must not resume a stopped stream
  assert.equal(sent.length, 2);
});

test("demo levelOf reflects the clip's loudness (display meter only)", () => {
  assert.equal(DM.levelOf(new Int16Array([0, 0, 0]).buffer), 0);
  assert.ok(DM.levelOf(new Int16Array([32767, -32768]).buffer) > 0.9);
});

test("demo clips are bundled, short, PCM16 16 kHz mono (<= 2 MB), and copied into the APK", () => {
  for (const name of ["scam.pcm", "human.pcm"]) {
    const p = join(root, "demo", name);
    assert.ok(existsSync(p), "missing bundled clip " + name);
    const size = readFileSync(p).length;
    assert.equal(size % 2, 0, "whole PCM16 samples");
    assert.ok(size > 16000 && size <= 2 * 1024 * 1024, name + " size " + size);   // real content, under 2 MB
  }
  const buildWww = readFileSync(join(root, "native", "build-www.mjs"), "utf8");
  assert.match(buildWww, /"demo"/, "demo folder must be copied into native/www for the APK");
});

test("demo mode is additive and honest in the markup: RECORDED DEMO label, hidden by default, no claim of a live call", () => {
  const h = readFileSync(join(root, "index.html"), "utf8");
  assert.match(h, /id="demo-banner"[^>]*hidden/, "the demo banner is hidden by default");
  assert.match(h, /RECORDED DEMO[\s\S]*?not a live call/, "the persistent label says it is a recorded demo, not live");
  assert.ok(h.includes('id="demo-scam"') && h.includes('id="demo-human"') && h.includes('id="demo-exit"'), "scam/human/exit controls present");
  assert.match(h, /src="lib\/demo\.js"/);
  const js = readFileSync(join(root, "app.js"), "utf8");
  // entry is hidden and off by default: only a long-press on the logo or ?demo=1 turns it on
  assert.match(js, /QS\.get\("demo"\) === "1"/);
  assert.match(js, /pointerdown[\s\S]*enterDemo/);
  // the clip is streamed to the real engine over the same session/WS path; the hello marks it a recorded demo
  assert.match(js, /openSession\("android demo \(recorded clip: " \+ kind/);
  // nothing in the demo path fabricates a verdict: no hardcoded tier/score/alert is assigned for display
  const demoBlock = js.slice(js.indexOf("function startDemo"), js.indexOf("/* ---------- sheets"));
  assert.ok(!/dataset\.tier = "(human|scam|ai_|unsure)/.test(demoBlock), "demo must not hardcode a tier");
  assert.ok(!/\b(p_scam|p_ai|confidence)\s*[:=]\s*0?\.[0-9]/.test(demoBlock), "demo must not hardcode scores");
});

// A tiny DOM so app.js can run under node. It stores only what the assertions read; everything else is a no-op.
function fakeDom(search) {
  const byId = new Map();
  const cl = () => { const s = new Set(); return { add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c), toggle: (c, f) => { const on = f === undefined ? !s.has(c) : f; on ? s.add(c) : s.delete(c); return on; } }; };
  function El(id) {
    return { id, dataset: {}, style: {}, attrs: {}, children: [], classList: cl(), textContent: "", innerHTML: "", hidden: false, disabled: false,
      value: "", scrollHeight: 0, scrollTop: 0, clientHeight: 0, onclick: null,
      appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      removeAttribute(k) { delete this.attrs[k]; }, addEventListener() {}, removeEventListener() {}, focus() {}, remove() {}, querySelector() { return El("q"); }, querySelectorAll() { return []; } };
  }
  const get = (id) => { if (!byId.has(id)) byId.set(id, El(id)); return byId.get(id); };
  const document = {
    documentElement: El("html"),
    getElementById: get, createElement: () => El("new"), createElementNS: () => El("ns"),
    querySelector: () => El("q"), querySelectorAll: () => [], addEventListener() {},
  };
  const sandbox = {
    document, navigator: {}, console, addEventListener() {}, removeEventListener() {},
    location: { search, protocol: "http:", href: "http://localhost/" },
    URL, URLSearchParams, Promise, Math, JSON, Int16Array, ArrayBuffer, Float32Array, performance, AbortController,
    matchMedia: () => ({ matches: true }),                       // reduced motion: swapText runs synchronously
    localStorage: { getItem: () => null, setItem: () => {} },
    setTimeout: (fn, ms) => { const t = global.setTimeout(fn, ms); if (t && t.unref) t.unref(); return t; },
    clearTimeout: (t) => global.clearTimeout(t), setInterval: () => 0, clearInterval: () => {},
    requestAnimationFrame: () => 0, cancelAnimationFrame: () => {},
    fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
  };
  sandbox.window = sandbox;                                        // app.js reads window.DSPcm etc. off the global
  sandbox.DSPcm = P; sandbox.DSProtocol = X; sandbox.DSVerdict = V; sandbox.DSAuto = require("../lib/autolisten.js"); sandbox.DSDemo = DM;
  return sandbox;
}
const loadApp = (search) => { const s = fakeDom(search); vm.runInNewContext(readFileSync(join(root, "app.js"), "utf8"), s); return s; };
const settle = () => new Promise((r) => setTimeout(r, 20));

test("demo mode stays hidden and off until it is explicitly entered", async () => {
  const s = loadApp("?test=1");
  await settle();
  assert.equal(s.__ds.S.demo, false, "not in demo mode on a normal boot");
  assert.notEqual(s.document.getElementById("dock").dataset.state, "demo");
});

test("entering demo shows the persistent RECORDED-DEMO banner", async () => {
  const s = loadApp("?test=1");
  await settle();
  s.__ds.enterDemo();
  assert.equal(s.__ds.S.demo, true);
  assert.equal(s.document.getElementById("demo-banner").hidden, false, "banner visible in demo mode");
  assert.equal(s.document.getElementById("dock").dataset.state, "demo");
  assert.equal(s.document.documentElement.dataset.demo, "1");
});

test("the UI renders whatever tier the engine sends — verdicts are never hardcoded", async () => {
  const s = loadApp("?test=1");
  await settle();
  s.__ds.listening();                                                            // enter the live view (as a real call would)
  const evt = (tier) => ({ type: "verdict", tick: 0, elapsed_s: 5,
    stable: { state: "steady", tier, alert: "none", reasons: [] },
    verdict: { tier, p_ai: 0.2, p_scam: 0.2, confidence: 0.7, tells: [] } });
  const html = s.document.documentElement, orb = s.document.getElementById("orb-word");
  for (const tier of ["human", "ai_undisclosed", "scam", "ai_disclosed"]) {      // the engine, not the app, chooses the tier
    s.__ds.onEvent(evt(tier));
    assert.equal(html.dataset.tier, tier, "orb colour follows the engine's tier: " + tier);
    assert.equal(orb.textContent, V.ORB_WORD[tier], "orb word follows the engine's tier: " + tier);
  }
  s.__ds.onEvent({ type: "verdict", tick: 1, elapsed_s: 6, stable: { state: "warming" }, verdict: { tier: "scam" } });
  assert.equal(orb.textContent, "Listening", "a warming event shows Listening, not a verdict");
});
