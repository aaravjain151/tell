/* Demo mode (stage): streams a BUNDLED recorded PCM16 16 kHz mono clip into the REAL engine over the same
   /session + WS /ws/stream path the microphone uses, at real-time pace (100 ms frames). The orb and verdict are the
   engine's genuine output for a known input: nothing here fakes a tier, score or alert. The clip is always labelled a
   recorded demo on screen, never presented as a live call. Pure (no DOM); used by the page and the node tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DSDemo = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var FRAME_BYTES = 3200;            // 100 ms of PCM16 mono 16 kHz = 1600 samples = 3200 bytes (matches lib/pcm.js)
  var FRAME_MS = 100;

  /* Split a raw PCM16 clip (ArrayBuffer) into fixed-size frames. Byte lengths stay even (whole samples); any trailing
     odd byte is dropped so the engine never sees half a sample. Returns an array of ArrayBuffer frames. */
  function frameClip(buf, frameBytes) {
    frameBytes = frameBytes || FRAME_BYTES;
    if (frameBytes % 2) frameBytes -= 1;
    var total = buf.byteLength - (buf.byteLength % 2), frames = [];
    for (var off = 0; off < total; off += frameBytes) frames.push(buf.slice(off, Math.min(off + frameBytes, total)));
    return frames;
  }

  /* RMS level 0..1 of one PCM16 frame, so the meter animates from the real clip (display only). */
  function levelOf(buf) {
    var v = new Int16Array(buf), a = 0;
    for (var i = 0; i < v.length; i++) { var s = v[i] / 32768; a += s * s; }
    return v.length ? Math.sqrt(a / v.length) : 0;
  }

  /* Paces frames one per interval. Timers are injectable so tests can drive it with a fake clock and a fake WS.
     opts: { frames, send(frame), onFrame(frame, i), onDone(), intervalMs, setTimer(fn,ms)->id, clearTimer(id) }. */
  function createStreamer(opts) {
    var frames = opts.frames || [], interval = opts.intervalMs != null ? opts.intervalMs : FRAME_MS;
    var setT = opts.setTimer || function (fn, ms) { return setTimeout(fn, ms); };
    var clrT = opts.clearTimer || function (id) { clearTimeout(id); };
    var i = 0, timer = null, running = false, finished = false;
    function tick() {
      if (!running) return;
      if (i >= frames.length) { running = false; finished = true; if (opts.onDone) opts.onDone(); return; }
      var f = frames[i]; i++;
      if (opts.send) opts.send(f);
      if (opts.onFrame) opts.onFrame(f, i - 1);
      timer = setT(tick, interval);
    }
    return {
      start: function () { if (running || finished) return; running = true; tick(); },
      stop: function () { running = false; if (timer != null) clrT(timer); timer = null; },
      sent: function () { return i; },
      total: function () { return frames.length; },
      running: function () { return running; },
    };
  }

  return { FRAME_BYTES: FRAME_BYTES, FRAME_MS: FRAME_MS, frameClip: frameClip, levelOf: levelOf, createStreamer: createStreamer };
});
