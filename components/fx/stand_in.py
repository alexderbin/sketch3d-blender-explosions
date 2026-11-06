"""Explosion stand-ins for the sketch — the look knob stand_in of the "explosions" step (the sketch stage).
The same event, the same similarity law and the same bake summary as the full explosion (bl_fx), but instead of volumes,
cards and lamps — an object per layer, keyed per take frame (visibility, position, scale; in wind — the cloud shear or
the column lean):
  fire (flash and fireball) — a ball, sk_kind fx;  body smoke — an ellipsoid, smoke;  ground ejecta — a dome, dust (the
  dust color of the place's soil);
  burning (a blaze, machinery after the ball, a napalm strip) — a flame cone (fx) and a smoke column above it (smoke),
  growing from below with a front.
The layer size at moment t is the isosurface frame of the high-level asset (the bake summary "frames": center, largest
half-size, top; density 0.05, fire 0.15) × s = (W / W_asset)^(1/3) at the asset time asset_time (early phase × s, late
phase × √s); the center — with the body's rotation and mirroring by the event seed, as in bl_fx._body; a cloud in wind —
the drift a + b·(z − z0) (bl_fx._puff, _lean), a burning column — a lean from the base. Fire and body smoke are not drawn
together: while the asset frame has fire — a ball, afterwards — smoke (the asset's smoke contains the fire, and an opaque
ellipsoid would hide the ball). A layer is visible while its fade (the kind's smoke duration, the hold after the last
asset frame, the burning ramp-up) is not below FADE_MIN. Burning: the flame — the top of the fire of the asset loop × s,
the base — the asset's fire patch; the column — up to the front L + vf·t, no higher than the asset cut, widening upward
by PLUME_K.
The formulas are the same as in bl_fx (asset_time, norm_event, wind_at, _puff, _lean, _burning): if you change the law
there, change it here too; the stand bench/stand_in_check.py checks the stand-in against the law (it takes asset_time
and norm_event from the bl_fx source).
Python without Blender: layers(e, t, ctx) — the layers of an event at moment t; box(layer) — the frame of the built
stand-in. build(...) — objects (Blender)."""
import json, math, os, random

import core.paths as _core_paths

FXDIR = os.path.join(_core_paths.ROOT, "library", "fx")
FADE_MIN = 0.1              # a layer is visible while the fade is not below this: at 0.1 the isosurface edge is still a third opaque and the core is dense
Z0_ROUGH = 0.05             # = bl_fx.Z0_ROUGH: terrain roughness length, m (the wind near the ground is a logarithm of U10)
LEAN_MAX = 60.0             # = bl_fx.LEAN_MAX: a burning column is no steeper than 60° from vertical
PLUME_K = 0.25              # a burning column widens upward by 0.25 m per meter (the burning card frame: 5.3 × 8.4 m at Q = 500 kW)
FIRE_RGB = (0.95, 0.55, 0.15)   # fire is warm (like the fx class in core/blender/stand_in.py)
_K = None


def knowledge():
    """Knowledge and bake summaries (library/fx/explosions.json, as in bl_fx); none — {}."""
    global _K
    if _K is None:
        p = os.path.join(FXDIR, "explosions.json")
        _K = json.load(open(p)) if os.path.exists(p) else {}
    return _K


def asset(K, name, level):
    """Summary of the baked asset of level level, otherwise of another baked one (as bl_fx.asset); none — None."""
    for lv in [level] + [x for x in ("high", "low") if x != level]:
        m = (K.get("baked") or {}).get(name, {}).get(lv)
        if m and os.path.isdir(os.path.join(FXDIR, name, lv, "cache")): return dict(m, level=lv)
    return None


def norm_event(K, e):
    """Event → kind, the kind's knowledge, W (kg of TNT, for fuel — kg of fuel), height (as bl_fx.norm_event)."""
    V_ = K["kinds"]; vid = e.get("kind") if e.get("kind") in V_ else "grenade"; V = V_[vid]
    return vid, V, float(V.get("W", V.get("M", 1.0))) * float(e.get("strength", 1.0)), float(e.get("height", 0.0))


def asset_time(dt, s, T1):
    """Event time → asset time: early phase × s, late phase × s^0.5 (as bl_fx.asset_time)."""
    return dt / s if dt <= T1 * s else T1 + (dt - T1 * s) / math.sqrt(s)


def wind_at(w, z):
    """Wind at height z above the ground, m/s (ux, uy): w is m/s at 10 m, the profile is logarithmic (as bl_fx.wind_at); calm —
    None."""
    if not w or len(w) < 2 or not (float(w[0]) or float(w[1])): return None
    k = math.log(max(z, Z0_ROUGH * math.e) / Z0_ROUGH) / math.log(10.0 / Z0_ROUGH)
    return float(w[0]) * k, float(w[1]) * k


def dust_rgb(K, ground, W):
    """Dust color of the ejecta on soil ground at strength W (as bl_fx.dust_rgb); no dust — None."""
    GR = K["soils"].get(ground, K["soils"]["ground"])
    if not GR.get("dust"): return None
    earth = (GR.get("ground") or 0) * min(1.0, W / 7.0)
    return tuple(a * (1 - earth) + b * earth for a, b in zip(GR["dust"], K["soils"]["ground"]["dust"]))


def _row(A, ta):
    """The summary row of the asset frame at its time ta and the hold after the last frame, s (as bl_fx._body)."""
    f = int(round(A["frame_start"] + ta * A["fps"])); hold = max(0.0, (f - A["n_frames"]) / A["fps"]); f = min(max(f, 1), int(A["n_frames"]))
    return (A.get("frames") or [None] * f)[f - 1] or {}, hold


def _at(c, p, s, rot, mirror):
    """Asset point p (m, from the explosion center) → world: scale s, mirror along x, rotation rot about the vertical,
    translation to c (as bl_fx._body)."""
    x, y = (-p[0] if mirror else p[0]) * s, p[1] * s; cr, sr = math.cos(rot), math.sin(rot)
    return [c[0] + cr * x - sr * y, c[1] + sr * x + cr * y, c[2] + p[2] * s]


def _cloud_wind(w, dt, tm, H):
    """Cloud drift in wind — (a, b): the shift at world height z is a + b·(z − z0), z0 is the event's ground (as bl_fx._puff
    and _lean without the base: d(z) = U(z)·t_ef at heights 0.15 H and 0.85 H, along a straight line); calm — None."""
    if not w or H <= 0: return None
    te = dt - tm * (1.0 - math.exp(-dt / max(tm, 1e-3))); za, zb = 0.15 * H, 0.85 * H
    ua, ub = wind_at(w, za), wind_at(w, zb)
    if ua is None: return None
    b = ((ub[0] - ua[0]) * te / (zb - za), (ub[1] - ua[1]) * te / (zb - za))
    return (ua[0] * te - b[0] * za, ua[1] * te - b[1] * za), b


_CARD = {}


def card_half(vid):
    """Half-width of the kind's card frame at strength 1, m (library/fx/cards/<kind>/card.json: shot as a render of the high
    asset); none — None."""
    if vid not in _CARD:
        p = os.path.join(FXDIR, "cards", vid, "card.json")
        _CARD[vid] = float(json.load(open(p))["width_m"]) / 2 if os.path.exists(p) else None
    return _CARD[vid]


def _cloud(layer, kind, shape, st, s, c, rot, mirror, rgb, fade, ab, z0, cap=None):
    """A cloud layer from a summary row st (center, largest half-size, top): the isosurface frame × s; an ellipsoid is
    inscribed in the frame, a dome sits with its base on the frame's bottom. A puff stretched upward (the largest half-size
    is the height) has no width in the summary: the radius is no more than cap (the half-width of the kind's card frame).
    Wind ab — the base drifts, the shape shears by b per meter above the base."""
    cx, cy, cz = _at(c, st["center"], s, rot, mirror); hz = max(0.025, (float(st["top"]) - float(st["center"][2])) * s); r = float(st["radius"]) * s
    if cap and float(st["top"]) - float(st["center"][2]) >= 0.98 * float(st["radius"]): r = min(r, cap)
    rec = {"layer": layer, "kind": kind, "shape": shape, "base": [cx, cy, cz - hz], "r": max(0.05, r), "h": 2 * hz,
           "rgb": tuple(rgb), "fade": round(fade, 3)}
    if ab:
        (ax, ay), (bx, by) = ab; k = rec["base"][2] - z0
        rec["base"][0] += ax + bx * k; rec["base"][1] += ay + by * k; rec["shear"] = [bx, by]
    return rec


_FLAME = {}


def _flame_top(A):
    """Top of the fire of the burning asset's loop, m (the mean over the loop frames of the summary)."""
    key = (A.get("level"), A.get("n_frames"))
    if key not in _FLAME:
        L0, L1 = A.get("loop") or (1, A["n_frames"]); rows = (A.get("frames") or [])[int(L0) - 1:int(L1)]
        tops = [float(r["fire"]["top"]) for r in rows if r and r.get("fire")]
        _FLAME[key] = sum(tops) / len(tops) if tops else 0.235 * 500 ** 0.4 - 1.02
    return _FLAME[key]


def _burn(tag, db, base, Q, dur, ramp, K, ctx):
    """Burning (as bl_fx._burning): size ∝ Q^(2/5) from the "combustion" asset, the column front vf = 0.39·Q^(1/3) m/s; db —
    time since the start of burning. The flame — a cone on the fire patch, the column — above the flame up to the front; in
    wind — a lean from the base. → [flame layer, column layer]."""
    probe, A = asset(K, "combustion", "low"), asset(K, "combustion", "high")
    if probe is None or A is None or db < 0: return []
    s = (Q / float(probe.get("Q_kw", 500))) ** 0.4; L = max(0.3, 0.235 * Q ** 0.4 - 1.02 * 1.0 * s); vf = 0.39 * Q ** (1 / 3)
    f = min(1.0, db / ramp) * (1.0 if db < dur else math.exp(-(db - dur) / 3.0))
    if f < FADE_MIN: return []
    hf = _flame_top(A) * s; r0 = float(K["assets"]["combustion"]["hotspot"]["radius"]) * s
    Hm = float((A.get("cut") or [0.0, A["height"]])[1]) * s; Hc = min(L + vf * db, Hm)   # the column goes up to the front, no higher than the asset cut
    tilt, n = None, (0.0, 0.0, 1.0)
    H, w = L + vf * db, ctx.get("wind")                                # the lean — as bl_fx._lean with the base: the smoke at height z was emitted z / vf ago
    if wind_at(w, 0.15 * H) is not None:
        u = wind_at(w, 0.85 * H); t_ = min(0.85 * H / vf, db); d = (u[0] * t_, u[1] * t_); dl = math.hypot(*d)
        if dl > 1e-6:
            th = min(math.atan2(dl, 0.85 * H), math.radians(LEAN_MAX)); tilt = [d[0] / dl, d[1] / dl, th]
            n = (math.sin(th) * d[0] / dl, math.sin(th) * d[1] / dl, math.cos(th))
    out = [{"layer": "flame" + tag, "kind": "fx", "shape": "cone", "base": list(base), "r": r0, "h": hf, "tilt": tilt, "rgb": FIRE_RGB,
            "fade": round(f, 3)}]
    if Hc > hf + 0.1:
        rt = r0 + PLUME_K * Hc
        out.append({"layer": "column" + tag, "kind": "smoke", "shape": "frustum", "base": [base[i] + hf * n[i] for i in range(3)], "r": rt,
                    "h": Hc - hf, "rho": (r0 + PLUME_K * hf) / (r0 + PLUME_K * Hm), "tilt": tilt,
                    "rgb": tuple(K["kinds"]["blaze"]["smoke"]["color"]), "fade": round(f, 3)})
    return out


def layers(e, t, ctx):
    """Layers of event e at moment t (s, take time): [{layer, kind (fx | smoke | dust), shape (ellipsoid | dome | cone |
    frustum), base — the bottom of the shape along the axis (m, world), r — radius (the top one for a column), h — height,
    rho — bottom-to-top ratio for a column, shear — [bx, by] shift per meter of height (a cloud in wind), tilt — [dx, dy,
    angle] lean from the base (burning), rgb, fade}]. Before the event — []; no knowledge or asset — None (as
    bl_fx.explosion: the event is skipped). ctx: K (knowledge), wind [ux, uy] m/s at 10 m, ground — soil, z_at(x, y) — the
    ground (napalm strip points)."""
    K = ctx.get("K") or knowledge()
    if not K or "c" not in e: return None
    dt = t - float(e["at"])
    if dt < 0: return []
    vid, V, W, h = norm_event(K, e); M = K["scale"]; sila = float(e.get("strength", 1.0))
    c0 = [float(x) for x in e["c"]]; c = [c0[0], c0[1], c0[2] + h]
    if V["fire"]["asset"] == "combustion":                               # blaze: burning only
        if asset(K, "combustion", "low") is None: return None
        return _burn("", dt, c, float(V["combustion"]["Q_kw"]) * sila, float(V["combustion"]["dur"]), 0.5, K, ctx)
    body = asset(K, V["fire"]["asset"], "high")
    if body is None: return None
    rng = random.Random(int(e.get("seed", 0)) * 7919 + int(float(e["at"]) * 1000)); rot = rng.uniform(0, 2 * math.pi); mirror = rng.random() < 0.5
    s = (W / float(body.get("W", body.get("M", 1.0)))) ** M["size"]; w = ctx.get("wind")
    dl = float(V["smoke"]["dur"]) * sila ** (1 / 6); fade = 1.0 if dt < dl else math.exp(-(dt - dl) / 2.0)
    T1 = float(body.get("early_s", 0.3)); row, hold = _row(body, asset_time(dt, s, T1)); fb = fade * math.exp(-hold / 1.5)
    ab = _cloud_wind(w, dt, T1 * s, h + float((row.get("smoke") or {}).get("top", body.get("height", 5.0))) * s)
    out, cap = [], (card_half(vid) or 0.0) * sila ** (1 / 3) or None    # the card frame is by the law from strength 1
    if fb >= FADE_MIN and (row.get("fire") or row.get("smoke")):
        if row.get("fire"):
            tint = e.get("tint") or V["fire"].get("tint")      # magic takes its colors (a normalized tint, as bl_fx.tint_of)
            rgb = tuple(x / max(tint) for x in tint) if tint and list(tint) != [1.0, 1.0, 1.0] else FIRE_RGB
            out.append(_cloud("fire", "fx", "ellipsoid", row["fire"], s, c, rot, mirror, rgb, fb, ab, c0[2], cap))
        else:
            out.append(_cloud("smoke", "smoke", "ellipsoid", row["smoke"], s, c, rot, mirror, V["smoke"]["color"], fb, ab, c0[2], cap))
    GR = K["soils"].get(ctx.get("ground") or "ground", K["soils"]["ground"])
    B = asset(K, "ejecta", "high") if h < 0.5 and V.get("soil", 0) > 0 and GR.get("dust") else None
    if B:                                                              # ground ejecta and the dust ring: rotation +1.1 and the mirror reversed, as in bl_fx
        se = (W / float(B["W"])) ** M["size"]; Tb = float(B.get("early_s", 0.5)); rb, hb = _row(B, asset_time(dt, se, Tb)); fd = fade * math.exp(-hb / 1.5)
        if rb.get("smoke") and fd >= FADE_MIN:
            abd = _cloud_wind(w, dt, Tb * se, float(rb["smoke"]["top"]) * se)
            out.append(_cloud("dust", "dust", "dome", rb["smoke"], se, c0, rot + 1.1, not mirror, dust_rgb(K, ctx.get("ground") or "ground", W),
                              fd, abd, c0[2]))
    if V.get("combustion") and asset(K, "combustion", "low"):            # after the fireball — burning (machinery, a napalm strip)
        Bg = V["combustion"]; t0 = 0.03 * s; Qb = float(Bg["Q_kw"]) * sila
        if Bg.get("strip"):                                           # the strip points use the same formulas and seed (without a body card in the queue)
            Lp, n_ = Bg["strip"]; tgt = e.get("to"); z_at = ctx.get("z_at")
            if tgt:
                dx, dy = float(tgt[0]) - c[0], float(tgt[1]) - c[1]; dn = math.hypot(dx, dy) or 1.0; d = (dx / dn, dy / dn)
            else: d = (math.cos(rot), math.sin(rot))
            for i in range(int(n_)):
                k_ = Lp * (i + 0.5) / n_ * rng.uniform(0.85, 1.1); p = [c0[0] + d[0] * k_ + rng.uniform(-0.9, 0.9), c0[1] + d[1] * k_ + rng.uniform(-0.9, 0.9), c0[2]]
                if z_at: p[2] = z_at(p[0], p[1])
                out += _burn(str(i), dt - t0 * 0.5 - 0.08 * i, p, Qb * rng.uniform(0.6, 1.3), float(Bg["dur"]), 0.5, K, ctx)
        else:
            out += _burn("", dt - t0, c0, Qb, float(Bg["dur"]), 0.2, K, ctx)
    return out


def box(rec):
    """Frame of a layer (min, max), m — as for the built stand-in (exact shapes: the 24-sided mesh touches the frame on the
    axes; with a shear or lean the polygon is narrower than the circle by at most 1 %). An ellipsoid with shear b:
    half-size √(r² + (b·h/2)²); a dome — on the shear side √(r² + (b·h)²), on the other side r at the base; a cone and a
    column — the envelope of two rims tilted by the angle tilt."""
    b0, r, h = rec["base"], rec["r"], rec["h"]
    if rec["shape"] in ("ellipsoid", "dome"):
        sh = rec.get("shear") or (0.0, 0.0); lo, hi = [0.0] * 3, [0.0] * 3
        for i in (0, 1):
            if rec["shape"] == "ellipsoid":
                cc, ext = b0[i] + sh[i] * h / 2, math.hypot(r, sh[i] * h / 2); lo[i], hi[i] = cc - ext, cc + ext
            else:
                ext = math.hypot(r, sh[i] * h); lo[i], hi[i] = (b0[i] - r, b0[i] + ext) if sh[i] >= 0 else (b0[i] - ext, b0[i] + r)
        lo[2], hi[2] = b0[2], b0[2] + h
        return lo, hi
    tl = rec.get("tilt"); n = (math.sin(tl[2]) * tl[0], math.sin(tl[2]) * tl[1], math.cos(tl[2])) if tl else (0.0, 0.0, 1.0)
    rb, rt = (r, 0.0) if rec["shape"] == "cone" else (rec["rho"] * r, r)
    top = [b0[i] + h * n[i] for i in range(3)]; q = [math.sqrt(max(0.0, 1.0 - n[i] ** 2)) for i in range(3)]
    return ([min(b0[i] - rb * q[i], top[i] - rt * q[i]) for i in range(3)], [max(b0[i] + rb * q[i], top[i] + rt * q[i]) for i in range(3)])


def plan(events, fps, nf, ctx, seed0=0):
    """Layers of all events over the take frames 1…nf (frame k is moment (k − 1) / fps), like the loop of the "explosions" step
    (an event frame starts from at): → ({(event, layer): [(frame, layer)]}, skipped events, {event: first frame})."""
    tracks, skipped, first = {}, [], {}
    for i, e in enumerate(events):
        ee = dict(e, seed=i + seed0)
        for k in range(1, nf + 1):
            t = (k - 1) / fps
            if t < float(e["at"]) - 1e-9: continue
            L = layers(ee, t, ctx)
            if L is None: skipped.append(i); break
            first.setdefault(i, k)
            for rec in L: tracks.setdefault((i, rec["layer"]), []).append((k, rec))
    return tracks, skipped, first


def _unit(SI, shape, rho=1.0, n=24):
    """A unit-size shape (radius 1, height 1, bottom at z = 0): an ellipsoid (the equator is on a ring — the frame is exact), a
    dome, a cone, a column; n sides is a multiple of 4 — vertices on the axes, the frame in x and y is exact."""
    m = 8
    if shape == "ellipsoid":
        return SI.lathe([(0.0, 0.0)] + [(math.sin(math.pi * j / m), (1 - math.cos(math.pi * j / m)) / 2) for j in range(1, m)] + [(0.0, 1.0)], n)
    if shape == "dome":
        return SI.lathe([(0.0, 0.0)] + [(math.cos(math.pi / 2 * j / 6), math.sin(math.pi / 2 * j / 6)) for j in range(6)] + [(0.0, 1.0)], n)
    return SI.cone(1.0, 1.0, n) if shape == "cone" else SI.cone(rho, 1.0, n, r_top=1.0)


def build(sc, coll, events, fps, nf, ctx, seed0=0, samples=8):
    """Event stand-ins in an open scene: an object per event layer (sk_stand_in = 1, sk_kind fx | smoke | dust, sk_id
    "blast<i>.<layer>", sk_layer time), keys per take frame (scene frame = take frame): visibility, position, scale; a cloud
    in wind — a "shear" shape key (x += z, the object is rotated downwind), burning — a rotation from the base. Check: the
    mesh frame in samples frames against box(layer). → the step statistics."""
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector
    from core.blender import stand_in as SI
    ctx = dict(ctx, K=ctx.get("K") or knowledge())
    tracks, skipped, first = plan(events, fps, nf, ctx, seed0)
    made, frames, per_layer = [], set(), {}
    for (i, name), recs in sorted(tracks.items()):
        r0 = recs[0][1]; sid = f"blast{i}.{name}"
        ob = SI.build(f"fx_stand_{i}_{name}", [SI.place(_unit(SI, r0["shape"], r0.get("rho", 1.0)), rgb=r0["rgb"], smooth=r0["shape"] in ("ellipsoid", "dome"))],
                      coll, kind=r0["kind"], sk_id=sid)
        ob["sk_layer"] = "time"
        kb = None
        sh = next((r.get("shear") for _, r in recs if r.get("shear") and math.hypot(*r["shear"]) > 1e-9), None)
        if sh:                                                         # cloud shear in wind: a shape key x += z (local axes), the object is oriented downwind
            ob.rotation_euler = (0.0, 0.0, math.atan2(sh[1], sh[0]))
            ob.shape_key_add(name="Basis", from_mix=False); kb = ob.shape_key_add(name="shear", from_mix=False)
            co = np.empty(len(ob.data.vertices) * 3); ob.data.vertices.foreach_get("co", co); co = co.reshape(-1, 3); co[:, 0] += co[:, 2]
            kb.data.foreach_set("co", co.ravel()); kb.slider_min, kb.slider_max = -10.0, 10.0
        vis = set()
        for k, rec in recs:
            ob.location = rec["base"]; ob.scale = (rec["r"], rec["r"], rec["h"]); vis.add(k); frames.add((i, k))
            ob.keyframe_insert("location", frame=k); ob.keyframe_insert("scale", frame=k)
            if kb is not None:
                kb.value = math.hypot(*(rec.get("shear") or (0.0, 0.0))) * rec["h"] / rec["r"]; kb.keyframe_insert("value", frame=k)
            if rec.get("tilt"):
                dx, dy, th = rec["tilt"]; ob.rotation_euler = Matrix.Rotation(th, 4, Vector((-dy, dx, 0.0))).to_euler(); ob.keyframe_insert("rotation_euler", frame=k)
            elif r0["shape"] in ("cone", "frustum") and any(r.get("tilt") for _, r in recs):
                ob.rotation_euler = (0.0, 0.0, 0.0); ob.keyframe_insert("rotation_euler", frame=k)
        prev = None
        for k in range(1, nf + 1):                                     # visibility: keys at state changes (booleans as steps)
            hid = k not in vis
            if hid != prev:
                for p in ("hide_render", "hide_viewport"): setattr(ob, p, hid); ob.keyframe_insert(p, frame=k)
                prev = hid
        made.append((ob, recs)); per_layer[r0["kind"]] = per_layer.get(r0["kind"], 0) + len(recs)
    err = 0.0                                                          # check on the scene: the stand-in mesh frame against box() in several frames
    picks = [(ob, recs[j]) for ob, recs in made for j in sorted({0, len(recs) // 2, len(recs) - 1})]
    for ob, (k, rec) in picks[::max(1, len(picks) // samples)][:samples]:
        sc.frame_set(k); dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
        P = np.array([tuple(ev.matrix_world @ v.co) for v in me.vertices]); ev.to_mesh_clear()
        lo, hi = (np.array(x) for x in box(rec)); size = np.maximum(hi - lo, 0.5)
        err = max(err, float(np.max(np.maximum(np.abs(P.min(0) - lo), np.abs(P.max(0) - hi)) / size)))
    sc.frame_set(1); bpy.context.view_layer.update()
    return {"look": "stand_in", "explosions": len(events) - len(set(skipped)), "objects": len(made), "frames_with_fx": len(frames),
            "layers": ",".join(f"{a}:{b}" for a, b in sorted(per_layer.items())), "skipped": ",".join(str(s) for s in skipped),
            "ground": ctx.get("ground"), "wind": [round(x, 2) for x in ctx["wind"]] if ctx.get("wind") else 0,
            "first_frame": min(first.values()) if first else 0, "box_err": round(err, 3)}
