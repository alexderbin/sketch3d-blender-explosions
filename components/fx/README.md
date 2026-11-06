# FX — procedural explosions for Blender in Python: baked OpenVDB fire and smoke, ground ejecta, debris, distant cards

FX is a procedural explosion generator for Blender, written in Python. It assembles an explosion from layers by the
knowledge of its type: a flash, a fire-and-smoke body (a volume read from a baked OpenVDB cache), ground ejecta, clods
and sparks, smoke under-lighting, a scorch mark, sustained burning. Size and timing follow blast-scaling laws, detail
follows the body's height on screen, distant explosions become pre-rendered cards, and light is exposure-relative, so
fire reads the same by day and by night. The `explosions` step animates the `time` layer: it reads the events and
per-frame cameras of a take, plus the site (ground) and the light plan (exposure, night, wind) when present.

**Use it to:**

- Add an explosion of a given type, strength and burst height to a Blender scene — a grenade, mortar round, artillery
  shell, aerial bomb, demolition charge, airburst or fuel fireball —
  `components.fx.api.explosion(event, t, camera, ctx, scene)` with
  `event = {"at": 0.0, "c": [x, y, z], "kind": "projectile", "strength": 2.0, "height": 0.0}`.
- Bake a fire-and-smoke body to an OpenVDB cache with Blender's Mantaflow, headless —
  `python -m components.fx.fx_bake bake explosive ejecta --level=low`.
- Render many distant explosions cheaply as pre-rendered cards instead of volumes — `explosions: {cards: auto}`,
  `python -m components.fx.fx_bake cards projectile`.
- Put sustained fire into a scene — a campfire, a burning vehicle or debris, a napalm strip — event `kind: blaze`,
  `fuel` or `napalm`.
- Leave a growing soot scorch on the terrain and let smoke drift and burning columns lean in the wind —
  `explosions: {scorch: true, wind: [4, 1]}`.
- Preview a blast in a fast sketch with sphere, ellipsoid, dome and cone stand-ins timed by the same scaling law —
  `explosions: {look: stand_in}`.

## Features

- **Ten kinds** (`library/fx/explosions.yaml`): hand grenade, mortar round, artillery shell, aerial bomb, demolition
  charge, fuel fireball, airburst, fireball, fire without a blast, napalm line. An event sets kind, power (a multiplier
  of the kind's TNT mass) and burst height. **Eight grounds** — snow, sand, earth, mud, rock, concrete, metal, water — set
  dust colour, albedo and clods; the scene's ground comes from the site's `location.json`.
- **Scaling laws**: size and early phase ∝ W^(1/3) (Hopkinson–Cranz), smoke rise ∝ size^(1/2) (Froude); fuel fireball
  D = 5.8·M^(1/3) m (CCPS); flame height by Heskestad; one baked asset serves events from ×0.25 to ×4 its size.
- **Levels by screen size**: `close` ≥ 150 px (128³ volume, volumetric and lamp shadows), `medium` ≥ 40 px, `far` ≥ 8 px
  (64³ volume or a card), `very_far` — flash only; fewer clods and sparks farther away.
- **Far-plane cards**: each kind rendered once from the high-resolution asset into 8 × 8 atlases of 64 moments with
  six-way lighting (as in game engines), alpha, scattering, tint and emission, relit by the scene's sun and sky; source
  fingerprints mark cards stale after a re-bake.
- **Exposure-relative light**: emission and lamps × 2^(−EV) of the light plan (× 1.4 at night); fire as black-body
  emission from the `flame` field, smoke darkened by soot, a Kelvin-coloured flash lamp, under-lighting that follows the
  fire.
- **Ballistic clods and sparks** without baking (streak = speed × half-frame), a growing soot **scorch** on the terrain,
  **wind** drift by the log profile with an inertia-aware effective time, burning columns leaning from the base.
- **Sketch stand-ins**: a sphere, ellipsoid, dome or cone per layer, sized and timed by the same law and bake summary.
- **Cost**: one explosion adds 0.1–0.2 s per frame; 100 far explosions cost 0.41 s per frame as volumes, 0.25 s as cards.

## How it works

`bl_fx.explosion(event, t, camera, context, scene)` turns an event (start `at`, ground centre `c`, kind, power, height)
and a frame context (exposure, night, ground, fps, wind) into the objects of moment `t`. The step builds them once per
take frame with visibility keys, so the frames output renders them from the `.blend`. Knowledge
`library/fx/explosions.yaml` (scaling, kinds, grounds, levels, bake settings of five assets: explosive body, ground
ejecta, fireball, fuel bursts, burning loop) compiles to `explosions.json` (Blender has no YAML). Bodies are simulated
with Mantaflow into OpenVDB (Blosc, half floats) under `library/fx/<asset>/<level>/` with per-frame statistics;
slimming keeps only the channels the shader reads (3–12× less disk).

## Steps and keys

| Step | Reads → writes | Keys (defaults) |
|---|---|---|
| `explosions` | time, cameras (+ site, light) → time | `level` (auto; `close` … `very_far` force one), `cards` (medium — below `close`; `none`, `auto`, `all`), `seed` (0), `exposure` (light plan's EV), `scorch` (true), `wind` ([ux, uy] m/s at 10 m; light plan's), `look` (full; `sketch`: stand_in) |
| `fx_knowledge` | `explosions.yaml` → `explosions.json` | — |
| `fx_bake` | an asset → OpenVDB cache, `stats.json`, `meta.yaml` | `level` (both levels) |
| `fx_cards` | baked assets → card atlases | — (stale cards) |

All keys with descriptions: [component.yaml](/components/fx/component.yaml)

## Usage

`explosions` runs after a take step (events in `blasts.json`, per-frame cameras `take_NNN`) and after `light`. The
animation component that writes takes is not part of this release; your own Blender scripts reach the mechanism through
`api.py` (`explosion`, `scorch`, `frame_settings`, `knowledge`, `norm_event`, `ground_kind`, `glow_k`, `tidy`).

```yaml
steps:
  # … relief, a take step with explosion events …
  - light: {time: night}
  - explosions: {cards: medium, wind: [4, 1]}   # a light change rebuilds light, explosions, frames; the take stays cached
outputs:
  - frames: {cameras: all}
```

```sh
.venv/bin/python -m components.fx.fx_bake compile                     # knowledge → library/fx/ (explosions.json)
# bake the assets listed in explosions.yaml (--level: 128³, 64³ or both); their cards are re-rendered after the bake
.venv/bin/python -m core.services.guard heavy --what "fx bake" -- .venv/bin/python -m components.fx.fx_bake bake <asset …> [--level=…]
.venv/bin/python -m components.fx.fx_bake cards --stale               # re-render cards whose source changed
# checks — after compile and bake
.venv/bin/python -m components.fx.bench.check                         # 12 stand cases vs golden.json (Blender)
.venv/bin/python -m components.fx.bench.stand_in_check                # stand-ins vs the scaling law, no Blender
blender -b --factory-startup -P core/blender/run.py -- components/fx/bench/stand.py -- <out> [options]   # one explosion by a 1.8 m figure
```

## Driving it from an AI agent

The recipe line goes after `light`. The events (`blasts.json`) and the per-frame `take_NNN` cameras come from a take
step that is not part of this release, so `--dry` refuses `explosions` while nothing provides the `time` layer:

```yaml
steps:
  # … relief, camera, a take step that writes blasts.json and the take_NNN cameras …
  - light: {time: night}
  - explosions: {level: auto, cards: medium, wind: [4, 1], scorch: true, seed: 3}
```

Without a take an agent calls the mechanism directly: bake once (this also compiles `explosions.json` in `library/fx/`), then
use `components.fx.api.explosion` in a Blender script or render one stand frame:

```sh
.venv/bin/python -m core.services.guard heavy --what "fx bake" -- .venv/bin/python -m components.fx.fx_bake bake explosive ejecta --level=low
blender -b --factory-startup -P core/blender/run.py -- components/fx/bench/stand.py -- out/fx kind=projectile strength=2 light=night dist=60 time=0.2,1
```

- All keys with defaults and descriptions: `components/fx/component.yaml`. A recipe run ends with the pipeline's
  `__RESULT__{…}` line and leaves `journal.md` and, in `NN_frames/`, `contact.jpg`; the step's journal line reports
  `explosions`, `objects`, `levels` and `skipped` (a kind with no baked asset). The stand prints a `__STAND__ {json}`
  line (frame time, layers and level per moment) beside the PNGs, and `fx_bake bake` ends with a `__RESULT__` line of
  per-asset rows.
- Request → keys, the event `kind` by name: grenade `grenade`, mortar round `mine`, artillery shell `projectile`, aerial
  bomb `bomb`, demolition charge `charge`, fuel fireball `fuel`, airburst `airburst` (with `height`), fireball
  `fire_ball`, fire without a blast `blaze`, napalm line `napalm`. `strength: 8` (the event's power) is eight times the
  mass and twice the size; the detail level follows the on-screen size by itself, so a distant barrage needs no key but
  `cards`.

## Files

| File | Role |
|---|---|
| `steps.py`, `api.py` | the `explosions` step; public entry |
| `bl_fx.py` | the mechanism: layers, levels, scaling, light, wind, scorch |
| `bl_fx_cards.py`, `card_source.py` | far-plane cards and their source fingerprints |
| `fx_bake.py`, `bl_fx_bake.py`, `bl_fx_slim.py` | knowledge compile; Mantaflow bake; cache slimming |
| `stand_in.py` | sketch stand-ins |
| `bench/` | `check.py`, `stand.py`, `bench.py` (frame cost), `massed.py` (many far blasts), `cases.py`, `stand_in_check.py` |

## Assets

Nothing is downloaded. Bodies are simulated locally with Blender's Mantaflow (`fx_bake bake`): ~10 s (64³) to ~100 s
(128³ with noise, peak memory ~3.6 GB) per asset and level, about 2 GB on disk for five assets at both levels; cards (~2.5 min each) are rendered from
them. Git keeps only the bake summaries (`meta.yaml`); `explosions.json`, caches and cards are generated.

## Limitations

- Events and per-frame cameras come from a take; without one the step stops with a reason.
- No plasma or energy blasts, no explosions in space; a blast on water throws no water column yet.
- Volumes write no depth or masks into the map packs.
- The bake has no adaptive domain; `fx_bake bake` reads the memory peak with macOS `/usr/bin/time -l`.

## FAQ

**How do I add a realistic explosion to a Blender scene with Python?** Bake the assets once with
`fx_bake bake explosive ejecta`, then call `components.fx.api.explosion(event, t, camera, ctx, scene)` in a Blender
script with an event dict:

```python
event = {"at": 0.0, "c": [x, y, z], "kind": "projectile", "strength": 1.0, "height": 0.0}
```

The stand `bench/stand.py kind=projectile` renders the same blast on flat ground beside a 1.8 m figure.

**How do I bake fire and smoke to OpenVDB from the command line?** Run the bake under the heavy-job guard:

```sh
.venv/bin/python -m core.services.guard heavy --what "fx bake" -- .venv/bin/python -m components.fx.fx_bake bake explosive --level=low
```

It runs Blender's Mantaflow headless and writes an OpenVDB cache (Blosc, half floats) with `stats.json` and `meta.yaml`
under `library/fx/explosive/low/`; `--level=all` bakes the 128³ level too. Time and disk are listed under Assets.

**How do I render many distant explosions without slowing Blender down?** Render a kind's cards once with
`fx_bake cards <kind>` (from the baked high-level asset) and keep `cards` on: by default everything below the `close`
level becomes a card (`auto` — only far and very far blasts, `all` — every level), and 100 far explosions cost 0.25 s
per frame as cards against 0.41 s as volumes.

**Which explosions can it make?** Ten kinds — `grenade`, `mine`, `projectile`, `bomb`, `charge`, `fuel`, `airburst`,
`fire_ball`, `blaze`, `napalm` — on eight grounds (snow, sand, earth, mud, rock, concrete, metal, water). Plasma or
energy blasts, explosions in space and a water column from a blast on water are not supported yet.

**Can I use it without the rest of sketch3d?** Yes. FX also ships as its own repository, `sketch3d-blender-explosions`, with the
core it needs. A Blender script uses `components.fx.api` (`explosion`, `scorch`, `frame_settings`, `knowledge`,
`norm_event`, `ground_kind`, `glow_k`, `tidy`); only the `explosions` step needs a take for its events and cameras.
