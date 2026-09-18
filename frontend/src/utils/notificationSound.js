/**
 * Plays an authentic, modern Apple-style glass notification chime using Web Audio API.
 * Autoplay policies in modern browsers are bypassed by automatically capturing the
 * first user interaction (click, keypress, touch) to resume the AudioContext.
 */
class SoundNotifier {
  constructor() {
    this.audioCtx = null;
    this.isUnlocked = false;
    this._setupAutoUnlock();
  }

  _setupAutoUnlock() {
    if (typeof window === 'undefined') return;

    const unlockHandler = () => {
      this._ensureContext();
      this.isUnlocked = true;
      ['pointerdown', 'keydown', 'touchstart', 'click'].forEach(evt => {
        window.removeEventListener(evt, unlockHandler, true);
      });
    };

    ['pointerdown', 'keydown', 'touchstart', 'click'].forEach(evt => {
      window.addEventListener(evt, unlockHandler, { once: true, capture: true, passive: true });
    });
  }

  _ensureContext() {
    if (!this.audioCtx) {
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (AudioCtxClass) {
        this.audioCtx = new AudioCtxClass();
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume().catch(() => {});
    }
    return this.audioCtx;
  }

  /**
   * Play the Apple-inspired crystal glass chime (C6 -> E6 harmonic bell with shimmer)
   */
  playChime() {
    try {
      const ctx = this._ensureContext();
      if (!ctx) return;

      if (ctx.state === 'suspended') {
        ctx.resume().then(() => this._renderAppleChime(ctx)).catch(() => {});
      } else {
        this._renderAppleChime(ctx);
      }
    } catch (e) {
      console.warn('[NotificationSound] Audio playback failed:', e);
    }
  }

  _renderAppleChime(ctx) {
    const now = ctx.currentTime;

    // Tone 1: Pure crystal chime (1046.50 Hz - C6)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(1046.50, now);
    gain1.gain.setValueAtTime(0, now);
    gain1.gain.linearRampToValueAtTime(0.28, now + 0.012);
    gain1.gain.exponentialRampToValueAtTime(0.0001, now + 0.38);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.38);

    // Tone 2: Bright harmonic chime (1318.51 Hz - E6)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(1318.51, now + 0.075);
    gain2.gain.setValueAtTime(0, now + 0.075);
    gain2.gain.linearRampToValueAtTime(0.32, now + 0.09);
    gain2.gain.exponentialRampToValueAtTime(0.0001, now + 0.58);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(now + 0.075);
    osc2.stop(now + 0.58);

    // Glass shimmer overtone (2093.00 Hz - C7)
    const osc3 = ctx.createOscillator();
    const gain3 = ctx.createGain();
    osc3.type = 'triangle';
    osc3.frequency.setValueAtTime(2093.00, now + 0.075);
    gain3.gain.setValueAtTime(0, now + 0.075);
    gain3.gain.linearRampToValueAtTime(0.08, now + 0.09);
    gain3.gain.exponentialRampToValueAtTime(0.00005, now + 0.28);
    osc3.connect(gain3);
    gain3.connect(ctx.destination);
    osc3.start(now + 0.075);
    osc3.stop(now + 0.28);
  }
}

export const soundNotifier = new SoundNotifier();
