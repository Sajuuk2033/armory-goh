"""Armory loadout engine: parse / edit / serialize one soldier's {Inventory} block.

Every rule the UI relies on lives here (auto-place, ammo follow the weapon, fit checks) so it is tested once.
A loadout is a plain dict (JSON-friendly):
  {"eid": "0xb006", "entries": [ {"id": 0, "tokens": ["k98"], "mid": ["filled"], "x": 0, "y": 0, "user": "hand_right"|None,
                                  "role": "primary", "size": [6, 2]}, ... ], "extra": [raw lines we do not understand]}
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

LAUNCHER_CATS = ("bazooka", "flame")        # what the Launcher slot offers (not mines, charges, binoculars...)
GRID_W, GRID_H = 8, 11         # width 8 confirmed; height = tallest pack seen in real saves (true limit unknown)
HERE = Path(__file__).parent
DEFAULT_ROUNDS = {"rifle": 60, "smg": 224, "pistol": 32, "mgun": 600, "bazooka": 0}

_ITEM = re.compile(r'^\s*\{item ((?:"[^"]+"\s*)+)(.*?)\{cell (\d+) (\d+)\}(?:\{user "([^"]+)"\})?\}\s*$')


class LoadoutError(ValueError):
    pass


class Catalog:
    def __init__(self, data=HERE / "catalog.json"):
        if isinstance(data, dict):
            d = data
        else:
            with open(data, encoding="utf-8") as f:
                d = json.load(f)
        self.items, self.ammo = d["items"], d["ammo"]
        self.names = d.get("names") or {"squads": {}, "breeds": {}}
        self.mods = d.get("mods") or {}
        self.light = d.get("light_ammo") or {}
        self.skins = d.get("skins") or {}
        self.breed_info = d.get("breed_info") or {}
        self.vet_max = d.get("vet_max", 8)
        self.perk_presets = d.get("perk_presets") or {}
        self.name_lists = d.get("name_lists") or {}
        self.identity = d.get("identity") or {"icons": [], "tags": []}
        self.fill = d.get("weapon_fill") or {}         # weapon -> ammo stem, where breeds say so explicitly
        self.item_names = d.get("item_names") or {}    # the game's own English names for weapons / gear / ammo

    def lookup(self, tokens):
        kind = tokens[-1] if tokens[-1] in ("ammo", "grenade") else "item"
        stem = ".".join(tokens[:-1] if kind != "item" else tokens)
        rec = (self.ammo if kind == "ammo" else self.items).get(stem)
        return kind, stem, rec

    def role(self, tokens):
        kind, stem, rec = self.lookup(tokens)
        if not rec:
            return "other"
        if kind == "ammo":
            return "ammo"
        if kind == "grenade":
            return "grenade"
        cat, tags = rec["cat"], rec["tags"]
        if "head" in tags or cat == "head":
            return "head"
        if cat in ("bazooka", "flame", "mortar", "reactive", "explosive", "special"):
            return "launcher"          # carried IN ADDITION to the rifle; spelling in saves unverified -> not offered in v1
        if cat in ("rifle", "smg", "mgun"):
            return "primary"
        if cat == "pistol":
            return "sidearm"
        if cat == "med":
            return "medical"
        return "tool"

    def size(self, tokens):
        rec = self.lookup(tokens)[2]
        return list(rec["size"]) if rec and rec["size"] else [1, 1]

    def stack(self, stem):
        r = self.ammo.get(stem, {})
        return r.get("stack") or r.get("block") or 1

    def total(self, stem):
        return self.ammo.get(stem, {}).get("total")

    def tokens(self, name):
        """Exact save spelling for a catalog key: 'k98' -> ['k98'], 'm24' -> ['m24','grenade'], 'x.weapon' -> ['x','weapon']."""
        rec = self.items.get(name)
        if not rec:
            raise LoadoutError(f"Unknown item {name}")
        return list(rec["tokens"])

    def weapon_ammo(self, name):
        """Ammo stem a weapon uses. Resolved from its own filling; breeds' explicit fillings only fill the gaps."""
        stem = self._weapon_ammo(name)
        if (stem is None or stem not in self.ammo) and self.fill.get(name) in self.ammo:
            return self.fill[name]
        return stem

    def _weapon_ammo(self, name):
        """Ammo stem a weapon uses, e.g. 'k98' -> 'rifle_ger.clip' (None if it takes none)."""
        rec = self.items.get(name)
        if not rec or not rec["filling"]:
            return None
        stem = ".".join(rec["filling"]["ammo"].split())
        if stem in self.ammo or not rec["filling"].get("family"):
            return stem
        # an ammo FAMILY ('mgun_ger'): the variant is spelled in the weapon's name (mg42_drum -> mgun_ger.drum)
        words = set(re.split(r"[_.]", name))
        best = None
        for k in self.ammo:
            if not k.startswith(stem + "."):
                continue
            parts = k[len(stem) + 1:].split(".")
            if parts[0] in words and all(p in words for p in parts[1:]):
                if best is None or len(k) > len(best):
                    best = k
        return best


# ---------------------------------------------------------------- parse / serialize
def parse(block_text: str, cat: Catalog) -> dict:
    """block_text = the text of one '\\t{Inventory 0xEID ... \\t}' block (any newline style)."""
    lines = block_text.replace("\r", "").split("\n")
    head = re.match(r"\s*\{Inventory (0x[0-9a-fA-F]+)", lines[0])
    if not head:
        raise LoadoutError("not an Inventory block")
    entries, extra = [], []
    for ln in lines[1:]:
        m = _ITEM.match(ln)
        if not m:
            if ln.strip() not in ("", "{box", "{clear}", "}"):
                extra.append(ln)
            continue
        toks = re.findall(r'"([^"]+)"', m.group(1))
        mid = [t for t in m.group(2).split() if t]
        e = {"id": len(entries), "tokens": toks, "key": cat.lookup(toks)[1], "mid": mid, "x": int(m.group(3)), "y": int(m.group(4)),
             "user": m.group(5)}
        e["role"] = cat.role(toks)
        e["size"] = cat.size(toks)
        entries.append(e)
    return {"eid": head.group(1), "entries": entries, "extra": extra}


def serialize(lo: dict) -> str:
    out = ["\t{Inventory %s" % lo["eid"], "\t\t{box", "\t\t\t{clear}"]
    for e in lo["entries"]:
        names = " ".join('"%s"' % t for t in e["tokens"])
        mid = (" " + " ".join(e["mid"])) if e["mid"] else ""
        user = '{user "%s"}' % e["user"] if e["user"] else ""
        out.append("\t\t\t{item %s%s {cell %d %d}%s}" % (names, mid, e["x"], e["y"], user))
    out += lo.get("extra", [])
    out += ["\t\t}", "\t}"]
    return "\n".join(out)


# ---------------------------------------------------------------- grid helpers
def occupied(lo, skip_id=None):
    g = set()
    for e in lo["entries"]:
        if e["id"] == skip_id:
            continue
        for dx in range(e["size"][0]):
            for dy in range(e["size"][1]):
                g.add((e["x"] + dx, e["y"] + dy))
    return g


def fits_at(lo, size, x, y, skip_id=None):
    if x < 0 or y < 0 or x + size[0] > GRID_W or y + size[1] > GRID_H:
        return False
    g = occupied(lo, skip_id)
    return all((x + dx, y + dy) not in g for dx in range(size[0]) for dy in range(size[1]))


def find_spot(lo, size, prefer=None):
    if prefer and fits_at(lo, size, *prefer):
        return prefer
    for y in range(GRID_H):
        for x in range(GRID_W):
            if fits_at(lo, size, x, y):
                return (x, y)
    return None


def used_cells(lo):
    return len(occupied(lo))


def _next_id(lo):
    return max([e["id"] for e in lo["entries"]], default=-1) + 1


def _new_entry(lo, tokens, cat, mid=None, user=None, x=0, y=0):
    e = {"id": _next_id(lo), "tokens": list(tokens), "key": cat.lookup(list(tokens))[1], "mid": list(mid or []), "x": x, "y": y, "user": user,
         "role": cat.role(tokens), "size": cat.size(tokens)}
    return e


def _place(lo, e, prefer=None):
    spot = find_spot(lo, e["size"], prefer)
    if spot is None:
        # last resort: repack everything (largest first) and retry once
        repack(lo)
        spot = find_spot(lo, e["size"])
    if spot is None:
        return False
    e["x"], e["y"] = spot
    lo["entries"].append(e)
    return True


def repack(lo):
    """Re-place every entry first-fit, largest first (stable). Keeps worn/held marks."""
    entries = sorted(lo["entries"], key=lambda e: (-(e["size"][0] * e["size"][1]), e["id"]))
    lo["entries"] = []
    for e in entries:
        spot = find_spot(lo, e["size"])
        if spot is None:
            raise LoadoutError("Not enough room to arrange the pack")
        e["x"], e["y"] = spot
        lo["entries"].append(e)


# ---------------------------------------------------------------- operations (pure: return a new loadout + messages)
def _ammo_entries(lo, stem):
    return [e for e in lo["entries"] if e["role"] == "ammo" and ".".join(e["tokens"][:-1]) == stem]


def _weapons(lo, cat):
    return [e for e in lo["entries"] if e["role"] in ("primary", "sidearm", "launcher") and "filled" in e["mid"]]


def _long_guns(lo):
    """Rifle/SMG/MG entries that are loaded weapons: the one in his hands first, then any backup carried in the pack."""
    gs = [e for e in lo["entries"] if e["role"] == "primary" and "filled" in e["mid"]]
    return sorted(gs, key=lambda e: e["user"] != "hand_right")


def held_gun(lo):
    gs = _long_guns(lo)
    return gs[0] if gs else None


def backup_guns(lo):
    return _long_guns(lo)[1:]


def _stack_count(cat, stem, rounds_default):
    return max(1, math.ceil((cat.total(stem) or rounds_default) / cat.stack(stem)))


def equip(lo, cat, role, name, *, same_family_keep=True):
    """Replace the primary / sidearm / head item with `name`. Ammo follows the weapon automatically."""
    lo = copy.deepcopy(lo)
    msgs = []
    rec = cat.items.get(name)
    if not rec:
        raise LoadoutError(f"Unknown item {name}")
    if cat.role(cat.tokens(name)) != ("primary" if role == "backup" else role):
        raise LoadoutError(f"{name} is not a {role} item")
    if role == "launcher" and rec["cat"] not in LAUNCHER_CATS:
        raise LoadoutError(f"{name} is not a launcher")

    if role == "head":
        old = next((e for e in lo["entries"] if e["role"] == "head" and e["user"] == "head"), None)
        hidx = lo["entries"].index(old) if old else None
        if old:
            lo["entries"].remove(old)
        spare = next((e for e in lo["entries"] if e["tokens"] == cat.tokens(name)), None)   # already carried -> just wear it
        if spare:
            spare["user"] = "head"
        else:
            e = _new_entry(lo, cat.tokens(name), cat, user="head")
            if not _place(lo, e, prefer=(old["x"], old["y"]) if old else None):
                raise LoadoutError("Not enough room for that headgear")
            if hidx is not None:
                lo["entries"].remove(e)
                lo["entries"].insert(min(hidx, len(lo["entries"])), e)
        msgs.append(f"Headgear: {old['tokens'][0] if old else 'none'} -> {name}")
        return lo, msgs

    # weapons
    if role == "primary":
        old = held_gun(lo)                          # the gun in his hands, never the backup in the pack
    elif role == "backup":
        bs = backup_guns(lo)
        old = bs[0] if bs else None
    else:
        olds = [e for e in lo["entries"] if e["role"] == role and "filled" in e["mid"]]
        old = olds[0] if olds else None
    old_stem = cat.weapon_ammo(old["key"]) if old else None
    new_stem = cat.weapon_ammo(name)
    user = old["user"] if old else ("hand_right" if role == "primary" else None)
    prefer = (old["x"], old["y"]) if old else None
    idx = lo["entries"].index(old) if old else None
    if old:
        lo["entries"].remove(old)
    e = _new_entry(lo, cat.tokens(name), cat, mid=["filled"], user=user)
    if not _place(lo, e, prefer):
        raise LoadoutError("Not enough room for that weapon")
    if idx is not None and e in lo["entries"] and lo["entries"].index(e) != idx:
        lo["entries"].remove(e)
        lo["entries"].insert(min(idx, len(lo["entries"])), e)

    if new_stem and new_stem != old_stem:
        # drop ammo of the old weapon unless another carried weapon still uses it
        still_used = {cat.weapon_ammo(w["key"]) for w in _weapons(lo, cat) if w["id"] != e["id"]}
        n_old = 0
        if old_stem and old_stem not in still_used:
            stacks = _ammo_entries(lo, old_stem)
            n_old = len(stacks)
            for s in stacks:
                lo["entries"].remove(s)
        have = _ammo_entries(lo, new_stem)
        if cat.total(new_stem) is None and DEFAULT_ROUNDS.get(rec["cat"], 60) == 0:
            want = 0 - len(have)                    # single-shot launchers (panzerfaust): the weapon IS the round, no spares
        else:
            want = _stack_count(cat, new_stem, DEFAULT_ROUNDS.get(rec["cat"], 60)) - len(have)
        added = 0
        block = cat.stack(new_stem)
        tokens = new_stem.split(".") + ["ammo"]
        for _ in range(max(0, want)):
            a = _new_entry(lo, tokens, cat, mid=[str(block)])
            if _place(lo, a):
                added += 1
            else:
                break
        msgs.append(f"{role.capitalize()}: {old['tokens'][0] if old else 'none'} -> {name}")
        msgs.append(f"Ammo: {n_old} old stack(s) removed, {added} new stack(s) of {new_stem.replace('.', ' ')} added")
        if added < want:
            msgs.append("Warning: pack is full, fewer magazines than usual were added")
    else:
        msgs.append(f"{role.capitalize()}: {old['tokens'][0] if old else 'none'} -> {name} (ammo unchanged)")
    return lo, msgs


def add_item(lo, cat, name, count=1):
    """Add grenade / medical / tool items. Names: 'm24_splinter' (grenade) or 'bandage_ger'."""
    lo = copy.deepcopy(lo)
    tokens = cat.tokens(name)
    added = 0
    for _ in range(count):
        e = _new_entry(lo, tokens, cat)
        if not _place(lo, e):
            break
        added += 1
    if added == 0:
        raise LoadoutError("Not enough room")
    return lo, [f"Added {added}x {name}" + ("" if added == count else f" (only {added} fit)")]


def remove_entry(lo, entry_id):
    lo = copy.deepcopy(lo)
    e = next((e for e in lo["entries"] if e["id"] == entry_id), None)
    if not e:
        raise LoadoutError("No such item")
    lo["entries"].remove(e)
    return lo, [f"Removed {e['tokens'][0]}"]


def move_entry(lo, entry_id, x, y):
    lo = copy.deepcopy(lo)
    e = next((e for e in lo["entries"] if e["id"] == entry_id), None)
    if not e:
        raise LoadoutError("No such item")
    if not fits_at(lo, e["size"], x, y, skip_id=entry_id):
        raise LoadoutError("That spot is taken or out of the pack")
    e["x"], e["y"] = x, y
    return lo, []


def set_ammo_stacks(lo, cat, stem, n):
    """Set how many magazines/clips of an ammo type are carried."""
    lo = copy.deepcopy(lo)
    have = _ammo_entries(lo, stem)
    block = cat.stack(stem)
    tokens = stem.split(".") + ["ammo"]
    while len(have) > n:
        lo["entries"].remove(have.pop())
    while len(have) < n:
        a = _new_entry(lo, tokens, cat, mid=[str(block)])
        if not _place(lo, a):
            raise LoadoutError(f"Only {len(have)} fit in the pack")
        have.append(a)
    return lo, [f"{stem.replace('.', ' ')}: {n} stack(s)"]


def add_ammo(lo, cat, stem, count=1):
    """Carry `count` more magazines/belts/clips of an ammo type (any type: an assistant gunner's spare drums, say)."""
    have = len(_ammo_entries(lo, stem))
    return set_ammo_stacks(lo, cat, stem, have + max(1, int(count)))


def auto_sort(lo):
    """Tidy the pack: weapons, then ammo, grenades, medical, tools; big items first. Worn/held marks are kept."""
    lo = copy.deepcopy(lo)
    order = {"primary": 0, "sidearm": 1, "head": 2, "ammo": 3, "grenade": 4, "medical": 5}
    ids = {e["id"]: i for i, e in enumerate(lo["entries"])}
    lo["entries"].sort(key=lambda e: (order.get(e["role"], 6), -(e["size"][0] * e["size"][1]), e["key"], ids[e["id"]]))
    entries = list(lo["entries"])
    lo["entries"] = []
    for e in entries:
        spot = find_spot(lo, e["size"])
        if spot is None:                   # first-fit failed: fall back to largest-first, which packs tighter
            lo["entries"] = entries
            repack(lo)
            return lo, ["Pack tidied (tight fit)"]
        e["x"], e["y"] = spot
        lo["entries"].append(e)
    return lo, ["Pack sorted: weapons, ammo, grenades, medical, tools"]


def ammo_candidates(lo, cat, nations=None, sources=None):
    """Every ammo type the picker can offer. Ammo for weapons this soldier already carries comes first.
    nations: breed nations to offer (e.g. ["usa"]); None = every nation."""
    fits_for = {}                                     # ammo stem -> names of the carried weapons that fire it
    for w in _weapons(lo, cat):
        s = cat.weapon_ammo(w["key"])
        if s:
            fits_for.setdefault(s, []).append(w["key"])
    carried = set(fits_for)
    have = {}
    for e in lo["entries"]:
        if e["role"] == "ammo":
            k = ".".join(e["tokens"][:-1])
            have[k] = have.get(k, 0) + 1
    nats = nations or list(cat.light)
    allowed = set(carried)
    for n in ["generic"] + list(nats):
        allowed.update(cat.light.get(n, []))
    out = []
    for stem, rec in cat.ammo.items():
        if sources is not None and rec.get("source", "") not in sources:
            continue
        mod_ammo = rec.get("source", "") != "" and rec.get("cat") in ("rifle", "smg", "pistol", "mgun") \
            and (not nations or set(nations) & set(rec.get("nations") or []))
        if stem not in allowed and not mod_ammo:
            continue
        tokens = stem.split(".") + ["ammo"]
        size = cat.size(tokens)
        ok = find_spot(lo, size) is not None
        out.append({"name": stem, "size": size, "stack": cat.stack(stem), "have": have.get(stem, 0), "carried": stem in carried, "for_weapons": fits_for.get(stem, []),
                    "fits": ok, "why": "" if ok else f"No room (needs {size[0]}x{size[1]})",
                    "mod": cat.mods.get(rec.get("source", ""), ""), "source": rec.get("source", "")})
    out.sort(key=lambda r: (not r["carried"], not r["fits"], -(r["have"] > 0), r["name"]))
    return out


def candidates(lo, cat, role, nations=None, sources=None):
    """Picker data for a slot: every catalog item of that role with a fit flag + reason. (grenade/medical/tool also)
    nations: breed nations to offer (e.g. ["rus"]); None = every nation.
    sources: allowed item sources ('' = base game, else mod ids). None = everything."""
    out = []
    pref = nations[0] if nations else None                # whose usage counts decide the order; None = busiest nation
    use_of = lambda rec: (rec.get("uses") or {}).get(pref, 0) if pref else max((rec.get("uses") or {}).values(), default=0)
    rows = [(k, r) for k, r in cat.items.items() if r["size"] and (sources is None or r.get("source", "") in sources)]
    for name, rec in rows:
        tokens = rec["tokens"]
        if cat.role(tokens) != ("primary" if role == "backup" else role):
            continue
        if role == "launcher" and rec["cat"] not in LAUNCHER_CATS:
            continue
        if nations and not (set(nations) & set(rec["nations"])):
            continue
        ok, why = True, ""
        if role in ("primary", "sidearm", "head", "launcher", "backup"):
            try:
                equip(lo, cat, role, name)
            except LoadoutError as ex:
                ok, why = False, str(ex)
        else:
            if find_spot(lo, rec["size"]) is None:
                ok, why = False, f"No room (needs {rec['size'][0]}x{rec['size'][1]})"
        out.append({"name": name, "display": tokens[0], "size": rec["size"], "fits": ok, "why": why, "cat": rec["cat"],
                    "uses": use_of(rec), "nations": rec["nations"],
                    "source": rec.get("source", ""), "mod": cat.mods.get(rec.get("source", ""), ""),
                    "ammo": cat.weapon_ammo(name) if role in ("primary", "sidearm", "launcher", "backup") else None})
    out.sort(key=lambda r: (not r["fits"], -r["uses"], r["name"]))
    return out


def diff(before, after):
    """Plain-language list of what changed, comparing two loadouts of the same soldier."""
    def bag(lo):
        c = {}
        for e in lo["entries"]:
            k = (e["role"], " ".join(e["tokens"]), e["user"])
            c[k] = c.get(k, 0) + 1
        return c
    a, b = bag(before), bag(after)
    out = []
    for k in sorted(set(a) | set(b)):
        d = b.get(k, 0) - a.get(k, 0)
        if d:
            out.append(("+" if d > 0 else "-") + f"{abs(d)} {k[1]}" + (" (worn)" if k[2] == "head" else ""))
    return out
