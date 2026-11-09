// A short bell for a new 「お会計」 call, made with the browser's own audio (no sound file to ship). Browsers allow sound
// only after the page has been touched once; before that the call is silently skipped (the banner still shows).
const MUTE_KEY = 'ury.serviceRequest.muted';

export function isBellMuted(): boolean {
  try {
    return window.localStorage.getItem(MUTE_KEY) === '1';
  } catch {
    return false;
  }
}

export function setBellMuted(muted: boolean): void {
  try {
    window.localStorage.setItem(MUTE_KEY, muted ? '1' : '0');
  } catch {
    /* the setting is only a convenience */
  }
}

let context: AudioContext | null = null;

export function ringBell(): void {
  if (isBellMuted()) return;
  try {
    const Audio = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Audio) return;
    context = context ?? new Audio();
    if (context.state === 'suspended') void context.resume();
    const start = context.currentTime;
    [880, 1175].forEach((frequency, index) => {
      const oscillator = context!.createOscillator();
      const gain = context!.createGain();
      oscillator.frequency.value = frequency;
      oscillator.connect(gain);
      gain.connect(context!.destination);
      const at = start + index * 0.22;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.4);
      oscillator.start(at);
      oscillator.stop(at + 0.45);
    });
  } catch {
    /* no sound is not an error */
  }
}
