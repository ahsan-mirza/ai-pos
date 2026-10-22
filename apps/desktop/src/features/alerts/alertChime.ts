/** Two short beeps for a waiter call, a rising three-note chime for a bill request. */
export function playAlertChime(kind: "call-waiter" | "request-bill"): void {
  const Ctx = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (Ctx === undefined) return;
  const audio = shared(Ctx);
  if (audio === null) return;
  if (audio.state === "suspended") void audio.resume();
  const now = audio.currentTime;
  if (kind === "call-waiter") {
    tone(audio, 880, now, 0.12, "square");
    tone(audio, 988, now + 0.16, 0.18, "square");
    return;
  }
  tone(audio, 523.25, now, 0.14, "sine");
  tone(audio, 659.25, now + 0.12, 0.14, "sine");
  tone(audio, 783.99, now + 0.24, 0.24, "sine");
}

let audio: AudioContext | null = null;

function shared(Ctx: typeof AudioContext): AudioContext | null {
  try {
    audio ??= new Ctx();
    return audio;
  } catch {
    return null;
  }
}

function tone(context: AudioContext, frequency: number, start: number, duration: number, type: OscillatorType): void {
  const osc = context.createOscillator();
  const gain = context.createGain();
  osc.type = type;
  osc.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.2, start + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(gain);
  gain.connect(context.destination);
  osc.start(start);
  osc.stop(start + duration + 0.02);
}
