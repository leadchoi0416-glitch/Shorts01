"""Tighten long pauses in the continuous narration take and time every script phrase.

Writes voice.wav (48 kHz mono) and phrases.json [{text, start, end}] in the new timeline.
Phrase boundaries come from aligning the script's punctuation to detected pauses (DP),
so subtitles follow the actual speech instead of an even split.
"""
import json, re, subprocess, sys
import numpy as np

SR = 48000
MAX_PAUSE = 0.55   # sentence-end pauses longer than this are shortened to it
EDGE = 0.15        # silence kept at head/tail

src, script = sys.argv[1], sys.argv[2]
raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", src, "-ar", str(SR), "-ac", "1", "-f", "f32le", "-"])
a = np.frombuffer(raw, dtype=np.float32).copy()

def silences(a, thr_db=-38, min_ms=120):
    win = SR // 100
    n = len(a) // win
    rms = np.sqrt(np.mean(a[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / rms.max())
    out, st = [], None
    for i, q in enumerate(np.append(db < thr_db, False)):
        if q and st is None:
            st = i
        elif not q and st is not None:
            if (i - st) * 10 >= min_ms or st == 0 or i >= n:
                out.append((st * win, i * win))
            st = None
    return out

sil = silences(a)
# rebuild with edges trimmed and long pauses shortened (cut from the middle, short crossfade)
pieces, pauses, cur, t = [], [], 0, 0.0
for k, (s, e) in enumerate(sil):
    is_head, is_tail = s == 0, e >= len(a) - SR // 100
    keep = EDGE if (is_head or is_tail) else min((e - s) / SR, MAX_PAUSE)
    keep_n = int(keep * SR)
    seg = a[cur:s]
    pieces.append(seg); t += len(seg) / SR
    if not (is_head or is_tail):
        pauses.append((t, t + keep))
    half = keep_n // 2
    pieces.append(a[s:s + half]); pieces.append(a[e - (keep_n - half):e])
    t += keep_n / SR
    cur = e
pieces.append(a[cur:])
out = np.concatenate(pieces)
if sil and sil[0][0] != 0:
    out = np.concatenate([np.zeros(int(EDGE * SR), np.float32), out])
    pauses = [(p0 + EDGE, p1 + EDGE) for p0, p1 in pauses]
dur = len(out) / SR

text = open(script).read().replace("\n", " ")
phrases = [p.strip() for p in re.findall(r"[^,.?!]+[,.?!]", text)]
syl = [len(re.findall("[가-힣]", p)) for p in phrases]
nb = len(phrases) - 1
pause_total = sum(p1 - p0 for p0, p1 in pauses)
voiced = dur - 2 * EDGE - pause_total
# expected boundary time after phrase i
exp, acc = [], 0
for i in range(nb):
    acc += syl[i]
    exp.append(EDGE + acc / sum(syl) * voiced + pause_total * (i + 1) / (nb + 1))
mids = [(p0 + p1) / 2 for p0, p1 in pauses]
# monotonic DP: assign each boundary to a distinct pause, minimizing time error
INF = 1e18
P = len(mids)
dp = np.full((nb + 1, P + 1), INF); dp[0, :] = 0
ch = np.zeros((nb + 1, P + 1), dtype=int)
for i in range(1, nb + 1):
    for j in range(1, P + 1):
        skip = dp[i, j - 1]
        take = dp[i - 1, j - 1] + abs(exp[i - 1] - mids[j - 1])
        if take <= skip:
            dp[i, j], ch[i, j] = take, 1
        else:
            dp[i, j] = skip
i, j, assign = nb, P, [0] * nb
while i > 0:
    if ch[i, j] == 1:
        assign[i - 1] = j - 1; i -= 1
    j -= 1
res, start = [], EDGE
for k, p in enumerate(phrases):
    if k < nb:
        p0, p1 = pauses[assign[k]]
        res.append({"text": p, "start": round(start, 3), "end": round(p0, 3)}); start = p1
    else:
        res.append({"text": p, "start": round(start, 3), "end": round(dur - EDGE, 3)})
unused = P - nb
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                "voice.wav"], input=out.tobytes(), check=True)
json.dump(res, open("phrases.json", "w"), ensure_ascii=False, indent=1)
print(f"in {len(a)/SR:.1f}s -> out {dur:.1f}s | pauses {P} for {nb} boundaries (unassigned {unused})")
for r in res:
    print(f"{r['start']:6.2f}-{r['end']:6.2f} {r['text']}")
