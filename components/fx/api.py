"""Public entry of the Effects component (ARCHITECTURE.md: a mechanism belongs to its owner, neighbors call the api): the
explosions of a take. The Time component places the explosions of its beats from here — the kind knowledge, the event,
the explosion itself, the scorch, the frame light; the internal modules of Effects (bl_fx) change freely while the entry
holds. The Blender part loads on first access (the entry imports without Blender)."""

_BL = ("explosion", "frame_settings", "glow_k", "ground_kind", "knowledge", "norm_event", "scorch", "tidy")   # bl_fx


def __getattr__(name):
    if name in _BL:
        from components.fx import bl_fx
        return getattr(bl_fx, name)
    raise AttributeError(f"components.fx.api: no '{name}'")
