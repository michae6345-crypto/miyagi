"""Skill tree engine (ui-v4 lane "skills"): tracks -> skills -> steps, mastery, spaced review, proof of a pass.

    catalog.py  the tracks and skills (Adrian's plans catalog, vendored as catalog.json; Blender and CAD included)
    tagging.py  which skills a step practises (deterministic: catalog lesson metadata first, keyword fallback, no model)
    ledger.py   passes, mastery (unassisted on 2 different days), review schedule 3 / 7 / 21 / 60 days
    proofs.py   the contract Proof: a size-capped code / cell / command kept as proof of a pass (local, deletable)
    graph.py    the tree on progress.graph (SkillGraphInfo round 3: tracks, skills, steps, mastery, schedule)
    service.py  proof.get, and which data.delete kinds remove proofs

Everything is local (server.sessions.store.state_dir()), deterministic, and never calls a model or the network.
"""
