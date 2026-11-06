"""Reference test of the Effects component (pass / fail): the explosion mechanism on the stand (bench/stand.py of this
folder, without cost) — over the 12 cost cases (kinds, light, ground, distances) the detail level, the screen size of
the body and the layers of each frame are compared against golden.json. Frame time is not compared (the cost stand
bench.py measures it). No full-size render — only the stand frame; ~2 min.
.venv/bin/python -m components.fx.bench.check [--record]   → a line __RESULT__ {n_failures, n_checks}."""
import json, os, re, subprocess, sys, tempfile, time
import core.paths

HERE = os.path.dirname(os.path.realpath(__file__)); ROOT = HERE
while not os.path.isdir(os.path.join(ROOT, "core")): ROOT = os.path.dirname(ROOT)   # project root: walk up until the folder with core/ is found
CASES = [("projectile", "day", "snow", d) for d in (18, 45, 120, 400, 1500)] + [("grenade", "night", "snow", d) for d in (15, 60)] + \
        [("fuel", "day", "ground", 70), ("airburst", "day", "ground", 70), ("fire_ball", "night", "ground", 20),
         ("napalm", "day", "ground", 30), ("blaze", "night", "ground", 20)]   # the same cases as the cost stand bench.py
GOLD = os.path.join(HERE, "golden.json"); t0 = time.time(); got = {}
out = tempfile.mkdtemp(prefix="fx_check_")
for vid, light, gnd, dist in CASES:
    args = [f"kind={vid}", f"light={light}", f"soil={gnd}", f"dist={dist}", "time=0.2,1.0" if vid not in ("napalm", "blaze") else "time=0.2,4.0"] + \
           (["height=25"] if vid == "airburst" else ["height=1.5"] if vid == "fire_ball" else [])
    p = subprocess.run(["blender", "-b", "--factory-startup", "-P", core.paths.RUN, "--", os.path.join(HERE, "stand.py"), "--", out, *args],
                       capture_output=True, text=True, cwd=ROOT, timeout=900)
    m = re.search(r"__STAND__ (\{.*\})", p.stdout); key = f"{vid} {light} {gnd} {dist}"
    got[key] = [{"t": k["t"], "level": k["level"], "px": k["px"], "layers": k["layers"]} for k in json.loads(m.group(1))["frames"]] if m \
        else {"error": (p.stderr or p.stdout)[-300:]}
if "--record" in sys.argv:
    json.dump(got, open(GOLD, "w"), ensure_ascii=False, indent=1); print("written", GOLD)
gold = json.load(open(GOLD)); bad = [k for k in gold if gold[k] != got.get(k)]
for k in bad: print("MISMATCH", k, "\n  was:", gold[k], "\n  now:", got.get(k))
print("__RESULT__", json.dumps({"n_failures": len(bad), "n_checks": len(gold), "sec": round(time.time() - t0, 1)}, ensure_ascii=False))
sys.exit(len(bad))
