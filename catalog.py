"""Build the item catalog from the player's own game install (and the mods they use).

Reads `set/stuff/**` (items), `set/breed/**` (which nation uses what, typical ammo loads) and the English localization
(in-game names of squads and soldiers). Nothing is copied from the game into the repo: this runs on the user's machine.

Items inherit from `{from "pattern X"}` files and from other items (`{from "fg42"}` = scoped variant); both chains are
resolved so every carryable item gets a grid size, ammo type and nationality.

usage: python catalog.py [out.json]      (debug dump; the server calls build() itself)
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import config

CATS = {"rifle", "smg", "pistol", "mgun", "grenade", "melee", "med", "head", "explosive", "special",
        "bazooka", "flame", "mortar", "gun", "body", "reactive", "bombing", "throwable"}


def block(text, start):
    """Text of the balanced {...} starting at text[start] == '{'."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def child(text, name):
    """First direct child block {name ...} of a top-level block."""
    inner = text[1:-1]
    depth, i = 0, 0
    while i < len(inner):
        c = inner[i]
        if c == "{":
            if depth == 0 and re.match(r"\{%s[\s}]" % re.escape(name), inner[i:i + len(name) + 3]):
                return block(inner, i)
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return None


def parse_item(text):
    text = re.sub(r";[^\n]*", "", text)
    m = text.find("{")
    if m < 0:
        return None
    top = block(text, m)
    d = {"from": None, "from_item": None, "size": None, "tags": [], "filling": None, "weight": None, "block": None}
    f = re.match(r'\{from\s+"pattern ([^"]+)"', top)
    if f:
        d["from"] = f.group(1)
    else:                                   # {from "fg42" ...}: a variant of another ITEM (scoped, bayonet, ...)
        g = re.match(r'\{from\s+"([^"]+)"', top)
        d["from_item"] = g.group(1) if g else None
    inv = child(top, "inventory")
    if inv:
        s = re.search(r"\{size (\d+) (\d+)\}", inv)
        if s:
            d["size"] = [int(s.group(1)), int(s.group(2))]
        b = re.search(r"\{block (\d+)\}", inv)
        if b:
            d["block"] = int(b.group(1))
        w = re.search(r"\{weight (\d+)\}", inv)
        if w:
            d["weight"] = int(w.group(1))
    for t in re.finditer(r'\{tag "([^"]*)"\}', top):
        d["tags"] += t.group(1).split()
    fl = re.search(r'\{filling "ammo ([^"]+)"\s*(\d+)?\}', top)
    if fl:
        d["filling"] = {"ammo": fl.group(1), "count": int(fl.group(2) or 0)}
    else:                                   # machine guns: {filling "mgun_ger" 50} = ammo family; the variant (drum/belt) is in the name
        fg = re.search(r'\{filling "([^"]+)"\s*(\d+)?\}', top)
        if fg:
            d["filling"] = {"ammo": fg.group(1), "count": int(fg.group(2) or 0), "family": True}
    return d


# ------------------------------------------------------------------ sources (vanilla + mods)
def mod_sources(game: Path, workshop: Path | None):
    """[(source_id, display_name, [pak paths])]. source_id is exactly what a save lists in {mods}, minus the ':0'."""
    out = []
    roots = [(p.name, p) for p in sorted((game / "mods").glob("*")) if p.is_dir()]
    if workshop and workshop.is_dir():
        roots += [("mod_" + p.name, p) for p in sorted(workshop.glob("*")) if p.is_dir()]
    for sid, root in roots:
        paks = sorted(root.rglob("*.pak"))
        if not paks:
            continue
        name = sid
        info = next(iter(root.rglob("mod.info")), None)
        if info:
            m = re.search(r'\{name "([^"]+)"', info.read_text(encoding="utf-8", errors="replace"))
            if m:
                name = m.group(1)
        out.append((sid, name, paks))
    return out


# Conquest army code (the save's {army ...}) -> the game's own folders for that army. Verified against the base game:
# conquest unit sets exist for these five (set/multiplayer/units/conquest/units_<army>.set), breeds live in set/breed/mp/<code>/,
# and humanskin/ keeps each army's uniforms in one folder. Any other army (a total conversion, say) is NOT in this table:
# Armory then shows every skin and item instead of guessing.
ARMIES = {
    "ger": {"label": "German", "skins": "germans"},
    "rus": {"label": "Soviet", "skins": "soviets"},
    "eng": {"label": "British", "skins": "united_kingdom"},
    "usa": {"label": "American", "skins": "united_states"},
    "fin": {"label": "Finnish", "skins": "finnish"},
}


# Item-name affixes that name an army ("ger_stalhelm_m43", "us_m1_helmet", "sov_ushanka") -> that army's breed nation code.
HEAD_PREFIX = {"ger": "ger", "us": "usa", "usa": "usa", "sov": "rus", "rus": "rus", "uk": "eng", "eng": "eng", "fin": "fin"}


def army_info(code):
    """{"code", "label", "nation", "skins"} for a known army, else None. `nation` is the breed / item nation folder (same as the code)."""
    a = ARMIES.get((code or "").strip())
    return {"code": code.strip(), "label": a["label"], "nation": code.strip(), "skins": a["skins"]} if a else None


def read_skins(names, sid, out):
    """humanskin/[germans]/ger_heer_43/ger_heer_43_rfl_1.def -> out['ger_heer_43_rfl_1']. First source wins (base game)."""
    for n in names:
        m = re.match(r"humanskin/\[([^\]]+)\]/([^/]+)/([^/]+)\.def$", n)
        if m and m.group(3) not in out:
            out[m.group(3)] = {"nation": m.group(1), "group": m.group(2), "source": sid}


def read_light_ammo(game: Path) -> dict:
    """Infantry-carryable ammo per nation, from the supply crates' own lists (properties/resupply.inc): {'ger': ['rifle_ger.clip', ...]}.
    This is the clean way to tell a rifle clip from a tank shell; the ammo files alone can't."""
    out = {}
    p = game / "resource" / "properties.pak"
    try:
        t = zipfile.ZipFile(p).read("properties/resupply.inc").decode("utf-8", "replace")
    except Exception:
        return out
    for m in re.finditer(r'\(define "items_light_(\w+)"(.*?)\n\)', t, re.S):
        stems = []
        for q in re.finditer(r'\{item((?:\s+"[^"]+")+?)\s+"ammo"', m.group(2)):
            stems.append(".".join(re.findall(r'"([^"]+)"', q.group(1))))
        out[m.group(1)] = stems
    return out


def read_vet_max(game: Path) -> int:
    try:
        t = zipfile.ZipFile(game / "resource" / "gamelogic.pak").read("set/ability/veterancy.set").decode("utf-8", "replace")
        return max(int(x) for x in re.findall(r'\{"lvl_(\d+)"', t))
    except Exception:
        return 8


def breed_summary(text: str) -> dict:
    """What a soldier of this breed starts as: uniform skin, veterancy level and skill layers (see perks.py)."""
    import perks
    sk = re.search(r'\{skin "([^"]+)"\}', text)
    vt = re.search(r'\("veterancy_lvl_(\d+)"\)', text)
    import identity
    return {"skin": sk.group(1) if sk else "", "vet": int(vt.group(1)) if vt else 0, "perks": perks.read(text), **identity.read(text)}


WEAPON_CATS = ("rifle", "smg", "mgun", "pistol", "bazooka", "flame")


def identity_values(breed_files, items=None) -> dict:
    """The icons, tags and portraits the BASE game's breeds use (most common first): the only values Armory offers.
    `by_nation` narrows them to what that nation's own breeds use, so a German soldier isn't offered the US bazooka tag.
    With `items` (the catalog's item table) each nation also gets `tag_for_weapon`: weapon -> the tag the game gives soldiers
    who carry it, kept only where >= 80% of that nation's breeds with the weapon share one non-plain tag (read, not guessed)."""
    import collections
    allic, alltg, allpo = collections.Counter(), collections.Counter(), collections.Counter()
    per = {}
    wtag = {}                                   # (nation, weapon) -> Counter of tags over the breeds that carry it
    for sid, n, t in breed_files:
        if sid:
            continue
        m = re.match(r"set/breed/(?:mp/)?([a-z_]+)/", n)
        ics, tgs, pos = (re.findall(r'\{%s "([^"]+)"\}' % k, t) for k in ("icon", "tags", "portrait"))
        allic.update(ics)
        alltg.update(tgs)
        allpo.update(pos)
        if m:
            c = per.setdefault(m.group(1), (collections.Counter(), collections.Counter(), collections.Counter()))
            c[0].update(ics)
            c[1].update(tgs)
            c[2].update(pos)
            if items:
                tag = tgs[0] if tgs else ""
                inv = t[t.find("{inventory"):] if "{inventory" in t else ""
                for it in set(re.findall(r'\{item "([^"]+)"', inv)):
                    if it.endswith(" ammo") or " ammo " in it or it.endswith(" grenade"):
                        continue
                    key = next((k for k in (it.replace(" ", "."), it.replace(" ", ".") + ".weapon") if k in items), None)
                    if key and items[key]["cat"] in WEAPON_CATS:
                        wtag.setdefault((m.group(1), re.sub(r"\.weapon$", "", key)), collections.Counter())[tag] += 1
    order = lambda c: [k for k, _ in c.most_common()]
    by_nation = {n: {"icons": order(a), "tags": order(b), "portraits": order(p), "tag_for_weapon": {}} for n, (a, b, p) in per.items()}
    for (n, w), c in wtag.items():
        tag, k = c.most_common(1)[0]
        if tag not in ("", "soldier", "crew") and sum(c.values()) >= 2 and k / sum(c.values()) >= 0.8:
            by_nation[n]["tag_for_weapon"][w] = tag
    if "ger" in by_nation and items:                # the German launcher / AT-rifle tags Armory always offered (identity.TAG_FOR_WEAPON)
        import identity
        by_nation["ger"]["tag_for_weapon"] = {**identity.TAG_FOR_WEAPON, **by_nation["ger"]["tag_for_weapon"]}
    return {"icons": order(allic), "tags": order(alltg), "portraits": order(allpo), "by_nation": by_nation}


def read_item_names(game: Path, items: dict, ammo: dict) -> dict:
    """The game's own English names for weapons, gear and ammo (localization desc/weapon|stuff|ammo/<key>), for the
    items Armory knows: {'bazooka_m1a1.weapon': "M1A1 'Bazooka' Anti-tank Launcher", 'rifle_usa.garand_clip': '.30 cal Ball M2 Garand Clip'}."""
    out = {}
    p = game / "localizations" / "default.pak"
    if not p.is_file():
        return out
    pat = re.compile(r'msgctxt "desc/(?:weapon|stuff|ammo)/([^"]+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"')
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if not n.endswith(".pot") or "/desc/" not in n:
                continue
            for key, msg in pat.findall(z.read(n).decode("utf-8", "replace")):
                msg = re.sub(r"</?c(?:\([0-9A-Fa-f]+\))?>", "", msg).replace('\\"', '"').strip()
                k = key.replace(" ", ".")
                for cand in (k, k + ".weapon"):
                    if msg and (cand in items or cand in ammo) and cand not in out:
                        out[cand] = msg
    return out


def read_name_lists(game: Path) -> dict:
    """{'ger': {'first': [...], 'last': [...]}, ...}: the game's own name tables (localizations names/<nation>/first|last).
    A save's {NameId a b} indexes into these. Only base nations (ger, rus, eng, ...), not the civilian / officer variants."""
    out = {}
    p = game / "localizations" / "default.pak"
    if not p.is_file():
        return out
    z = zipfile.ZipFile(p)
    pat = re.compile(r'msgctxt "names/([a-z]+)/(first|last)"\s*\nmsgid "((?:[^"\\]|\\.)*)"')
    for n in z.namelist():
        if "/names/" in n and n.endswith(".pot") and "dlg_names" in n:
            for nation, kind, msg in pat.findall(z.read(n).decode("utf-8", "replace")):
                names = msg.replace('\\"', '"').split("\\n")
                while names and not names[-1]:
                    names.pop()
                out.setdefault(nation, {})[kind] = names
    return out


def read_perks(game: Path) -> dict:
    """The skill presets the game defines (set/breed/presets/perks/*.inc): the only values the Skills section offers."""
    import perks
    out = {}
    try:
        z = zipfile.ZipFile(game / "resource" / "gamelogic.pak")
        for n in ("skills", "health", "specialties", "vision"):
            out[n] = z.read(f"set/breed/presets/perks/{n}.inc").decode("utf-8", "replace")
    except Exception:
        pass
    return perks.read_presets(out)


def read_localization(game: Path) -> dict:
    """In-game English names: {'squads': {template: name}, 'breeds': {'mp/ger/mid/vet_rifle': name}}."""
    out = {"squads": {}, "breeds": {}}
    p = game / "localizations" / "default.pak"
    if not p.is_file():
        return out
    z = zipfile.ZipFile(p)
    pat = re.compile(r'msgctxt "([^"]+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"')
    for n in z.namelist():
        if not n.endswith(".pot") or "/desc/" not in n:
            continue
        for ctx, msg in pat.findall(z.read(n).decode("utf-8", "replace")):
            msg = re.sub(r"<c\([0-9A-Fa-f]+\)>.*?</c>\s*", "", msg).replace('\\"', '"').strip()
            if not msg:
                continue
            if ctx.startswith("desc/squad/"):
                out["squads"][ctx[len("desc/squad/"):]] = msg
            elif ctx.startswith("desc/human/"):
                out["breeds"][ctx[len("desc/human/"):]] = msg
    return out


# ------------------------------------------------------------------ build
def build(game_dir, workshop_dir=None) -> dict:
    game = Path(game_dir)
    workshop = Path(workshop_dir) if workshop_dir else None
    sources = [("", "Base game", [game / "resource" / "gamelogic.pak"])] + mod_sources(game, workshop)
    files = {}                      # path -> (source id, text); later sources (mods) override earlier ones
    breed_files = []                # (source id, path, text)
    skins = {}                      # skin name -> {"nation", "group", "source"}   (humanskin/[germans]/<group>/<name>.def)
    hs = game / "resource" / "entity" / "humanskin.pak"
    if hs.is_file():
        try:
            read_skins(zipfile.ZipFile(hs).namelist(), "", skins)
        except Exception:
            pass
    for sid, _name, paks in sources:
        for p in paks:
            try:
                z = zipfile.ZipFile(p)
            except Exception:
                continue
            read_skins(z.namelist(), sid, skins)
            for n in z.namelist():
                if n.endswith("/"):
                    continue
                if n.startswith("set/stuff/"):
                    if n not in files:          # base game wins: a mod that re-defines a vanilla file (say the smg pattern)
                        files[n] = (sid, z.read(n).decode("utf8", "replace"))   # must not change vanilla item sizes for everyone
                elif n.startswith("set/breed/") and n.endswith(".set"):
                    breed_files.append((sid, n, z.read(n).decode("utf8", "replace")))

    patterns = {}
    for n, (_, t) in files.items():
        if n.endswith(".pattern"):
            patterns.setdefault(Path(n).name[:-8], []).append((n, t))

    def resolve(name, cat, depth=0):
        cands = patterns.get(name, [])
        if not cands or depth > 8:
            return {"size": None, "tags": [], "weight": None}
        pick = next((c for c in cands if f"/{cat}/" in c[0]), cands[0])
        d = parse_item(pick[1]) or {}
        up = resolve(d["from"], cat, depth + 1) if d.get("from") else {"size": None, "tags": [], "weight": None}
        return {"size": d.get("size") or up["size"], "tags": up["tags"] + d.get("tags", []),
                "weight": d.get("weight") or up["weight"]}

    items, ammo = {}, {}
    for n, (sid, t) in sorted(files.items()):
        parts = n.split("/")
        cat = parts[2] if len(parts) > 3 else ""
        base = parts[-1]
        kind = "ammo" if base.endswith(".ammo") else "grenade" if base.endswith(".grenade") else "item"
        if n.endswith(".pattern") or (cat not in CATS and kind == "item") or base.startswith("."):
            continue
        d = parse_item(t)
        if not d:
            continue
        up = resolve(d["from"], cat) if d["from"] else {"size": None, "tags": [], "weight": None}
        stem = base.rsplit(".", 1)[0] if kind != "item" else base
        tokens = stem.split(".") + ([kind] if kind != "item" else [])      # exactly as a save spells it
        rec = {"file": n, "source": sid, "cat": cat, "kind": kind, "tokens": tokens, "pattern": d["from"],
               "size": d["size"] or up["size"], "tags": sorted(set(up["tags"] + d["tags"])),
               "filling": d["filling"], "block": d["block"], "from_item": d["from_item"]}
        (ammo if kind == "ammo" else items)[stem] = rec

    for _ in range(8):              # variants inherit size / ammo / tags from the item they derive from
        for rec in items.values():
            fi = rec.get("from_item") or ""
            if fi.startswith("weapon "):                 # {from "weapon panzershreck_43"} = the file panzershreck_43.weapon
                fi = fi[len("weapon "):] + ".weapon"
            p = items.get(fi) if fi else None
            if p:
                rec["size"] = rec["size"] or p["size"]
                rec["filling"] = rec["filling"] or p["filling"]
                rec["pattern"] = rec["pattern"] or p["pattern"]
                rec["tags"] = sorted(set(rec["tags"]) | set(p["tags"]))

    # nationality + typical carried amounts, from the breeds' own inventories
    nat, use, tot, stk = {}, {}, {}, {}
    tot_o, stk_o = {}, {}            # the same counts for every OTHER nation: only used for stems the German breeds never carry
    binfo = {}                      # breed path -> {"skin": ..., "vet": N}   (what a soldier of that breed starts as)
    fills = {}                      # {item "g43" filling "rifle_ger gewehr ammo" 10}: which ammo a weapon really uses
    for _sid, n, t in breed_files:
        bp = re.match(r"set/breed/(.*)\.set$", n)
        if bp:
            binfo[bp.group(1)] = breed_summary(t)
        for q in re.finditer(r'\{item "([^"]+)" filling "([^"]+?) ammo"', t):
            fills.setdefault(q.group(1).replace(" ", "."), ".".join(q.group(2).split()))
        m = re.match(r"set/breed/(?:mp/)?([a-z_]+)/", n)
        if not m:
            continue
        nation, words = m.group(1), set()
        for q in re.finditer(r'\{item "([^"]+)"(?: ([\d.]+))?(?: ([\d.]+))?', t):
            ws = q.group(1).split()
            words.update(ws)
            if ws[-1] == "ammo" and q.group(2):
                stem = ".".join(ws[:-1])
                t_, k_ = (tot, stk) if nation == "ger" else (tot_o, stk_o)      # German values win (unchanged); others fill the gaps
                t_.setdefault(stem, {}).setdefault(float(q.group(2)), 0)
                t_[stem][float(q.group(2))] += 1
                if q.group(3):
                    k_.setdefault(stem, {}).setdefault(float(q.group(3)), 0)
                    k_[stem][float(q.group(3))] += 1
        for w in words:
            nat.setdefault(w, set()).add(nation)
            u = use.setdefault(w, {})
            u[nation] = u.get(nation, 0) + 1
    for table in (items, ammo):
        for rec in table.values():
            ts = [t for t in rec["tokens"] if t not in ("ammo", "grenade", "weapon", "mine")]
            rec["nations"] = sorted(set().union(*(nat.get(t, set()) for t in ts))) if ts else []
            rec["uses"] = {k: max(use.get(t, {}).get(k, 0) for t in ts) for k in rec["nations"]} if ts else {}
    for rec in items.values():     # headgear is not in any breed's pack (the skin supplies it), so its army comes from its name
        if rec["cat"] == "head" and not rec["nations"]:
            ends = {rec["tokens"][0].split("_")[0], rec["tokens"][0].split("_")[-1]}
            hit = sorted({HEAD_PREFIX[e] for e in ends if e in HEAD_PREFIX})
            if len(hit) == 1:
                rec["nations"], rec["uses"] = hit, {hit[0]: 0}
    for _ in range(8):             # a variant that no breed mentions is still its parent's nationality
        for rec in items.values():
            fi = rec.get("from_item") or ""
            p = items.get(fi[len("weapon "):] + ".weapon" if fi.startswith("weapon ") else fi)
            if p and not rec["nations"]:
                rec["nations"], rec["uses"] = list(p["nations"]), {k: 0 for k in p["nations"]}
    mode = lambda d: int(max(d, key=d.get)) if d else None
    for stem, rec in ammo.items():
        rec["stack"] = mode(stk.get(stem) or stk_o.get(stem)) or rec.get("block")
        rec["total"] = mode(tot.get(stem) or tot_o.get(stem))

    # in-game names for squads / soldiers, and the base breed texts we may need to clone later (see breeds.py)
    return {"items": items, "ammo": ammo, "names": read_localization(game), "light_ammo": read_light_ammo(game), "weapon_fill": fills, "skins": skins, "breed_info": binfo, "vet_max": read_vet_max(game), "perk_presets": read_perks(game), "name_lists": read_name_lists(game), "identity": identity_values(breed_files, items), "item_names": read_item_names(game, items, ammo),
            "mods": {sid: name for sid, name, _ in sources if sid},
            "game_dir": str(game), "workshop_dir": str(workshop or "")}


def main(out="catalog.json"):
    r = config.resolved()
    if not r["game_ok"]:
        raise SystemExit("Game folder not found. Run the editor and use Settings, or edit config.json.")
    d = build(r["game_dir"], r["workshop_dir"] or None)
    json.dump(d, open(out, "w"), indent=1)
    print(len(d["items"]), "items,", len(d["ammo"]), "ammo types,", len(d["mods"]), "mods ->", out)


if __name__ == "__main__":
    main(*sys.argv[1:2])
