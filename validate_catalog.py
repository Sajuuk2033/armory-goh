"""Check catalog.json against every {item ...} in real saves: does each name resolve, and do the cells
used by a soldier's items fit the catalog sizes without overlapping?
usage: python -I validate_catalog.py catalog.json <save.sav> [...]
"""
import collections, json, re, sys, zipfile


def lookup(cat, toks):
    kind = toks[-1] if toks[-1] in ("ammo", "grenade") else "item"
    stem = ".".join(toks[:-1] if kind != "item" else toks)
    return kind, stem, (cat["ammo"] if kind == "ammo" else cat["items"]).get(stem)


def main(catfile, *saves):
    cat = json.load(open(catfile))
    missing, total, bad_fit = collections.Counter(), 0, []
    for s in saves:
        z = zipfile.ZipFile(s)
        text = z.read("campaign.scn").decode("utf-8", "replace").replace("\r", "")
        for inv in re.finditer(r"\{Inventory (0x[0-9a-f]+)\n(.*?)\n\t\}", text, re.S):
            eid, body = inv.groups()
            grid = {}
            for it in re.finditer(r"\{item ((?:\"[^\"]+\"\s*)+)(.*?)\{cell (\d+) (\d+)\}", body):
                toks = re.findall(r'"([^"]+)"', it.group(1))
                total += 1
                kind, stem, rec = lookup(cat, toks)
                if not rec:
                    missing[(kind, stem)] += 1
                    continue
                w, h = rec["size"] or (1, 1)
                x, y = int(it.group(3)), int(it.group(4))
                for dx in range(w):
                    for dy in range(h):
                        if (x + dx, y + dy) in grid and grid[(x + dx, y + dy)] != stem:
                            bad_fit.append((s.split("/")[-1], eid, stem, grid[(x + dx, y + dy)]))
                        grid[(x + dx, y + dy)] = stem
                if x + w > 8:
                    bad_fit.append((s.split("/")[-1], eid, stem, f"overflows width x={x} w={w}"))
    print(f"{total} item rows checked; {sum(missing.values())} unresolved ({len(missing)} distinct)")
    for k, v in missing.most_common(25):
        print("  MISSING", k, v)
    print(f"{len(bad_fit)} overlap/overflow rows")
    for b in bad_fit[:15]:
        print("  FIT", b)


if __name__ == "__main__":
    main(*sys.argv[1:])
