"""Render the Jensen Huang explainer short (1080x1920, 30fps) from images + narration."""
import json, subprocess, sys, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
V = os.path.dirname(os.path.abspath(__file__))
D = os.path.dirname(V)
FB = os.path.join(D, "fonts/NotoSansKR-Black.otf")
FM = os.path.join(D, "fonts/NotoSansKR-Bold.otf")

YEL = (255, 214, 0)
RED = (235, 40, 50)
GRN = (118, 185, 0)
WHITE = (255, 255, 255)

# Each scene: headline (top), subtitle chunks (bottom), optional infographic
# display text for each spoken phrase (same order as narration.txt phrases)
SUBS = [
    "AI 황제가,", "하루아침에 #물러났다?#", "젠슨 황에게,", "무슨 일이 있었던 걸까요?",
    "11월 11일,", "엔비디아 이사회가 젠슨 황의 #사임#을 수리", "#1993년# 회사를 세운 지,", "#33년# 만입니다",
    "발단은 #혼외 관계 의혹#", "황 전 CEO는 직원들에게 보낸 메시지에서,", "불륜을 #인정#했습니다",
    "상대 여성이 #중국 정보기관#과 연관됐다는 보도엔,", "국가 안보·회사 기밀 훼손은 #없다#고 부인",
    "시장은 곧바로 반응했습니다", "엔비디아 주가는 장 초반,", "#15%# 가까이 급락했고,", "한 달 새 #25%# 정도가 빠졌습니다",
    "임시 CEO에 #콜레트 크레스# CFO 선임,", "미국 하원 3개 위원회는,", "#12월 1일# 비공개 면담 요구",
    "중국은 #\"스파이 서사 조작\"#이라며,", "강하게 반발했습니다",
    "그런데 #반전#이 있습니다", "사임 나흘 만에 파이낸셜타임스가,", "황이 #복귀#를 논의 중이라고 보도",
    "반면 베선트 재무장관은,", "\"#외부#에서 후임 찾아야\" 선 그어",
    "관건은 이번 주 #실적 발표#", "젠슨 황,", "다시 돌아올 수 있을까요?", "여러분 생각은 #댓글#로!",
]
SCENES = [
    dict(tag="속보 해설", head=["AI 황제,", "#퇴진#"], phrases=(0, 3)),
    dict(tag="무슨 일?", head=["창업 #33년# 만에", "CEO 사임"], phrases=(4, 7), info="timeline"),
    dict(tag="발단", head=["불륜은 인정,", "#기밀 유출#은 부인"], phrases=(8, 12), info="claims"),
    dict(tag="시장 충격", head=["엔비디아 주가", "#급락#"], phrases=(13, 16), info="drop"),
    dict(tag="후폭풍", head=["임시 CEO 선임", "#의회 소환#까지"], phrases=(17, 21), info="cards"),
    dict(tag="반전", head=["사임 나흘 만에", "#복귀설?#"], phrases=(22, 26), info="versus"),
    dict(tag="다음 관전 포인트", head=["젠슨 황,", "#돌아올까?#"], phrases=(27, 30), info="cta"),
]

# scene index -> (photo file, card box (x0,y0,x1,y1), focus point (fx,fy) as fractions, label)
PH = os.path.join(os.path.dirname(V), "photos")
PHOTOS = {
    0: ("p1.jpg", (60, 620, 1020, 1180), (0.47, 0.42), "자료사진"),
    1: ("p2.jpg", (60, 620, 1020, 1100), (0.58, 0.40), "자료사진"),
    2: ("p3_masked.jpg", (60, 620, 1020, 1060), (0.50, 0.40), "온라인 유포 사진 · 인물 모자이크 · 진위 미확인"),
    5: ("p5.jpg", (60, 620, 1020, 1060), (0.55, 0.50), "엔비디아 본사 · 자료사진"),
    6: ("p6.webp", (60, 620, 1020, 1100), (0.60, 0.45), "자료사진"),
}
AVATAR = ("p4.jpg", (0.495, 0.36), 0.33)  # scene 5: interim CEO portrait (focus, crop radius as frac of height)

def load_card_img(i):
    f, (x0, y0, x1, y1), (fx, fy), _ = PHOTOS[i]
    im = Image.open(os.path.join(PH, f)).convert("RGB")
    cw, ch = x1 - x0, y1 - y0
    # crop to the card aspect around the focus point, with 8% headroom for the in-card zoom
    ar = cw / ch
    w, h = im.size
    if w / h > ar:
        nw, nh = int(h * ar), h
    else:
        nw, nh = w, int(w / ar)
    cx = min(max(fx * w, nw / 2), w - nw / 2)
    cy = min(max(fy * h, nh / 2), h - nh / 2)
    im = im.crop((int(cx - nw / 2), int(cy - nh / 2), int(cx + nw / 2), int(cy + nh / 2)))
    return im.resize((int(cw * 1.08), int(ch * 1.08)), Image.LANCZOS)

def load_avatar(d=250):
    f, (fx, fy), rf = AVATAR
    im = Image.open(os.path.join(PH, f)).convert("RGB")
    w, h = im.size
    r = rf * h
    im = im.crop((int(fx * w - r), int(fy * h - r), int(fx * w + r), int(fy * h + r))).resize((d, d), Image.LANCZOS)
    m = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * 4, d * 4), fill=255)
    im.putalpha(m.resize((d, d), Image.LANCZOS))
    return im

_mask_cache = {}
def round_mask(size, r):
    if size not in _mask_cache:
        m = Image.new("L", size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=255)
        _mask_cache[size] = m
    return _mask_cache[size]

def draw_photo_card(frame, i, card, t, dur):
    _, (x0, y0, x1, y1), _, label = PHOTOS[i]
    cw, ch = x1 - x0, y1 - y0
    a = ease((t - 0.15) / 0.45)
    if a <= 0:
        return
    # slow push-in inside the card
    z = 1.0 + 0.07 * (t / dur)
    bw, bh = card.size
    vw, vh = int(bw / 1.08 / z * 1.0), int(bh / 1.08 / z)
    ox, oy = (bw - vw) // 2, (bh - vh) // 2
    view = card.crop((ox, oy, ox + vw, oy + vh)).resize((cw, ch), Image.BILINEAR)
    yo = int((1 - a) * 70)
    d = ImageDraw.Draw(frame, "RGBA")
    # drop shadow + accent frame
    d.rounded_rectangle((x0 + 10, y0 + 18 + yo, x1 + 10, y1 + 18 + yo), 30, fill=(0, 0, 0, int(140 * a)))
    d.rounded_rectangle((x0 - 6, y0 - 6 + yo, x1 + 6, y1 + 6 + yo), 34, fill=(*YEL, int(255 * a)))
    m = round_mask((cw, ch), 28)
    if a < 1:
        m = m.point(lambda v: int(v * a))
    frame.paste(view, (x0, y0 + yo), m)
    # source chip
    f = font(FM, 26)
    tw = d.textlength(label, font=f)
    d.rounded_rectangle((x0 + 18, y1 - 58 + yo, x0 + 46 + tw, y1 - 16 + yo), 12, fill=(0, 0, 0, int(170 * a)))
    d.text((x0 + 32, y1 - 37 + yo), label, font=f, fill=(255, 255, 255, int(230 * a)), anchor="lm")

_fc = {}
def font(path, size):
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]

def parse(text):
    """Split '#highlight#' markup into [(segment, highlighted)]."""
    parts = text.split("#")
    return [(p, i % 2 == 1) for i, p in enumerate(parts) if p]

def text_w(draw, text, f):
    return draw.textlength(text.replace("#", ""), font=f)

def draw_rich(draw, cx, y, text, f, base=WHITE, hi=YEL, stroke=6):
    total = text_w(draw, text, f)
    x = cx - total / 2
    for seg, h in parse(text):
        draw.text((x, y), seg, font=f, fill=hi if h else base,
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        x += draw.textlength(seg, font=f)

def fit_font(draw, text, path, size, maxw):
    while size > 30 and text_w(draw, text, font(path, size)) > maxw:
        size -= 4
    return font(path, size)

def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3

def cover(img):
    s = max(W / img.width, H / img.height) * 1.12
    return img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)

# gradient overlay (dark top & bottom for legibility)
def make_grad():
    g = Image.new("RGBA", (W, H))
    px = ImageDraw.Draw(g)
    for y in range(H):
        if y < 700:
            a = int(200 * (1 - y / 700) ** 1.2) + 40
        elif y > 1150:
            a = int(230 * ((y - 1150) / (H - 1150)) ** 1.1) + 40
        else:
            a = 40
        px.line([(0, y), (W, y)], fill=(0, 0, 0, min(a, 235)))
    return g
GRAD = make_grad()

def rounded(draw, box, r, fill, outline=None, width=0):
    draw.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)

def draw_info(img, kind, t, dur, cues):
    d = ImageDraw.Draw(img, "RGBA")
    first = {"timeline": cues[2], "claims": cues[2], "drop": cues[2], "cards": cues[0],
             "versus": cues[1], "cta": cues[0]}[kind]
    a = ease((t - first) / 0.4)
    if a <= 0:
        return
    yoff = int((1 - a) * 60)
    A = int(255 * a)
    if kind == "timeline":
        y = 1150 + yoff
        rounded(d, (160, y, 920, y + 170), 30, (0, 0, 0, int(190 * a)))
        f = font(FB, 88)
        d.text((340, y + 85), "1993", font=f, fill=(*GRN, A), anchor="mm")
        d.text((540, y + 85), "→", font=f, fill=(*WHITE, A), anchor="mm")
        d.text((740, y + 85), "2026", font=f, fill=(*RED, A), anchor="mm")
    elif kind == "claims":
        f = font(FB, 58)
        rows = [("불륜", "인정", GRN), ("기밀 유출 의혹", "부인", RED)]
        for i, (k, v, c) in enumerate(rows):
            ai = ease((t - (cues[2], cues[4])[i]) / 0.4)
            if ai <= 0:
                continue
            y = 1095 + i * 140 + int((1 - ai) * 40)
            rounded(d, (110, y, 970, y + 120), 26, (0, 0, 0, int(200 * ai)))
            d.text((150, y + 60), k, font=f, fill=(255, 255, 255, int(255 * ai)), anchor="lm")
            vw = d.textlength(v, font=f)
            rounded(d, (930 - vw - 40, y + 16, 940, y + 104), 20, (*c, int(255 * ai)))
            d.text((930 - vw - 20, y + 60), v, font=f, fill=(255, 255, 255, int(255 * ai)), anchor="lm")
        d.text((W / 2, 1385), "※ 언론 보도 기준", font=font(FM, 32), fill=(220, 220, 220, A), anchor="mm")
    elif kind == "drop":
        items = [("-15%", "장 초반 한때", cues[2]), ("-25%", "최근 한 달", cues[3])]
        for i, (num, lab, st) in enumerate(items):
            ai = ease((t - st) / 0.35)
            if ai <= 0:
                continue
            y = 820 + i * 240
            sc = 1.4 - 0.4 * ai
            f = font(FB, int(150 * sc))
            d.text((W / 2 + 120, y + 100), num, font=f, fill=(*RED, int(255 * ai)),
                   anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0, int(255 * ai)))
            d.text((W / 2 - 250, y + 100), lab, font=font(FB, 52), fill=(255, 255, 255, int(255 * ai)),
                   anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
    elif kind == "cards":
        cards = [("임시 CEO", "콜레트 크레스"), ("美 하원", "12/1 면담 요구"), ("중국", "\"조작\" 반발")]
        for i, (k, v) in enumerate(cards):
            ai = ease((t - (cues[0], cues[1], cues[3])[i]) / 0.4)
            if ai <= 0:
                continue
            y = 935 + i * 145 + int((1 - ai) * 40)
            rounded(d, (110, y, 970, y + 125), 24, (15, 15, 25, int(210 * ai)), outline=(*YEL, int(255 * ai)), width=4)
            d.text((150, y + 62), k, font=font(FB, 52), fill=(*YEL, int(255 * ai)), anchor="lm")
            d.text((930, y + 62), v, font=font(FB, 52), fill=(255, 255, 255, int(255 * ai)), anchor="rm")
            if i == 0 and AV is not None:
                # interim CEO portrait badge above the cards, revealed with the first card
                dia = AV.size[0]
                cx, cy = W // 2, 770 - int((1 - ai) * 30)
                d.ellipse((cx - dia / 2 - 8, cy - dia / 2 - 8, cx + dia / 2 + 8, cy + dia / 2 + 8), fill=(*YEL, int(255 * ai)))
                av = AV.copy()
                av.putalpha(av.getchannel("A").point(lambda v: int(v * ai)))
                img.alpha_composite(av, (int(cx - dia / 2), int(cy - dia / 2)))
    elif kind == "versus":
        al_ = ease((t - cues[1]) / 0.4)
        ar_ = ease((t - cues[3]) / 0.4)
        if al_ > 0:
            y = 1100 + int((1 - al_) * 40)
            rounded(d, (80, y, 520, y + 260), 28, (*GRN, int(230 * al_)))
            al = int(255 * al_)
            d.text((300, y + 85), "복귀 논의", font=font(FB, 58), fill=(255, 255, 255, al), anchor="mm")
            d.text((300, y + 170), "FT 보도", font=font(FM, 44), fill=(255, 255, 255, al), anchor="mm")
        if ar_ > 0:
            y = 1100 + int((1 - ar_) * 40)
            rounded(d, (560, y, 1000, y + 260), 28, (*RED, int(230 * ar_)))
            ar = int(255 * ar_)
            d.text((780, y + 85), "외부 영입", font=font(FB, 58), fill=(255, 255, 255, ar), anchor="mm")
            d.text((780, y + 170), "美 재무장관", font=font(FM, 44), fill=(255, 255, 255, ar), anchor="mm")
            d.text((540, 1230), "VS", font=font(FB, 80), fill=(255, 255, 255, ar), anchor="mm",
                   stroke_width=8, stroke_fill=(0, 0, 0))
    elif kind == "cta":
        y = 1150 + yoff
        rounded(d, (190, y, 890, y + 160), 30, (0, 0, 0, int(200 * a)), outline=(*YEL, A), width=5)
        d.text((W / 2, y + 80), "이번 주 실적 발표", font=font(FB, 66), fill=(*YEL, A), anchor="mm")

def render_frame(sc, bg, t, dur, gt, total, idx, cues, subs, card=None):
    # Ken Burns: slow zoom + drift
    z = 1.0 + 0.08 * (t / dur)
    bw, bh = bg.size
    cw, ch = int(bw / z), int(bh / z)
    dx = (bw - cw) / 2 + (-1) ** idx * 30 * (t / dur)
    dy = (bh - ch) / 2
    frame = bg.crop((int(dx), int(dy), int(dx) + cw, int(dy) + ch)).resize((W, H), Image.BILINEAR)
    # scene-in flash fade
    frame = frame.convert("RGBA")
    frame.alpha_composite(GRAD)
    d = ImageDraw.Draw(frame, "RGBA")

    # progress bar
    d.rectangle((0, 0, W, 12), fill=(255, 255, 255, 60))
    d.rectangle((0, 0, int(W * gt / total), 12), fill=(*YEL, 255))

    # tag pill
    a = ease(t / 0.3)
    tf = font(FB, 44)
    tw = d.textlength(sc["tag"], font=tf)
    rounded(d, (W / 2 - tw / 2 - 30, 150, W / 2 + tw / 2 + 30, 230), 40, (*RED, int(255 * a)))
    d.text((W / 2, 190), sc["tag"], font=tf, fill=(255, 255, 255, int(255 * a)), anchor="mm")

    # headline, slide in
    for i, line in enumerate(sc["head"]):
        ai = ease((t - 0.08 - i * 0.12) / 0.35)
        if ai <= 0:
            continue
        f = fit_font(d, line, FB, 128, W - 120)
        y = 270 + i * 160 + int((1 - ai) * 40)
        draw_rich(d, W / 2, y, line, f, stroke=9)

    if card is not None:
        draw_photo_card(frame, idx, card, t, dur)
        d = ImageDraw.Draw(frame, "RGBA")
    if sc.get("info"):
        draw_info(frame, sc["info"], t, dur, cues)

    # subtitles: each phrase shown from its spoken start until the next phrase starts
    cur = subs[0]
    for c, txt in zip(cues, subs):
        if t >= c - 0.05:
            cur = txt
    f = fit_font(d, cur, FB, 70, W - 100)
    tw = text_w(d, cur, f)
    rounded(d, (W / 2 - tw / 2 - 30, 1450, W / 2 + tw / 2 + 30, 1570), 20, (0, 0, 0, 150))
    draw_rich(d, W / 2, 1465, cur, f, stroke=5)

    # footer disclaimer
    d.text((W / 2, 1800), "언론 보도 종합 · 2026.11.16 기준 · 일부 의혹은 미확인",
           font=font(FM, 30), fill=(230, 230, 230, 200), anchor="mm")
    return frame.convert("RGB")

def dur_of(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode())

AV = None

def main():
    global AV
    AV = load_avatar(250)
    out = os.path.join(V, "out")
    os.makedirs(out, exist_ok=True)
    ph = json.load(open(os.path.join(V, "phrases.json")))
    assert len(ph) == len(SUBS)
    voice_src = os.path.join(V, "voice.wav")
    total = dur_of(voice_src) + 1.2  # short musical tail after the last word
    # scene cuts at the middle of the pause before each scene's first phrase
    cuts = [0.0]
    for sc in SCENES[1:]:
        k = sc["phrases"][0]
        cuts.append((ph[k - 1]["end"] + ph[k]["start"]) / 2)
    cuts.append(total)
    print("scene cuts", [round(c, 2) for c in cuts])

    # audio: voice at -14 LUFS, one continuous BGM bed ducked under the voice, faded at the end
    mix = os.path.join(out, "mix.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", voice_src, "-i", os.path.join(V, "bgm.mp3"),
        "-filter_complex",
        "[0:a]aresample=48000,pan=stereo|c0=c0|c1=c0,loudnorm=I=-14:TP=-1.5:LRA=11,apad[v];"
        f"[1:a]aresample=48000,volume=-10dB,afade=t=in:d=0.6,afade=t=out:st={total-2.2:.2f}:d=2.2[m];"
        "[v]asplit[v1][v2];"
        "[m][v2]sidechaincompress=threshold=0.04:ratio=3:attack=40:release=450:makeup=1[md];"
        "[v1][md]amix=inputs=2:duration=shortest:normalize=0,alimiter=limit=0.84[o]",
        "-map", "[o]", "-t", f"{total:.3f}", "-ar", "48000", mix], check=True)

    preview = "--preview" in sys.argv
    video = os.path.join(out, "video.mp4")
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", video],
                           stdin=subprocess.PIPE)
    frames_done = 0
    for i, sc in enumerate(SCENES):
        a0, a1 = sc["phrases"]
        s0, s1 = cuts[i], cuts[i + 1]
        dd = s1 - s0
        cues = [ph[k]["start"] - s0 for k in range(a0, a1 + 1)]
        subs = SUBS[a0:a1 + 1]
        bg = cover(Image.open(os.path.join(D, f"img/{i+1}.png")).convert("RGB"))
        card = None
        if i in PHOTOS:
            card = load_card_img(i)
            bg = bg.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.7))
        n = int(round(s1 * FPS)) - frames_done
        for k in range(n):
            t = k / FPS
            fr = render_frame(sc, bg, t, dd, s0 + t, total, i, cues, subs, card)
            if preview and k == int(n * 0.7):
                fr.save(os.path.join(out, f"preview_{i+1}.jpg"), quality=80)
            enc.stdin.write(fr.tobytes())
        frames_done += n
        print("scene", i + 1, "done", flush=True)
    enc.stdin.close()
    enc.wait()
    final = os.path.join(out, "jensen_huang_shorts_v3.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", mix, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
    print("wrote", final)

if __name__ == "__main__":
    main()
