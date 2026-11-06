"""Explosion and burning cards for the far plane. A kind is shot in advance from the side at a distance with a narrow lens,
as bl_fx sets it (high level), and put into an 8 × 8 atlas of frames:
- an explosion kind (`projectile`, `fuel` …) at strength 1 — the body, ejecta and the glow from inside at 64 moments
  (0–2 s every 1/16 s, 2–10 s every 0.25 s);
- `combustion` — the burning asset loop (the asset's Q, the whole column) at 64 moments of one period: two instances of
  the loop shifted by half a period already give a seamless repeat.
Light is "6 sides": each moment is shot under a sun of 1 W/m² from six sides (right, top,
front → pos.rgb; left, bottom, back → neg.rgb; brightness is the RGB average), alpha — pos.a, multiple scattering
(fx_ms = 1) — neg.a, the color of smoke and dust (the front shot / its brightness) — tint.rgb, the dust share (a shot
with dust red and smoke green) — tint.a, the fire emission with the glow from inside (ev 0, day) — emit.rgb; in the
frame they are mixed by the scene's sun and sky (bl_fx.card_set). An atlas frame is rectangular by kind (area px²): the
burning column is narrow and tall.
With an EEVEE 5.2 orthographic camera the sun shadow map kills the light from the side and from above entirely — hence a
perspective camera from 500 m (depth ±10 m — ±2 %).
blender -b --factory-startup -P core/blender/run.py -- components/fx/bl_fx_cards.py -- <kind|combustion> <output> [px=192]
    → <output>/{pos,neg,tint,emit}.png (8-bit, √ and a channel multiplier — card.json atlases), card.json"""
import bpy, json, math, os, sys, time
import numpy as np
from mathutils import Vector

from components.fx import bl_fx, card_source

A = sys.argv[sys.argv.index("--") + 1:]; VID, OUT = A[0], os.path.abspath(A[1]); P = dict(a.split("=", 1) for a in A[2:]); os.makedirs(OUT, exist_ok=True)
PX, COLS, ROWS, DIST = int(P.get("px", 192)), 8, 8, 500.0
LOOP = VID == "combustion"
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"; sc.render.film_transparent = True
ee = sc.eevee; ee.taa_render_samples = 32; ee.volumetric_tile_size = "2"; ee.volumetric_samples = 64; ee.use_volumetric_shadows = True
sc.view_settings.view_transform = "Standard"; sc.view_settings.exposure = 0.0
sc.render.image_settings.file_format = "OPEN_EXR"; sc.render.image_settings.color_depth = "32"; sc.render.image_settings.color_mode = "RGBA"
w = bpy.data.worlds.new("w"); sc.world = w; w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
CAM_FAR = {"location": [0.0, -2000.0, 5.0], "lens_mm": 30, "sensor_width_mm": 36, "resolution": [1280, 720]}
if LOOP:                                                               # burning loop: the asset's Q (s = 1), the whole column (db is large — the front is above the domain)
    BURN = bl_fx.asset("combustion", "high"); Q_REF = float(BURN.get("Q_kw", 500)); L0, L1 = BURN["loop"]; LOOP_S = (L1 - L0) / BURN["fps"]
    TIMES = [LOOP_S * k / (COLS * ROWS) for k in range(COLS * ROWS)]; KEEP = ("fx_burn",)
else:
    e = {"at": 0.0, "c": [0.0, 0.0, 0.0], "kind": VID, "strength": 1.0, "seed": 1}
    ctx = {"ev": 0.0, "night": False, "soil": "ground", "fps": 24, "ground": lambda x, y: 0.0, "screen_level": "close"}   # body and ejecta — the high level
    TIMES = [k / 16 for k in range(32)] + [2.0 + 0.25 * k for k in range(32)]; KEEP = ("fx_body", "fx_dust", "fx_inner")   # flash, burning, clods, sparks — none


def build(t):
    """Objects of moment t: the body, ejecta and the glow lamp of an explosion — or two instances of the burning loop and the
    fire lamp."""
    if LOOP:
        out = []; bl_fx._burning(sc, {"strength": 1.0}, 100.0 + t, Vector((0.0, 0.0, 0.0)), Q_REF, 1e9, 1.0, 0.0, CAM_FAR, 0.7, out, {"layers": []}, level="close")
        objs = out
    else: objs = bl_fx.explosion(e, t, CAM_FAR, ctx, sc) or []
    keep = []
    for o in objs:
        if o.name.startswith(KEEP): keep.append(o)
        else: bpy.data.objects.remove(o, do_unlink=True)
    return keep


def clear(objs):
    for o in objs: bpy.data.objects.remove(o, do_unlink=True)
    bl_fx.tidy()


lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)                     # the frame's box comes from the volume boxes at all moments (the asset domain)
for t in TIMES[::4]:
    objs = build(t)
    for o in objs:
        if o.type != "VOLUME": continue
        for c in o.bound_box:
            v = o.matrix_world @ Vector(c); lo = Vector(map(min, lo, v)); hi = Vector(map(max, hi, v))
    clear(objs)
SIDE = max(2 * max(abs(lo.x), abs(hi.x), abs(lo.y), abs(hi.y)), hi.z)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "PERSP"; cam.data.sensor_fit = "HORIZONTAL"; cam.data.sensor_width = 36.0
cam.data.clip_end = DIST + 10 * SIDE + 100; cam.rotation_euler = (math.radians(90), 0, 0)    # looks along +Y, the ground is the bottom edge of the frame
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 1.0; sun.data.angle = math.radians(2)
DIRS = {"right": (-1, 0, 0), "top": (0, 0, -1), "front": (0, 1, 0), "left": (1, 0, 0), "bottom": (0, 0, 1), "back": (0, -1, 0)}   # where the light goes
TMP = os.path.join(OUT, "_tmp"); os.makedirs(TMP, exist_ok=True)


def frame(width, height, pw, ph):
    """A frame of width width and height height (m), the bottom at the ground; the shot is pw × ph px."""
    sc.render.resolution_x, sc.render.resolution_y = pw, ph
    cam.data.lens = 36.0 * DIST / width; cam.location = (0.0, -DIST, height / 2)


def shot(name):
    pw, ph = sc.render.resolution_x, sc.render.resolution_y
    sc.render.filepath = os.path.join(TMP, name + ".exr"); bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath); a = np.empty(pw * ph * 4, np.float32); im.pixels.foreach_get(a); bpy.data.images.remove(im)
    return a.reshape(ph, pw, 4)


sun.rotation_euler = Vector(DIRS["front"]).to_track_quat("-Z", "Y").to_euler()
for _ in range(4):                                                    # frame by what is visible: the alpha of test shots (the ejecta domain is three times wider than the smoke);
    frame(SIDE, SIDE, PX, PX); amax = np.zeros((PX, PX), np.float32)  # if it touches the edge — a wider frame and the probe again (for fuel the mushroom by 5 s
    for t in TIMES[::3]:                                              # went out of the frame: the volume boxes before the meshes load are wrong)
        objs = build(t); amax = np.maximum(amax, shot("probe")[..., 3]); clear(objs)
    if max(amax[-1].max(), amax[:, 0].max(), amax[:, -1].max()) <= 0.02: break
    SIDE *= 1.6
WIDTH = HEIGHT = SIDE
ys, xs = np.nonzero(amax > 0.02)
if len(xs):
    px_m = SIDE / PX; WIDTH = 2 * max(abs((xs.min() - PX / 2) * px_m), abs((xs.max() + 1 - PX / 2) * px_m)) * 1.06; HEIGHT = (ys.max() + 1) * px_m * 1.06
PW = max(16, int(round(PX * math.sqrt(WIDTH / HEIGHT) / 8)) * 8); PH = max(16, int(round(PX * math.sqrt(HEIGHT / WIDTH) / 8)) * 8)   # area ≈ px²
WIDTH = HEIGHT * PW / PH if WIDTH / HEIGHT < PW / PH else WIDTH; HEIGHT = WIDTH * PH / PW            # the frame's proportions are exact in pixels
frame(WIDTH, HEIGHT, PW, PH)
AT = {k: np.zeros((PH * ROWS, PW * COLS, 4), np.float32) for k in ("pos", "neg", "tint", "emit")}
t0 = time.time(); DUST_RGB = None
for i, t in enumerate(TIMES):
    objs = build(t); vols = [o for o in objs if o.type == "VOLUME"]; lamps = [o for o in objs if o.type == "LIGHT"]
    fire = {o.name: float(o.get("fx_fire", 0.0)) for o in vols}
    for o in vols: o["fx_fire"] = 0.0; o["fx_ms"] = 0.0
    for o in lamps: o.hide_render = True
    sun.hide_render = False; L = {}
    for k, d in DIRS.items():
        sun.rotation_euler = Vector(d).to_track_quat("-Z", "Y").to_euler(); L[k] = shot(f"{i}_{k}")
    sun.hide_render = True
    for o in vols: o["fx_ms"] = 1.0
    ms = shot(f"{i}_ms")
    for o in vols: o["fx_ms"] = 0.0
    dust = [o for o in vols if o.name.startswith("fx_dust")]; dfrac = np.zeros((PH, PW), np.float32)
    if dust:                                                          # dust share in a pixel: dust is red, smoke is green, light from the front;
        cols = {}                                                     # in the frame the dust is recolored with the scene's soil color (bl_fx._card)
        for o in vols:
            m_ = o.data.materials[0]; pv = m_.node_tree.nodes.get("Principled Volume")
            if pv is not None and m_.name not in cols:
                cols[m_.name] = tuple(pv.inputs["Color"].default_value); pv.inputs["Color"].default_value = (1, 0, 0, 1) if o in dust else (0, 1, 0, 1)
                if o in dust: DUST_RGB = list(cols[m_.name][:3])
        sun.hide_render = False; sun.rotation_euler = Vector(DIRS["front"]).to_track_quat("-Z", "Y").to_euler(); mk = shot(f"{i}_mask"); sun.hide_render = True
        dfrac = np.where(mk[..., 3] > 1e-3, mk[..., 0] / np.maximum(mk[..., 0] + mk[..., 1], 1e-6), 0.0)
        for o in vols:
            m_ = o.data.materials[0]; pv = m_.node_tree.nodes.get("Principled Volume")
            if pv is not None and m_.name in cols: pv.inputs["Color"].default_value = cols.pop(m_.name)
    for o in vols: o["fx_fire"] = fire[o.name]
    for o in lamps: o.hide_render = False
    em = shot(f"{i}_emit") if (any(fire.values()) or lamps) else np.zeros((PH, PW, 4), np.float32)
    r, c = divmod(i, COLS); ys, xs = slice((ROWS - 1 - r) * PH, (ROWS - r) * PH), slice(c * PW, (c + 1) * PW)   # atlas row 0 is at the top
    Y = {k: v[..., :3].mean(2) for k, v in L.items()}                 # brightness is the RGB average (the color is in the tint map)
    AT["pos"][ys, xs] = np.dstack([Y["right"], Y["top"], Y["front"], L["front"][..., 3]])
    AT["neg"][ys, xs] = np.dstack([Y["left"], Y["bottom"], Y["back"], ms[..., :3].mean(2)])
    fr = L["front"]; lum = fr[..., :3].mean(2, keepdims=True)
    AT["tint"][ys, xs, :3] = np.where(lum > 1e-5, fr[..., :3] / np.maximum(lum, 1e-5), 1.0); AT["tint"][ys, xs, 3] = dfrac   # tint.a — dust share
    AT["emit"][ys, xs] = em; AT["emit"][ys, xs, 3] = 1.0
    clear(objs)
    for f in os.listdir(TMP): os.remove(os.path.join(TMP, f))
    print(f"frame {i + 1}/{len(TIMES)} t={t:.2f} {time.time() - t0:.0f} s", flush=True)
os.rmdir(TMP)
ATLASES = {}                                                          # atlas: 8-bit PNG, channel = √(v / multiplier) — dark smoke gets enough
for k, a in AT.items():                                               # steps (an EXR in Blender memory is float32: 38 MB per atlas, PNG — 9)
    sq = [True, True, True, k != "pos"]                               # alpha (pos.a) as is, ms (neg.a) through a square root
    m = [max(float(a[..., c].max()), 1e-6) if sq[c] else 1.0 for c in range(4)]
    if k in ("tint", "emit"): m[3] = 1.0; sq[3] = False
    q = np.stack([np.sqrt(np.clip(a[..., c] / m[c], 0, 1)) if sq[c] else np.clip(a[..., c], 0, 1) for c in range(4)], -1)
    im = bpy.data.images.new(k, PW * COLS, PH * ROWS, alpha=True); im.colorspace_settings.name = "Non-Color"; im.pixels.foreach_set(q.astype(np.float32).ravel())
    im.filepath_raw = os.path.join(OUT, f"{k}.png"); im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
    ATLASES[k] = {"scale": [round(x, 6) for x in m], "sqrt": sq}
meta = {"kind": VID, "source": card_source.fingerprint(VID, bl_fx.knowledge()), "times": TIMES, "cols": COLS, "rows": ROWS, "tile_px": [PW, PH], "width_m": WIDTH, "height_m": HEIGHT, "sun_w": 1.0,
        "atlases": ATLASES, "bake_s": round(time.time() - t0, 1), "disk_mb": round(sum(os.path.getsize(os.path.join(OUT, f"{k}.png")) for k in AT) / 1e6, 1)}
if DUST_RGB: meta.update(dust_rgb=[round(x, 4) for x in DUST_RGB])   # dust color of the shot (the default ground soil); tint.a — dust share
if LOOP: meta.update(loop_s=LOOP_S, q_ref_kw=Q_REF, s=1.0)
else:
    body = bl_fx.asset(bl_fx.knowledge()["kinds"][VID]["fire"]["asset"], "high") or {}
    meta.update(W=bl_fx.norm_event(e)[2], s=(bl_fx.norm_event(e)[2] / float(body.get("W", body.get("M", 1.0)))) ** (1 / 3), early_s=float(body.get("early_s", 0.3)))
json.dump(meta, open(os.path.join(OUT, "card.json"), "w"), ensure_ascii=False, indent=1)
print("__CARDS__", json.dumps({k: v for k, v in meta.items() if k not in ("times", "atlases")}, ensure_ascii=False), flush=True)
