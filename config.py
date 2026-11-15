"""Where is the game, its mods, and your saves? Auto-detected, overridable, remembered in config.json.

Everything the rest of Armory needs to know about the install goes through here, so users with the game on another drive
(or a different Documents folder) only have to point at it once.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).parent
CONFIG = HERE / "config.json"
APP_ID = "400750"                      # Gates of Hell on Steam (Workshop content folder name)
GAME_DIRNAME = "Call to Arms - Gates of Hell"


def load() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")


def is_game_dir(p) -> bool:
    p = Path(p)
    return (p / "resource" / "gamelogic.pak").is_file() and (p / "binaries").is_dir()


def steam_libraries() -> list[Path]:
    libs = []
    roots = []
    try:
        import winreg
        for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(Path(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots += [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"]
    for r in roots:
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
    seen, out = set(), []
    for l in libs:
        if str(l).lower() not in seen and l.exists():
            seen.add(str(l).lower())
            out.append(l)
    return out


def detect_game() -> Path | None:
    for lib in steam_libraries():
        p = lib / "steamapps" / "common" / GAME_DIRNAME
        if is_game_dir(p):
            return p
    return None


def workshop_dir(game: Path | None) -> Path | None:
    """<steam library>/steamapps/workshop/content/400750 next to the game's library."""
    if not game:
        return None
    lib = game.parent.parent.parent                     # .../steamapps/common/<game> -> .../ (library root)
    p = lib / "steamapps" / "workshop" / "content" / APP_ID
    return p if p.is_dir() else None


def documents_candidates() -> list[Path]:
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    c = [home / "Documents", home / "OneDrive" / "Documents"]
    for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(k):
            c.append(Path(os.environ[k]) / "Documents")
    return c


def detect_profiles_dir() -> Path | None:
    for d in documents_candidates():
        p = d / "My Games" / "gates of hell" / "profiles"
        if p.is_dir():
            return p
    return None


def resolved() -> dict:
    """The effective settings: saved overrides first, then auto-detection. 'ok' says whether Armory can run."""
    cfg = load()
    game = Path(cfg["game_dir"]) if cfg.get("game_dir") else detect_game()
    prof = Path(cfg["profiles_dir"]) if cfg.get("profiles_dir") else detect_profiles_dir()
    game_ok = bool(game and is_game_dir(game))
    return {"game_dir": str(game) if game else "", "game_ok": game_ok,
            "profiles_dir": str(prof) if prof else "", "profiles_ok": bool(prof and prof.is_dir()),
            "workshop_dir": str(workshop_dir(game) or "") if game_ok else "",
            "ok": game_ok and bool(prof and prof.is_dir()),
            "auto_game": not cfg.get("game_dir"), "auto_profiles": not cfg.get("profiles_dir")}


def campaign_dirs() -> list[Path]:
    if os.environ.get("ARMORY_CAMPAIGN_DIR"):          # test mode: scratch folder
        return [Path(os.environ["ARMORY_CAMPAIGN_DIR"])]
    r = resolved()
    if not r["profiles_ok"]:
        return []
    return sorted(p for p in Path(r["profiles_dir"]).glob("*/campaign") if p.is_dir())
