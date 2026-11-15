"""Armory slice 1: edit ONE soldier's inventory in a COPY of a Conquest save.

Never touches the source save. Edits only inside the target soldier's
{Inventory 0xEID ...} block, preserves CRLF/encoding and every other ZIP member.

usage: python -I slice.py <src.sav> <dst.sav> <eid e.g. 0xb006>
"""
import io, re, sys, zipfile


def edit_block(text: str, eid: str) -> tuple[str, list[str]]:
    m = re.search(r"\t\{Inventory %s\r?\n" % re.escape(eid), text)
    if not m:
        raise SystemExit(f"no Inventory block for {eid}")
    start = m.start()
    # block ends at the first line that is exactly '\t}' after start
    end = re.compile(r"\r?\n\t\}").search(text, m.end()).end()
    block = text[start:end]
    log = []

    new = block.replace('{item "k98" filled', '{item "g41" filled', 1)
    if new != block:
        log.append("weapon k98 -> g41 (same rifle_ger clips)")
    block = new

    # helmet -> field cap: move the {user "head"} marker
    helm = re.search(r'\{item "(ger_stalhelm_[a-z0-9_]+)" (\{cell \d+ \d+\})\{user "head"\}\}', block)
    cap = re.search(r'\{item "(ger_fieldcap_[a-z0-9_]+|ger_sidecap_[a-z0-9_]+)" (\{cell \d+ \d+\})\}', block)
    if helm and cap:
        block = block.replace(helm.group(0), '{item "%s" %s}' % (helm.group(1), helm.group(2)))
        block = block.replace(cap.group(0), '{item "%s" %s{user "head"}}' % (cap.group(1), cap.group(2)))
        log.append(f"head {helm.group(1)} -> {cap.group(1)}")
    return text[:start] + block + text[end:], log


def main(src, dst, eid):
    zin = zipfile.ZipFile(src)
    raw = zin.read("campaign.scn")
    assert raw.decode("utf-8").encode("utf-8") == raw, "unexpected encoding"
    text, log = edit_block(raw.decode("utf-8"), eid)
    if not log:
        raise SystemExit("nothing changed")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = text.encode("utf-8") if info.filename == "campaign.scn" else zin.read(info.filename)
            zout.writestr(info, data, compress_type=info.compress_type)
    open(dst, "wb").write(out.getvalue())
    print("\n".join(log))


if __name__ == "__main__":
    main(*sys.argv[1:4])
