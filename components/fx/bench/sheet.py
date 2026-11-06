"""Sheet of the explosion stand frames: .venv/bin/python -m components.fx.bench.sheet <folder> <output.jpg> [pattern-substring …] — rows by case, columns by time."""
import glob, os, re, sys
from PIL import Image, ImageDraw, ImageFont
D, OUTP, pats = sys.argv[1], sys.argv[2], sys.argv[3:]
fs = sorted(glob.glob(os.path.join(D, "*_t*.png")))
fs = [f for f in fs if not pats or any(p in os.path.basename(f) for p in pats)]
rows = {}
for f in fs:
    m = re.match(r"(.*)_t([\d.]+)\.png$", os.path.basename(f)); rows.setdefault(m.group(1), []).append((float(m.group(2)), f))
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16); W, H = 480, 270
cols = max(len(v) for v in rows.values()); sh = Image.new("RGB", (cols * W, len(rows) * (H + 20)), (20, 20, 20)); d = ImageDraw.Draw(sh)
for j, (k, v) in enumerate(sorted(rows.items())):
    for i, (t, f) in enumerate(sorted(v)):
        sh.paste(Image.open(f).convert("RGB").resize((W, H), Image.LANCZOS), (i * W, j * (H + 20) + 20)); d.text((i * W + 5, j * (H + 20) + 2), f"{k} · {t} s", fill=(230, 230, 230), font=font)
sh.save(OUTP, quality=88); print(OUTP)
