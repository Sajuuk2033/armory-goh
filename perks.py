"""Soldier skills ("perks") live in a breed's {perks} block as preset tokens, e.g.  ("rifle_skill_rank_2")("tier2_standard")("at_rank_3").

The game defines the presets in set/breed/presets/perks/{skills,health,specialties}.inc. They fall into independent layers:

  skill    which weapon he is trained with and how well:  skill_rank_0, rifle|smg|mg|loader|loader_smg _skill_rank_1..5
  tier     toughness: health, stamina, speed.  tier1..4 _ standard | recon (fast, fragile) | defense (slow, regenerates)
  at       anti-tank / rocket skill: at_rank_1..6
  extras   one-off specialties: stealth, medic, marksman, sniper_vision, binocular_vision, skilled_repair, engineer

A "spec" is {"skill": name|None, "tier": name|None, "at": 0..6, "extras": [names]}. `read` pulls a spec out of breed text; `apply`
rewrites only the layers named in the spec, so anything else in the block (include lines, tank crew presets, {"health" ...} pairs) is kept.
"""
from __future__ import annotations

import re

from catalog import block

SKILL_RE = re.compile(r"^(?:skill_rank_0|(rifle|smg|mg|loader|loader_smg)_skill_rank_([1-5])|loader_skill_smg_rank_([1-5]))$")
TIER_RE = re.compile(r"^(?:tier([1-4])_(standard|recon|defense))$")
AT_RE = re.compile(r"^at_rank_([1-6])$")
EXTRAS = ["stealth", "medic", "marksman", "sniper_vision", "binocular_vision", "skilled_repair", "engineer"]
TOKEN = re.compile(r'\("([^"]+)"\)')


def classify(name: str):
    """('skill'|'tier'|'at'|'extra'|None, parsed parts)."""
    m = SKILL_RE.match(name)
    if m:
        if name == "skill_rank_0":
            return "skill", ("", 0)
        if m.group(3):
            return "skill", ("loader_smg", int(m.group(3)))
        return "skill", (m.group(1), int(m.group(2)))
    m = TIER_RE.match(name)
    if m:
        return "tier", (int(m.group(1)), m.group(2))
    m = AT_RE.match(name)
    if m:
        return "at", int(m.group(1))
    if name in EXTRAS:
        return "extra", name
    return None, None


def perks_block(text: str) -> str | None:
    i = text.find("{perks")
    return block(text, i) if i >= 0 else None


def read(text: str) -> dict | None:
    """The editable layers of a breed's {perks}, or None when the breed has no {perks} block."""
    b = perks_block(text)
    if b is None:
        return None
    spec = {"skill": None, "tier": None, "at": 0, "extras": []}
    for name in TOKEN.findall(b):
        kind, _ = classify(name)
        if kind == "skill" and spec["skill"] is None:
            spec["skill"] = name
        elif kind == "tier" and spec["tier"] is None:
            spec["tier"] = name
        elif kind == "at":
            spec["at"] = max(spec["at"], classify(name)[1])
        elif kind == "extra" and name not in spec["extras"]:
            spec["extras"].append(name)
    return spec


def clean(spec: dict | None) -> dict | None:
    """Validate a spec from the UI; raise ValueError on anything the game doesn't define."""
    if not spec:
        return None
    out = {}
    if "skill" in spec:
        s = spec["skill"]
        if s is not None and classify(s)[0] != "skill":
            raise ValueError(f"Unknown weapon skill: {s}")
        out["skill"] = s
    if "tier" in spec:
        t = spec["tier"]
        if t is not None and classify(t)[0] != "tier":
            raise ValueError(f"Unknown toughness level: {t}")
        out["tier"] = t
    if "at" in spec:
        a = int(spec["at"] or 0)
        if not 0 <= a <= 6:
            raise ValueError(f"Anti-tank skill must be 0-6, not {a}")
        out["at"] = a
    if "extras" in spec:
        bad = [e for e in spec["extras"] if e not in EXTRAS]
        if bad:
            raise ValueError(f"Unknown specialty: {', '.join(bad)}")
        out["extras"] = list(dict.fromkeys(spec["extras"]))
    return out


def apply(text: str, spec: dict) -> str:
    """Breed text with the layers named in `spec` replaced. Layers not in the spec are left exactly as they were."""
    spec = clean(spec)
    if not spec:
        return text
    i = text.find("{perks")
    if i < 0:
        raise ValueError("base breed has no {perks} block")
    old = block(text, i)
    drop = set()
    for name in TOKEN.findall(old):
        kind, _ = classify(name)
        if (kind == "skill" and "skill" in spec) or (kind == "tier" and "tier" in spec) or \
           (kind == "at" and "at" in spec) or (kind == "extra" and "extras" in spec):
            drop.add(name)
    body = TOKEN.sub(lambda m: "" if m.group(1) in drop else m.group(0), old)
    add = []
    if spec.get("skill"):
        add.append(spec["skill"])
    if spec.get("tier"):
        add.append(spec["tier"])
    add += spec.get("extras", [])
    if spec.get("at"):
        add.append(f"at_rank_{spec['at']}")
    body = re.sub(r"\n[ \t]*\n", "\n", body)                     # lines emptied by the removals
    body = body.rstrip()
    if not body.endswith("}"):
        raise ValueError("unbalanced {perks} block")
    new = body[:-1].rstrip() + "\n\t\t" + "".join('("%s")' % n for n in add) + "\n\t}"
    return text[:i] + new + text[i + len(old):]


def read_presets(pak_text: dict) -> dict:
    """What the UI may offer, from the game's own preset names. pak_text = {file stem: text of the .inc}."""
    names = []
    for t in pak_text.values():
        names += re.findall(r'\(define "([^"]+)"', t)
    bodies = {}
    for t in pak_text.values():
        for m in re.finditer(r'\(define "([^"]+)"(.*?)(?=\n\(define "|\Z)', t, re.S):
            bodies[m.group(1)] = m.group(2)
    num = lambda body, key: (lambda m: float(m.group(1)) / (100 if m.group(2) else 1) if m else None)(
        re.search(r'\{"%s"\s+"?([\d.]+)("?%%)?' % key, body))
    skills, tiers, ats = [], [], set()
    for n in names:
        kind, p = classify(n)
        if kind == "skill":
            # what this preset sets for each weapon family, e.g. rifle_skill_rank_2 -> rifle 3, pistol 3, everything else 2
            levels = {k: int(v) for k, v in re.findall(r'\{"(pistol|smg|mgun|mgun_light|rifle|melee|avoidance)"\s+lvl_(\d+)\}', bodies.get(n, ""))}
            skills.append({"name": n, "family": p[0], "level": p[1], "levels": levels})
        elif kind == "tier":
            b = bodies.get(n, "")
            sp = re.search(r'\{"speed"\s+([\d.]+)', b)
            tiers.append({"name": n, "tier": p[0], "style": p[1], "health": num(b, "health"), "regen": num(b, "health_regeneration"),
                          "stamina": num(b, "stamina"), "speed": float(sp.group(1)) if sp else None})
        elif kind == "at":
            ats.add(p)
    return {"skills": skills, "tiers": tiers, "at_max": max(ats) if ats else 0, "extras": [e for e in EXTRAS if e in names]}
