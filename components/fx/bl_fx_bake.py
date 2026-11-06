# source: Pearson 2022, ch. 5 — an explosion from particles (an icosphere core and three circles on the sides, fire +
#         smoke from particles, initial speed ×15, the ground is a collision, a domain with a bottom boundary, vortices,
#         noise ×2); ground ejecta — the same method: dust only, heavier than air.
"""Baking of an explosion asset (components/fx/fx_bake.py prepares the job from library/fx/explosions.yaml): Mantaflow →
OpenVDB (Blosc, half), then per-frame statistics: where the smoke and fire are, the radius and share of fire (the glow
lamp), the body height (screen size), the end of the early phase.
blender -b --factory-startup --python-exit-code 1 -P core/blender/run.py -- components/fx/bl_fx_bake.py -- <job.json>   → <output>/cache, <output>/stats.json"""
import bpy, bmesh, json, math, os, sys, time, glob

J = json.load(open(sys.argv[sys.argv.index("--") + 1])); A, OUT, RES, NOISE = J["asset"], J["output"], int(J["resolution"]), int(J["noise"])
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
F0 = min(int(z["frame"]) for z in A["volleys"]) if A.get("volleys") else int((A.get("core") or A.get("cone") or A.get("ball") or A.get("hotspot"))["frames"][0])
N = F0 + int(A["n_frames"])
sc.render.fps, sc.frame_start, sc.frame_end = 24, 1, N


def emitter(ob, P, kind, velocity=15.0):
    """Particles from the surface of ob: count, frames, speed along the normal, spread → a Mantaflow flow from particles (fire +
    smoke or dust)."""
    ob.modifiers.new("parts", "PARTICLE_SYSTEM"); ps = ob.particle_systems[0].settings
    ps.count, (ps.frame_start, ps.frame_end), ps.lifetime = int(P["n_particles"]), (P.get("frames") or (A.get("core") or A["cone"])["frames"]), int(P.get("life", 5))
    ps.normal_factor, ps.factor_random, ps.render_type = float(P["speed"]), float(P["spread"]), "NONE"
    ps.lifetime_random = float(P.get("life_spread", 0.0))            # jets of different lengths rather than an even "hedgehog"
    if P.get("size_particle"): ps.particle_size, ps.size_random = float(P["size_particle"]), 0.5
    md = ob.modifiers.new("fluid", "FLUID"); md.fluid_type = "FLOW"; fs = md.flow_settings
    fs.flow_type, fs.flow_behavior, fs.flow_source = kind, "INFLOW", "PARTICLES"; fs.particle_system = ob.particle_systems[0]
    fs.use_initial_velocity, fs.velocity_factor, fs.subframes = True, float(P.get("injection", A.get("injection", velocity))), 5; ob.hide_render = True
    fs.use_particle_size = bool(P.get("size_particle"))                # thick jets from few particles (ground ejecta)
    if kind != "SMOKE": fs.fuel_amount = float(P.get("fuel_amount", 1.0))     # more fuel — a longer and wider fire (fuel)
    fs.temperature = float(P.get("heat", 1.0))                           # heat of the ejection — the buoyancy of the hot gas (the fireball rises)


def active():
    return bpy.context.active_object


if "core" in A:                                                       # body: an icosphere core + three circles (sides and top)
    P = A["core"]; k = P["radius"] / 0.125
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=P["radius"], location=(0, 0, P["height"])); emitter(active(), P, "BOTH")
    if A.get("flanks"):                                                   # fuel has no sides: they gave a ring of fire on the ground
        B = dict(A["flanks"], frames=P["frames"])
        for loc, rot in (((0.2 * k, 0, P["height"]), (0, 1.5708, 0)), ((0, 0, P["height"] + 0.2 * k), (0, 0, 0)), ((-0.2 * k, 0, P["height"]), (0, -1.5708, 0))):
            bpy.ops.mesh.primitive_circle_add(vertices=16, radius=0.1 * k, fill_type="NGON", location=loc, rotation=rot); emitter(active(), B, "BOTH")
if "ball" in A:                                                        # fuel fireball: a sphere mesh emits fuel for 2–4 frames
    P = A["ball"]                                                      # with a velocity along the normal, then burning and rising from the heat
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=P["radius"], location=(0, 0, P["height"])); ob = active()
    md = ob.modifiers.new("fluid", "FLUID"); md.fluid_type = "FLOW"; fs = md.flow_settings
    fs.flow_type, fs.flow_behavior, fs.flow_source = "BOTH", "INFLOW", "MESH"; fs.fuel_amount = float(P.get("fuel_amount", 1.0))
    fs.temperature = float(P.get("heat", 1.0)); fs.surface_distance = float(P.get("layer", 0.5)); fs.volume_density = 1.0
    fs.use_initial_velocity, fs.velocity_normal = True, float(P["normal"]); ob.hide_render = True
    fs.velocity_coord = (0.0, 0.0, float(P.get("up", 0.0)))         # fuel is ejected upward: the ball rises (H = D, van den Bosch 2005)
    f0, f1 = P["frames"]                                               # emission only in frames f0…f1: keys on "use_inflow"
    for f, on in ((f0 - 1, False), (f0, True), (f1, True), (f1 + 1, False)): fs.use_inflow = on; fs.keyframe_insert("use_inflow", frame=f)
if "volleys" in A:                                                      # fuel fireball (3–4 flashes with
    E = A["emitter"]                                               # a shift in frames; rays of different lengths; the expansion is fast at the start):
    for i, Z in enumerate(A["volleys"]):                                # an icosphere dome emits fuel particles upward and sideways, a particle
        r = float(Z.get("radius", E["radius"]))                       # slows down (damping) and dies out (lifetime ± spread) — a ray of fuel
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=Z["center"]); ob = active()
        bm = bmesh.new(); bm.from_mesh(ob.data)                       # dome: the bottom of the sphere is cut off — the fuel does not fly into the ground (otherwise a pancake of fire)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -float(E.get("dome", 0.2)) * r], context="VERTS"); bm.to_mesh(ob.data); bm.free()
        emitter(ob, {"n_particles": Z["n_particles"], "frames": [int(Z["frame"]), int(Z["frame"]) + int(Z.get("dur", 1))], "life": Z["life"],
                     "life_spread": E.get("life_spread", 0.6), "speed": Z["speed"], "spread": Z["spread"], "fuel_amount": E["fuel_amount"],
                     "heat": E["heat"], "injection": E.get("injection", 1.0), "size_particle": E.get("size_particle")}, E.get("flow", "FIRE"))
        ps = ob.particle_systems[0].settings; ps.damping = float(E.get("damping", 0.2)); ps.effector_weights.gravity = 0.0
        ps.object_align_factor[2] = float(E.get("up", 0.0)); ob.particle_systems[0].seed = 11 + 7 * i   # no gravity: the fuel is vapor
        ps.brownian_factor = float(E.get("brownian", 0.0))                # wandering: the rays are curved, not a "broom" of straight strokes
if "hotspot" in A:                                                       # steady burning: a disk at the ground emits fuel for the whole duration,
    P = A["hotspot"]                                                     # flicker — a cloud texture with a moving offset (Pearson, ch. 3)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=P["radius"], depth=0.3, location=(0, 0, float(P.get("height", 0.4)))); ob = active()
    # a volumetric fire patch (a flat disk did not emit on a 64 grid — the surface-emission threshold relative to the cell);
    # not right at the ground — the domain boundary
    md = ob.modifiers.new("fluid", "FLUID"); md.fluid_type = "FLOW"; fs = md.flow_settings
    fs.flow_type, fs.flow_behavior, fs.flow_source = "BOTH", "INFLOW", "MESH"; fs.fuel_amount = float(P.get("fuel_amount", 1.0))
    fs.temperature = float(P.get("heat", 1.0)); fs.surface_distance = 0.15; fs.volume_density = 1.0; fs.use_initial_velocity = True
    fs.velocity_coord = (0.0, 0.0, float(P.get("up", 0.0))); ob.hide_render = True
    if P.get("texture"):
        tx = bpy.data.textures.new("flicker", "CLOUDS"); tx.noise_scale = 0.35
        fs.use_texture, fs.noise_texture, fs.texture_size = True, tx, float(P["texture"])
    f0, f1 = P["frames"]
    for f, off in ((1, 0.0), (f1 + 10, (f1 + 9) * 0.04)):                # the texture shifts over time — the flame "breathes" instead of standing still
        fs.texture_offset = off; fs.keyframe_insert("texture_offset", frame=f)
    for f, on in ((f0 - 1, False), (f0, True), (f1, True), (f1 + 1, False)): fs.use_inflow = on; fs.keyframe_insert("use_inflow", frame=f)
if "cone" in A:                                                      # ejecta: a circle on the ground upward (the spread is a cone) and a ring along the ground
    P = A["cone"]
    bpy.ops.mesh.primitive_circle_add(vertices=24, radius=P["radius"], fill_type="NGON", location=(0, 0, 0.05))
    emitter(active(), dict(P, spread=float(P["speed"]) * math.tan(math.radians(P["angle"]))), "SMOKE")
if "ring" in A:
    P = A["ring"]
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=P["radius"], depth=0.2, end_fill_type="NOTHING", location=(0, 0, 0.12))
    emitter(active(), dict(P, spread=float(P.get("spread", 2.0))), "SMOKE")
bpy.ops.mesh.primitive_plane_add(size=400); g = active(); g.modifiers.new("c", "COLLISION")
g.collision.friction_factor = g.collision.damping_factor = 0.9
D = A["domain"]; bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, D[2] / 2)); dom = active(); dom.scale = (D[0] / 2, D[1] / 2, D[2] / 2)
md = dom.modifiers.new("fluid", "FLUID"); md.fluid_type = "DOMAIN"; ds = md.domain_settings
G = A["combustion"]; ds.domain_type, ds.resolution_max, ds.use_collision_border_bottom = "GAS", RES, True
ds.use_adaptive_domain = False                                        # an adaptive domain spoils the .vdb as an asset: the cell and the subdomain offset are not in the file
ds.vorticity, (ds.alpha, ds.beta) = float(G["whirls"]), G["buoyancy"]
if G.get("speed_reaction"): ds.burning_rate, ds.flame_smoke = float(G["speed_reaction"]), float(G["smoke_fire"])
if G.get("fire_max"): ds.flame_max_temp = float(G["fire_max"])     # a hotter flame rises faster (fuel fireball;
if G.get("fire_min"): ds.flame_ignition = float(G["fire_min"])       # the manual: Temperature Maximum/Minimum — rise speed)
if G.get("time"): ds.time_scale = float(G["time"])                   # Mantaflow time step: otherwise a large domain is "slow"
if G.get("whirls_fire"): ds.flame_vorticity = float(G["whirls_fire"])     # the fire swirls by itself (the rolling edge of the fireball)
ds.use_dissolve_smoke = bool(G.get("dissolve"))                     # dust settles: it dissolves over "dissolve" frames (logarithmically)
if G.get("dissolve"): ds.dissolve_speed, ds.use_dissolve_smoke_log = int(G["dissolve"]), True
ds.cache_type, ds.cache_data_format, ds.openvdb_cache_compress_type = "ALL", "OPENVDB", "BLOSC"; ds.openvdb_data_depth = "16"   # half: disk ×0.5
ds.use_noise = NOISE > 1
if NOISE > 1: ds.noise_scale = NOISE; ds.cache_noise_format = "OPENVDB"
CD = os.path.join(OUT, "cache"); ds.cache_directory = CD; ds.cache_frame_start, ds.cache_frame_end = 1, N
t0 = time.time()
with bpy.context.temp_override(scene=sc): bpy.ops.ptcache.bake_all(bake=True)
for o in sc.objects: o.select_set(False)
dom.select_set(True); bpy.context.view_layer.objects.active = dom
with bpy.context.temp_override(scene=sc, object=dom, active_object=dom, selected_objects=[dom], selected_editable_objects=[dom]): bpy.ops.fluid.bake_all()
bake_s = round(time.time() - t0, 1)
corner = [round(min((dom.matrix_world @ v.co)[i] for v in dom.data.vertices), 3) for i in range(3)]

# ---- per-frame statistics: the isosurface of density and fire (Volume to Mesh) → frame, center, radius
folder, stem, sfx = ("noise", "fluid_noise", "_noise") if NOISE > 1 else ("data", "fluid_data", "")
for o in list(sc.objects): bpy.data.objects.remove(o, do_unlink=True)
probe = bpy.data.objects.new("probe", bpy.data.meshes.new("probe")); sc.collection.objects.link(probe)
stats, fire_max = [], 1e-6
for f in range(1, N + 1):
    p = os.path.join(CD, folder, f"{stem}_{f:04d}.vdb")
    if not os.path.exists(p): stats.append(None); continue
    vd = bpy.data.volumes.new("v"); vd.filepath = p; vo = bpy.data.objects.new("v", vd); sc.collection.objects.link(vo); vo.location = corner
    row = {}
    for key, grid, thr in (("smoke", "density" + sfx, 0.05), ("fire", "flame" + sfx, 0.15)):
        m = probe.modifiers.new("v2m", "VOLUME_TO_MESH"); m.object = vo; m.grid_name = grid; m.threshold = thr; m.resolution_mode = "GRID"
        dg = bpy.context.evaluated_depsgraph_get(); ev = probe.evaluated_get(dg); me = ev.to_mesh()
        if len(me.vertices):
            lo = [min(v.co[i] for v in me.vertices) for i in range(3)]; hi = [max(v.co[i] for v in me.vertices) for i in range(3)]
            row[key] = {"center": [round((a + b) / 2, 3) for a, b in zip(lo, hi)], "radius": round(max(b - a for a, b in zip(lo, hi)) / 2, 3), "top": round(hi[2], 3)}
        ev.to_mesh_clear(); probe.modifiers.remove(m)
    bpy.data.objects.remove(vo, do_unlink=True); bpy.data.volumes.remove(vd)
    if row.get("fire"): fire_max = max(fire_max, row["fire"]["radius"])
    stats.append(row or None)
early, f_max = None, max(range(len(stats)), key=lambda i: (stats[i] or {}).get("fire", {}).get("radius", 0)) + 1
for f, row in enumerate(stats, 1):
    if row and row.get("fire"): row["fire"]["frac"] = round((row["fire"]["radius"] / fire_max) ** 2, 3)
    if f > f_max and early is None and fire_max > 1e-5 and (not row or not row.get("fire") or row["fire"]["radius"] < 0.3 * fire_max):
        early = round((f - F0) / 24.0, 3)                             # end of the early phase — the fire shrank to 30 % after its peak
top = max([r["smoke"]["top"] for r in stats[:F0 + 48] if r and r.get("smoke")] or [D[2] / 2])
size = sum(os.path.getsize(x) for x in glob.glob(os.path.join(CD, "**", "*"), recursive=True) if os.path.isfile(x))
json.dump({"frame_start": F0, "n_frames": N, "fps": 24, "folder": folder, "name_file": stem, "sfx": sfx, "angle": corner, "domain": D,
           "height": round(top, 3), "early_s": early or (0.5 if "cone" in A else 0.3), "frames": stats,
           "bake_s": bake_s, "disk_mb": round(size / 1e6, 1), "resolution": RES, "noise": NOISE},
          open(os.path.join(OUT, "stats.json"), "w"), ensure_ascii=False)
print("__BAKE__", json.dumps({"output": OUT, "bake_s": bake_s, "disk_mb": round(size / 1e6, 1), "height": top, "early_s": early}, ensure_ascii=False), flush=True)
