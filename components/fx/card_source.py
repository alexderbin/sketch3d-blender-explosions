"""Fingerprint of a card's source (bl_fx_cards.py): the kind's knowledge and the summaries of the baked assets it was shot
from (the high level), the soil and the shooting level. If the asset was re-baked or the kind's knowledge was corrected,
the fingerprint differs and the card is stale: `fx_bake cards` re-shoots it, `fx_bake bake` does so by itself after
baking, `bl_fx.card_set` warns. No bpy — called from both Blender and the project's Python.
The fingerprint does not see the bl_fx code constants (FIRE0, MS0, INNER0 …): after changing them, re-shoot the cards
explicitly (`fx_bake cards --all`)."""
import hashlib, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FX = os.path.join(ROOT, "library", "fx")
CARDS = os.path.join(FX, "cards")


def knowledge():
    return json.load(open(os.path.join(FX, "explosions.json")))


def fingerprint(kind, K=None):
    """Fingerprint of the source of the card of kind kind (or "combustion" — the fire loop) from the compiled knowledge K
    (explosions.json)."""
    K = K or knowledge(); Z = K.get("baked") or {}
    if kind == "combustion":
        parts = {"kind": K["kinds"]["blaze"], "assets": {"combustion": (Z.get("combustion") or {}).get("high")}}
    else:
        V = K["kinds"][kind]; names = [V["fire"]["asset"]] + (["ejecta"] if float(V.get("soil", 0) or 0) > 0 else [])
        parts = {"kind": V, "assets": {n: (Z.get(n) or {}).get("high") for n in names}}
    parts.update(soil=(K.get("soils") or {}).get("ground"), level=(K.get("levels") or {}).get("close"), scale=K.get("scale"))
    return hashlib.sha1(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def baked():
    """Baked cards: [kind]."""
    return sorted(k for k in os.listdir(CARDS) if os.path.exists(os.path.join(CARDS, k, "card.json"))) if os.path.isdir(CARDS) else []


def stale(K=None):
    """Stale cards: [(kind, reason)] — there is no fingerprint or it does not match the current knowledge and assets."""
    K = K or knowledge(); out = []
    for k in baked():
        src = json.load(open(os.path.join(CARDS, k, "card.json"))).get("source")
        if k != "combustion" and k not in K["kinds"]: out.append((k, "the kind is not in the knowledge")); continue
        now = fingerprint(k, K)
        if src != now: out.append((k, "no fingerprint" if not src else f"fingerprint {src} → {now}"))
    return out


def users(asset, K=None):
    """Kinds (and "combustion") whose cards were shot from asset asset."""
    K = K or knowledge(); out = ["combustion"] if asset == "combustion" else []
    for k, V in K["kinds"].items():
        if V["fire"]["asset"] == asset or (asset == "ejecta" and float(V.get("soil", 0) or 0) > 0): out.append(k)
    return [k for k in out if k in baked()]
