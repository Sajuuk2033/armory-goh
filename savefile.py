"""Read Conquest saves for the Armory UI and write edited COPIES.

Rules: never modify a source save; the copy gets a new campaign name (the game saves back to <name>.sav, so a copy that
kept the old name would overwrite the original on the next in-game save).
"""
from __future__ import annotations

import io
import re
import subprocess
import time
import zipfile
from pathlib import Path

import breeds
import config
import loadout as lo

HERE = Path(__file__).parent
BACKUPS = HERE / "backups"
GAME_EXE = "call_to_arms.exe"

_HUMAN = re.compile(r'\t\{Human "([^"]+)" (0x[0-9a-fA-F]+)')
_INV = re.compile(r"\t\{Inventory (0x[0-9a-fA-F]+)\n.*?\n\t\}", re.S)

ROLE_NAMES = {
    "rifleman": "Rifleman", "nco": "NCO", "nco_asst": "NCO assistant", "vet_rifle": "Veteran rifleman",
    "vet_sa": "Veteran semi-auto rifleman", "vet_nco": "Veteran NCO", "vet_nco_asst": "Veteran NCO assistant",
    "vet_mg": "Veteran MG gunner", "vet_mg_asst": "Veteran MG assistant", "medic": "Medic",
    "recon_rifle": "Recon rifleman", "recon_sl_asst": "Recon assistant", "pioneer_1": "Pioneer",
    "pioneer_4": "Pioneer", "pioneer_mgun_asst": "Pioneer MG assistant", "mgun_42": "MG gunner",
    "officer": "Officer", "sniper": "Sniper", "antitank_1": "Anti-tank", "engineer": "Engineer",
}


def pretty_role(breed: str, cat: lo.Catalog | None = None) -> str:
    nm = cat.names["breeds"].get(breed) if cat else None
    if nm:                                           # the game's own English name, minus the "[Heer]" faction tag
        return re.sub(r"\s*\[[^\]]*\]\s*$", "", nm)
    base = breed.rsplit("/", 1)[-1]
    base = re.sub(r"_\d+$", "", base) if base not in ROLE_NAMES else base
    return ROLE_NAMES.get(base) or base.replace("_", " ").strip().capitalize()


def game_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH"], capture_output=True, text=True,
                             timeout=5).stdout
        return GAME_EXE.lower() in out.lower()
    except Exception:
        return False


def find_campaign_dirs():
    return config.campaign_dirs()


def save_mods(status: str) -> list[str]:
    """Mod ids a save was made with, e.g. ['mod_1000002', 'female_soldiers'] (the ':0' suffix dropped)."""
    m = re.search(r"\{mods\s*(.*?)\}", status.replace("\r", ""), re.S)
    return [x.split(":")[0] for x in re.findall(r'"([^"]+)"', m.group(1))] if m else []


def _read(path):
    z = zipfile.ZipFile(path)
    return z, z.read("campaign.scn").decode("utf-8"), z.read("status").decode("utf-8")


def _status_field(status, tag):
    m = re.search(r"\{%s ([^}\n]*)\}" % tag, status.replace("\r", ""))
    return m.group(1).strip().strip('"') if m else ""


def list_saves():
    out = []
    for d in find_campaign_dirs():
        for p in d.glob("*.sav"):
            try:
                z = zipfile.ZipFile(p)
                if "campaign.scn" not in z.namelist():
                    continue
                st = z.read("status").decode("utf-8", "replace")
                out.append({"file": p.name, "dir": str(d), "name": _status_field(st, "name") or p.stem,
                            "army": _status_field(st, "army"), "mtime": p.stat().st_mtime, "size": p.stat().st_size,
                            "mods": len(re.findall(r'"mod_\d+', st))})
            except Exception:
                continue
    out.sort(key=lambda s: -s["mtime"])
    return out


def resolve(file, base_dir):
    """Only allow *.sav directly inside a known campaign folder (blocks path tricks)."""
    p = (Path(base_dir) / file).resolve()
    if p.suffix != ".sav" or p.parent not in [d.resolve() for d in find_campaign_dirs()]:
        raise ValueError("Not a campaign save")
    return p


def _human_span(text, eid):
    """(start, end) of the soldier's one-tab-indented {Human "breed" EID ...} block, or None."""
    m = re.search(r'\t\{Human "[^"]+" %s\b' % re.escape(eid), text)
    if not m:
        return None
    end = text.find("\n\t}", m.end())
    return (m.start(), end if end >= 0 else len(text))


def human_vet(text, eid):
    """Veterancy level stored in the save for this soldier (None when the save has no explicit value)."""
    sp = _human_span(text, eid)
    v = re.search(r"\{Veterancy (\d+)\}", text[sp[0]:sp[1]]) if sp else None
    return int(v.group(1)) if v else None


def set_human_vet(text, eid, level):
    sp = _human_span(text, eid)
    if not sp:
        raise ValueError(f"Could not find soldier {eid} to set his rank")
    blk = text[sp[0]:sp[1]]
    if re.search(r"\{Veterancy \d+\}", blk):
        blk = re.sub(r"\{Veterancy \d+\}", "{Veterancy %d}" % level, blk, count=1)
    elif '{Extender "vitality"' in blk:
        blk = re.sub(r'(\{Extender "vitality"[^\n]*\n)', lambda m: m.group(1) + "\t\t\t{Veterancy %d}\n" % level, blk, count=1)
    else:
        ins = '\t\t{Extender "vitality"\n\t\t\t{Veterancy %d}\n\t\t}\n' % level
        k = blk.find("\t\t{Player ")
        if k < 0:
            raise ValueError(f"Could not place a rank for soldier {eid}")
        blk = blk[:k] + ins + blk[k:]
    return text[:sp[0]] + blk + text[sp[1]:]


def human_name(text, eid):
    """(first, last) name indexes stored in the save for this soldier, or None. They index the game's name lists (catalog.name_lists)."""
    sp = _human_span(text, eid)
    m = re.search(r"\{NameId (\d+) (\d+)\}", text[sp[0]:sp[1]]) if sp else None
    return [int(m.group(1)), int(m.group(2))] if m else None


def set_human_name(text, eid, first, last):
    sp = _human_span(text, eid)
    if not sp:
        raise ValueError(f"Could not find soldier {eid} to rename him")
    blk, k = re.subn(r"\{NameId \d+ \d+\}", "{NameId %d %d}" % (int(first), int(last)), text[sp[0]:sp[1]], count=1)
    if not k:
        raise ValueError(f"Soldier {eid} has no name entry to change")
    return text[:sp[0]] + blk + text[sp[1]:]


def open_save(path, cat: lo.Catalog):
    z, scn, status = _read(path)
    text = scn.replace("\r", "")
    breeds = {eid: breed for breed, eid in _HUMAN.findall(text)}
    loads = {}
    for m in _INV.finditer(text):
        l = lo.parse(m.group(0), cat)
        loads[l["eid"]] = l
    squads = []
    csq = re.search(r"\{CampaignSquads\n(.*?)\n\t\}", text, re.S)
    if csq:
        for i, row in enumerate(re.findall(r"\{(\"[^\n]*)\}", csq.group(1))):
            toks = re.findall(r'"([^"]*)"|(0x[0-9a-fA-F]+)', row)
            names = [a for a, b in toks if a]
            eids = [b for a, b in toks if b]
            squads.append({"index": i, "template": names[0] if names else "", "eids": eids})
    soldiers, counters = [], {}
    in_squad = {e: s["index"] for s in squads for e in s["eids"]}
    for eid, breed in breeds.items():
        if eid not in loads:
            continue
        role = pretty_role(breed, cat)
        counters[role] = counters.get(role, 0) + 1
        info = cat.breed_info.get(breed) or {}
        sv = human_vet(text, eid)
        soldiers.append({"eid": eid, "breed": breed, "role": role, "n": counters[role], "squad": in_squad.get(eid),
                         "loadout": loads[eid], "skin": info.get("skin", ""), "vet": sv if sv is not None else info.get("vet", 0),
                         "perks": info.get("perks"), "icon": info.get("icon"), "tag": info.get("tag"), "portrait": info.get("portrait"), "name_id": human_name(text, eid)})
    nsq = {}
    for s in soldiers:
        nsq.setdefault(s["squad"], 0)
        nsq[s["squad"]] += 1
    squad_list = []
    for s in squads:
        humans = [x for x in soldiers if x["eid"] in s["eids"]]
        if humans:
            lead = max(set(h["role"] for h in humans), key=lambda r: sum(h["role"] == r for h in humans))
            squad_list.append({"index": s["index"], "label": f"Squad {len(squad_list) + 1}", "template": s["template"],
                               "game_name": cat.names["squads"].get(s["template"], ""),
                               "count": len(humans), "main_role": lead})
    return {"name": _status_field(status, "name"), "army": _status_field(status, "army"),
            "soldiers": soldiers, "squads": squad_list, "mods": save_mods(status)}


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|{}]+', " ", s).strip()
    return s[:60] or "Armory copy"


def write_copy(src: Path, edits: dict, new_name: str | None, overwrite: bool = False,
               remap: dict | None = None, vets: dict | None = None, names: dict | None = None) -> Path:
    """edits: {eid: loadout dict}. Returns the path written.
    Default: a NEW file under a new campaign name; `src` is never touched.
    overwrite=True: back `src` up to armory/backups/ first, then replace it in place (campaign name unchanged).
    remap {eid: breed path}: point those soldiers at generated breeds (see breeds.py) and list the mod in the save."""
    z, scn, status = _read(src)
    crlf = "\r\n" in scn
    text = scn.replace("\r", "")
    n_done = 0

    def sub(m):
        nonlocal n_done
        eid = re.match(r"\t\{Inventory (0x[0-9a-fA-F]+)", m.group(0)).group(1)
        if eid in edits:
            n_done += 1
            return lo.serialize(edits[eid])
        return m.group(0)

    text = _INV.sub(sub, text)
    if n_done != len(edits):
        raise ValueError(f"Expected {len(edits)} inventories, rewrote {n_done}")
    for eid, newp in (remap or {}).items():
        text, k = re.subn(r'(\t\{Human )"[^"]+"( %s\b)' % re.escape(eid),
                          lambda m: '%s"%s"%s' % (m.group(1), newp, m.group(2)), text)
        if k != 1:
            raise ValueError(f"Could not find soldier {eid} to give a new breed")
    for eid, level in (vets or {}).items():          # rank is also stored per soldier in the save, so write it there too
        text = set_human_vet(text, eid, int(level))
    for eid, (first, last) in (names or {}).items():      # names are save-only: {NameId first last}
        text = set_human_name(text, eid, first, last)
    if remap:
        status = breeds.add_to_mods(status)
    new_scn = text.replace("\n", "\r\n") if crlf else text
    if overwrite:
        BACKUPS.mkdir(exist_ok=True)
        (BACKUPS / f"{src.stem}_{time.strftime('%Y%m%d-%H%M%S')}.sav").write_bytes(src.read_bytes())
        return _write_zip(z, src, new_scn, status)
    sx = status.replace("\r", "")
    # The campaign name lives in {saveinfo ... {name X}}. Quote it unless it is a plain word (the game's own saves do
    # the same: {name TESTCAMPAIGN} vs {name "Conquest 4"}). Only touch the first {name} inside {saveinfo}.
    q = new_name if re.fullmatch(r"[A-Za-z0-9_]+", new_name) else '"%s"' % new_name.replace('"', "")
    i0 = sx.find("{saveinfo")
    if i0 < 0:
        raise ValueError("Could not find the save info block")
    tail, k = re.subn(r"\{name [^}\n]*\}", lambda m: "{name %s}" % q, sx[i0:], count=1)
    if k != 1:
        raise ValueError("Could not find the campaign name in the save")
    sx2 = sx[:i0] + tail
    new_status = sx2.replace("\n", "\r\n") if "\r\n" in status else sx2
    out = src.parent / (safe_name(new_name) + ".sav")
    i = 2
    while out.exists():                                   # never overwrite anything
        out = src.parent / f"{safe_name(new_name)} ({i}).sav"
        i += 1
    return _write_zip(z, out, new_scn, new_status)


def _write_zip(z, out: Path, new_scn: str, new_status: str) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zo:
        for info in z.infolist():
            data = {"campaign.scn": new_scn.encode("utf-8"), "status": new_status.encode("utf-8")}.get(
                info.filename) or z.read(info.filename)
            zo.writestr(info, data, compress_type=info.compress_type)
    out.write_bytes(buf.getvalue())
    return out
