"""Explosion assets: baking from the knowledge library/fx/explosions.yaml and compiling the knowledge for Blender.

.venv/bin/python -m core.services.guard heavy --what "explosions: baking" -- .venv/bin/python -m components.fx.fx_bake bake <asset …> [--level=high|low|all]
    → library/fx/<asset>/<level>/cache (OpenVDB Blosc half), stats.json, meta.yaml (git keeps a summary: size, frames, disk, cost)
.venv/bin/python -m components.fx.fx_bake compile   → library/fx/explosions.json — knowledge + baked data for components/fx/bl_fx.py (there is no yaml in Blender)
.venv/bin/python -m components.fx.fx_bake slim <asset …> [--level=all]   → in-place cache cleanup (bl_fx_slim.py: only the shader channels,
    no voxels below 0.01, half; the frame is the same, the disk is 3–12 times smaller); it runs by itself after baking (--no-cleanup disables it)
.venv/bin/python -m components.fx.fx_bake cards [<kind|combustion> …] [--stale] [--all] [--stamp]   → re-shooting the cards (bl_fx_cards.py; under guard
    heavy): the named ones, all of them, or the stale ones (the source fingerprint — the kind's knowledge and the asset summaries — does not match; card_source.py); --stamp only
    records the fingerprint. After an asset is baked its cards are re-shot by themselves (--no-cards disables it); compile names the stale ones.
Baking is heavy (128 + noise: ~100 s, a peak of ~3.6 GB): only through guard heavy."""
import core.paths         # the code is here, the core — core/<part> through kernel
import json, os, re, subprocess, sys, time

import yaml

from components.fx import card_source

ROOT = core.paths.ROOT; FX = os.path.join(ROOT, "library", "fx")
KNOW = os.path.join(FX, "explosions.yaml")


def compile_():
    K = yaml.safe_load(open(KNOW, encoding="utf-8")); K["baked"] = {}
    for name in K["assets"]:
        for lv in ("high", "low"):
            st = os.path.join(FX, name, lv, "stats.json")
            if not os.path.exists(st): continue
            S = json.load(open(st)); a = K["assets"][name]
            K["baked"].setdefault(name, {})[lv] = dict(S, **{k: a[k] for k in ("W", "M", "Q_kw", "loop", "cut") if k in a})
            meta = {k: S[k] for k in ("resolution", "noise", "n_frames", "frame_start", "fps", "domain", "angle", "height", "early_s", "bake_s", "disk_mb", "peak_gb") if k in S}
            open(os.path.join(FX, name, lv, "meta.yaml"), "w", encoding="utf-8").write(
                f"# {name}, level '{lv}' — bake summary (components/fx/fx_bake.py); the .vdb frames and stats.json are outside git\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False))
    json.dump(K, open(os.path.join(FX, "explosions.json"), "w"), ensure_ascii=False)
    done = {n: sorted(v) for n, v in K["baked"].items()}
    print("knowledge →", os.path.relpath(os.path.join(FX, "explosions.json"), ROOT), "; baked:", done or "nothing")
    old = card_source.stale(K)
    if old: print("cards are stale (re-shoot: python -m components.fx.fx_bake cards --stale):", ", ".join(f"{k} ({r})" for k, r in old))
    return 0


def cards(kinds=None, stamp=False):
    """Re-shooting of cards (bl_fx_cards.py, Blender — under guard heavy): the kinds kinds or the stale ones (the source
    fingerprint does not match); stamp — only write the fingerprint into card.json without re-shooting (the cards were shot
    from the current assets). → 0 / 1."""
    K = json.load(open(os.path.join(FX, "explosions.json"))); kinds = kinds or [k for k, _ in card_source.stale(K)]; bad = 0
    for k in kinds:
        cj = os.path.join(card_source.CARDS, k, "card.json")
        if stamp:
            m = json.load(open(cj)); m["source"] = card_source.fingerprint(k, K); json.dump(m, open(cj, "w"), ensure_ascii=False, indent=1)
            print(f"{k}: fingerprint {m['source']}", flush=True); continue
        t = time.time(); out = os.path.join(card_source.CARDS, k)
        p = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "-P", core.paths.RUN, "--",
                            os.path.join(ROOT, "components/fx/bl_fx_cards.py"), "--", k, out + ".new"], capture_output=True, text=True, cwd=ROOT)
        if p.returncode or not os.path.exists(os.path.join(out + ".new", "card.json")):
            print(f"{k}: ERROR", (p.stdout + p.stderr)[-1200:]); bad = 1; continue
        import shutil
        if os.path.isdir(out): shutil.rmtree(out)
        os.replace(out + ".new", out); print(f"{k}: re-shot in {time.time() - t:.0f} s", flush=True)
    if not kinds: print("cards: no stale ones")
    return bad


def trim_loop(out, f0):
    """Loop asset: delete the cache frames before the start of the loop (the growth of the fire does not go into the frame); →
    disk, MB."""
    import glob
    for f in glob.glob(os.path.join(out, "cache", "*", "*_*.vdb")):
        m = re.search(r"_(\d{4})\.vdb$", f)
        if m and int(m.group(1)) < f0: os.remove(f)
    return round(sum(os.path.getsize(f) for f in glob.glob(os.path.join(out, "cache", "**", "*"), recursive=True) if os.path.isfile(f)) / 1e6, 1)


def slim(names, level):
    """In-place cleanup of the baked levels (bl_fx_slim.py) and compiling the knowledge; → 0 / 1."""
    rows = []
    for name in names:
        for lv in (("high", "low") if level == "all" else (level,)):
            out = os.path.join(FX, name, lv)
            if not os.path.exists(os.path.join(out, "stats.json")): continue
            p = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "-P", core.paths.RUN, "--", os.path.join(ROOT, "components/fx/bl_fx_slim.py"), "--", out],
                               capture_output=True, text=True, cwd=ROOT)
            m = re.search(r"__SLIM__ (\{.*\})", p.stdout)
            rows.append(dict(json.loads(m.group(1)), asset=name, level=lv) if m else {"asset": name, "level": lv, "error": (p.stdout + p.stderr)[-800:]})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    compile_()
    return 1 if any(r.get("error") for r in rows) else 0


def bake(names, level, clean=True, with_cards=True):
    K = yaml.safe_load(open(KNOW, encoding="utf-8")); jobs = os.path.join(ROOT, "out", "fx_bake"); os.makedirs(jobs, exist_ok=True); rows = []
    for name in names:
        A = K["assets"][name]
        for lv in (("high", "low") if level == "all" else (level,)):
            L = A["levels"][lv]; out = os.path.join(FX, name, lv); jp = os.path.join(jobs, f"{name}_{lv}.json")
            if os.path.isdir(os.path.join(out, "cache")):
                import shutil; shutil.rmtree(os.path.join(out, "cache"))   # from scratch — do not mix in old frames of a different length
            for f in ("stats.json", "meta.yaml"):                          # and the summary too: if baking failed, there is no asset, not a stale one
                if os.path.exists(os.path.join(out, f)): os.remove(os.path.join(out, f))
            json.dump({"asset": A, "output": out, "resolution": L["resolution"], "noise": L["noise"]}, open(jp, "w"), ensure_ascii=False)
            t = time.time()
            tm = ["/usr/bin/time", "-l" if sys.platform == "darwin" else "-v"] if os.path.exists("/usr/bin/time") else []   # peak memory: BSD -l, GNU -v
            p = subprocess.run([*tm, "blender", "-b", "--factory-startup", "--python-exit-code", "1",
                                "-P", core.paths.RUN, "--", os.path.join(ROOT, "components/fx/bl_fx_bake.py"), "--", jp], capture_output=True, text=True, cwd=ROOT)
            m = re.search(r"__BAKE__ (\{.*\})", p.stdout); rss = re.search(r"(\d+)\s+maximum resident set size", p.stderr)   # bytes (macOS)
            rss_k = re.search(r"Maximum resident set size \(kbytes\): (\d+)", p.stderr)                                  # KB (Linux)
            rss_b = int(rss.group(1)) if rss else int(rss_k.group(1)) * 1024 if rss_k else None
            if not m:
                print(f"{name}/{lv}: ERROR", (p.stdout + p.stderr)[-1500:]); rows.append({"asset": name, "level": lv, "error": True}); continue
            r = json.loads(m.group(1)); st = os.path.join(out, "stats.json"); S = json.load(open(st))
            if A.get("loop"): S["disk_mb"] = trim_loop(out, A["loop"][0])   # loop: the frames before its start are not needed — disk
            S["peak_gb"] = round(rss_b / 1e9, 2) if rss_b else None; json.dump(S, open(st, "w"), ensure_ascii=False)
            rows.append(dict(r, asset=name, level=lv, peak_gb=S["peak_gb"], total_s=round(time.time() - t, 1))); print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            if clean: slim([name], lv)                                   # only the shader channels, no empty voxels — the frame is the same
    compile_()
    bad = 0
    if with_cards:                                                     # a re-baked asset — its cards are re-shot
        K = json.load(open(os.path.join(FX, "explosions.json"))); kinds = sorted({k for n in names for k in card_source.users(n, K)} & {k for k, _ in card_source.stale(K)})
        bad = cards(kinds) if kinds else 0
    print("__RESULT__", json.dumps(rows, ensure_ascii=False))
    return 1 if any(r.get("error") for r in rows) or bad else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("bake", "compile", "slim", "cards"): print(__doc__); sys.exit(2)
    if a[0] == "compile": sys.exit(compile_())
    if a[0] == "cards":
        ks = [x for x in a[1:] if not x.startswith("--")]
        sys.exit(cards(card_source.baked() if "--all" in a else ks or None, stamp="--stamp" in a))
    lv = next((x.split("=", 1)[1] for x in a if x.startswith("--level=")), "low" if a[0] == "bake" else "all")
    names = [x for x in a[1:] if not x.startswith("--")]
    sys.exit(slim(names, lv) if a[0] == "slim" else bake(names, lv, "--no-cleanup" not in a, "--no-cards" not in a))
