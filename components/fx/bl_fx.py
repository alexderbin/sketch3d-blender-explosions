# particle explosions — Pearson 2022, ch. 5; fire in EEVEE; layers and timing —
#         practitioners' breakdowns (a flash of 2–3 frames, the fireball stays in place, the smoke
#         follows the fireball, the ground layer ties it to the earth, sparks in bundles);
#         Hopkinson–Cranz scaling (W^(1/3)), Froude scaling (smoke time ∝ size^(1/2)), crater ejecta — velocity ∝ W^(1/6).
"""Explosions in the frame. An event {at, c, kind, strength, height} + the frame context {ev, night, soil, ground, fps} →
the objects of frame t: a flash (a lamp), the body (a Volume from .vdb: fire is a black body by flame, smoke), ground
ejecta (a dust Volume in the soil color), clods and sparks (ballistics; a streak = speed × exposure), smoke glow (a lamp
in the fire). The level depends on the screen size of the body; light and glow are "screen-space" (× 2^(−node EV)). No
knowledge or asset — None: the caller has its own fallback (the take's balls).
Knowledge for Blender — library/fx/explosions.json (built by components/fx/fx_bake.py compile from explosions.yaml and
the assets' meta)."""
import core.paths as _core_paths         # the code is here, the core — core/<part> through kernel
import json, math, os, random
import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

ROOT = _core_paths.ROOT
FXDIR = os.path.join(ROOT, "library", "fx")
FIRE0 = 2.5                 # fire on screen at flame = 1 (above white — the core blows out to white, the edge stays orange)
INNER0 = 1.2                # smoke glow from inside: a fraction of the key light at a distance of 2 fire radii
FLASH0 = 1.5                # flash: this many times brighter than the key light at radius R = 4 m × W^(1/3) (3 whitens snow at night)
FIRE_HI = 2.0               # high-level fire: in the flame_noise noise cache it is weaker than the flame of the base grid (on the stand: it did not glow inside the body)
FIRE_LO = 0.5               # low-level fire (a volume without a card): the smooth 64 grid glowed as a solid peach lump
                            # 0.5 suppresses the blow-out, only the card gives the shape
MS0 = 0.12                  # multiple scattering (EEVEE does not compute it: dense smoke darkens and takes the sky's color) — smoke and dust
                            # glow with their own color: the on-screen saturation ≈ MS0 × albedo under the key light
Z0_ROUGH = 0.05             # roughness length of open terrain, m: the wind near the ground is a logarithmic profile from U10 (m/s at 10 m)
CARD_LEVELS = {"auto": ("far", "very_far"), "medium": ("medium", "far", "very_far")}   # card mode → the levels where a card replaces the volume
CARD_MODE = "medium"         # cards by default: everything below close is a card from the high asset (the low volume looked different: "cotton wool,"
                            # faded dust; the look must not depend on the frame resolution); none | auto (far and beyond) | medium | all; the context key "cards"
_K, VOL, MAT, LOG, FRAME, CARDS = None, {}, {}, [], [], {}


def knowledge():
    global _K
    if _K is None:
        p = os.path.join(FXDIR, "explosions.json")
        _K = json.load(open(p)) if os.path.exists(p) else {}
    return _K


def asset(name, level):
    """meta of the baked asset: of level level, otherwise another baked one; none — None."""
    for lv in [level] + [x for x in ("high", "low") if x != level]:
        m = (knowledge().get("baked") or {}).get(name, {}).get(lv)
        if m and os.path.isdir(os.path.join(FXDIR, name, lv, "cache")): return dict(m, dir=os.path.join(FXDIR, name, lv), level=lv)
    return None


def ground_kind(scene_dir):
    """Soil of the place: location.json (ground, biome) or the plan (env ice, ground: snow) → a soil key of the knowledge;
    otherwise — ground."""
    G = {"snow": "snow", "ice": "snow", "sand": "sand", "desert": "sand", "mud": "mud", "wasteland": "mud", "rock": "stone",
         "alpine": "stone", "volcanic": "stone", "grass": "ground", "soil": "ground", "temperate": "ground", "ash": "ground"}
    try:
        lo = json.load(open(os.path.join(scene_dir, "location.json")))
        for k in (lo.get("ground"), lo.get("biome")):
            if k in G: return G[k]
    except (OSError, ValueError): pass
    p = os.path.join(scene_dir, "plan.yaml")
    if os.path.exists(p) and any(w in open(p, encoding="utf-8").read() for w in ("env: ice", "ground: snow")): return "snow"
    return "ground"


def norm_event(e):
    """Event → kind, the kind's knowledge, W (kg of TNT, for fuel — kg of fuel), height. Without a kind — a grenade; "strength"
    is the kind's multiplier."""
    V_ = knowledge()["kinds"]; vid = e.get("kind") if e.get("kind") in V_ else "grenade"; V = V_[vid]
    return vid, V, float(V.get("W", V.get("M", 1.0))) * float(e.get("strength", 1.0)), float(e.get("height", 0.0))


def px_of(height_m, c, cam):
    """Height of an object in frame pixels for camera cam {location, lens_mm, sensor_width_mm, resolution}."""
    d = max(0.5, (Vector(cam["location"]) - Vector(c)).length)
    return height_m * (cam.get("resolution") or [1280, 720])[0] * float(cam.get("lens_mm", cam.get("lens", 30))) / (float(cam.get("sensor_width_mm", 36)) * d)


def level_of(px):
    U = knowledge()["levels"]
    return next(((n, U[n]) for n in ("close", "medium", "far", "very_far") if px >= U[n]["off"]), ("very_far", U["very_far"]))


def asset_time(dt, s, T1):
    """Event time → asset time: the early phase (fire, ejecta, T1 — in the asset) × s, the late one (smoke, settling) × s^0.5."""
    return dt / s if dt <= T1 * s else T1 + (dt - T1 * s) / math.sqrt(s)


def tidy():
    """Volumes of past frames with no users are dropped from memory (the take deletes the effect objects after a frame)."""
    for k, v in list(VOL.items()):
        if v.name not in bpy.data.volumes: VOL.pop(k); continue
        if v.users == 0: bpy.data.volumes.remove(v); VOL.pop(k)


def _attr(nt, name, kind="GEOMETRY"):
    a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = kind; a.attribute_name = name; return a.outputs["Fac"]


def _math(nt, op, a, b=None, v=None):
    m = nt.nodes.new("ShaderNodeMath"); m.operation = op; nt.links.new(a, m.inputs[0])
    if b is not None: nt.links.new(b, m.inputs[1])
    else: m.inputs[1].default_value = v
    return m.outputs[0]


def _vmath(nt, op, a, b):
    m = nt.nodes.new("ShaderNodeVectorMath"); m.operation = op; nt.links.new(a, m.inputs[0])
    if isinstance(b, (int, float)): m.inputs[3].default_value = b                     # SCALE — multiplier
    else: nt.links.new(b, m.inputs[1])
    return m.outputs[0]


def volume_material(key, sfx, smoke, fire=None):
    """Body or dust: density σ = density × layer density × 20 × fx_fade (the fade is an object property). Emission (color,
    strength 1): fire is a black body T = T0 + flame·(T1 − T0) × flame^1.5 × fx_fire; multiple scattering — smoke color × σ
    × fx_ms (object properties: screen strengths × 2^(−EV)), so dense dust neither turns black nor turns blue from the sky."""
    if key in MAT: return MAT[key]
    m = bpy.data.materials.new(f"fx_{key}"); nt = m.node_tree; nt.nodes.clear()
    out, pv = nt.nodes.new("ShaderNodeOutputMaterial"), nt.nodes.new("ShaderNodeVolumePrincipled")
    dfl = nt.nodes.new("ShaderNodeMath"); dfl.operation = "SUBTRACT"; dfl.use_clamp = True; dfl.inputs[1].default_value = 0.01
    nt.links.new(_attr(nt, "density" + sfx), dfl.inputs[0])          # threshold 0.01: a thin backing (×20 along the ray) darkened the sky within the layer
    sig = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", dfl.outputs[0], _attr(nt, "fx_fade", "OBJECT")), v=float(smoke["density"]) * 20.0)
    if smoke.get("cut"):                                             # the smoke fades toward the domain ceiling (z is in asset meters: object coordinates)
        tc = nt.nodes.new("ShaderNodeTexCoord"); sp = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sp.inputs[0])
        cut = nt.nodes.new("ShaderNodeMapRange"); cut.inputs["From Min"].default_value, cut.inputs["From Max"].default_value = smoke["cut"]
        cut.inputs["To Min"].default_value, cut.inputs["To Max"].default_value = 1.0, 0.0; nt.links.new(sp.outputs["Z"], cut.inputs["Value"])
        sig = _math(nt, "MULTIPLY", sig, cut.outputs["Result"])
        rise = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", _attr(nt, "fx_top", "OBJECT"), sp.outputs["Z"]), v=1 / 1.5)   # the column grows from below:
        nt.nodes[-1].use_clamp = True; sig = _math(nt, "MULTIPLY", sig, rise)   # above the front fx_top (asset m) there is no smoke yet — the burning loop
                                                                       # is baked in a steady state, otherwise the column would reach the sky from the first frame
    if fire:                                                          # where it burns there is little soot: the smoke is thinner (1 − 1.5·flame), the fireball
        fl_ = _math(nt, "MULTIPLY", _attr(nt, "flame" + sfx), v=1.5 * float(fire.get("soot", 1.0)))   # is visible, the smoke appears as it cools
        keep = nt.nodes.new("ShaderNodeMath"); keep.operation = "SUBTRACT"   # (for fuel the soot envelops the fire: soot < 1)
        keep.use_clamp = True; keep.inputs[0].default_value = 1.0; nt.links.new(fl_, keep.inputs[1])
        sig = _math(nt, "MULTIPLY", sig, keep.outputs[0])
    kap = float(fire.get("optical_depth", 0.0)) if fire else 0.0              # the fire is optically dense (soot in the flame): absorption flame × κ per meter
    nt.links.new(sig, pv.inputs["Density"])                           # (the absorption node is below), emission ∝ the same κ — thick fire glows
    pv.inputs["Color"].default_value = (*smoke["color"], 1.0); pv.inputs["Anisotropy"].default_value = float(smoke.get("anisotropy", 0.3))
    rgb = nt.nodes.new("ShaderNodeRGB"); rgb.outputs[0].default_value = (*smoke["color"], 1.0)
    thick = nt.nodes.new("ShaderNodeMapRange"); thick.inputs["From Min"].default_value, thick.inputs["From Max"].default_value = 0.05, 0.4
    nt.links.new(_attr(nt, "density" + sfx), thick.inputs["Value"])  # only the dense part: EEVEE lights thin smoke anyway (a "box" of thin dust)
    emit = _vmath(nt, "MULTIPLY", rgb.outputs[0], _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", sig, _attr(nt, "fx_ms", "OBJECT")), thick.outputs["Result"]))
    if fire:
        fl = _attr(nt, "flame" + sfx); T0, T1 = fire["T"]; bb = nt.nodes.new("ShaderNodeBlackbody")
        nt.links.new(_math(nt, "ADD", _math(nt, "MULTIPLY", fl, v=T1 - T0), v=T0), bb.inputs["Temperature"])
        powr = _math(nt, "POWER", fl, v=float(fire.get("exponent", 1.5)))   # 1.5 — the core is brighter than the edge; for the sparse fire of fuel — 1
        col = bb.outputs["Color"]
        if tint_of(fire):                                              # magic: the color is the tint itself (blue died out on a black body), the core is whiter:
            tn = nt.nodes.new("ShaderNodeRGB"); tn.outputs[0].default_value = (*tint_of(fire), 1.0)   # + white × max(0, flame − 0.7)·2
            core = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", fl, v=0.7), v=2.0); nt.nodes[-1].use_clamp = True
            col = _vmath(nt, "ADD", tn.outputs[0], core)
        if kap: powr = _math(nt, "MULTIPLY", powr, v=kap)              # brightness of thick fire ≈ color × flame^(exponent − 1) × fx_fire
        emit = _vmath(nt, "ADD", emit, _vmath(nt, "MULTIPLY", col, _math(nt, "MULTIPLY", powr, _attr(nt, "fx_fire", "OBJECT"))))
    nt.links.new(emit, pv.inputs["Emission Color"]); pv.inputs["Emission Strength"].default_value = 1.0
    vol = pv.outputs["Volume"]
    if kap:                                                           # by temperature, not by thickness (a 15 m ball is no brighter than a 5 m one); only
        ab = nt.nodes.new("ShaderNodeVolumeAbsorption"); ab.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)   # absorption: density
        nt.links.new(_math(nt, "MULTIPLY", _attr(nt, "flame" + sfx), v=kap), ab.inputs["Density"])   # Principled also scatters —
        add = nt.nodes.new("ShaderNodeAddShader"); nt.links.new(vol, add.inputs[0]); nt.links.new(ab.outputs["Volume"], add.inputs[1])   # the lamp
        vol = add.outputs[0]                                          # of the fire inside the ball bleached it to peach
    nt.links.new(vol, out.inputs["Volume"]); MAT[key] = m
    return m


def tint_of(fire):
    """Tint of magical fire, normalized (the largest channel is 1); ordinary fire — None."""
    t = fire.get("tint")
    if not t or list(t) == [1.0, 1.0, 1.0]: return None
    m = max(t); return [x / m for x in t]


def _surface(key, rgb, emit=False):
    if key in MAT: return MAT[key]
    m = bpy.data.materials.new(f"fx_{key}"); b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0); b.inputs["Roughness"].default_value = 0.95
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1.0); m.node_tree.links.new(_attr(m.node_tree, "fx_fire", "OBJECT"), b.inputs["Emission Strength"])
    MAT[key] = m; return m


def _lamp(name, loc, power, kelvin, radius, shadow, sc, rgb=None):
    L = bpy.data.lights.new(name, "POINT"); L.energy = power; L.use_temperature = rgb is None; L.temperature = kelvin
    if rgb: L.color = rgb                                              # magic: light of the fire's color, not by Kelvin
    L.shadow_soft_size = radius; L.use_shadow = shadow
    o = bpy.data.objects.new(name, L); o.location = loc; sc.collection.objects.link(o); return o


def _body(sc, name, A, t_a, c, s, rot, mirror, mat, fade, fire_k, ms_k):
    """Volume of asset A at asset time t_a: a baked frame (after the last one — hold and fade); the object origin is the
    domain corner: the explosion center at c with scale s, rotation rot and a mirror along X. → (object, frame statistics)
    or (None, None)."""
    f = int(round(A["frame_start"] + t_a * A["fps"])); hold = max(0.0, (f - A["n_frames"]) / A["fps"]); f = min(max(f, 1), A["n_frames"])
    path = os.path.join(A["dir"], "cache", A["folder"], f"{A['name_file']}_{f:04d}.vdb")
    if not os.path.exists(path): return None, None
    v = VOL.get((path, mat.name))
    if v is None or v.name not in bpy.data.volumes:                    # one volume per (frame, material): different kinds share one asset
        v = bpy.data.volumes.new("fx_vdb"); v.filepath = path; v.render.precision = "HALF"; v.materials.append(mat); VOL[(path, mat.name)] = v
        v.render.clipping = 0.02                                       # empty stays empty: a noise backing over the whole domain gave a "box"
    o = bpy.data.objects.new(name, v); sc.collection.objects.link(o)
    sx = -s if mirror else s; cx, cy, cz = A["angle"]
    off = Vector((sx * cx, s * cy, s * cz)); off.rotate(Euler((0, 0, rot)))
    o.rotation_euler = (0, 0, rot); o.scale = (sx, s, s); o.location = Vector(c) + off
    o["fx_fade"] = fade * math.exp(-hold / 1.5); o["fx_fire"] = fire_k; o["fx_ms"] = ms_k
    o["fx_shadows"] = 1                                               # a layer over the node's haze — with lamp shadows: the shape of the smoke (bl_far.render_scene_fx)
    return o, (A.get("frames") or [None] * f)[f - 1]


def wind_at(ctx, z):
    """Wind at height z above the ground, m/s (a downwind vector): the context key "wind" [ux, uy] — m/s at 10 m; none or calm
    — None."""
    w = (ctx or {}).get("wind")
    if not w or len(w) < 2 or not (float(w[0]) or float(w[1])): return None
    k = math.log(max(z, Z0_ROUGH * math.e) / Z0_ROUGH) / math.log(10.0 / Z0_ROUGH)
    return Vector((float(w[0]) * k, float(w[1]) * k, 0.0))


LEAN_MAX = 60.0             # a burning column leaning into the wind is no steeper than 60° from vertical (more than that would be a bent column, which a straight one cannot show)


def _lean(sc, o, z0, H, disp, base=None):
    """Wind drift without recomputing the volume — through the parent matrix (an fx_wind empty at the origin; the object has
    its own position, rotation and mirror). Cloud: the drift d(z) (m, a vector) at heights 0.15 H and 0.85 H above the
    ground z0 → a shift a + a shear b·(z − z0) (the upper layer drifts farther, as in wind near the ground). Burning column
    (base is the base point): a rotation about the base by the angle atan(|d(0.85 H)| / 0.85 H), no steeper than LEAN_MAX —
    the column's thickness is preserved (a shear stretched a strong lean into a thin strip), the fire stands on its source."""
    za, zb = 0.15 * H, 0.85 * H; da = disp(za) if H > 0 else None
    if da is None: return
    if base is not None:
        d = disp(zb); th = min(math.atan2(d.length, zb), math.radians(LEAN_MAX))
        if d.length < 1e-6: return
        ax = Vector((0, 0, 1)).cross(d.normalized()); bp = Vector(base)
        S = Matrix.Translation(bp) @ Matrix.Rotation(th, 4, ax) @ Matrix.Translation(-bp)
    else:
        b = (disp(zb) - da) / (zb - za); a = da - b * za
        S = Matrix.Identity(4); S[0][2], S[1][2] = b.x, b.y; S[0][3], S[1][3] = a.x - b.x * z0, a.y - b.y * z0
    root = bpy.data.objects.get("fx_wind")
    if root is None: root = bpy.data.objects.new("fx_wind", None)
    if root.name not in sc.collection.objects: sc.collection.objects.link(root)
    o.parent = root; o.matrix_parent_inverse = S


def _puff(ctx, dt, tm):
    """Drift of the explosion cloud d(z) = U(z) · t_ef: while the ball flies by inertia (the early phase tm), the wind hardly
    moves it."""
    te = dt - tm * (1.0 - math.exp(-dt / max(tm, 1e-3)))
    return lambda z: (lambda u: u * te if u is not None else None)(wind_at(ctx, z))


def _smoke_top(A, t_a, s):
    """Top of the smoke of asset A at its time t_a, m (the bake summary × scale); no summary — the asset height."""
    f = min(max(int(round(A["frame_start"] + t_a * A["fps"])), 1), int(A["n_frames"])); row = (A.get("frames") or [None] * f)[f - 1] or {}
    return float((row.get("smoke") or {}).get("top", A.get("height", 5.0))) * s


def _burning(sc, e, db, c, Q, dur, q, ev, cam, rot, out, info, phase=0.0, name="fx_burn", ramp=0.5, ctx=None, level=None):
    """Steady burning after an explosion, or a fire: the loop of the "combustion" asset — two instances shifted by half a
    period with a triangular fade (the sum is constant — the seam is invisible), scaled by power: size ∝ Q^(2/5), time ∝
    size^(1/2) (the flame is buoyant); the flame by Heskestad L = 0.235·Q^(2/5) − 1.02·D; the fire lamp flickers. db — time
    since the start of burning, s."""
    K = knowledge(); P = K["kinds"]["blaze"]; probe = asset("combustion", "low")
    if probe is None or db < 0: return
    s = (Q / float(probe.get("Q_kw", 500))) ** 0.4; L = max(0.3, 0.235 * Q ** 0.4 - 1.02 * 1.0 * s)
    px = px_of(4.0 * L, c, cam); lvl, U = level_of(px)                 # the smoke column is ~4 flame lengths — the level is set by it
    if level: lvl, U = level, K["levels"][level]                       # baking a burning card — the level is forced
    info.setdefault("level", lvl); info.setdefault("px", round(px))
    fin = min(1.0, db / ramp); fout = 1.0 if db < dur else math.exp(-(db - dur) / 3.0)
    mode = str((ctx or {}).get("cards", CARD_MODE)); vf = 0.39 * Q ** (1 / 3)   # smoke front: ~0.6 of the plume speed per McCaffrey, m/s
    cs = card_set("combustion") if mode == "all" or lvl in CARD_LEVELS.get(mode, ()) else None
    if cs is not None:                                                 # far away — the loop card: the frame by phase, a cut at the front, a lean into the wind
        TM = cs[0]["times"]; per = float(cs[0]["loop_s"]) * math.sqrt(s); k = int(((db / per + phase) % 1.0) * len(TM)) % len(TM)
        o = _card_object(sc, f"{name}_card", cs, Vector(c), cam, ctx, s, False)
        o["fx_frame"] = float(k); o["fx_fire"] = q; o["fx_fade"] = fin * fout; o["fx_top"] = (L + vf * db) / s; out.append(o)
        _lean(sc, o, c.z, L + vf * db, lambda z: (lambda u: u * min(z / vf, db) if u is not None else None)(wind_at(ctx, z)), base=c)
        info["layers"].append("combustion")
    elif U["body"] is not None:
        A = asset("combustion", U["body"]); L0, L1 = A["loop"]; Lf = (L1 - L0) / A["fps"]; ta = db / math.sqrt(s)
        mat = volume_material(f"combustion_{A['level']}", A["sfx"], dict(P["smoke"], cut=A.get("cut")) if A.get("cut") else P["smoke"], P["fire"])
        fk = FIRE0 * float(P["fire"]["strength"]) * q * (FIRE_HI if A["level"] == "high" else FIRE_LO)
        for i in (0, 1):
            ph = (ta / Lf + 0.5 * i + phase) % 1.0; w = 1.0 - abs(2.0 * ph - 1.0)
            o, _ = _body(sc, f"{name}{i}", A, (L0 - A["frame_start"]) / A["fps"] + ph * Lf, c, s, rot + 2.1 * i, i == 1, mat,
                         w * fin * fout, fk, MS0 * 2.0 ** (-ev))
            if o:
                o["fx_top"] = (L + vf * db) / s; out.append(o)         # wind: the smoke at height z was emitted z / vf ago (not before the start of burning)
                _lean(sc, o, c.z, L + vf * db, lambda z: (lambda u: u * min(z / vf, db) if u is not None else None)(wind_at(ctx, z)), base=c)
        info["layers"].append("combustion")
    fl = 0.85 + 0.15 * math.sin(13.1 * db + 1.7) * math.sin(7.3 * db)   # fire flicker
    out.append(_lamp(name + "_light", Vector(c) + Vector((0, 0, 0.3 * L)), 2 * math.pi ** 2 * L * L * q * fl * fin * fout,   # at the base, half as strong:
                     2100, 0.3 * L, U["lamp_shadow"], sc))   # otherwise the smoke column glowed like a flame; 2100 K — at 1700 AgX turned it pink
    info["flame_m"] = round(L, 2); FRAME.append(lvl)


def _inner(sc, V, st, s, rot, mirror, c, q, U, fire):
    """Smoke glow from inside — a lamp in the asset fire while it exists (the frame summary st); strength ∝ the fire fraction ×
    the kind's "light" (if the glow is set by thickness, the strength is the brightness of dense fire). No fire — None."""
    if not st or not st.get("fire"): return None
    pc = Vector(st["fire"]["center"]) * s; pc.x *= -1 if mirror else 1; pc.rotate(Euler((0, 0, rot)))
    Rf = max(0.3, st["fire"]["radius"] * s); P_in = 4 * math.pi ** 2 * (2 * Rf) ** 2 * INNER0 * st["fire"]["frac"] * float(V["fire"].get("light", V["fire"]["strength"])) * q
    return _lamp("fx_inner", c + pc, P_in, max(2100, int(sum(V["fire"]["T"]) / 2)), Rf, U["lamp_shadow"], sc, tint_of(fire))


def card_set(vid):
    """Card of a kind or of the combustion loop (library/fx/cards/<kind|combustion>: atlases of bl_fx_cards.py and card.json
    with English keys): (meta, material, mesh); not baked — None. The mesh is width_m × height_m, the bottom at the ground;
    cut from the top at the front fx_top (card m)."""
    if vid in CARDS and (CARDS[vid] is None or CARDS[vid][1].name in bpy.data.materials): return CARDS[vid]
    d = os.path.join(FXDIR, "cards", vid)
    if not os.path.exists(os.path.join(d, "card.json")): CARDS[vid] = None; return None
    meta = json.load(open(os.path.join(d, "card.json"))); m = bpy.data.materials.new(f"fx_card_{vid}"); m.surface_render_method = "DITHERED"
    from components.fx import card_source                             # the asset was re-baked or the kind's knowledge was corrected — the card is stale
    if meta.get("source") != card_source.fingerprint(vid, knowledge()):
        print(f"bl_fx: the card '{vid}' is stale (the source changed) — re-shoot: python -m components.fx.fx_bake cards --stale", flush=True)
    nt = m.node_tree; nt.nodes.clear(); out = nt.nodes.new("ShaderNodeOutputMaterial"); n, nr = int(meta["cols"]), int(meta.get("rows", meta["cols"]))
    fr = _attr(nt, "fx_frame", "OBJECT"); row = _math(nt, "FLOOR", _math(nt, "DIVIDE", fr, v=n), v=0.0); col = _math(nt, "SUBTRACT", fr, _math(nt, "MULTIPLY", row, v=n))
    uv = nt.nodes.new("ShaderNodeTexCoord"); sp = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(uv.outputs["UV"], sp.inputs[0])
    cu = nt.nodes.new("ShaderNodeCombineXYZ")                          # frame k: column k mod n, row from the top k div n
    nt.links.new(_math(nt, "DIVIDE", _math(nt, "ADD", sp.outputs["X"], col), v=n), cu.inputs["X"])
    nt.links.new(_math(nt, "DIVIDE", _math(nt, "ADD", sp.outputs["Y"], _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", row, v=-1.0), v=-(nr - 1))), v=nr), cu.inputs["Y"])
    T, AT = {}, meta.get("atlases") or {}                              # atlases: 8-bit PNG (√ and a channel multiplier) or EXR as is
    for k in ("pos", "neg", "tint", "emit"):
        fn = os.path.join(d, f"{k}.png") if os.path.exists(os.path.join(d, f"{k}.png")) else os.path.join(d, f"{k}.exr")
        im = bpy.data.images.load(fn, check_existing=True); im.colorspace_settings.name = "Non-Color"; im.alpha_mode = "CHANNEL_PACKED"
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = im; tx.extension = "EXTEND"; tx.interpolation = "Linear"; nt.links.new(cu.outputs[0], tx.inputs["Vector"])
        s3 = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(tx.outputs["Color"], s3.inputs[0])
        A_ = AT.get(k) or {"scale": [1.0] * 4, "sqrt": [False] * 4}; ch = []
        for i, sock in enumerate((s3.outputs["Red"], s3.outputs["Green"], s3.outputs["Blue"], tx.outputs["Alpha"])):
            v = _math(nt, "MULTIPLY", sock, sock) if A_["sqrt"][i] else sock
            ch.append(_math(nt, "MULTIPLY", v, v=float(A_["scale"][i])) if float(A_["scale"][i]) != 1.0 else v)
        rgb = nt.nodes.new("ShaderNodeCombineColor")
        for i, nm in enumerate(("Red", "Green", "Blue")): nt.links.new(ch[i], rgb.inputs[nm])
        T[k] = {"Red": ch[0], "Green": ch[1], "Blue": ch[2], "Alpha": ch[3], "Color": rgb.outputs[0]}
    P, N = T["pos"], T["neg"]; lv = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(_attrv(nt, "fx_l"), lv.inputs[0])
    lum = None                                                         # sun light: 6 sides by the direction to the sun in the card's axes
    for ax, (a_, b_) in zip(("X", "Y", "Z"), ((P["Red"], N["Red"]), (P["Green"], N["Green"]), (P["Blue"], N["Blue"]))):
        pp = _math(nt, "MAXIMUM", lv.outputs[ax], v=0.0); nn = _math(nt, "MAXIMUM", _math(nt, "MULTIPLY", lv.outputs[ax], v=-1.0), v=0.0)
        term = _math(nt, "ADD", _math(nt, "MULTIPLY", pp, a_), _math(nt, "MULTIPLY", nn, b_)); lum = term if lum is None else _math(nt, "ADD", lum, term)
    sun = _vscale(nt, _attrv(nt, "fx_sun"), lum)
    side = _math(nt, "ADD", _math(nt, "ADD", P["Red"], N["Red"]), _math(nt, "ADD", P["Blue"], N["Blue"]))   # sky and ground: 4π/6 per side
    sky = _vscale(nt, _attrv(nt, "fx_sky"), _math(nt, "MULTIPLY", _math(nt, "ADD", P["Green"], _math(nt, "MULTIPLY", side, v=0.5)), v=4 * math.pi / 6))
    gnd = _vscale(nt, _attrv(nt, "fx_gnd"), _math(nt, "MULTIPLY", _math(nt, "ADD", N["Green"], _math(nt, "MULTIPLY", side, v=0.5)), v=4 * math.pi / 6))
    ms = _math(nt, "MULTIPLY", N["Alpha"], _attr(nt, "fx_ms", "OBJECT"))
    lit = _vmath(nt, "ADD", _vmath(nt, "ADD", sun, sky), gnd)
    tint = T["tint"]["Color"]                                          # the smoke and dust color is a tint map; the dust is matched to the scene's ground:
    if meta.get("dust_rgb"):                                           # + dust fraction × tint shift, brightness × (1 + fraction × albedo shift)
        dfr = T["tint"]["Alpha"]; tint = _vmath(nt, "ADD", tint, _vscale(nt, _attrv(nt, "fx_dust_shift"), dfr))
        ms = _math(nt, "MULTIPLY", ms, _math(nt, "ADD", _math(nt, "MULTIPLY", dfr, _attr(nt, "fx_dust_k", "OBJECT")), v=1.0))
        lit = _vscale(nt, lit, _math(nt, "ADD", _math(nt, "MULTIPLY", dfr, _attr(nt, "fx_dust_k", "OBJECT")), v=1.0))
    smoke = _vmath(nt, "MULTIPLY", _vmath(nt, "ADD", lit, _cvec(nt, ms)), tint)
    fire = _vscale(nt, T["emit"]["Color"], _attr(nt, "fx_fire", "OBJECT"))
    em = nt.nodes.new("ShaderNodeEmission"); nt.links.new(_vmath(nt, "ADD", smoke, fire), em.inputs["Color"]); em.inputs["Strength"].default_value = 1.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader")
    Wm, Hm = float(meta["width_m"]), float(meta.get("height_m", meta["width_m"]))
    top = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", _attr(nt, "fx_top", "OBJECT"), _math(nt, "MULTIPLY", sp.outputs["Y"], v=Hm)), v=1 / 1.5)
    nt.nodes[-1].use_clamp = True                                      # the burning column grows from below: above the front fx_top (card m) it is empty
    alpha = _math(nt, "MULTIPLY", P["Alpha"], _attr(nt, "fx_fade", "OBJECT"))
    if meta.get("dust_rgb"):                                           # a ground without dust (metal, water) — the card's dust is removed
        alpha = _math(nt, "MULTIPLY", alpha, _math(nt, "SUBTRACT", _cval(nt, 1.0), _math(nt, "MULTIPLY", T["tint"]["Alpha"], _attr(nt, "fx_dust_off", "OBJECT"))))
    nt.links.new(_math(nt, "MULTIPLY", alpha, top), mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])
    rows = 6                                                           # mesh: Wm × Hm, the bottom at the ground, 6 rows in height
    V_ = [((i % 2 - 0.5) * Wm, 0.0, (i // 2) / rows * Hm) for i in range(2 * (rows + 1))]
    F_ = [(2 * j, 2 * j + 1, 2 * j + 3, 2 * j + 2) for j in range(rows)]
    me = bpy.data.meshes.new(f"fx_card_{vid}"); me.from_pydata(V_, [], F_); uvl = me.uv_layers.new()
    for poly in me.polygons:
        for li in poly.loop_indices: x, _, z = V_[me.loops[li].vertex_index]; uvl.data[li].uv = (x / Wm + 0.5, z / Hm)
    me.materials.append(m); CARDS[vid] = (meta, m, me)
    return CARDS[vid]


def _attrv(nt, name):
    """An object property as a vector (color, direction)."""
    a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = "OBJECT"; a.attribute_name = name; return a.outputs["Vector"]


def _vscale(nt, vec, k):
    """Vector × number (sockets)."""
    m = nt.nodes.new("ShaderNodeVectorMath"); m.operation = "SCALE"; nt.links.new(vec, m.inputs[0]); nt.links.new(k, m.inputs[3]); return m.outputs[0]


def _cval(nt, v):
    """A constant number as a socket."""
    n = nt.nodes.new("ShaderNodeValue"); n.outputs[0].default_value = v; return n.outputs[0]


def _cvec(nt, v):
    """Number → vector (v, v, v) for mixing with light."""
    c = nt.nodes.new("ShaderNodeCombineXYZ")
    for k in ("X", "Y", "Z"): nt.links.new(v, c.inputs[k])
    return c.outputs[0]


def scene_light(sc, ctx):
    """Sun and sky for the cards: from the context (sun: {dir — toward the sun, rgb — W/m²}, sky — the sky brightness,
    ground_light), otherwise from the scene — the strongest SUN lamp and the world background color; no sky found — 0.064 ×
    sun, blue (sky E ≈ 0.2 sun E)."""
    ctx = ctx or {}
    if ctx.get("sun"):
        su = ctx["sun"]; d, rgb = Vector(su["dir"]).normalized(), Vector(su["rgb"])
    else:
        L = [o for o in sc.objects if o.type == "LIGHT" and o.data.type == "SUN" and not o.hide_render]
        if L:
            o = max(L, key=lambda o: o.data.energy); d = (o.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized(); rgb = Vector(o.data.color) * o.data.energy
        else: d, rgb = Vector((0, 0, 1)), Vector((0, 0, 0))
    sky = ctx.get("sky")
    if sky is None:
        bg = sc.world.node_tree.nodes.get("Background") if sc.world and sc.world.node_tree else None
        if bg is not None and not bg.inputs["Color"].is_linked:
            sky = [c * bg.inputs["Strength"].default_value for c in bg.inputs["Color"].default_value[:3]]
        else: sky = [0.064 * x * k for x, k in zip((rgb.length,) * 3, (0.6, 0.75, 1.0))]
    gnd = ctx.get("ground_light") or [0.2 * (x * max(d.z, 0.0) / math.pi + y) for x, y in zip(rgb, sky)]
    return d, rgb, Vector(sky), Vector(gnd)


def _card_object(sc, name, cs, c, cam, ctx, scale, mirror):
    """Card object: a plane facing the camera (rotated around the vertical), scale scale relative to the baked one, a mirror;
    light — the scene's sun, sky and ground in the card's axes (fx_l, fx_sun, fx_sky, fx_gnd), multiple scattering by the
    node's exposure."""
    meta, m, me = cs; o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.visible_shadow = False
    cl = Vector(cam["location"]); th = math.atan2(cl.x - c.x, -(cl.y - c.y))
    o.location = c; o.rotation_euler = (0, 0, th); o.scale = (-scale if mirror else scale, scale, scale)
    d, rgb, sky, gnd = scene_light(sc, ctx); right, front = Vector((math.cos(th), math.sin(th), 0)), Vector((math.sin(th), -math.cos(th), 0))
    o["fx_l"] = ((-1 if mirror else 1) * d.dot(right), d.z, d.dot(front)); o["fx_sun"] = tuple(rgb / float(meta.get("sun_w", 1.0)))
    o["fx_sky"] = tuple(sky); o["fx_gnd"] = tuple(gnd); o["fx_ms"] = MS0 * 2.0 ** (-float((ctx or {}).get("ev", 0.0))); o["fx_top"] = 1e6; o["fx_card"] = 1
    return o


def _card(sc, e, vid, dt, c, cam, ctx, sila, q, fade, rng):
    """Explosion card at time dt: the atlas frame by time (the similarity law: early phase × s, late × √s from strength 1), a
    plane facing the camera, mirrored by the seed. No card — None."""
    cs = card_set(vid)
    if cs is None: return None
    meta = cs[0]; s_ref, T1 = float(meta["s"]), float(meta.get("early_s", 0.3)); s_rel = sila ** (1 / 3)
    a = asset_time(dt, s_ref * s_rel, T1); tau = a * s_ref if a <= T1 else T1 * s_ref + (a - T1) * math.sqrt(s_ref)   # card time (strength 1)
    TM = meta["times"]; k = min(range(len(TM)), key=lambda i: abs(TM[i] - tau)); hold = max(0.0, tau - TM[-1])
    o = _card_object(sc, "fx_card", cs, c, cam, ctx, s_rel, rng.random() < 0.5)
    o["fx_frame"] = float(k); o["fx_fire"] = q; o["fx_fade"] = fade * math.exp(-hold / 1.5)
    if meta.get("dust_rgb"):                                           # the card's dust was shot on plain ground — recolor it to match the scene's soil
        dn = dust_rgb(ctx.get("soil", "ground"), norm_event(e)[2]); db = meta["dust_rgb"]; mb = sum(db) / 3
        if dn is None: o["fx_dust_shift"], o["fx_dust_k"], o["fx_dust_off"] = (0.0, 0.0, 0.0), 0.0, 1.0
        else:
            mn = sum(dn) / 3; o["fx_dust_shift"] = tuple(a / mn - b / mb for a, b in zip(dn, db)); o["fx_dust_k"] = mn / mb - 1.0; o["fx_dust_off"] = 0.0
    return o


def dust_rgb(ground, W):
    """Dust color of the ejecta on soil ground at strength W (as for the volume: the soil with a share of earth under it); no
    dust (metal, water) — None."""
    K = knowledge(); GR = K["soils"].get(ground, K["soils"]["ground"])
    if not GR.get("dust"): return None
    earth = (GR.get("ground") or 0) * min(1.0, W / 7.0)
    return [a * (1 - earth) + b * earth for a, b in zip(GR["dust"], K["soils"]["ground"]["dust"])]


def explosion(e, t, cam, ctx, sc=None):
    """Objects of explosion e in frame t (s) for camera cam. ctx: ev, night, soil, ground(x, y) → z, fps. None — no knowledge
    or asset."""
    sc = sc or bpy.context.scene; K = knowledge()
    if not K or "c" not in e: return None
    dt = t - float(e["at"])
    if dt < 0: return []
    vid, V, W, h = norm_event(e); M = K["scale"]; sila = float(e.get("strength", 1.0))
    if V["fire"]["asset"] == "combustion":                               # blaze: only burning, no explosion
        if asset("combustion", "low") is None: return None
        out, info = [], {"kind": vid, "layers": []}; q = 2.0 ** (-float(ctx.get("ev", 0.0))) * (M["at_night"] if ctx.get("night") else 1.0)
        _burning(sc, e, dt, Vector(e["c"]) + Vector((0, 0, h)), float(V["combustion"]["Q_kw"]) * sila, float(V["combustion"]["dur"]), q,   # "height" —
                 float(ctx.get("ev", 0.0)), cam, 0.7, out, info, ctx=ctx)   # the fire patch is above the ground (wall, roof), as for explosions; it used to be always on the ground
        LOG.append(info); return out
    body = asset(V["fire"]["asset"], "high")
    if body is None: return None
    rng = random.Random(int(e.get("seed", 0)) * 7919 + int(float(e["at"]) * 1000)); rot = rng.uniform(0, 2 * math.pi); mirror = rng.random() < 0.5
    c = Vector(e["c"]) + Vector((0, 0, h)); g = ctx.get("soil", "ground"); GR = K["soils"].get(g, K["soils"]["ground"])
    q = 2.0 ** (-float(ctx.get("ev", 0.0))) * (M["at_night"] if ctx.get("night") else 1.0)    # screen strength → into the frame
    s = (W / float(body.get("W", body.get("M", 1.0)))) ** M["size"]
    px = px_of(body["height"] * s, c, cam); lvl, U = level_of(px)
    if ctx.get("screen_level"): lvl, U = ctx["screen_level"], K["levels"][ctx["screen_level"]]   # the "explosions" step in step-by-step assembly: the level by a key (by default — by the screen size)
    info = {"kind": vid, "W": round(W, 3), "s": round(s, 3), "px": round(px), "level": lvl, "layers": []}
    if not (M["limit"][0] <= s <= M["limit"][1]): info["warning"] = f"s = {s:.2f} is outside the limit of asset {V['fire']['asset']}"
    out, Fl = [], V["flash"]; tau = Fl["dur"] * sila ** (1 / 3)
    if dt < 6 * tau:                                                  # flash: at R three times brighter than the key light (on screen)
        R = 4.0 * W ** (1 / 3); P = 4 * math.pi ** 2 * R * R * FLASH0 * Fl["strength"] * q * math.exp(-dt / tau)
        tint = tint_of(dict(V["fire"], **({"tint": e["tint"]} if e.get("tint") else {})))
        out.append(_lamp("fx_flash", c + Vector((0, 0, 0.6 * W ** (1 / 3))), P, Fl["K"], 0.3 * W ** (1 / 3), U["lamp_shadow"], sc, tint)); info["layers"].append("flash")
    mode = str(ctx.get("cards", CARD_MODE))                       # a card instead of a volume (bl_fx_cards.py): auto — far and beyond, medium —
    if (mode == "all" or lvl in CARD_LEVELS.get(mode, ())) and not e.get("tint") and card_set(vid) is not None:
        smoke = V["smoke"]; fade = 1.0 if dt < smoke["dur"] * sila ** (1 / 6) else math.exp(-(dt - smoke["dur"] * sila ** (1 / 6)) / 2.0)
        o = _card(sc, e, vid, dt, c, cam, ctx, sila, q, fade, rng)
        if o:
            out.append(o); info["layers"].append("card"); Ah = asset(V["fire"]["asset"], "high"); T1 = float(Ah.get("early_s", 0.3))
            ta = asset_time(dt, s, T1); _lean(sc, o, float(e["c"][2]), h + _smoke_top(Ah, ta, s), _puff(ctx, dt, T1 * s))
            f = min(max(int(round(Ah["frame_start"] + ta * Ah["fps"])), 1), int(Ah["n_frames"])); st = (Ah.get("frames") or [None] * f)[f - 1]
            lamp = _inner(sc, V, st, s, rot, mirror, c, q, U, V["fire"])   # glow — as for the volume: the fire's light on the ground and its neighbors
            if lamp: out.append(lamp); info["layers"].append("glow")
    elif U["body"] is not None:
        if ctx.get("level"): U = dict(U, body=ctx["level"])         # asset selection on the stand: the asset level is forced
        A = asset(V["fire"]["asset"], U["body"]); smoke = V["smoke"]
        fade = 1.0 if dt < smoke["dur"] * sila ** (1 / 6) else math.exp(-(dt - smoke["dur"] * sila ** (1 / 6)) / 2.0)
        fire = dict(V["fire"], tint=e["tint"]) if e.get("tint") else V["fire"]   # the magic color belongs to the event (blue, green…)
        mat = volume_material(f"{vid}_{A['level']}" + (f"_{'_'.join(str(x) for x in e['tint'])}" if e.get("tint") else ""), A["sfx"], smoke, fire)
        k_ms = MS0 * 2.0 ** (-float(ctx.get("ev", 0.0)))              # without the at_night factor: scattering comes from the key light, not from the fire
        fk = FIRE0 * float(V["fire"]["strength"]) * q * (FIRE_HI if A["level"] == "high" else FIRE_LO) * (0.45 if tint_of(fire) else 1.0)   # magic is dimmer —
                                                                       # otherwise AgX bleaches the color
        o, st = _body(sc, "fx_body", A, asset_time(dt, s, float(A.get("early_s", 0.3))), c, s, rot, mirror, mat, fade, fk, k_ms)
        if o:
            out.append(o); info["layers"].append("body"); T1 = float(A.get("early_s", 0.3))
            _lean(sc, o, float(e["c"][2]), h + _smoke_top(A, asset_time(dt, s, T1), s), _puff(ctx, dt, T1 * s))
        lamp = _inner(sc, V, st, s, rot, mirror, c, q, U, fire)
        if lamp: out.append(lamp); info["layers"].append("glow")
        B = asset("ejecta", U["body"]) if h < 0.5 and V.get("soil", 0) > 0 and GR.get("dust") else None
        if B:                                                          # ground ejecta and a dust ring in the soil color
            se = (W / float(B["W"])) ** M["size"]; earth = GR.get("ground", 0) * min(1.0, W / 7.0)
            dust = [a * (1 - earth) + b * earth for a, b in zip(GR["dust"], K["soils"]["ground"]["dust"])]
            dm = volume_material(f"dust_{g}_{round(earth, 2)}_{B['level']}", B["sfx"], {"color": dust, "density": V["soil"] * 1.2, "anisotropy": 0.2})   # denser: the soil must read
            ob, _ = _body(sc, "fx_dust", B, asset_time(dt, se, float(B.get("early_s", 0.5))), Vector(e["c"]), se, rot + 1.1, not mirror, dm, fade, 0.0, k_ms)
            if ob:
                out.append(ob); info["layers"].append("soil"); T1 = float(B.get("early_s", 0.5))
                _lean(sc, ob, float(e["c"][2]), _smoke_top(B, asset_time(dt, se, T1), se), _puff(ctx, dt, T1 * se))
    if V.get("combustion") and asset("combustion", "low"):                # after the fireball, the machinery burns: from the end of the fire phase
        B_ = V["combustion"]; t0 = 0.03 * s; Qb = float(B_["Q_kw"]) * sila   # spilled fuel ignites with the ball: the base burns
                                                                       # from the first frames (a 0.2 s ramp-up) — the ball does not hang above the ground
        if B_.get("strip"):                                           # napalm: a chain of fire patches along the strip, the fire runs along it (0.08 s per patch)
            Lp, n_ = B_["strip"]; tgt = e.get("to")
            d = (Vector((tgt[0], tgt[1], 0)) - Vector((c.x, c.y, 0))).normalized() if tgt else Vector((math.cos(rot), math.sin(rot), 0))
            for i in range(int(n_)):
                p_ = Vector(e["c"]) + d * Lp * (i + 0.5) / n_ * rng.uniform(0.85, 1.1) + Vector((rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), 0))
                if ctx.get("ground"): p_.z = ctx["ground"](p_.x, p_.y)
                _burning(sc, e, dt - t0 * 0.5 - 0.08 * i, p_, Qb * rng.uniform(0.6, 1.3), float(B_["dur"]), q, float(ctx.get("ev", 0.0)), cam,
                         rot + 1.7 * i, out, info, phase=0.37 * i, name=f"fx_burn_{i}_", ctx=ctx)
        else:
            _burning(sc, e, dt - t0, Vector(e["c"]), Qb, float(B_["dur"]), q, float(ctx.get("ev", 0.0)), cam, rot + 0.4, out, info, ramp=0.2, ctx=ctx)
    gz = ctx.get("ground") or (lambda x, y: float(e["c"][2]))
    n = int(V.get("clods", 0) * U["clods"]) if h < 0.5 and GR.get("clods") else 0
    if n and dt < 4.0:                                                 # clods: the ejection speed ∝ W^(1/6) (a crater in the gravity regime)
        ob = _ballistic(sc, "fx_clumps", c, dt, n, 9.0 * W ** (1 / 6), 55, 0.04 * W ** (1 / 3), GR["clods"], 0.0, gz, rng, ctx)
        if ob: out.append(ob); info["layers"].append("clods")
    n = int(V.get("sparks", 0) * U["sparks"] * (GR.get("sparks") or 1.0))
    if n and dt < max(V.get("sparks_life", (0.15, 0.45))):
        tint = tint_of(dict(V["fire"], **({"tint": e["tint"]} if e.get("tint") else {})))   # magic embers take its colors
        ob = _ballistic(sc, "fx_sparks" + ("_" + "_".join(f"{x:.2f}" for x in tint) if tint else ""), c + Vector((0, 0, 0.3)), dt, n,
                        float(V.get("sparks_v", 38.0)), 80, 0.012, tuple(tint) if tint else (1.0, 0.55, 0.2), 6.0 * q, gz, rng, ctx,
                        life=tuple(V.get("sparks_life", (0.15, 0.45))))       # fragments are fast and short; embers of the fireball are slow
        if ob: out.append(ob); info["layers"].append("sparks")
    LOG.append(info); FRAME.append(lvl)
    return out


def _ballistic(sc, name, c, dt, n, v0, spread_deg, size, rgb, emit, gz, rng, ctx, life=None):
    """n bodies from c: directions in an upward cone (half-angle spread), speed v0 × U(0.4…1), g = 9.81; the fallen ones lie
    (clods) or fade (sparks, lifetime life). A streak along the velocity = speed × exposure (half a frame) — motion blur
    without animation."""
    sh = 0.5 / float(ctx.get("fps", 24)); bm = bmesh.new(); k = 0
    for _ in range(n):
        th = math.radians(spread_deg) * math.sqrt(rng.random()); ph = rng.uniform(0, 2 * math.pi); sp = v0 * rng.uniform(0.4, 1.0)
        v = Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th))) * sp
        lf = rng.uniform(*life) if life else None; r = size * rng.uniform(0.5, 1.6)
        if lf is not None and dt > lf: continue
        p = c + v * dt + Vector((0, 0, -4.905 * dt * dt)); vel = v + Vector((0, 0, -9.81 * dt)); z0 = gz(p.x, p.y)
        if p.z < z0 + r:
            if lf is not None: continue
            p.z, vel = z0 + r * 0.6, Vector((0, 0, 0))
        d = vel.normalized() if vel.length > 1e-3 else Vector((0, 0, 1)); L = max(r * 2, vel.length * sh); qd = d.to_track_quat("Z", "Y")
        if lf is None:                                                 # a clod of earth is faceted and uneven (smooth spheres at 20 m read as
            ax = [r * rng.uniform(0.6, 1.4) for _ in range(3)]; rot = Euler((rng.uniform(0, 6.3), rng.uniform(0, 6.3), rng.uniform(0, 6.3)))   # "potatoes")
            for vv in bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)["verts"]:
                co = vv.co * rng.uniform(0.65, 1.25); co = Vector((co.x * ax[0], co.y * ax[1], co.z * ax[2])); co.rotate(rot)
                co = Vector((co.x, co.y, co.z * max(1.0, L / (2 * r)))) if vel.length * sh > 2 * r else co   # motion streak along the velocity
                co.rotate(qd); vv.co = p + co
        else:
            for vv in bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)["verts"]:   # a spark is a streak along the velocity
                co = Vector((vv.co.x * r, vv.co.y * r, vv.co.z * L * 0.5)); co.rotate(qd); vv.co = p + co
        k += 1
    if not k: bm.free(); return None
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(_surface(name, rgb, emit > 0))
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o["fx_fire"] = emit
    return o


def scorch(e, dt, sc, gz, name="fx_scorch"):
    """Scorch on the ground: a soot patch following the relief gz(x, y) → z — the radius is the kind's "scorch" × W^(1/3), a
    ragged edge (noise), denser toward the center; it grows with the fire (explosive — 0.15 s, fuel and fireball — the
    kind's fire phase). A burst higher than 2 m or a kind without scorch — None."""
    vid, V, W, h = norm_event(e)
    if dt < 0 or h > 2.0 or not V.get("scorch"): return None
    R = float(V["scorch"]) * W ** (1 / 3); c = Vector(e["c"])
    m = MAT.get("scorch")
    if m is None:                                                      # alpha: 1 − smoothstep(0.55…1) over the radius + noise × 0.5; strength — fx_scorch
        m = bpy.data.materials.new("fx_scorch_soft"); m.surface_render_method = "DITHERED"; nt = m.node_tree; b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.045, 0.04, 0.035, 1.0); b.inputs["Roughness"].default_value = 1.0
        tc = nt.nodes.new("ShaderNodeTexCoord"); sp = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sp.inputs[0])
        xy = nt.nodes.new("ShaderNodeCombineXYZ"); nt.links.new(sp.outputs["X"], xy.inputs["X"]); nt.links.new(sp.outputs["Y"], xy.inputs["Y"])
        ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; nt.links.new(xy.outputs[0], ln.inputs[0]); r = ln.outputs["Value"]
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 2.5; nz.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        rr = _math(nt, "ADD", r, _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", nz.outputs["Fac"], v=0.5), v=0.6))
        st = nt.nodes.new("ShaderNodeMapRange"); st.interpolation_type = "SMOOTHSTEP"; st.inputs["From Min"].default_value, st.inputs["From Max"].default_value = 0.55, 1.0
        st.inputs["To Min"].default_value, st.inputs["To Max"].default_value = 0.9, 0.0; nt.links.new(rr, st.inputs["Value"])
        nt.links.new(_math(nt, "MULTIPLY", st.outputs["Result"], _attr(nt, "fx_scorch", "OBJECT")), b.inputs["Alpha"]); MAT["scorch"] = m
    seg, rings = 32, 6; Vt = [(0.0, 0.0, gz(c.x, c.y) - c.z + 0.03)]; F = []
    for j in range(1, rings + 1):                                      # a unit-radius circle by rings; the object scale is R along x, y
        for i in range(seg):
            a = 2 * math.pi * i / seg; x, y = math.cos(a) * j / rings * 1.15, math.sin(a) * j / rings * 1.15
            Vt.append((x, y, gz(c.x + x * R, c.y + y * R) - c.z + 0.03))
    for i in range(seg): F.append((0, 1 + i, 1 + (i + 1) % seg))
    for j in range(1, rings):
        b0, b1 = 1 + (j - 1) * seg, 1 + j * seg
        for i in range(seg): F.append((b0 + i, b1 + i, b1 + (i + 1) % seg, b0 + (i + 1) % seg))
    me = bpy.data.meshes.new(name); me.from_pydata(Vt, [], F); me.materials.append(m)
    o = bpy.data.objects.new(name, me); o.location = c; o.scale = (R, R, 1.0); sc.collection.objects.link(o)
    o["fx_scorch"] = scorch_grow(e, dt); return o


def scorch_grow(e, dt):
    """Scorch strength at moment dt (0…1): soot settles while it burns — over the kind's fire phase (no shorter than 0.15 s)."""
    vid, V, W, h = norm_event(e)
    return 0.0 if dt < 0 else min(1.0, dt / max(0.15, float(V["fire"].get("dur", 0.15)) * float(e.get("strength", 1.0)) ** (1 / 3)))


def glow_k(e):
    """Share of the explosion glow in the light node's haze (take: the node's events, the peak by the explosion size): the
    kind's flash relative to the explosive's flash, no more than 1. Fuel and napalm have a weak flash — the light comes from
    the fireball (a lamp inside), otherwise the first frame at night is white."""
    vid, V, W, h = norm_event(e)
    return min(1.0, float(V.get("flash", {}).get("strength", 1.0)) / float(knowledge()["kinds"]["grenade"]["flash"]["strength"]))


def frame_settings(sc):
    """EEVEE volume settings for a frame: for an explosion "up close" — tile 4, 64 layers, volumetric shadows. → a function
    that restores the previous settings."""
    ee = sc.eevee; old = (ee.volumetric_tile_size, ee.volumetric_samples, ee.use_volumetric_shadows)
    if "close" in FRAME: ee.volumetric_tile_size, ee.volumetric_samples, ee.use_volumetric_shadows = "4", max(64, old[1]), True
    FRAME.clear()

    def restore():
        ee.volumetric_tile_size, ee.volumetric_samples, ee.use_volumetric_shadows = old
    return restore
