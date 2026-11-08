/* Doublespeak for Android: thin client. The phone captures microphone audio (speaker mode) and sends PCM16 16 kHz to the
   Doublespeak engine on the owner's computer over loopback (adb reverse). Display comes from GET /live/events.
   No LAN, no cloud, no analytics; nothing is stored. Passive only: it never speaks to the caller. */
(function () {
  "use strict";
  var P = window.DSPcm, X = window.DSProtocol, V = window.DSVerdict;
  var HTML = document.documentElement, $ = function (id) { return document.getElementById(id); };
  var API = X.loopbackApi(location.search, "http://localhost:8000");
  var QS = new URLSearchParams(location.search);
  var REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var CONSENT_KEY = "ds-android-consent-v1";
  var TUNNEL_CMD = "adb reverse tcp:8000 tcp:8000";
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  var native = function () { return window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.ListenService; };

  var S = {
    mode: "boot",            // boot | offline | idle | starting | listening | ended
    engine: false, health: null, pAiThr: 0.6,
    ws: null, stream: null, ctx: null, node: null, wake: null, ready: false,
    tier: null, tick: -1, elapsed: 0, startedAt: 0, ticks: [], alert: "none", dismissed: false, lastSig: "",
    level: 0, maxLevel: 0, sentBytes: 0, foreign: false, err: null, installEvt: null, ping: 0,
  };

  /* ---------- small helpers ---------- */
  function setMode(m) {
    S.mode = m; HTML.dataset.mode = m;
    $("dock").dataset.state = m === "listening" || m === "starting" ? "live" : m === "ended" ? "end" : "idle";
    $("pair").hidden = !(m === "offline");
    $("steps").hidden = !(m === "idle" || m === "offline" && false);
    $("read").hidden = !(S.tier && (m === "listening" || m === "ended"));
    var st = $("start"); st.disabled = m === "offline" || m === "boot";
    $("start-t").textContent = m === "offline" ? "Connect to your computer first" : "Start listening";
    $("dock-note").textContent = m === "offline" ? "Run the command above, then check again." : "Speaker mode. Put the call on speakerphone first.";
    if (m === "offline") drawIdleHero("Offline", "", "Not connected to your computer", "The app opens, but the engine on your computer cannot be reached yet.");
    if (m === "idle") drawIdleHero("Ready", "", "Waiting for a call", "Put the call on speakerphone, then tap Start listening.");
  }
  function toast(t) { var e = $("toast"); e.textContent = t; e.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(function () { e.hidden = true; }, 3200); }
  function chip(state, text) { var c = $("conn"); c.dataset.s = state; $("conn-t").textContent = text; }

  /* ---------- orb ---------- */
  var NT = 48, SVGNS = "http://www.w3.org/2000/svg";
  (function buildTicks() {
    var g = $("ticks"), c = 120;
    for (var i = 0; i < NT; i++) {
      var a = (i / NT) * 2 * Math.PI - Math.PI / 2, l = document.createElementNS(SVGNS, "line");
      l.setAttribute("x1", (c + Math.cos(a) * 93).toFixed(2)); l.setAttribute("y1", (c + Math.sin(a) * 93).toFixed(2));
      l.setAttribute("x2", (c + Math.cos(a) * 108).toFixed(2)); l.setAttribute("y2", (c + Math.sin(a) * 108).toFixed(2));
      l.setAttribute("class", "tk"); g.appendChild(l);
    }
  })();
  function lit(n) { var t = $("ticks").children; for (var i = 0; i < t.length; i++) t[i].classList.toggle("on", i < n); }
  function swapText(h, a) {
    var hero = document.querySelector(".hero");
    if ($("headline").textContent === h && $("advice").textContent === a) return;
    var go = function () { $("headline").textContent = h; $("advice").textContent = a; hero.classList.remove("swap"); };
    if (REDUCED) return go();
    hero.classList.add("swap"); setTimeout(go, 220);
  }
  function drawIdleHero(word, sub, h, a) {
    HTML.dataset.tier = ""; lit(0); $("orb-word").textContent = word; $("orb-sub").textContent = sub;
    $("headline").textContent = h; $("advice").textContent = a; $("changed").hidden = true; $("caution").hidden = true;
    $("orb").setAttribute("aria-label", word);
  }

  /* ---------- connection ---------- */
  function connectHtml(full) {
    var h = S.health, up = S.engine, ok = function (v) { return v ? "1" : "0"; };
    var egress = h && h.egress ? Number(h.egress.caller_audio_bytes_sent) || 0 : null;
    return '<h2 id="' + (full ? "pair-h" : "cn-h") + '">' + (up ? "Connected to your computer" : "Connect to your computer") + "</h2>" +
      "<p>" + (up ? "The engine answers over the USB cable. Audio goes only there." :
        "Doublespeak runs on your computer. The phone only listens and sends the audio over the USB cable. Nothing goes over Wi-Fi or the internet.") + "</p>" +
      (up ? "" : '<p class="num">On your computer, with the phone plugged in and USB debugging on, run:</p>' +
        '<div class="cmd"><code>' + TUNNEL_CMD + '</code><button type="button" data-copy>Copy</button></div>' +
        '<p class="num">Then start the engine: <b>make api-android</b>. Keep the cable plugged in while you listen.</p>') +
      '<ul class="checks">' +
      '<li data-ok="1"><i></i><span>This app is on your phone<small>' + (native() ? "Installed app" : "Opened in the browser") + "</small></span></li>" +
      '<li data-ok="' + ok(up) + '"><i></i><span>' + (up ? "Engine reachable" : "Engine not reachable") + "<small>" + esc(API) + (up ? " answers" : " does not answer yet") + "</small></span></li>" +
      (egress === null ? "" : '<li data-ok="1"><i></i><span>Caller audio sent outside your computer: ' + egress + ' bytes<small>Reported by the engine.</small></span></li>') +
      "</ul>" +
      '<div class="sheet-actions"><button class="btn primary" type="button" data-recheck>Check connection</button>' +
      (S.installEvt && !native() ? '<button class="btn ghost" type="button" data-install>Add to Home screen</button>' : "") + "</div>";
  }
  function bindConnect(root) {
    root.querySelectorAll("[data-copy]").forEach(function (b) { b.onclick = function () {
      (navigator.clipboard ? navigator.clipboard.writeText(TUNNEL_CMD) : Promise.reject()).then(function () { b.textContent = "Copied"; }, function () { toast("Select the command and copy it"); });
    }; });
    root.querySelectorAll("[data-recheck]").forEach(function (b) { b.onclick = function () { b.textContent = "Checking..."; probe().then(function () { renderConnect(); }); }; });
    root.querySelectorAll("[data-install]").forEach(function (b) { b.onclick = function () { S.installEvt.prompt(); S.installEvt = null; renderConnect(); }; });
  }
  function renderConnect() {
    $("pair").innerHTML = connectHtml(true); bindConnect($("pair"));
    $("connect-body").innerHTML = connectHtml(false); bindConnect($("connect-body"));
  }
  function probe() {
    var ctl = new AbortController(), to = setTimeout(function () { ctl.abort(); }, 2500);
    return fetch(API + "/health", { cache: "no-store", signal: ctl.signal }).then(function (r) { return r.json(); }).then(function (j) {
      clearTimeout(to); S.engine = !!j.ok; S.health = j;
      return fetch(API + "/thresholds", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (th) {
        if (th && th.P_AI_THRESHOLD > 0 && th.P_AI_THRESHOLD < 1) S.pAiThr = th.P_AI_THRESHOLD;
      }).catch(function () {});
    }).catch(function () { clearTimeout(to); S.engine = false; S.health = null; }).then(function () {
      chip(S.engine ? "up" : "down", S.engine ? "Your computer" : "Not connected");
      if (S.mode === "boot" || S.mode === "offline" || S.mode === "idle") setMode(S.engine ? "idle" : "offline");
      renderConnect();
    });
  }

  /* ---------- live feed (SSE) ---------- */
  var conn = { es: null, tries: 0, timer: 0 };
  function feed() {
    clearTimeout(conn.timer);
    if (typeof EventSource === "undefined") return;
    var es; try { es = new EventSource(API + "/live/events"); } catch (e) { return retry(); }
    conn.es = es;
    es.onopen = function () { conn.tries = 0; if (!S.engine) probe(); };
    es.onmessage = function (m) { var e; try { e = JSON.parse(m.data); } catch (x) { return; } if (e && typeof e === "object") onEvent(e); };
    es.onerror = function () { es.close(); if (S.mode === "listening") lostNote(); retry(); if (S.mode !== "listening") probe(); };
  }
  function retry() { conn.tries++; conn.timer = setTimeout(feed, Math.min(15000, 1000 * Math.pow(2, Math.min(conn.tries - 1, 4)))); }
  function lostNote() { var n = $("live-note"); n.textContent = "Lost contact with your computer. Check the USB cable."; n.classList.add("warn"); }
  function onEvent(e) {
    if (e.type === "state") {
      S.foreign = !!e.active && S.mode !== "listening" && S.mode !== "starting";
      if (S.mode === "idle") $("dock-note").textContent = S.foreign ? "Another listener is active on your computer" : "Speaker mode. Put the call on speakerphone first.";
    } else if (e.type === "verdict" && (S.mode === "listening" || S.mode === "ended" && false)) onVerdict(e);
    else if (e.type === "ended" && S.mode === "listening" && !S.ws) finish();
  }

  var pending = null;
  function onVerdict(e) {
    var st = e.stable || {}, v = e.verdict || {};
    if (e.tick != null && e.tick < S.tick) { S.ticks = []; S.tier = null; }
    S.tick = e.tick; S.elapsed = e.elapsed_s || S.elapsed;
    var warm = st.state === "warming", tier = st.tier || v.tier || "unsure";
    S.ticks.push({ tier: tier, t: S.elapsed, w: warm ? 1 : 0 });
    var prev = S.tier, shown = warm ? "unsure" : tier;
    HTML.dataset.tier = shown;
    var sv = V.stableView(v, st), sc = V.scoresOf(sv);
    var word = warm ? "Listening" : V.ORB_WORD[tier] || tier;
    $("orb-word").textContent = word;
    $("orb-sub").textContent = warm ? "Gathering speech" : tier === "scam" || tier === "ai_undisclosed" || tier === "ai_disclosed" || tier === "human" ? V.LEVELS[sc.level] + " risk" : "";
    $("orb").setAttribute("aria-label", "Verdict: " + word + (warm ? "" : ". Risk " + V.LEVELS[sc.level] + "."));
    lit(warm ? 0 : V.ringTicks(sc, NT));
    var txt = warm ? { h: "Listening", a: "Gathering the first few seconds before judging." } :
      (tier === v.tier && v.headline ? { h: v.headline, a: v.advice } : V.TEXT[tier] || V.TEXT.unsure);
    swapText(txt.h, txt.a);
    if (!warm) {
      if (prev && prev !== tier) { $("changed").hidden = false; $("changed").innerHTML = "Changed to <b>" + esc(V.TIER[tier] || tier) + "</b> at " + V.mmss(S.elapsed) + ", was " + esc(V.TIER[prev] || prev) + "."; }
      S.tier = tier;
    } else if (!S.tier) S.tier = "unsure";
    $("read").hidden = false; $("steps").hidden = true;
    var sig = JSON.stringify([warm, tier, sc, st.reasons]);
    if (sig !== S.lastSig) { S.lastSig = sig; drawRead(sv, sc, warm); }
    drawTimeline(); drawText(v);
    alertState(st.alert || "none", sv, txt);
  }
  function px(el, x, n) { n = n || 12; var k = Math.round(Math.max(0, Math.min(1, x)) * n), h = ""; for (var i = 0; i < n; i++) h += '<i class="' + (i < k ? "on" : "") + '"></i>'; el.innerHTML = h; }
  function drawRead(sv, sc, warm) {
    var q = V.quadrantOf(sv, S.pAiThr);
    [].forEach.call($("quad-grid").children, function (c) {
      var p = c.dataset.c.split("_"), vo = p[0], it = p[1], vm = q.voice === vo, im = (q.intent === "scam") === (it === "scam");
      var vOk = q.voice === "unclear" || vm, iOk = q.intent === "unclear" || (q.intent === "scam") === (it === "scam");
      c.className = warm ? "" : q.combo !== "unclear" ? (vm && im ? "on" : "") : (vOk && iOk ? "maybe" : "");
    });
    $("quad-grid").setAttribute("aria-label", q.voice_label + ". " + q.intent_label + ". " + q.combo_label);
    $("quad-txt").textContent = warm ? "Still listening: not enough speech yet to judge." : q.combo_label;
    $("s-scam").textContent = warm ? "-" : sc.scam; px($("p-scam"), warm ? 0 : sc.scam / 100);
    $("s-ai").textContent = warm ? "-" : sc.ai_voice; px($("p-ai"), warm ? 0 : sc.ai_voice / 100);
    $("s-conf").textContent = warm ? "-" : V.LEVELS[sc.confidence_label]; px($("p-conf"), warm ? 0 : sc.confidence / 100);
    $("why").innerHTML = warm ? "" : V.plainReasons(sv).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("");
  }
  function drawTimeline() {
    var t = S.ticks.slice(-60), prev = null, h = "";
    t.forEach(function (x) { var chg = !x.w && prev !== null && x.tier !== prev; if (!x.w) prev = x.tier; h += '<i class="' + (chg ? "chg" : "") + '" data-t="' + esc(x.tier) + '" data-w="' + x.w + '"></i>'; });
    $("tl").innerHTML = h; $("tl-end").textContent = V.mmss(t.length ? t[t.length - 1].t : 0);
    var segs = []; t.forEach(function (x) { if (x.w) return; var l = segs[segs.length - 1]; if (!l || l.tier !== x.tier) segs.push({ tier: x.tier, t: x.t }); });
    $("tl").setAttribute("aria-label", "The call so far: " + (segs.length ? segs.map(function (g, i) { return (i ? "then " : "") + (V.TIER[g.tier] || g.tier) + " from " + V.mmss(g.t); }).join(", ") : "still warming up") + ".");
    $("tl-note").textContent = segs.length > 1 ? (segs.length - 1) + " change" + (segs.length > 2 ? "s" : "") : "";
  }
  function drawText(v) {
    var box = $("tx"), text = v.transcript || "";
    if (!text.trim()) { box.innerHTML = '<span class="none">Nothing heard yet. Speech appears here as it is understood.</span>'; return; }
    var marks = V.buildMarks(text, v.tells), h = "", at = 0, stick = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    marks.forEach(function (r) { h += esc(text.slice(at, r.s)) + '<mark title="' + esc((V.NAMES[r.t.name] || r.t.name)) + '">' + esc(text.slice(r.s, r.e)) + "</mark>"; at = r.e; });
    box.innerHTML = h + esc(text.slice(at)); if (stick) box.scrollTop = box.scrollHeight;
  }

  /* ---------- alerts + haptics (amber and red only) ---------- */
  function buzz(p) { try { if (navigator.vibrate) navigator.vibrate(p); } catch (e) {} }
  function alertState(a, sv, txt) {
    if (a !== S.alert) {
      if (a === "amber") buzz([80, 60, 80]);
      if (a === "red" && !S.dismissed) buzz([300, 120, 300, 120, 600]);
    }
    if (a !== "red") S.dismissed = false;
    S.alert = a;
    var cau = $("caution");
    if (a === "amber") { cau.hidden = false; cau.textContent = (sv.reasons && sv.reasons[0]) || "Part of this call sounds risky. Do not share money, codes or passwords."; }
    else cau.hidden = true;
    var showRed = a === "red" && !S.dismissed;
    if ($("alert").hidden === showRed) {
      $("alert").hidden = !showRed;
      if (showRed) {
        $("al-a").textContent = txt && txt.a || V.TEXT.scam.a;
        $("al-why").innerHTML = V.plainReasons(sv).slice(0, 3).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("");
        setTimeout(function () { $("al-dismiss").focus(); }, 0);
      }
    }
  }
  function dismissAlert() {
    S.dismissed = true; $("alert").hidden = true;
    if (S.ws && S.ws.readyState === 1) try { S.ws.send(JSON.stringify({ type: "dismiss" })); } catch (e) {}
    fetch(API + "/live/dismiss", { method: "POST" }).catch(function () {});
  }

  /* ---------- level meter ---------- */
  var MC = 14;
  (function () { var h = ""; for (var i = 0; i < MC; i++) h += "<i></i>"; $("meter").innerHTML = h; })();
  var meterRaf = 0;
  function drawMeter() {
    meterRaf = 0;
    var db = S.level > 0 ? 20 * Math.log10(S.level) : -90, x = Math.max(0, Math.min(1, (db + 60) / 50)), k = Math.round(x * MC);
    [].forEach.call($("meter").children, function (c, i) { c.classList.toggle("on", i < k); });
  }
  function clock() {
    if (S.mode !== "listening") return;
    var s = (performance.now() - S.startedAt) / 1000;
    $("live-sub").textContent = V.mmss(s) + " · speaker mode";
    if (s > 8 && S.maxLevel < 0.003 && !$("live-note").classList.contains("warn")) {
      var n = $("live-note"); n.classList.add("warn");
      n.textContent = "No sound is reaching the microphone. Is the call on speakerphone? Some phones silence the mic during calls.";
    }
  }
  setInterval(clock, 500);

  /* ---------- listening ---------- */
  function fail(title, body) {
    S.err = { title: title, body: body }; cleanup();
    var e = $("err"); e.hidden = false; e.innerHTML = "<h2>" + esc(title) + "</h2><p>" + esc(body) + "</p>";
    setMode(S.engine ? "idle" : "offline"); $("err").hidden = false;
    HTML.dataset.tier = "";
  }
  function consent() {
    return new Promise(function (res) {
      if (store.get(CONSENT_KEY) === "yes") return res(true);
      openSheet("sheet-consent");
      $("consent-yes").onclick = function () { store.set(CONSENT_KEY, "yes"); closeSheets(); res(true); };
      $("consent-no").onclick = function () { closeSheets(); res(false); };
    });
  }
  function start() {
    if (S.mode === "listening" || S.mode === "starting") return;
    $("err").hidden = true;
    consent().then(function (ok) { if (ok) begin(); });
  }
  function begin() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return fail("Microphone not available", "This browser cannot capture audio here. Open the Doublespeak app, or Chrome at http://localhost.");
    setMode("starting"); resetSession();
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } }).then(function (stream) {
      S.stream = stream;
      var svc = native(); if (svc && svc.start) svc.start().catch(function () {});   // foreground service: capture survives screen lock
      return openSession().then(function (ws) { S.ws = ws; return startCapture(stream); });
    }).then(function () {
      S.startedAt = performance.now(); setMode("listening"); HTML.dataset.tier = "";
      drawIdleHero("Listening", "Gathering speech", "Listening", "Gathering the first few seconds before judging.");
      $("live-note").textContent = "Audio goes only to your computer over USB. Nothing is saved."; $("live-note").classList.remove("warn");
      $("steps").hidden = true; wakeLock();
      S.ping = setInterval(function () { if (S.ws && S.ws.readyState === 1) S.ws.send('{"type":"ping"}'); }, 10000);
    }).catch(function (e) {
      var n = e && e.name, m = e && e.message || "";
      if (n === "NotAllowedError" || n === "SecurityError") fail("Microphone is blocked", "Allow the microphone for Doublespeak in your phone's app settings (Permissions > Microphone), then tap Start listening again.");
      else if (n === "NotFoundError") fail("No microphone found", "This phone did not offer a microphone to the app.");
      else if (m === "origin") fail("The engine refused this page", "Start the engine with make api-android so it accepts the app, then try again.");
      else if (m === "busy") fail("Another listening session is open", "Stop it on your computer, or wait a minute, then try again.");
      else fail("Could not start listening", "Check the USB cable and that the engine is running on your computer. (" + (m || n || "unknown") + ")");
    });
  }
  function openSession() {
    return fetch(API + "/session", { method: "POST" }).then(function (r) {
      if (r.status === 403) throw new Error("origin"); if (r.status === 429) throw new Error("busy"); if (!r.ok) throw new Error("session " + r.status);
      return r.json();
    }).then(function (j) {
      return new Promise(function (res, rej) {
        var ws = new WebSocket(X.wsUrl(API, j.ws_path || "/ws/stream")); ws.binaryType = "arraybuffer"; var done = false;
        var t = setTimeout(function () { if (!done) { done = true; try { ws.close(); } catch (e) {} rej(new Error("no answer from the engine")); } }, 8000);
        ws.onopen = function () { ws.send(JSON.stringify(X.hello(j.token))); };
        ws.onmessage = function (m) {
          var d; try { d = JSON.parse(m.data); } catch (e) { return; }
          if (d.type === "ready" && !done) { done = true; clearTimeout(t); S.ready = true; res(ws); }
          else if (d.type === "error") { if (!done) { done = true; clearTimeout(t); rej(new Error(d.code || "error")); } else if (S.mode === "listening") { toast("Engine: " + d.code); } }
          else if (d.type === "warn" && d.code) toast(d.code === "lagging" ? "The engine is a little behind" : "The engine is busy");
          else if (d.type === "final") finish();
        };
        ws.onclose = function () { clearTimeout(t); if (!done) { done = true; rej(new Error("connection closed")); } else if (S.mode === "listening") { finish("The connection to your computer closed."); } };
        ws.onerror = function () {};
      });
    });
  }
  function startCapture(stream) {
    var AC = window.AudioContext || window.webkitAudioContext, ctx;
    try { ctx = new AC({ sampleRate: P.TARGET_RATE, latencyHint: "interactive" }); } catch (e) { ctx = new AC(); }
    S.ctx = ctx;
    return ctx.audioWorklet.addModule("worklet.js").then(function () {
      var src = ctx.createMediaStreamSource(stream), node = new AudioWorkletNode(ctx, "ds-capture", { numberOfOutputs: 1, outputChannelCount: [1] });
      var pipe = P.createPipeline({ inRate: ctx.sampleRate,
        onLevel: function (l) { S.level = l; if (l > S.maxLevel) S.maxLevel = l; if (!meterRaf) meterRaf = requestAnimationFrame(drawMeter); },
        onFrame: function (f) { if (S.ws && S.ws.readyState === 1 && S.ready) { if (S.ws.bufferedAmount < 1 << 20) S.ws.send(f.buffer); S.sentBytes += f.byteLength; } } });
      node.port.onmessage = function (m) { pipe.push(m.data); };
      var mute = ctx.createGain(); mute.gain.value = 0;
      src.connect(node); node.connect(mute); mute.connect(ctx.destination);
      S.node = node;
      return ctx.state === "suspended" ? ctx.resume() : null;
    });
  }
  function resetSession() {
    S.tier = null; S.tick = -1; S.elapsed = 0; S.ticks = []; S.alert = "none"; S.dismissed = false; S.lastSig = ""; S.level = 0; S.maxLevel = 0; S.sentBytes = 0; S.ready = false;
    $("alert").hidden = true; $("read").hidden = true; $("tx").innerHTML = ""; $("tl").innerHTML = ""; $("why").innerHTML = ""; $("changed").hidden = true; $("caution").hidden = true;
  }
  function cleanup() {
    clearInterval(S.ping);
    try { if (S.node) { S.node.port.onmessage = null; S.node.disconnect(); } } catch (e) {}
    try { if (S.stream) S.stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    try { if (S.ctx) S.ctx.close(); } catch (e) {}
    var ws = S.ws; S.ws = null; S.node = null; S.stream = null; S.ctx = null; S.ready = false;
    try { if (ws) { ws.onclose = null; ws.close(); } } catch (e) {}
    try { if (S.wake) S.wake.release(); } catch (e) {} S.wake = null;
    var svc = native(); if (svc && svc.stop) svc.stop().catch(function () {});
    S.level = 0; drawMeter();
  }
  function stop() {
    if (S.ws && S.ws.readyState === 1) try { S.ws.send('{"type":"stop"}'); } catch (e) {}
    finish();
  }
  function finish(why) {
    if (S.mode !== "listening" && S.mode !== "starting") return;
    var secs = (performance.now() - S.startedAt) / 1000;
    cleanup(); $("alert").hidden = true;
    setMode("ended");
    $("end-sub").textContent = (why ? why + " " : "") + V.mmss(secs) + " listened. Nothing was saved.";
    $("orb-sub").textContent = S.tier ? "Stopped" : "";
    $("read").hidden = !S.tier;
    if (!S.tier) { $("steps").hidden = true; drawIdleHero("Stopped", "", "Listening stopped", "No verdict was reached. Start again when the call is on speakerphone."); }
  }
  function clearScreen() { $("err").hidden = true; resetSession(); setMode(S.engine ? "idle" : "offline"); }
  function wakeLock() {
    if (!navigator.wakeLock) return;
    navigator.wakeLock.request("screen").then(function (l) { S.wake = l; }).catch(function () {});
  }
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible" && S.mode === "listening" && (!S.wake || S.wake.released)) wakeLock(); });

  /* ---------- sheets ---------- */
  var lastFocus = null;
  function openSheet(id) {
    closeSheets(true); lastFocus = document.activeElement; $("scrim").hidden = false; var s = $(id); s.hidden = false;
    var f = s.querySelector("button.primary, button"); if (f) f.focus();
  }
  function closeSheets(keep) {
    ["sheet-consent", "sheet-speaker", "sheet-connect"].forEach(function (i) { $(i).hidden = true; }); $("scrim").hidden = true;
    if (!keep && lastFocus && lastFocus.focus) try { lastFocus.focus(); } catch (e) {}
  }
  document.querySelectorAll("[data-close]").forEach(function (b) { b.onclick = function () { closeSheets(); }; });
  $("scrim").onclick = function () { if (!$("sheet-consent").hidden) $("consent-no").click(); else closeSheets(); };
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("scrim").hidden) $("scrim").click(); });

  $("start").onclick = start; $("stop").onclick = stop; $("again").onclick = function () { clearScreen(); start(); };
  $("clear").onclick = clearScreen; $("al-dismiss").onclick = dismissAlert;
  $("open-speaker").onclick = function () { openSheet("sheet-speaker"); };
  $("conn").onclick = function () { renderConnect(); openSheet("sheet-connect"); };
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); S.installEvt = e; renderConnect(); });

  /* ---------- boot ---------- */
  if ("serviceWorker" in navigator && location.protocol.indexOf("http") === 0 && !native()) navigator.serviceWorker.register("sw.js").catch(function () {});
  if (QS.get("test") === "1") {            // test harness only (screenshots without a mic); never linked from the UI
    window.__ds = { S: S, onEvent: onEvent, setMode: function (m) { setMode(m); }, listening: function () { S.startedAt = performance.now(); resetSession(); setMode("listening"); drawIdleHero("Listening", "Gathering speech", "Listening", "Gathering the first few seconds before judging."); },
      level: function (l) { S.level = l; S.maxLevel = Math.max(S.maxLevel, l); drawMeter(); }, finish: finish, sheet: openSheet };
  }
  setMode("boot"); chip("", "Checking"); drawIdleHero("...", "", "Looking for your computer", "One moment.");
  renderConnect();
  probe().then(feed);
})();
