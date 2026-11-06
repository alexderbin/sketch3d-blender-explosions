"""Case map of the explosion mechanism: the kinds at the same moments (day, ground) and a projectile on different soils —
which explosion the mechanism gives for which case. .venv/bin/python -m components.fx.bench.cases [output=out/fx_cases]
→ sheets <output>/sheet_kinds.jpg, sheet_soils.jpg."""
import os, subprocess, sys
import core.paths
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))   # components/fx/bench → the root; HERE is this folder
HERE = os.path.dirname(os.path.realpath(__file__))
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "out", "fx_cases")
ST, SH = os.path.join(HERE, "stand.py"), os.path.join(HERE, "sheet.py")
run = lambda d, *a: subprocess.run(["blender", "-b", "--factory-startup", "-P", core.paths.RUN, "--", ST, "--", d, *a], capture_output=True, text=True)
KINDS = [("grenade", 20, 0), ("mine", 30, 0), ("projectile", 45, 0), ("bomb", 140, 0), ("charge", 45, 0), ("airburst", 70, 30),
         ("fuel", 50, 0), ("fire_ball", 20, 1.5), ("napalm", 30, 0), ("blaze", 20, 0)]
for vid, dist, h in KINDS:
    run(os.path.join(OUT, "kinds"), f"kind={vid}", "light=day", f"dist={dist}", "soil=ground", "time=0.15,0.5,1.5,4", f"height={h}", "level=low")
for g in ("snow", "ground", "sand", "mud", "stone"):
    run(os.path.join(OUT, "soils"), "kind=projectile", "light=day", "dist=45", f"soil={g}", "time=0.6,2", "level=low")
for sub in ("kinds", "soils"):
    subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"), "-m", "components.fx.bench.sheet", os.path.join(OUT, sub), os.path.join(OUT, f"sheet_{sub}.jpg")], capture_output=True)
print("__RESULT__", OUT)
