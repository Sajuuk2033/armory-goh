"""Armory local server. Binds 127.0.0.1 only; every /api call needs the per-run token (stops other web pages
in your browser from poking the editor). Standard library only - nothing to install.

usage: python server.py [--port 8765] [--no-browser]
"""
from __future__ import annotations

import argparse
import os
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import breeds
import identity as ident
import catalog as catmod
import config
import loadout as lo
import savefile as sf

HERE = Path(__file__).parent
WEB = HERE / "web"
TOKEN = secrets.token_urlsafe(16)
CAT = None


def load_catalog():
    """(Re)build the item catalog from the configured game folder. ~6 s with many Workshop mods, so only on start/setup."""
    global CAT
    r = config.resolved()
    if r["game_ok"]:
        data = catmod.build(r["game_dir"], r["workshop_dir"] or None)
        (HERE / "catalog.json").write_text(json.dumps(data), encoding="utf-8")
        CAT = lo.Catalog(data)
    else:
        CAT = lo.Catalog() if (HERE / "catalog.json").is_file() else None
    return CAT is not None
STATIC = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def need_catalog():
    if CAT is None:
        raise lo.LoadoutError("Armory can't find your game folder yet. Open Settings and point it at the game.")


def army_of(b):
    """The army info for a request: the soldier's own nation if the UI sent one ('nation'), else the save's army ('army').
    None = unknown army (a modded campaign): callers then offer everything instead of guessing."""
    for key in ("nation", "army"):
        a = catmod.army_info(b.get(key) or "")
        if a:
            return a
    return None


def api_state(_q, _b):
    return {"saves": sf.list_saves(), "game_running": sf.game_running(), "config": config.resolved(),
            "catalog_ready": CAT is not None}


def api_config(_q, b):
    """Set / clear the game and profiles folders. Folders are validated before they are remembered."""
    cfg = config.load()
    for key, check, label in (("game_dir", config.is_game_dir, "game folder (needs resource\gamelogic.pak)"),
                              ("profiles_dir", lambda p: Path(p).is_dir(), "profiles folder")):
        if key in b:
            v = (b[key] or "").strip().strip('"')
            if not v:
                cfg.pop(key, None)                       # back to auto-detect
            elif check(v):
                cfg[key] = str(Path(v))
            else:
                raise lo.LoadoutError(f"That doesn't look like the {label}: {v}")
    config.save(cfg)
    ok = load_catalog()
    return {"config": config.resolved(), "catalog_ready": ok}


def fill_missing_breeds(soldiers):
    """Soldiers on a breed the catalog doesn't know (typically an Armory breed made after the catalog was built) would show no
    uniform, rank or skills. Read those breed files now, in one pass over the paks, and remember them for this session."""
    missing = {s["breed"] for s in soldiers if s["breed"] not in CAT.breed_info}
    if not missing:
        return
    r = config.resolved()
    mods_dir = Path(os.environ["ARMORY_MODS_DIR"]) if os.environ.get("ARMORY_MODS_DIR") else None
    texts = breeds.find_bases(Path(r["game_dir"]), Path(r["workshop_dir"]) if r["workshop_dir"] else None, missing)
    if mods_dir and mods_dir.is_dir():                                   # test mode: scratch mods folder
        texts.update(breeds.find_bases(Path(r["game_dir"]), mods_dir, missing))
    for b, t in texts.items():
        CAT.breed_info[b] = catmod.breed_summary(t)
    for s in soldiers:
        info = CAT.breed_info.get(s["breed"])
        if info and s["breed"] in texts:
            s["skin"] = s["skin"] or info["skin"]
            s["perks"] = info["perks"]
            s["icon"], s["tag"], s["portrait"] = info.get("icon"), info.get("tag"), info.get("portrait")


def armory_breed_names():
    """On-screen names of the breeds Armory itself generated (the catalog only knows the base game's), so a soldier on an
    Armory breed is still listed as 'Rifleman', not 'Arm dfc22fe75d'."""
    r = config.resolved()
    root = Path(os.environ["ARMORY_MODS_DIR"]) if os.environ.get("ARMORY_MODS_DIR") else Path(r["game_dir"]) / "mods"
    try:
        return breeds.read_loc(root / breeds.MOD_ID / "localizations" / "default.pak")
    except Exception:
        return {}


def api_open(q, _b):
    need_catalog()
    CAT.names["breeds"].update(armory_breed_names())
    p = sf.resolve(q["file"][0], q["dir"][0])
    d = sf.open_save(p, CAT)
    d["mod_names"] = {m: CAT.mods.get(m, m) for m in d["mods"]}
    d["file"], d["dir"] = p.name, str(p.parent)
    d["grid"] = [lo.GRID_W, lo.GRID_H]
    d["vet_max"] = CAT.vet_max
    d["perk_presets"] = CAT.perk_presets
    d["identity"] = CAT.identity
    nations = {s["breed"].split("/")[1] for s in d["soldiers"] if s["breed"].startswith("mp/")}
    d["name_lists"] = {n: v for n, v in CAT.name_lists.items() if n in nations}     # only the nations this save uses
    a = catmod.army_info(d["army"])
    d["army_info"] = a or {"code": d["army"], "label": "", "nation": "", "skins": ""}
    d["army_known"] = bool(a)
    d["item_names"] = CAT.item_names
    fill_missing_breeds(d["soldiers"])
    d["game_running"] = sf.game_running()
    return d


def api_op(_q, b):
    cur = b["loadout"]
    op = b["op"]
    kind = op["kind"]
    if kind == "equip":
        new, msgs = lo.equip(cur, CAT, op["role"], op["name"])
    elif kind == "add":
        new, msgs = lo.add_item(cur, CAT, op["name"], op.get("count", 1))
    elif kind == "remove":
        new, msgs = lo.remove_entry(cur, op["id"])
    elif kind == "remove_name":      # remove one carried unit by name (the "-" button)
        e = next((e for e in reversed(cur["entries"]) if e["key"] == op["name"] and e["role"] != "ammo"), None)
        if not e:
            raise lo.LoadoutError("Nothing to remove")
        new, msgs = lo.remove_entry(cur, e["id"])
    elif kind == "move":
        new, msgs = lo.move_entry(cur, op["id"], op["x"], op["y"])
    elif kind == "ammo":
        new, msgs = lo.set_ammo_stacks(cur, CAT, op["stem"], op["n"])
    elif kind == "add_ammo":
        new, msgs = lo.add_ammo(cur, CAT, op["stem"], op.get("count", 1))
    elif kind == "sort":
        new, msgs = lo.auto_sort(cur)
    else:
        raise lo.LoadoutError("Unknown operation")
    return {"loadout": new, "messages": msgs}


def api_ammo_candidates(_q, b):
    need_catalog()
    a = army_of(b)
    nations = None if b.get("everything") or not a else [a["nation"]]          # unknown army: everything
    sources = {""} | set(b.get("mods") or [])
    return {"items": lo.ammo_candidates(b["loadout"], CAT, nations, sources)}


def api_candidates(_q, b):
    need_catalog()
    a = army_of(b)
    nations = None if b.get("everything") or not a else [a["nation"]]          # unknown army: everything
    sources = {""} | set(b.get("mods") or [])               # base game + the mods THIS save was made with
    return {"items": lo.candidates(b["loadout"], CAT, b["role"], nations, sources)}


def check_item_sources(src, edits):
    """Refuse loadouts holding items from a mod the save doesn't list: the game doesn't know them and silently turns
    them into something else (a mod-only `mp40` gun came back as an empty "mp40 ammo" item)."""
    allowed = {""} | set(sf.open_save(src, CAT)["mods"])
    bad = {}
    for lo_ in edits.values():
        for e in lo_["entries"]:
            rec = CAT.items.get(e.get("key")) if e["role"] != "ammo" else None
            if rec and rec["source"] not in allowed:
                bad.setdefault(CAT.mods.get(rec["source"], rec["source"]), set()).add(e["key"])
    if bad:
        raise lo.LoadoutError("These items come from mods this save doesn't use, so the game would drop them: " +
                              "; ".join(f"{', '.join(sorted(v))} (from {k})" for k, v in bad.items()) +
                              ". Pick the base-game version, or load the save with that mod enabled.")


def check_names(src, raw):
    """{eid: [first, last]} from the UI, each index checked against the game's name list for that soldier's nation."""
    if not raw:
        return {}
    soldiers = {x["eid"]: x for x in sf.open_save(src, CAT)["soldiers"]}
    out = {}
    for eid, pair in raw.items():
        s = soldiers.get(eid)
        if not s or not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise lo.LoadoutError("A name change refers to a soldier that is not in this save.")
        nation = s["breed"].split("/")[1] if s["breed"].startswith("mp/") else ""
        lists = CAT.name_lists.get(nation)
        if not lists:
            raise lo.LoadoutError(f"Armory doesn't know the name list for {nation or 'this soldier'}, so it can't rename him.")
        f, l = int(pair[0]), int(pair[1])
        if not (0 <= f < len(lists["first"]) and 0 <= l < len(lists["last"])):
            raise lo.LoadoutError("That name is not in the game's name list.")
        out[eid] = [f, l]
    return out


def api_save(_q, b):
    src = sf.resolve(b["file"], b["dir"])
    if sf.game_running():
        raise lo.LoadoutError("The game is running. Close it (or go back to the main menu) before saving a copy.")
    edits = {e["eid"]: e for e in b["edits"]}
    check_item_sources(src, edits)
    remap = None
    looks = {e: v for e, v in (b.get("looks") or {}).items() if v}          # {eid: {"skin": name, "vet": N, "perks": {...}, "icon": x, "tag": y}}
    for v in looks.values():                                                  # icon / tag: only values the game's own breeds use
        try:
            v.update(ident.clean(v, CAT.identity["icons"], CAT.identity["tags"], CAT.identity.get("portraits", [])))
        except ValueError as e:
            raise lo.LoadoutError(str(e))
    names = check_names(src, b.get("names") or {})
    vets = {e: v["vet"] for e, v in looks.items() if v.get("vet") is not None}
    # Every save gets its soldier types (generated breeds): that is what lets supply crates refill edited soldiers.
    r = config.resolved()
    soldiers = sf.open_save(src, CAT)["soldiers"]
    have = {x["eid"]: x["breed"] for x in soldiers}
    game, ws = Path(r["game_dir"]), Path(r["workshop_dir"]) if r["workshop_dir"] else None
    # Soldiers edited in an EARLIER save (not touched now) still need a matching breed, or crates won't refill them.
    texts = breeds.find_bases(game, ws, set(have.values()))          # one pass over the paks for the whole save
    want = dict(edits)
    for x in soldiers:
        if x["eid"] not in want and breeds.needs_breed(game, ws, x["loadout"], x["breed"], texts):
            want[x["eid"]] = x["loadout"]
    remap, files = breeds.plan(game, ws, want, have, CAT, looks, texts)
    mods_dir = Path(os.environ["ARMORY_MODS_DIR"]) if os.environ.get("ARMORY_MODS_DIR") else None
    breeds.install(Path(r["game_dir"]), files, mods_dir, CAT.names["breeds"])
    if b.get("overwrite"):
        out = sf.write_copy(src, edits, None, overwrite=True, remap=remap, vets=vets, names=names)
        return {"path": str(out), "file": out.name, "overwrote": True, "breeds": len(set((remap or {}).values())), "backup_dir": str(sf.BACKUPS)}
    out = sf.write_copy(src, edits, b["name"], remap=remap, vets=vets, names=names)
    return {"path": str(out), "file": out.name, "breeds": len(set((remap or {}).values()))}


def api_skins(_q, b):
    need_catalog()
    sources = {""} | set(b.get("mods") or [])
    a = army_of(b)
    nation = None if b.get("everything") or not a else a["skins"]                 # unknown army: every skin
    out = [{"name": k, "group": v["group"], "nation": v["nation"], "mod": CAT.mods.get(v["source"], "")}
           for k, v in CAT.skins.items() if v["source"] in sources and (nation is None or v["nation"] == nation)]
    out.sort(key=lambda r: (r["group"], r["name"]))
    return {"skins": out, "vet_max": CAT.vet_max, "filtered": nation is not None}


GET = {"/api/state": api_state, "/api/open": api_open}
POST = {"/api/config": api_config, "/api/op": api_op, "/api/candidates": api_candidates, "/api/ammo_candidates": api_ammo_candidates, "/api/save": api_save, "/api/skins": api_skins}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _auth(self):
        return self.headers.get("X-Armory-Token") == TOKEN and self.headers.get("Host", "").split(":")[0] in (
            "127.0.0.1", "localhost")

    def _run(self, fn, q, b):
        try:
            self._send(200, fn(q, b))
        except lo.LoadoutError as e:
            self._send(200, {"error": str(e)})
        except (KeyError, ValueError) as e:
            self._send(400, {"error": f"Bad request: {e}"})
        except Exception as e:                               # keep the UI alive, show the reason
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in STATIC:
            f = WEB / STATIC[u.path]
            data = f.read_bytes()
            if f.name == "index.html":
                data = data.replace(b"__TOKEN__", TOKEN.encode())
            return self._send(200, data, TYPES[f.suffix])
        if u.path in GET:
            if not self._auth():
                return self._send(403, {"error": "forbidden"})
            return self._run(GET[u.path], parse_qs(u.query), None)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in POST:
            return self._send(404, {"error": "not found"})
        if not self._auth():
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        self._run(POST[u.path], parse_qs(u.query), body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    print("Reading game data (a few seconds)...")
    load_catalog()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = f"http://127.0.0.1:{a.port}/"
    print("Armory running at", url, "(Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
