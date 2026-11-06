"""Reference benchmark of the explosion mechanism: the frame cost by kind and distance — all detail levels; frames without
an explosion and with one are interleaved in a single process (the stand components/fx/bench/stand.py with cost=1), so
external load falls equally on both.
.venv/bin/python -m components.fx.bench.bench [output=out/fx_bench]   → components/fx/bench/RESULTS.md, sheets out/fx_bench/sheet.jpg; ~5 min."""
import json, os, re, subprocess, sys, time
import core.paths

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))   # components/fx/bench → the root; HERE is this folder
HERE = os.path.dirname(os.path.realpath(__file__))
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "out", "fx_bench")
CASES = [("projectile", "day", "snow", d) for d in (18, 45, 120, 400, 1500)] + [("grenade", "night", "snow", d) for d in (15, 60)] + \
        [("fuel", "day", "ground", 70), ("airburst", "day", "ground", 70), ("fire_ball", "night", "ground", 20),
         ("napalm", "day", "ground", 30), ("blaze", "night", "ground", 20)]
rows, t0 = [], time.time()
for vid, light, gnd, dist in CASES:
    args = [f"kind={vid}", f"light={light}", f"soil={gnd}", f"dist={dist}", "time=0.2,1.0" if vid not in ("napalm", "blaze") else "time=0.2,4.0", "cost=1"] + \
           (["height=25"] if vid == "airburst" else ["height=1.5"] if vid == "fire_ball" else [])
    p = subprocess.run(["/usr/bin/time", "-l", "blender", "-b", "--factory-startup", "-P", core.paths.RUN, "--", os.path.join(HERE, "stand.py"), "--", OUT, *args],
                       capture_output=True, text=True, cwd=ROOT, timeout=1800)
    m = re.search(r"__STAND__ (\{.*\})", p.stdout); rss = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
    if not m: rows.append({"case": f"{vid} {light} {gnd} {dist} m", "error": (p.stderr or p.stdout)[-300:]}); continue
    R = json.loads(m.group(1))
    for k in R["frames"]:
        rows.append({"case": f"{vid}, {light}, {gnd}, {dist} m", "t": k["t"], "level": k["level"], "px": k["px"], "layers": ", ".join(k["layers"]),
                     "without_s": k.get("without_s"), "incl_s": k.get("incl_s"), "Δ_s": k.get("Δ_s"), "memory_mb": round(int(rss.group(1)) / 1e6) if rss else None})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
L = ["# Explosion mechanism — frame cost by case", "", "EEVEE 1280×720, 16 samples, M1 Pro; stand `components/fx/bench/stand.py` (flat ground, a 1.8 m scale figure); 'without' and 'with' are the median of",
     "frames without an explosion and with one interleaved in a single process (cost as a pair), Δ is the explosion's increment; level — by the screen size of the body;",
     "memory is the peak of the Blender process. Run: `.venv/bin/python -m components.fx.bench.bench`.", "",
     "| case | t, s | level | px | layers | without, s | with, s | Δ, s | memory, MB |", "|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    L.append(f"| {r['case']} | {r.get('t', '—')} | {r.get('level', '—')} | {r.get('px', '—')} | {r.get('layers', r.get('error', ''))} | {r.get('without_s', '—')} | "
             f"{r.get('incl_s', '—')} | {r.get('Δ_s', '—')} | {r.get('memory_mb', '—')} |")
open(os.path.join(HERE, "RESULTS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"), "-m", "components.fx.bench.sheet", OUT, os.path.join(OUT, "sheet.jpg")], capture_output=True)
print("__RESULT__", json.dumps({"n_cases": len(CASES), "n_lines": len(rows), "n_errors": sum(1 for r in rows if "error" in r), "minutes": round((time.time() - t0) / 60, 1)}, ensure_ascii=False))
