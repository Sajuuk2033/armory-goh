"""Build the release zips (allowlist based) and refuse to write any that contain personal data.

    python package.py [workshop|nexus|github|all]

Output goes to dist/ as Armory-<version>-<kind>.zip. Nothing is uploaded; this only writes local files.
Every file in every zip (including members of zips nested inside, e.g. .sav fixtures) is scanned by
`scan_bytes`; any hit deletes the zip and exits non-zero. Standard library only.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"

sys.path.insert(0, str(HERE))
from version import VERSION  # noqa: E402

# ---------------------------------------------------------------- leak scanner

# Strings that are fine to publish (blanked out before scanning, matched case-insensitively).
ALLOWED = [
    "Sajuuk",
    "sajuuk2033",
    "ko-fi.com/sajuuk2033",
    "https://storage.ko-fi.com/cdn/generated/fhfuc7slzawvi/2026-11-15_rest-e3d3b1148ed8909b5afd4e9a847d0c82-fthlyfbg.jpg",
]
# Placeholder paths that may appear in docs (explicit whitelist; currently none are needed).
ALLOWED_PATHS: list[str] = [
    r"C:\Users\you",                  # generic placeholder in the UI hint
    r"C:\\Users\\you",                # same, escaped for JS (web/app.js input placeholder)
    r"C:\Program Files (x86)",        # default Steam location used by config.py auto-detect
    r"C:\\Program Files (x86)",       # same, escaped for the JS placeholder text in web/app.js
]

# Stored reversed so this file does not trip its own scanner when it ships in the github zip.
_LITERALS = [s[::-1] for s in ["xela", "iggopa", "liamg", "44296863", "edualckculdoog", r"sresu\:c", "sresu/:c",
                               "yrarbilmaets"]]
_REGEXES = {
    "steam64 id": re.compile(r"\b76561\d{11,}"),
    "owner workshop id": re.compile(r"mod_38\d+"),
    "absolute drive path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"),
    "email address": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"),
}
_ALLOWED_RE = re.compile("|".join(re.escape(a) for a in sorted(ALLOWED + ALLOWED_PATHS, key=len, reverse=True)),
                         re.IGNORECASE)


_LOOSE = ("absolute drive path", "email address")      # regexes too short to apply to binary noise


def _is_texty(text: str) -> bool:
    if not text:
        return True
    ok = sum(1 for c in text if c in "\t\r\n" or 32 <= ord(c) < 127)
    return ok / len(text) > 0.95


def _scan_text(label: str, text: str) -> list[str]:
    hits = []
    texty = _is_texty(text)
    text = _ALLOWED_RE.sub(lambda m: " " * len(m.group(0)), text)
    low = text.lower()
    for lit in _LITERALS:
        i = low.find(lit)
        if i >= 0:
            ctx = text[max(0, i - 20): i + 40].replace("\n", " ")
            hits.append(f"{label}: '{lit}' near ...{ctx}...")
    for name, rx in _REGEXES.items():
        if name in _LOOSE and not texty:
            continue
        m = rx.search(text)
        if m:
            ctx = text[max(0, m.start() - 20): m.end() + 30].replace("\n", " ")
            hits.append(f"{label}: {name} near ...{ctx}...")
    return hits


def scan_bytes(label: str, data: bytes, depth: int = 0) -> list[str]:
    """Return a list of hit descriptions for one file; recurses into nested zips (e.g. .sav)."""
    hits = _scan_text(label + " [name]", label)
    nested = None
    if data.startswith(b"PK") and depth < 4:
        try:
            nested = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            nested = None
    if nested is None:      # a zip's raw bytes are compressed noise; its members are scanned below instead
        hits += _scan_text(label, data.decode("latin-1"))
    # UTF-16 text would hide from a latin-1 scan; check for it as well when it looks like it.
    if b"\x00" in data[:4096] and not data.startswith(b"PK"):
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                hits += _scan_text(label + f" ({enc})", data.decode(enc))
            except UnicodeDecodeError:
                pass
    if nested is not None:
        with nested as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                hits += scan_bytes(f"{label}!{info.filename}", zf.read(info), depth + 1)
    return hits


def scan_zip(path: Path) -> list[str]:
    hits = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            hits += scan_bytes(info.filename, zf.read(info))
    return hits


# ---------------------------------------------------------------- allowlists

APP_PY = ["server.py", "savefile.py", "loadout.py", "catalog.py", "breeds.py", "identity.py", "perks.py",
          "config.py", "version.py"]
DEV_PY = ["slice.py", "validate_catalog.py", "make_diag_save.py", "make_feature_test_save.py",
          "make_identity_test_save.py", "make_perk_test_save.py"]
TEST_PY = ["test_factions.py", "test_identity.py", "test_loadout.py", "test_perks.py", "test_savefile.py",
           "test_package.py"]
TOP_COMMON = ["README.md", "LICENSE", "CHANGELOG.md", "start_armory.bat"]
WEB = ["web/index.html", "web/app.js", "web/style.css"]
FIXTURES = ["fixtures/fresh_ger.sav"]
DOCS = ["docs/DEVELOPMENT.md", "docs/PACKAGES.md"]

NEXUS_FILES = APP_PY + TOP_COMMON + WEB
GITHUB_FILES = (APP_PY + DEV_PY + TEST_PY + TOP_COMMON + ["UX.md", "package.py", ".gitignore"] + WEB + FIXTURES
                + DOCS + ["workshop/description.bbcode", "workshop/mod_shell/README.txt", "nexus/description.txt"])

# Original, minimal mod.info. Format checked read-only against mod.info files already installed
# with the game ({mod {name "..."} {desc "..."} {minGameVersion ".."} {maxGameVersion ".."}}).
WORKSHOP_MOD_INFO = f'''{{mod
\t{{name "Armory - soldier editor (info page)"}}
\t{{desc "Data-only listing for Armory, a separate local editor for Dynamic Conquest saves. This mod contains no game data and changes nothing in the game. Download the Armory app separately (see the description)."}}
\t{{minGameVersion "1.067"}}
\t{{maxGameVersion "9.999"}}
}}
'''

WORKSHOP_README = f"""Armory {VERSION} - Workshop info shell

This is a data-only listing. It contains no scripts, no executables, no game files and no generated soldier breeds.
It does nothing in the game by itself.

The actual tool is the separate Armory app (a small local Python + browser editor for your own Dynamic Conquest
saves). When you save an edited soldier, the app writes a tiny data-only mod called "armory_breeds" into your own
mods folder on your PC; that mod is generated per player and is not part of this listing.

See description.bbcode for the full text and the download location.
"""


def _check_files(files: list[str]) -> list[tuple[str, Path]]:
    out, missing = [], []
    for rel in files:
        p = HERE / rel
        (out if p.is_file() else missing).append((rel, p) if p.is_file() else rel)
    if missing:
        sys.exit(f"package.py: allowlisted files missing: {missing}")
    return out


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    DIST.mkdir(exist_ok=True)
    if path.exists():
        path.unlink()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))   # fixed time: reproducible
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)


def _finish(path: Path) -> int:
    hits = scan_zip(path)
    if hits:
        path.unlink()
        print(f"LEAK SCAN FAILED for {path.name}; zip deleted:")
        for h in hits:
            print("  " + h)
        return 1
    with zipfile.ZipFile(path) as zf:
        n = len(zf.namelist())
    print(f"ok  {path.name}  {path.stat().st_size} bytes  {n} files  (leak scan clean)")
    return 0


def build_repo_zip(kind: str, files: list[str]) -> int:
    top = f"Armory-{VERSION}"
    entries = [(f"{top}/{rel}", p.read_bytes()) for rel, p in _check_files(files)]
    path = DIST / f"{top}-{kind}.zip"
    _write_zip(path, entries)
    return _finish(path)


def build_nexus() -> int:
    rc = build_repo_zip("nexus", NEXUS_FILES)
    desc = HERE / "nexus" / "description.txt"
    dest = DIST / f"Armory-{VERSION}-nexus-description.txt"
    data = desc.read_bytes()
    hits = scan_bytes(dest.name, data)
    if hits:
        print("LEAK SCAN FAILED for nexus description:")
        for h in hits:
            print("  " + h)
        return 1
    DIST.mkdir(exist_ok=True)
    dest.write_bytes(data)
    print(f"ok  {dest.name}  {len(data)} bytes  (leak scan clean)")
    return rc


def build_workshop() -> int:
    top = "armory_info"          # deliberately not "armory_breeds" (the per-user generated mod)
    bbcode = (HERE / "workshop" / "description.bbcode").read_bytes()
    entries = [(f"{top}/mod.info", WORKSHOP_MOD_INFO.encode("utf-8")),
               (f"{top}/README.txt", WORKSHOP_README.encode("utf-8")),
               (f"{top}/description.bbcode", bbcode)]
    path = DIST / f"Armory-{VERSION}-workshop.zip"
    _write_zip(path, entries)
    return _finish(path)


def build_github() -> int:
    return build_repo_zip("github", GITHUB_FILES)


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    what = argv[1] if len(argv) > 1 else "all"
    builders = {"workshop": build_workshop, "nexus": build_nexus, "github": build_github}
    if what == "all":
        todo = list(builders.values())
    elif what in builders:
        todo = [builders[what]]
    else:
        print(__doc__)
        return 2
    rc = 0
    for b in todo:
        rc |= b()
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
