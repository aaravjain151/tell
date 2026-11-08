/* AudioWorklet: batches microphone samples (128 per callback) into 2048-sample chunks for the page.
   It only forwards samples to the main thread; nothing is stored here. */
class DSCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) {
          const out = this.buf; this.buf = new Float32Array(2048); this.n = 0;
          this.port.postMessage(out, [out.buffer]);
        }
      }
    }
    return true;
  }
}
registerProcessor("ds-capture", DSCapture);
