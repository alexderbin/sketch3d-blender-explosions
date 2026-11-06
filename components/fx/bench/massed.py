# Stand "many explosions in the distance" (the far plane): n explosions of various kinds 150–900 m in front of the camera
# near the ground, in different phases (starts 0…3 s before the frame), optionally one more close (at 30 m: volumes near
# and far in a single frame). Light and exposure as in the stand (stand.py). The body mode is whatever the mechanism
# decides (levels by screen size; cards — the "cards" key).
# blender -b --factory-startup -P core/blender/run.py -- components/fx/bench/massed.py -- <output> [light=day|night] [n=24] [seed=3] [time=0,1.5]
#   [close=0|1] [cards=auto|none|medium|all] [modes=none,medium — in pairs, 3 rounds, median] [tile=8] [wind=ux,uy] [label=…]
#   → <output>/massed_<…>_t<time>.png, a line __MASSED__ {json: frame time, objects, levels, memory}
import bpy, json, math, os, random, resource, sys, time
from mathutils import Vector
from components.fx import bl_fx

A = sys.argv[sys.argv.index("--") + 1:]; OUT = os.path.abspath(A[0]); P = dict(a.split("=", 1) for a in A[1:]); os.makedirs(OUT, exist_ok=True)
light, n, seed = P.get("light", "day"), int(P.get("n", 24)), int(P.get("seed", 3)); night = light == "night"
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x, sc.render.resolution_y = 1280, 720; sc.eevee.taa_render_samples = 16
sc.eevee.volumetric_tile_size = P.get("tile", "8"); sc.eevee.volumetric_samples = 64; sc.view_settings.view_transform = "AgX"
sun_E, sky_E, el = (0.06, 0.012, 35) if night else (4.0, 0.8, 40)          # as in stand.py: W/m²; the moon and the night sky for night, the sun and the sky for day
w = bpy.data.worlds.new("w"); sc.world = w; bg = w.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.25, 0.32, 0.5, 1) if night else (0.45, 0.6, 0.9, 1); bg.inputs["Strength"].default_value = sky_E
S = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(S); S.data.energy = sun_E
S.data.color = (0.7, 0.8, 1.0) if night else (1.0, 0.96, 0.9); S.rotation_euler = (math.radians(90 - el), 0, math.radians(-35))
EV = math.log2(math.pi / (sun_E * math.cos(math.radians(max(0.0, 45.0 - el))) + 0.85 * sky_E * math.pi)) - (1.0 if night else 0.0); sc.view_settings.exposure = EV   # the key is the same as in the light node
bpy.ops.mesh.primitive_plane_add(size=6000); gm = bpy.data.materials.new("g"); b = gm.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.32, 0.27, 0.21, 1); b.inputs["Roughness"].default_value = 0.9; bpy.context.active_object.data.materials.append(gm)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.lens = 30
cam.location = (0, -10, 1.8); cam.rotation_euler = (math.radians(88.5), 0, 0)
CAM = {"location": list(cam.location), "lens_mm": 30, "sensor_width_mm": 36, "resolution": [1280, 720]}
rng = random.Random(seed); kinds = ["projectile"] * 10 + ["mine"] * 5 + ["fuel"] * 3 + ["bomb"] * 2; E = []
for i in range(n):                                                     # a ±25° sector in front of the camera, the distance uniform over 150–900 m
    d = rng.uniform(150, 900); a = math.radians(rng.uniform(-25, 25))
    E.append({"at": -rng.uniform(0.0, 3.0), "c": [d * math.sin(a), -10 + d * math.cos(a), 0.0], "kind": rng.choice(kinds), "strength": 1.0, "seed": i})
if P.get("close") == "1": E.append({"at": -0.6, "c": [-4.0, 22.0, 0.0], "kind": "projectile", "strength": 1.0, "seed": 99})
ctx = {"ev": EV, "night": night, "soil": "ground", "fps": 24, "ground": lambda x, y: 0.0}
if P.get("wind"): ctx["wind"] = [float(x) for x in P["wind"].split(",")]
MODES = P.get("modes", P.get("cards", "none")).split(",")         # modes=none,medium — in pairs in one process (3 rounds, median): the load
res = []                                                               # of the machine drifts, single measurements from different runs cannot be compared


def build(tt, mode):
    bl_fx.LOG.clear(); objs = []; ctx["cards"] = mode; t0 = time.time()
    for e in E:
        o = bl_fx.explosion(e, tt, CAM, ctx, sc)
        if o: objs += o
    return objs, time.time() - t0


def drop(objs):
    for o in objs: bpy.data.objects.remove(o, do_unlink=True)
    bl_fx.tidy()


for tt in [float(x) for x in P.get("time", "0,1.5").split(",")]:
    T = {m: [] for m in MODES}; info = {}
    for rep in range(3 if len(MODES) > 1 else 1):
        for m in MODES:
            objs, t_build = build(tt, m); restore = bl_fx.frame_settings(sc)
            sc.render.filepath = os.path.join(OUT, f"massed_{light}_n{n}{'_close' if P.get('close') == '1' else ''}_{P.get('label', '') or m}{'_' + m if len(MODES) > 1 else ''}_t{tt}.png")
            t0 = time.time(); bpy.ops.render.render(write_still=rep == 0); T[m].append(time.time() - t0); restore()
            lv = {}
            for i in bl_fx.LOG: lv[i.get("level")] = lv.get(i.get("level"), 0) + 1
            info[m] = {"build_s": round(t_build, 2), "n_objects": len(objs), "n_volumes": sum(o.type == "VOLUME" for o in objs), "n_cards": sum(o.name.startswith("fx_card") for o in objs),
                       "levels": lv, "memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)}
            drop(objs)
    for m in MODES: res.append(dict(info[m], t=tt, mode=m, frame_s=round(sorted(T[m])[len(T[m]) // 2], 2), all_s=[round(x, 2) for x in T[m]]))
print("__MASSED__", json.dumps({"light": light, "n": n, "close": P.get("close") == "1", "modes": MODES, "frames": res}, ensure_ascii=False), flush=True)
