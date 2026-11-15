"""A soldier's icon, tag and portrait live in his breed:  {icon "smg"}  {tags "soldier_pzscheck"}  {portrait "ger_regular"}.

portrait  the face set the game draws his unit card and dialogue picture from (ger_regular, ger_pionier, usa_ranger, ...).
          A closed set per nation, read from the game's own breeds.

icon  the role symbol on his unit card (rifle, smg, mg, sniper, ...). A closed set the game's own breeds use.
tags  one label the game's logic keys on. Most soldiers are "soldier"; anti-tank carriers have a launcher-specific tag
      (every German Panzerschreck carrier in the base game is soldier_pzscheck, most Panzerfaust carriers soldier_pzfaust; US bazooka and
      British PIAT carriers are soldier_bazooka, Soviet/British AT-rifle carriers soldier_atr), vehicle crews "crew".

(His name is not here: it is {NameId first last} in the SAVE, two indexes into the game's name lists. See savefile.set_human_name.)
"""
from __future__ import annotations

import re

ICON_RE = re.compile(r'\{icon "([^"]*)"\}')
TAGS_RE = re.compile(r'\{tags "([^"]*)"\}')
PORTRAIT_RE = re.compile(r'\{portrait "([^"]*)"\}')

# German launcher / AT-rifle -> tag (read from the base German breeds). Other nations' tables are read from their breeds by
# catalog.identity_values (by_nation[n]["tag_for_weapon"]); this one is only the fallback and the German base of that table.
TAG_FOR_WEAPON = {"panzershreck_54": "soldier_pzscheck", "panzerfaust_60": "soldier_pzfaust", "pzb_39": "soldier_atr",
                  "k98_antitank": "soldier_atr_grenade"}


def read(text: str) -> dict:
    i, t, p = ICON_RE.search(text), TAGS_RE.search(text), PORTRAIT_RE.search(text)
    return {"icon": i.group(1) if i else None, "tag": t.group(1) if t else None, "portrait": p.group(1) if p else None}


def clean(spec: dict | None, icons, tags, portraits=()) -> dict:
    """Keep only icon/tag/portrait keys, each checked against what the game's own breeds use."""
    out = {}
    for key, allowed in (("icon", icons), ("tag", tags), ("portrait", portraits)):
        if spec and key in spec and spec[key] is not None:
            if spec[key] not in allowed:
                raise ValueError(f"Unknown {key}: {spec[key]}")
            out[key] = spec[key]
    return out


def apply(text: str, icon: str | None = None, tag: str | None = None, portrait: str | None = None) -> str:
    """Breed text with a new {icon}, {tags} and/or {portrait}. A breed that lacks the line gets it added at the top of the {breed} block."""
    for pat, tmpl, val in ((ICON_RE, '{icon "%s"}', icon), (TAGS_RE, '{tags "%s"}', tag), (PORTRAIT_RE, '{portrait "%s"}', portrait)):
        if val is None:
            continue
        new = tmpl % val
        text, k = pat.subn(lambda m: new, text, count=1)
        if not k:
            j = text.find("{breed")
            if j < 0:
                raise ValueError("base breed has no {breed} block")
            eol = text.find("\n", j)
            text = text[:eol + 1] + "\t" + new + "\n" + text[eol + 1:]
    return text


def suggest_tag(weapon_keys, mapping=None) -> str:
    """The tag the game would give a soldier carrying these weapons (the most specific one wins).
    `mapping` = the catalog's per-nation identity.by_nation[nation]["tag_for_weapon"]; without it, the German table above."""
    table = TAG_FOR_WEAPON if mapping is None else mapping
    for k in weapon_keys:
        k = re.sub(r"\.weapon$", "", k or "")
        if k in table:
            return table[k]
    return "soldier"
