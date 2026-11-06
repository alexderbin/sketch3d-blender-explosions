"""Stand for the explosion stand-ins (the look knob stand_in of the "explosions" step) — without Blender, ~1 s.
  Law: the stand-in frame of a layer at 3 moments of its life against the frame of the full explosion's layer by the
      law — the bake summary of the high-level asset (the isosurface frame: center, largest half-size, top) × s =
      (W / W_asset)^(1/3) at the asset time given by asset_time of the full explosion (the function is taken from the
      source of bl_fx.py), the center — with the body's rotation and mirroring by the seed, wind — the cloud drift per
      the component logic (U(z) is a logarithm, t_ef, a shift between 0.15 H and 0.85 H); burning — the top of the flame
      and of the column, the lean into the wind; tolerance — 12 %;
  similarity: a stand-in of strength ×8 at a similar moment is twice as large (early phase — t × 2, late phase — the
      same asset time), ±3 %;
  card: the stand-in frame over its life (strength 1, calm, all layers) against the frame of the kind's card (shot as a
      render of the high asset): 70–110 %;
  first event frame: the take frame with t ≥ at, as for the full explosion; the event does not change.
The frame of the built mesh (keys, shape offset) is checked by the step itself in Blender — box_err in the journal.
.venv/bin/python -m components.fx.bench.stand_in_check [--table]   → a line __RESULT__ {n_failures, n_checks}"""
import ast, copy, json, math, os, random, sys, time

import core.paths
from components.fx import stand_in as S

ROOT, TOL, FPS = core.paths.ROOT, 0.12, 24.0
WIND = [3.5, 1.2]                                                       # sample wind (fires.wind × 10), m/s at 10 m
CASES = [("projectile", {}, None), ("projectile", {}, WIND), ("grenade", {}, WIND), ("mine", {}, None), ("bomb", {}, None), ("charge", {}, WIND),
         ("fuel", {}, None), ("fuel", {}, WIND), ("airburst", {"height": 25}, WIND), ("fire_ball", {"height": 1.5}, None),
         ("napalm", {"to": [8, 0, 0]}, None), ("blaze", {"height": 3.5}, None), ("blaze", {"height": 3.5}, WIND)]


def full_law():
    """asset_time, norm_event and the constants of the full explosion come from the source of bl_fx.py (the project's Python
    has no bpy): the stand-in law is checked against the law of the full explosion, not against itself."""
    src = open(os.path.join(ROOT, "components", "fx", "bl_fx.py"), encoding="utf-8").read()
    keep = [n for n in ast.parse(src).body if (isinstance(n, ast.FunctionDef) and n.name in ("asset_time", "norm_event")) or
            (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("Z0_ROUGH", "LEAN_MAX") for t in n.targets))]
    ns = {"math": math, "knowledge": S.knowledge}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "bl_fx.py", "exec"), ns)
    return ns


def _u(w, z, z0):
    """Wind at height z: U10 · ln(z / z0) / ln(10 / z0), z not below z0·e."""
    k = math.log(max(z, z0 * math.e) / z0) / math.log(10.0 / z0)
    return w[0] * k, w[1] * k


def ref_cloud(e, dt, layer, F, K, wind):
    """Frame of a full-explosion layer by the law: fire | smoke — the body (an ellipsoid in the isosurface frame), dust — the
    ejecta (a dome at its bottom)."""
    vid, V, W, h = F["norm_event"](e); z0 = e["c"][2]
    A = S.asset(K, "ejecta" if layer == "dust" else V["fire"]["asset"], "high")
    s = (W / float(A.get("W", A.get("M", 1.0)))) ** K["scale"]["size"]; T1 = float(A["early_s"])
    f = int(round(A["frame_start"] + F["asset_time"](dt, s, T1) * A["fps"])); f = min(max(f, 1), A["n_frames"]); row = A["frames"][f - 1] or {}
    st = row.get({"fire": "fire", "smoke": "smoke", "dust": "smoke"}[layer])
    rng = random.Random(int(e.get("seed", 0)) * 7919 + int(float(e["at"]) * 1000)); rot = rng.uniform(0, 2 * math.pi); mirror = rng.random() < 0.5
    if layer == "dust": rot, mirror, h = rot + 1.1, not mirror, 0.0
    px, py = (-st["center"][0] if mirror else st["center"][0]) * s, st["center"][1] * s
    c = [e["c"][0] + math.cos(rot) * px - math.sin(rot) * py, e["c"][1] + math.sin(rot) * px + math.cos(rot) * py, z0 + h + st["center"][2] * s]
    r, hz = st["radius"] * s, (st["top"] - st["center"][2]) * s
    cj = os.path.join(S.FXDIR, "cards", vid, "card.json")             # the puff is stretched upward — the width is no wider than the kind's card frame (by the law)
    if layer != "dust" and st["top"] - st["center"][2] >= 0.98 * st["radius"] and os.path.exists(cj):
        r = min(r, json.load(open(cj))["width_m"] / 2 * float(e.get("strength", 1.0)) ** (1 / 3))
    b, a = (0.0, 0.0), (0.0, 0.0)
    if wind:                                                            # cloud: d(z) = U(z)·t_ef at 0.15 H and 0.85 H, a shift along a straight line
        H = h + float((row.get("smoke") or {}).get("top", A["height"])) * s; tm = T1 * s; te = dt - tm * (1 - math.exp(-dt / tm))
        za, zb = 0.15 * H, 0.85 * H; ua, ub = _u(wind, za, F["Z0_ROUGH"]), _u(wind, zb, F["Z0_ROUGH"])
        b = tuple((ub[i] - ua[i]) * te / (zb - za) for i in (0, 1)); a = tuple(ua[i] * te - b[i] * za for i in (0, 1))
    lo, hi = [0.0] * 3, [0.0] * 3
    if layer == "dust":                                                 # dome: the base at the bottom of the frame, the shift measured from the base
        zb_ = c[2] - hz
        for i in (0, 1):
            x0 = c[i] + a[i] + b[i] * (zb_ - z0); ext = math.hypot(r, b[i] * 2 * hz)
            lo[i], hi[i] = (x0 - r, x0 + ext) if b[i] >= 0 else (x0 - ext, x0 + r)
    else:                                                               # ellipsoid: the center drifts, half-size √(r² + (b·hz)²)
        for i in (0, 1):
            x0 = c[i] + a[i] + b[i] * (c[2] - z0); ext = math.hypot(r, b[i] * hz); lo[i], hi[i] = x0 - ext, x0 + ext
    lo[2], hi[2] = c[2] - hz, c[2] + hz
    return lo, hi


def ref_burn(e, dt, layer, F, K, wind):
    """Burning by the law: s = (Q/500)^(2/5), L by Heskestad, front 0.39·Q^(1/3) m/s; the flame is the top of the fire of the
    asset loop × s, the column goes up to min(L + vf·t, asset cut × s); the lean from the base atan(|d(0.85 H)| / 0.85 H) ≤
    LEAN_MAX. → (bottom, top along the axis, angle)."""
    vid, V, W, h = F["norm_event"](e); sila = float(e.get("strength", 1.0)); A = S.asset(K, "combustion", "high")
    if vid == "blaze": Q, db = float(V["combustion"]["Q_kw"]) * sila, dt
    else:
        Ab = S.asset(K, V["fire"]["asset"], "high"); s_ = (W / float(Ab.get("W", Ab.get("M", 1.0)))) ** (1 / 3)
        Q, db = float(V["combustion"]["Q_kw"]) * sila, dt - 0.03 * s_
    s = (Q / 500.0) ** 0.4; L = max(0.3, 0.235 * Q ** 0.4 - 1.02 * s); vf = 0.39 * Q ** (1 / 3)
    L0, L1 = A["loop"]; tops = [r["fire"]["top"] for r in A["frames"][L0 - 1:L1] if r and r.get("fire")]; hf = sum(tops) / len(tops) * s
    top = hf if layer == "flame" else min(L + vf * db, A["cut"][1] * s)
    th = 0.0
    if wind:
        H = L + vf * db; zb = 0.85 * H; u = _u(wind, zb, F["Z0_ROUGH"]); d = math.hypot(*u) * min(zb / vf, db)
        th = min(math.atan2(d, zb), math.radians(F["LEAN_MAX"]))
    return (hf if layer.startswith("column") else 0.0), top, th


def _moments(recs):
    """3 moments of a layer's life: at 15, 50 and 85 % of its frames."""
    return sorted({recs[min(len(recs) - 1, int(round(q * (len(recs) - 1))))][0] for q in (0.15, 0.5, 0.85)})


def main():
    t0, K, F = time.time(), S.knowledge(), full_law()
    table, fails, n = [], [], 0

    def check(ok, what):
        nonlocal n
        n += 1
        if not ok: fails.append(what)

    for at in (0.0, 1.0, 2.3):                                          # the law of the full explosion and of the stand-in is one (asset_time)
        for s in (0.33, 1.0, 2.47):
            check(abs(S.asset_time(at, s, 0.458) - F["asset_time"](at, s, 0.458)) < 1e-12, f"asset_time({at}, {s}) diverges from bl_fx")
    for vid, extra, wind in CASES:
        e = {"at": 0.5, "c": [10.0, -5.0, 2.0], "kind": vid, **extra}; e0 = copy.deepcopy(e)
        ctx = {"K": K, "wind": wind, "ground": "ground", "z_at": lambda x, y: 2.0}
        tr, sk, first = S.plan([e], FPS, int(14 * FPS), ctx)
        check(e == e0, f"{vid}: event changed")
        check(not sk and first.get(0) == int(math.ceil(0.5 * FPS - 1e-9)) + 1, f"{vid}: first frame {first.get(0)} (skipped {sk})")
        ee = dict(e, seed=0)
        for (i, layer), recs in sorted(tr.items()):
            if vid == "napalm" and layer.startswith(("flame", "column")): continue   # fire patches of the strip: their own strength and time shift by the seed
            for k in _moments(recs):
                rec = dict(recs)[k]; dt = (k - 1) / FPS - e["at"]; lo, hi = S.box(rec)
                if layer in ("fire", "smoke", "dust"):
                    rl, rh = ref_cloud(ee, dt, layer, F, K, wind)
                    size = [max(rh[j] - rl[j], 0.5) for j in range(3)]
                    d_size = max(abs((hi[j] - lo[j]) - (rh[j] - rl[j])) / size[j] for j in range(3))
                    d_cen = max(abs((hi[j] + lo[j]) - (rh[j] + rl[j])) / 2 / size[j] for j in range(3))
                    got, want = [hi[j] - lo[j] for j in range(3)], [rh[j] - rl[j] for j in range(3)]
                else:
                    zlo, ztop, th = ref_burn(ee, dt, layer, F, K, wind); tl = rec.get("tilt")
                    got = [rec["h"], math.degrees(tl[2]) if tl else 0.0]
                    want = [ztop - zlo, math.degrees(th)]
                    d_size = abs(got[0] - want[0]) / max(want[0], 0.5); d_cen = abs(got[1] - want[1]) / 60.0
                check(d_size <= TOL and d_cen <= TOL, f"{vid}{' wind' if wind else ''} {layer} t={dt:.2f}: {got} versus {want}")
                table.append((vid + (" wind" if wind else ""), layer, round(dt, 2), [round(x, 2) for x in got], [round(x, 2) for x in want],
                              round(max(d_size, d_cen) * 100, 1)))
    for vid in ("projectile", "grenade", "fuel"):                         # similarity: strength ×8 — twice as large at a similar moment
        A = S.asset(K, K["kinds"][vid]["fire"]["asset"], "high"); s1 = (F["norm_event"]({"kind": vid})[2] / float(A.get("W", A.get("M", 1.0)))) ** (1 / 3)
        T1 = float(A["early_s"])
        for ta in (0.15, 1.5, 3.0):                                     # asset time: an early phase and a late one
            ts = [(ta * ss if ta <= T1 else T1 * ss + (ta - T1) * math.sqrt(ss)) for ss in (s1, 2 * s1)]
            L1, L8 = (S.layers({"at": 0.0, "c": [0, 0, 0], "kind": vid, "strength": sl}, t, {"K": K}) for sl, t in ((1.0, ts[0]), (8.0, ts[1])))
            for a_, b_ in zip(sorted(L1, key=lambda r: r["layer"]), sorted(L8, key=lambda r: r["layer"])):
                if a_["layer"] != b_["layer"] or a_["layer"].startswith(("flame", "column")): continue
                q = [(S.box(b_)[1][j] - S.box(b_)[0][j]) / (S.box(a_)[1][j] - S.box(a_)[0][j]) for j in range(3)]
                check(all(abs(x - 2.0) <= 0.06 for x in q), f"similarity {vid} {a_['layer']} ta={ta}: ×{[round(x, 3) for x in q]}")
    cards = {}
    for vid in ("grenade", "mine", "projectile", "bomb", "charge", "fuel", "fire_ball", "napalm", "airburst"):   # the card frame is a render of the high asset
        cj = os.path.join(S.FXDIR, "cards", vid, "card.json")
        if not os.path.exists(cj): continue
        m = json.load(open(cj)); tr, _, _ = S.plan([{"at": 0.0, "c": [0.0, 0.0, 0.0], "kind": vid}], 8.0, 80, {"K": K})
        B = [S.box(r) for recs in tr.values() for _, r in recs if not r["layer"].startswith(("flame", "column"))]
        w = max(max(b[1][0] for b in B) - min(b[0][0] for b in B), max(b[1][1] for b in B) - min(b[0][1] for b in B))
        hgt = max(b[1][2] for b in B) - min(b[0][2] for b in B)
        q = (w / float(m["width_m"]), hgt / float(m["height_m"])); cards[vid] = [round(x, 2) for x in q]
        check(all(0.7 <= x <= 1.1 for x in q), f"card {vid}: stand-in frame to card frame ×{cards[vid]}")
    if "--table" in sys.argv:
        for row in table: print("  ".join(str(x) for x in row))
        print("cards (width, height of the stand-in relative to the card frame):", cards)
    for f in fails: print("MISMATCH", f)
    worst = max(table, key=lambda r: r[-1]) if table else None
    print("__RESULT__", json.dumps({"n_failures": len(fails), "n_checks": n, "n_layers_moments": len(table), "worst_%": worst[-1] if worst else None,
                                    "cards": cards, "sec": round(time.time() - t0, 2)}, ensure_ascii=False))
    return len(fails)


if __name__ == "__main__":
    sys.exit(main())
