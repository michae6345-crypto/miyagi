"""Skill tree engine (ui-v4 lane "skills"): tracks -> skills -> steps, mastery, spaced review, proof of a pass.

    catalog.py  the tracks and skills (Adrian's plans catalog, vendored as catalog.json; Blender and CAD included)
    tagging.py  which skills a step practises (deterministic: catalog lesson metadata first, keyword fallback, no model)
    ledger.py   passes, mastery (unassisted on 2 different days), review schedule 3 / 7 / 21 / 60 days
    proofs.py   a size-capped snippet / cell / command output kept as proof of a pass (local only, deletable)
    api.py      the wire payloads: tracks, one skill, mastery, reviews

Everything is local (server.sessions.store.state_dir()), deterministic, and never calls a model or the network.
"""
