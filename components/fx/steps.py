"""Entry of the Effects component for step-by-step assembly (core/blender/build.py): the "explosions" step — the take's
explosion events as time-keyed objects in an open scene.
The legacy path: the take (the Time component) calls bl_fx.explosion(event, t, camera, context) for every frame, builds
the frame's objects, renders the frame and deletes them; it stays working (explosions_3d: true) and gives the same
result byte for byte. Here — the same bl_fx functions (explosion: flash, body from .vdb, soil, clods, sparks, glow,
burning; the level by screen size relative to the frame camera), but the objects are built once, in the scene itself:
each take frame gets its own objects with visibility keys (hide_render and hide_viewport: visible only on its own frame;
scene frame = the take frame number, starting from 1), the scorch on the ground is a single disk with an appearance key.
The "frames" output (core/outputs/bl_frames_blend.py) renders the explosions from the .blend (frame_set) without calling
bl_fx.
Events — the file `blasts.json` in the take folder (written by the "take" step: at, c — the center on the ground, kind,
strength, height, tint, k); frame cameras — take_NNN in cameras.json of the run scene; light — "light_plan" and
"exposure" of the "light" step (it gives them): the effects strength is screen-based, × 2^(−node EV), at night × the
knowledge's "at_night" factor; place the step AFTER "light" (the "light" step removes the scene lamps and sets the
exposure; without a light plan the EV comes from the "exposure" key or from the scene kind).
Object tags: sk_layer "time" (the section collection is set by build.py), sketch_fx — not geometry for maps; fx_layer —
volumes and sparks: the output draws them as a layer over the node's haze (a volume writes no depth, and a haze by the
background depth would lie over the explosion; bl_far.render_scene_fx), as the legacy path does. No knowledge or asset
of the kind — the event is skipped (counted as skipped in the step output), there are no fallback balls — only the take places them.
The look knob: full (default) — everything above; stand_in (the sketch stage, passport profiles) — stand-ins
components/fx/stand_in.py: the same events, frames and similarity law, an object per layer (fire — a ball, smoke — an
ellipsoid, dust — a dome, burning — a cone and a column) with keys per take frame, without volumes, cards, lamps, clods
and scorch."""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _lander(sc):
    """z of the ground under a point (m): a ray from above onto the "terrain" object of the open scene; no object or a miss —
    None."""
    import bpy
    from mathutils import Vector
    ter = bpy.data.objects.get("terrain")
    if ter is None: return lambda x, y: None
    inv = ter.matrix_world.inverted()

    def z_at(x, y):
        o, d = inv @ Vector((x, y, 1e4)), inv.to_3x3() @ Vector((0, 0, -1))
        hit, loc, *_ = ter.ray_cast(o, d)
        return float((ter.matrix_world @ loc).z) if hit else None
    return z_at


def _light(ctx, keys):
    """Exposure, night and wind of the light node: from the plan of the "light" step (it gives light_plan); no plan — the
    "exposure" key or the exposure of the scene kind, no wind. The plan wind (fires.wind [x, y]: the direction and bend of
    far smoke columns, clouds — 10 m/s) → near the ground 10·|w| m/s at 10 m in the same direction; the "wind" key is its
    own: [ux, uy] m/s or 0 (calm)."""
    fp = ctx["gives"].get("light_plan"); wk = keys.get("wind")
    own = None if wk in (None, "") else ([float(x) for x in wk] if isinstance(wk, (list, tuple)) else [0.0, 0.0])
    if fp and os.path.exists(fp):
        P = json.load(open(fp))
        ev = float(P["light"]["ev"]) if keys.get("exposure") in (None, "") else float(keys["exposure"])
        w = (P.get("fires") or {}).get("wind")
        return ev, float(P.get("sun", {}).get("el", 90)) < -4, "light plan", own if own is not None else ([10.0 * float(w[0]), 10.0 * float(w[1])] if w else None)
    ev = float(keys["exposure"]) if keys.get("exposure") not in (None, "") else float(ctx["sc"].view_settings.exposure)
    return ev, False, "no light plan", own


def _show_only(o, k, NF):
    """Visibility keys: visible only on frame k (scene frame = the take frame number)."""
    for prop in ("hide_render", "hide_viewport"):
        if k > 1: setattr(o, prop, True); o.keyframe_insert(prop, frame=k - 1)
        setattr(o, prop, False); o.keyframe_insert(prop, frame=k)
        if k < NF: setattr(o, prop, True); o.keyframe_insert(prop, frame=k + 1)


def _show_from(o, k):
    """Visibility keys: visible from frame k onward (scorch on the ground)."""
    for prop in ("hide_render", "hide_viewport"):
        if k > 1: setattr(o, prop, True); o.keyframe_insert(prop, frame=k - 1)
        setattr(o, prop, False); o.keyframe_insert(prop, frame=k)


def build_explosions(ctx):
    import bpy
    from mathutils import Vector
    from components.fx import bl_fx
    sc, SD, keys, dd = ctx["sc"], ctx["scene"], ctx["keys"], ctx["gives"]
    take = dd.get("take_dir")
    bp = os.path.join(take, "blasts.json") if take else None
    if not bp or not os.path.exists(bp): raise SystemExit("explosions: no take events (blasts.json) — the 'explosions' step runs after the 'take' step")
    events = json.load(open(bp))
    if not events: return {"explosions": 0, "objects": 0}
    if not bl_fx.knowledge(): raise SystemExit("explosions: no library/fx/explosions.json — knowledge: fx_bake.py compile")
    FPS, NF = float(dd.get("take_fps") or sc.render.fps), int(dd.get("take_frames") or sc.frame_end)
    cams = {int(c["frame"]): c for c in json.load(open(os.path.join(SD, "cameras.json"))) if c.get("frame") is not None and c.get("location")}
    if not cams: raise SystemExit("explosions: cameras.json of the scene has no take cameras (take_NNN) — the 'take' step comes earlier")
    ev, night, src, wind = _light(ctx, keys)
    z_at = _lander(sc)
    if str(keys.get("look") or "full") == "stand_in":                 # sketch: layer stand-ins at the explosion's size and timing (components/fx/stand_in.py)
        from components.fx import stand_in
        gz = lambda x, y: (lambda z: float(z) if z is not None else 0.0)(z_at(x, y))
        return stand_in.build(sc, ctx.get("collection"), events, FPS, NF, {"wind": wind, "ground": bl_fx.ground_kind(SD), "z_at": gz},
                              seed0=int(keys.get("seed") or 0))
    FX = {"ev": ev, "night": night, "soil": bl_fx.ground_kind(SD), "fps": FPS, "wind": wind,
          "ground": lambda x, y: (lambda z: float(z) if z is not None else 0.0)(z_at(x, y))}
    if keys.get("cards") not in (None, ""): FX["cards"] = str(keys["cards"])   # far plane: cards instead of volumes (bl_fx_cards.py)
    lvl = str(keys.get("level") or "auto")
    if lvl != "auto": FX["screen_level"] = lvl                  # the knowledge levels are the knob's names (close … very_far)
    seed0 = int(keys.get("seed") or 0)
    n_obj, skipped, levels, k_first = 0, [], {}, {}
    bl_fx.LOG.clear(); bl_fx.FRAME.clear()
    for i, e in enumerate(events):
        ee = dict(e, seed=i + seed0)
        for k in range(1, NF + 1):
            t = (k - 1) / FPS
            if t < float(e["at"]) - 1e-9: continue
            objs = bl_fx.explosion(ee, t, cams.get(k) or cams[min(cams, key=lambda j: abs(j - k))], FX, sc)
            if objs is None: skipped.append({"event": i, "kind": e.get("kind")}); break   # no knowledge or asset of the kind — the event is skipped
            k_first.setdefault(i, k)
            for o in objs:
                o["sk_layer"] = "time"; o["sketch_fx"] = 1
                if o.type == "VOLUME" or o.name.startswith("fx_sparks"): o["fx_layer"] = 1   # a layer over the node's haze (the "frames" output)
                _show_only(o, k, NF); n_obj += 1
            info = bl_fx.LOG[-1] if bl_fx.LOG else {}
            if info.get("level"): levels[f"{i}:{k}"] = info["level"]
        if i in k_first and keys.get("scorch", True) not in (False, "false", 0):
            o = bl_fx.scorch(e, 0.0, sc, FX["ground"])                 # the mechanism's scorch: a soot patch following the relief, a ragged edge; an airburst gets none
            if o is not None:
                o["sk_layer"] = "time"; o["sketch_fx"] = 1; _show_from(o, k_first[i]); n_obj += 1
                for k in range(k_first[i], NF + 1):                    # soot settles while it burns: the strength by the frame time
                    o["fx_scorch"] = bl_fx.scorch_grow(e, (k - 1) / FPS - float(e["at"])); o.keyframe_insert('["fx_scorch"]', frame=k)
    bl_fx.frame_settings(sc)     # an explosion "up close" — volume tile 4, 64 layers, volumetric shadows: they stay in the scene (the legacy path restores them after the frame)
    sc.frame_set(1); bpy.context.view_layer.update()
    by_level = {}
    for v in levels.values(): by_level[v] = by_level.get(v, 0) + 1
    return {"explosions": len(events) - len({s["event"] for s in skipped}), "objects": n_obj, "frames_with_fx": len(levels),
            "levels": ",".join(f"{a}:{b}" for a, b in sorted(by_level.items())), "skipped": ",".join(str(s["event"]) for s in skipped),
            "exposure": round(ev, 3), "night": night, "light": src, "ground": FX["soil"], "wind": [round(x, 2) for x in wind] if wind else 0,
            "first_frame": min(k_first.values()) if k_first else 0}
