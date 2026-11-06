# Stand of the explosion mechanism: the explosion bl_fx.explosion on flat ground with a 1.8 m human reference figure, light — day (sun + sky) or night (moon + dark sky), exposure as in the far-view node: EV = log2(π / key illuminance).
# blender -b --factory-startup -P core/blender/run.py -- components/fx/bench/stand.py -- <output> kind=projectile time=0.05,0.2,0.6,1.5,3 light=day|night|sunset dist=40 ground=ground [cam_z=m]
#   [strength=1] [height=0] [volume=8/64] [shadows=0|1] [wind=ux,uy — m/s at 10 m] [cards=none|auto|medium|all] [auto=1|0 — frame settings of the mechanism]  → <output>/<case>_t<time>.png, a line __STAND__ {json: frame time, layers, level}
import bpy, json, math, os, sys, time
from mathutils import Vector
from components.fx import bl_fx

A = sys.argv[sys.argv.index("--") + 1:]; OUT = os.path.abspath(A[0]); P = dict(a.split("=", 1) for a in A[1:]); os.makedirs(OUT, exist_ok=True)
vid, light, dist, gnd = P.get("kind", "projectile"), P.get("light", "day"), float(P.get("dist", 40)), P.get("soil", "ground")
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x, sc.render.resolution_y = 1280, 720; sc.eevee.taa_render_samples = 16
t_, s_ = P.get("volume", "8/64").split("/"); sc.eevee.volumetric_tile_size = t_; sc.eevee.volumetric_samples = int(s_)
sc.eevee.use_volumetric_shadows = P.get("shadows", "0") == "1"; sc.view_settings.view_transform = "AgX"
night = light == "night"
sunset = light == "sunset"                                             # sunset: the sun at 12°, warm, a blue sky
sun_E, sky_E, el = (0.06, 0.012, 35) if night else (4.0, 0.14, 12) if sunset else (4.0, 0.8, 40)   # W/m²: moon and night sky — sunset — day
w = bpy.data.worlds.new("w"); sc.world = w; bg = w.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.25, 0.32, 0.5, 1) if night else (0.37, 0.6, 1.0, 1) if sunset else (0.45, 0.6, 0.9, 1); bg.inputs["Strength"].default_value = sky_E
S = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(S); S.data.energy = sun_E
az = {"from_front": -35, "from_side": -90, "from_behind": 145}[P.get("sun", "from_front")]    # front — from behind the camera's left shoulder; behind — backlight (contre-jour)
S.data.color = (0.7, 0.8, 1.0) if night else (1.0, 0.70, 0.35) if sunset else (1.0, 0.96, 0.9); S.rotation_euler = (math.radians(90 - el), 0, math.radians(az))
e_key = sun_E * math.cos(math.radians(max(0.0, 45.0 - el))) + 0.85 * sky_E * math.pi   # key — as in the light node (far.py): a surface turned
# 45° toward the light source, + 0.85 of the sky; a horizontal surface at sunset (12°) made the frame three times brighter than the node, and the fire and the glow looked dim
EV = math.log2(math.pi / e_key) - (1.0 if night else 0.0)            # night is one stop darker than the midpoint (like the node's "mood")
sc.view_settings.exposure = EV
gcol = {"snow": (0.85, 0.87, 0.9), "sand": (0.7, 0.6, 0.45), "ground": (0.32, 0.27, 0.21), "mud": (0.22, 0.18, 0.14), "stone": (0.45, 0.44, 0.42)}.get(gnd, (0.35, 0.3, 0.25))
bpy.ops.mesh.primitive_plane_add(size=4000); gm = bpy.data.materials.new("g"); b = gm.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (*gcol, 1); b.inputs["Roughness"].default_value = 0.9; bpy.context.active_object.data.materials.append(gm)
mk = bpy.data.materials.new("mk"); mk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.6, 0.15, 0.1, 1)
for x in (-6.0, 6.0):                                                  # scale reference: a 1.8 m "human" on both sides of the explosion
    bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=1.8, location=(x, -3.0, 0.9)); bpy.context.active_object.data.materials.append(mk)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.lens = 30
h0 = float(P.get("height", 0)); look = Vector((0, 0, 3 + h0 * 0.9 + dist * 0.05))
cam.location = (dist * 0.17, -dist, float(P["cam_z"]) if P.get("cam_z") else 1.7 + dist * 0.08 + h0 * 0.3); cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
CAM = {"location": list(cam.location), "lens_mm": 30, "sensor_width_mm": 36, "resolution": [1280, 720]}
e = {"at": 0.0, "c": [0, 0, 0], "kind": vid, "strength": float(P.get("strength", 1)), "height": h0, "seed": int(P.get("seed", 1)),
     **({"tint": [float(x) for x in P["tint"].split(",")]} if P.get("tint") else {})}   # tint=0.4,0.7,1.6 — magic
ctx = {"ev": EV, "night": night, "soil": gnd, "fps": 24, **({"level": P["level"]} if P.get("level") else {}),
       **({"wind": [float(x) for x in P["wind"].split(",")]} if P.get("wind") else {}), **({"cards": P["cards"]} if P.get("cards") else {})}
name = f"{vid}_{light}_{gnd}_d{int(dist)}" + (f"_h{int(h0)}" if h0 else "") + (f"_s{P['strength']}" if "strength" in P else "") + (f"_{P['label']}" if "label" in P else "")
res = []
for tt in [float(x) for x in P.get("time", "0.05,0.2,0.6,1.5,3").split(",")]:
    objs = bl_fx.explosion(e, tt, CAM, ctx, sc)
    if objs is None: print("__STAND__", json.dumps({"error": "no knowledge or asset"}, ensure_ascii=False)); sys.exit(1)
    if P.get("layers"):                                                  # only these layers (by the fx_* object names): analyzing the assets one at a time
        keep = {"flash": "fx_flash", "body": "fx_body", "glow": "fx_inner", "soil": "fx_dust", "clods": "fx_clumps", "sparks": "fx_sparks"}
        names = [keep[x] for x in P["layers"].split(",")]
        for o in objs: o.hide_render = not any(o.name.startswith(n) for n in names)
    restore = bl_fx.frame_settings(sc) if P.get("auto", "1") == "1" else (lambda: None)
    sc.render.filepath = os.path.join(OUT, f"{name}_t{tt}.png"); t0 = time.time(); bpy.ops.render.render(write_still=True); dt = round(time.time() - t0, 2)
    row = {"t": tt, "frame_s": dt, **bl_fx.LOG[-1]}
    if P.get("cost") == "1":                                           # price as a pair: the same frame without an explosion and with one, interleaved
        vis = {o.name: o.hide_render for o in objs}; T = {False: [], True: []}
        for _ in range(3):
            for on in (False, True):
                for o in objs: o.hide_render = vis[o.name] if on else True
                t0 = time.time(); bpy.ops.render.render(write_still=False); T[on].append(time.time() - t0)
        row["without_s"], row["incl_s"] = round(sorted(T[False])[1], 3), round(sorted(T[True])[1], 3); row["Δ_s"] = round(row["incl_s"] - row["without_s"], 3)
    restore(); res.append(row)
    for o in objs: bpy.data.objects.remove(o, do_unlink=True)
    bl_fx.tidy()
print("__STAND__", json.dumps({"case": name, "EV": round(EV, 2), "frames": res, "journal": [i for i in bl_fx.LOG if i.get("warning")][:3]}, ensure_ascii=False), flush=True)
