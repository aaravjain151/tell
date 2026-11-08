/* Illustration of the live card: a scripted animation on a loop. Words and stage changes follow apps/web/mock_live.py,
   the same script used to test the real app screens. It is labelled as a recording on the page. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var root = document.documentElement;
  var reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var STEP_S = 2;            // call seconds per tick in the replay
  var LAST = 17;
  var LINES = [
    [0, "Hi Grandma, it’s me."], [2, "How are you doing? I wanted to hear your voice."],
    [4, "I was thinking about coming over this weekend."], [7, "Grandma, it’s me, this is your grandson."],
    [8, "I’m in trouble, I got in an accident and I’m at the police station."],
    [10, "I need bail money right now, please don’t tell mom or dad."], [12, "The officer says you can wire the money within the hour."],
    [14, "Please hurry, I’m scared."], [17, "Don’t hang up. Just do it quickly."]
  ];
  var MARKS = ["this is your grandson", "I’m in trouble", "need bail", "right now", "don’t tell mom", "wire the money", "within the hour"];
  function stage(k) {
    if (k <= 2) return { tier: "unsure", h: "Listening", warm: true };
    if (k <= 6) return { tier: "human", h: "Sounds human" };
    if (k <= 8) return { tier: "unsure", h: "Not sure yet" };
    return { tier: "scam", h: "Scam pattern" };
  }
  function esc(s) { return s.replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }
  function mark(s) {
    var h = esc(s);
    MARKS.forEach(function (m) { var e = esc(m); h = h.split(e).join("<mark>" + e + "</mark>"); });
    return h;
  }
  function mmss(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }

  var cells = $("demo-cells"), timer = 0, lastShown = "", lastShownPrev = "";
  if (!cells) return;
  function buildCells() { cells.innerHTML = ""; for (var i = 0; i <= LAST; i++) cells.appendChild(document.createElement("i")); }

  function drawFrame(k, st, changed) {
    var now = k * STEP_S;
    root.dataset.tier = st.warm ? "unsure" : st.tier;
    $("demo-clock").textContent = mmss(now);
    $("demo-h").textContent = st.h;
    var said = LINES.filter(function (l) { return l[0] <= k; }).map(function (l) { return l[1]; }).join(" ");
    $("demo-tx").innerHTML = mark(said);
    var q = $("demo-q"), quad = $("demo-quad"), on = quad.querySelectorAll("i");
    on.forEach(function (c) { c.className = ""; });
    if (st.warm) q.innerHTML = "Gathering a few seconds before judging.<small>It does not guess early.</small>";
    else if (st.tier === "scam") { on[1].className = "on"; quad.style.setProperty("--c", "var(--red)"); q.innerHTML = "Human voice, but scam pattern in what was said.<small>Two separate answers.</small>"; }
    else if (st.tier === "human") { on[0].className = "on"; quad.style.setProperty("--c", "var(--teal)"); q.innerHTML = "Human voice, nothing in the words stood out.<small>Two separate answers.</small>"; }
    else q.innerHTML = "Something in the words is off.<small>Keeping an eye on it.</small>";
    if (changed) $("demo-changed").textContent = "Changed to " + st.h + " at " + mmss(now) + ", was " + lastShownPrev + ".";
    else if (st.warm) $("demo-changed").textContent = "";
    var cs = cells.children;
    for (var i = 0; i < cs.length; i++) { var s = stage(i); cs[i].className = i > k ? "" : s.warm ? "u" : s.tier === "human" ? "h" : s.tier === "scam" ? "s" : "u"; }
    if (changed && !reduced) { var r = $("demo-rule"); r.classList.remove("go"); void r.offsetWidth; r.classList.add("go"); }
  }
  function frame(k) {
    var st = stage(k), prev = lastShown;
    lastShownPrev = prev;
    drawFrame(k, st, !st.warm && !!prev && prev !== st.h);
    if (!st.warm) lastShown = st.h;
  }

  function play() {
    clearTimeout(timer); lastShown = ""; lastShownPrev = ""; $("demo-changed").textContent = "";
    var k = 0;
    (function next() {
      frame(k);
      if (k < LAST) { k++; timer = setTimeout(next, 650); }
      else timer = setTimeout(play, 5000);
    })();
  }

  buildCells();
  var btn = $("demo-replay");
  if (reduced) {
    for (var k = 0; k <= LAST; k++) frame(k);   // final frame, no motion
    btn.hidden = false; btn.addEventListener("click", function () { btn.disabled = true; var j = 0; var t = setInterval(function () { frame(j++); if (j > LAST) { clearInterval(t); btn.disabled = false; } }, 650); });
  } else {
    play();
  }

  var th = $("theme");
  function dark() { return root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; }
  function sync() { th.textContent = dark() ? "(Light)" : "(Dark)"; }
  th.addEventListener("click", function () { root.dataset.theme = dark() ? "light" : "dark"; try { localStorage.setItem("ds-theme", root.dataset.theme); } catch (e) {} sync(); });
  sync();
})();
