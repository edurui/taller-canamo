// PCM only. No network, persistence or playback of microphone audio.
class CanamoRecorder extends AudioWorkletProcessor {
  constructor() { super(); this.frames = 0; }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input || this.frames >= sampleRate * 120) return true;
    const length = Math.min(input.length, sampleRate * 120 - this.frames);
    const samples = new Int16Array(length);
    for (let i = 0; i < length; i++) {
      const value = Math.max(-1, Math.min(1, input[i]));
      samples[i] = Math.round(value < 0 ? value * 32768 : value * 32767);
    }
    this.frames += length;
    this.port.postMessage(samples, [samples.buffer]);
    return true;
  }
}
registerProcessor("canamo-recorder", CanamoRecorder);
