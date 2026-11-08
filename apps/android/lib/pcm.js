/* Tell for Android: microphone samples -> PCM16 mono 16 kHz frames.
   Pure functions (no DOM), loaded by the page and by the node tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DSPcm = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var TARGET_RATE = 16000, FRAME_MS = 100;

  /* Float32 [-1,1] -> Int16 samples (clamped). */
  function floatToPcm16(f32) {
    var out = new Int16Array(f32.length);
    for (var i = 0; i < f32.length; i++) {
      var s = f32[i];
      if (s !== s) s = 0;                       // NaN
      s = s < -1 ? -1 : s > 1 ? 1 : s;
      out[i] = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767);
    }
    return out;
  }

  /* Streaming box-filter resampler: averages the input that falls inside each output sample, so downsampling
     48 kHz -> 16 kHz does not alias. Keeps state between push() calls. */
  function Resampler(inRate, outRate) {
    this.ratio = inRate / outRate; this.sum = 0; this.filled = 0;
  }
  Resampler.prototype.push = function (x) {
    var out = [], ratio = this.ratio;
    if (ratio === 1) return x;
    for (var i = 0; i < x.length; i++) {
      var s = x[i], w = 1;
      while (w > 1e-9) {
        var take = Math.min(w, ratio - this.filled);
        this.sum += s * take; this.filled += take; w -= take;
        if (this.filled >= ratio - 1e-9) { out.push(this.sum / ratio); this.sum = 0; this.filled = 0; }
      }
    }
    return Float32Array.from(out);
  };

  /* Collects Int16 samples and hands out fixed-size frames (default 100 ms = 1600 samples = 3200 bytes). */
  function Framer(frameSamples) {
    this.n = frameSamples; this.buf = new Int16Array(frameSamples); this.len = 0;
  }
  Framer.prototype.push = function (pcm) {
    var frames = [], i = 0;
    while (i < pcm.length) {
      var take = Math.min(this.n - this.len, pcm.length - i);
      this.buf.set(pcm.subarray(i, i + take), this.len);
      this.len += take; i += take;
      if (this.len === this.n) { frames.push(this.buf.slice()); this.len = 0; }
    }
    return frames;
  };

  function rms(f32) {
    if (!f32.length) return 0;
    var a = 0;
    for (var i = 0; i < f32.length; i++) a += f32[i] * f32[i];
    return Math.sqrt(a / f32.length);
  }

  /* push(float32 at inRate) -> onFrame(Int16Array, 16 kHz) per 100 ms and onLevel(rms 0..1) per chunk. */
  function createPipeline(opts) {
    var rs = new Resampler(opts.inRate, TARGET_RATE),
        fr = new Framer(Math.round(TARGET_RATE * (opts.frameMs || FRAME_MS) / 1000));
    return {
      push: function (chunk) {
        if (opts.onLevel) opts.onLevel(rms(chunk));
        var frames = fr.push(floatToPcm16(rs.push(chunk)));
        for (var i = 0; i < frames.length; i++) opts.onFrame(frames[i]);
      },
    };
  }

  return { TARGET_RATE: TARGET_RATE, FRAME_MS: FRAME_MS, floatToPcm16: floatToPcm16, Resampler: Resampler,
           Framer: Framer, rms: rms, createPipeline: createPipeline };
});
