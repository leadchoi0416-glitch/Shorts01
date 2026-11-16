"""Score narration takes: transcription accuracy (CER), speaking rate, and pause placement.

Usage: python3 evaluate.py narration.txt take1.wav [take2.wav ...]
- CER: character error rate of Hangul vs. the script (whisper medium; lower is better).
- rate: Hangul syllables per second of voiced time (target 5.5-6.5).
- pauses: silences >=120ms. 'bad' = a pause landing where the script has no comma/period
  (i.e. a break inside a phrase — the word-by-word effect we want to avoid).
"""
import re, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel

def load(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1", "-f", "f32le", "-"])
    return np.frombuffer(raw, dtype=np.float32)

def hangul(s):
    return re.sub(r"[^가-힣]", "", s)

def cer(ref, hyp):
    r, h = hangul(ref), hangul(hyp)
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i]
        for j, hc in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / max(1, len(r))

def silences(a, sr=16000, thr_db=-38, min_ms=120):
    win = int(sr * 0.01)
    n = len(a) // win
    rms = np.sqrt(np.mean(a[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (np.max(rms) + 1e-9))
    quiet = db < thr_db
    out, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * 10 >= min_ms:
                out.append((start / 100, i / 100))
            start = None
    # drop leading/trailing silence
    return [s for s in out if s[0] > 0.05 and s[1] < n / 100 - 0.05]

def main():
    script = open(sys.argv[1]).read()
    n_breaks = len(re.findall(r"[,.?!]", script))
    m = WhisperModel("medium", device="cpu", compute_type="int8")
    for p in sys.argv[2:]:
        a = load(p)
        dur = len(a) / 16000
        segs, _ = m.transcribe(a, language="ko", beam_size=5, word_timestamps=True,
                               initial_prompt="엔비디아 젠슨 황 씨이오 콜레트 크레스 베선트 파이낸셜타임스")
        segs = list(segs)
        words = [w for s in segs for w in s.words]
        hyp = " ".join(s.text for s in segs)
        sil = silences(a)
        sil_total = sum(e - s for s, e in sil)
        rate = len(hangul(script)) / (dur - sil_total)
        # classify pauses: does the word before the pause end with punctuation in the script?
        # approximate by counting pauses beyond the script's punctuation budget
        long_p = [s for s in sil if s[1] - s[0] >= 0.12]
        extra = max(0, len(long_p) - n_breaks)
        print(f"\n== {p}")
        print(f"duration {dur:.1f}s | CER {cer(script, hyp):.3f} | rate {rate:.2f} syl/s | "
              f"pauses {len(long_p)} (script breaks {n_breaks}, excess {extra})")
        print("pause lengths (ms):", [int((e - s) * 1000) for s, e in long_p])
        print("transcript:", hyp[:400])

if __name__ == "__main__":
    main()
