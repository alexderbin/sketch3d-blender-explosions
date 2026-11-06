"""In-place cleanup of a baked explosion asset (fx_bake.py slim; after baking it runs by itself): the .vdb frames keep only
the channels the shader reads (bl_fx.volume_material: the level's density and flame), voxels below 0.01 are dropped (the
shader does not see them anyway: density − 0.01, volume cutoff 0.02), written as half; the other cache (data at the high
level — the body in noise) and empty Mantaflow folders are deleted.
The frame is the same (mean difference 0.01 out of 255); the library disk shrinks from 2.15 to 0.75 GB, the low level
by 7–12 times.
blender -b --factory-startup -P core/blender/run.py -- components/fx/bl_fx_slim.py -- <asset level folder> → __SLIM__ {json: disk before and after, MB}"""
import json, os, shutil, sys
import numpy as np
import openvdb as vdb

D = os.path.abspath(sys.argv[sys.argv.index("--") + 1]); S = json.load(open(os.path.join(D, "stats.json"))); TOL = 0.01
folder, sfx = S["folder"], S["sfx"]; keep = ("density" + sfx, "flame" + sfx); cache = os.path.join(D, "cache")


def size(d):
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)


before = size(cache)
for f in sorted(os.listdir(os.path.join(cache, folder))):
    if not f.endswith(".vdb"): continue
    p = os.path.join(cache, folder, f); new = []
    for g in vdb.readAll(p)[0]:
        if g.name not in keep: continue
        ng = vdb.FloatGrid(); ng.name = g.name; ng.transform = g.transform
        if g.activeVoxelCount():                                      # dense into an array → back with a threshold: below TOL — empty
            lo, hi = g.evalActiveVoxelBoundingBox(); a = np.zeros([hi[i] - lo[i] + 1 for i in range(3)], np.float32)
            g.copyToArray(a, ijk=lo); ng.copyFromArray(a, ijk=lo, tolerance=TOL)
        ng.saveFloatAsHalf = True; new.append(ng)
    vdb.write(p + ".tmp", grids=new); os.replace(p + ".tmp", p)
for sub in os.listdir(cache):                                         # the other cache and empty Mantaflow folders are not needed by the frame
    if sub not in (folder, "config") and os.path.isdir(os.path.join(cache, sub)): shutil.rmtree(os.path.join(cache, sub))
after = size(cache); S["disk_mb"] = round(after / 1e6, 1); S["cleanup"] = {"to_mb": round(before / 1e6, 1), "threshold": TOL, "channels": list(keep)}
json.dump(S, open(os.path.join(D, "stats.json"), "w"), ensure_ascii=False)
print("__SLIM__", json.dumps({"folder": D, "to_mb": round(before / 1e6, 1), "after_mb": round(after / 1e6, 1)}, ensure_ascii=False), flush=True)
