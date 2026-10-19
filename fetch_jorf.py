#!/usr/bin/env python3
"""Lit les données officielles de la DILA (Journal officiel) et écrit jorf.txt :
sommaire des derniers JO pour la Présidence, le Premier ministre, l'Intérieur,
la Justice et les Armées, avec lien Légifrance de chaque texte."""
import io
import re
import tarfile
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = "https://echanges.dila.gouv.fr/OPENDATA/JORF/"
UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0)"
DAYS_BACK = 3

ENTITIES = [  # (libellé, mots-clés à chercher dans les titres de sections)
    ("Présidence de la République", ["president de la republique", "presidence de la republique"]),
    ("Premier ministre", ["premier ministre"]),
    ("Intérieur", ["interieur"]),
    ("Justice", ["justice"]),
    ("Armées", ["armees", "defense", "anciens combattants"]),
]
NOMINATIVE = re.compile(
    r"nomination|nomm|cessation|promotion|admission|détachement|detachement|"
    r"mise à disposition|affectation|mutation|décoration|titularisation|"
    r"renouvellement|délégation de signature|delegation de signature|intérim|interim|"
    r"démission|demission|radiation|réintégration|reintegration", re.I)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def http(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120)


def walk(el, path, out):
    title = next(((c.text or "").strip() for c in el if local(c.tag) == "TITRE_TM"), None)
    here = path + [title] if title else path
    for c in el:
        name = local(c.tag)
        if name == "TITRE_TM":
            continue
        if name == "LIEN_TXT":
            out.append((here, c.get("idtxt", ""),
                        (c.get("titretxt") or "".join(c.itertext())).strip()))
        else:
            walk(c, here, out)


def parse_container(data):
    root = ET.fromstring(data)
    date = num = ""
    for el in root.iter():
        n = local(el.tag)
        if n == "DATE_PUBLI" and not date:
            date = (el.text or "").strip()
        elif n == "NUM" and not num:
            num = (el.text or "").strip()
    entries = []
    for el in root.iter():
        if local(el.tag) == "STRUCTURE":
            walk(el, [], entries)
    return date, num, entries


def main():
    now = datetime.now(PARIS)
    since = (now - timedelta(days=DAYS_BACK)).strftime("%Y%m%d")
    listing = http(BASE).read().decode("utf-8", "replace")
    files = sorted({m.group(1) for m in re.finditer(r'href="(JORF_(\d{8})-\d{6}\.tar\.gz)"', listing)
                    if m.group(2) >= since})
    containers = {}
    errors = []
    for name in files:
        try:
            raw = http(BASE + name).read()
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
                for member in tf:
                    base = member.name.rsplit("/", 1)[-1]
                    if member.isfile() and base.startswith("JORFCONT") and base.endswith(".xml"):
                        date, num, entries = parse_container(tf.extractfile(member).read())
                        if date:
                            containers[(date, num)] = entries
        except Exception as e:
            errors.append(f"{name} : {type(e).__name__} {e}")

    lines = [f"JORF — généré le {now:%Y-%m-%d %H:%M} (heure de Paris)",
             f"Archives lues : {len(files)} ; Journaux officiels trouvés : {len(containers)}", ""]
    for (date, num) in sorted(containers, reverse=True):
        entries = containers[(date, num)]
        lines.append(f"# JO du {date} (n° {num}) — {len(entries)} textes au total")
        for label, keys in ENTITIES:
            hits = [(p, i, t) for p, i, t in entries
                    if any(k in norm(" / ".join(p)) for k in keys)]
            lines.append(f"## {label}")
            if not hits:
                lines.append("- rien")
            for kind, flag in (("Textes", False), ("Mesures nominatives", True)):
                sel = [h for h in hits if bool(NOMINATIVE.search(h[2])) == flag]
                if sel:
                    lines.append(f"{kind} :")
                    for _, idtxt, titre in sel:
                        lines.append(f"- {titre}")
                        lines.append(f"  https://www.legifrance.gouv.fr/jorf/id/{idtxt}")
            lines.append("")
        heads = sorted({" / ".join(p[:2]) for p, _, _ in entries})
        lines.append("(sections présentes : " + " ; ".join(heads)[:600] + ")")
        lines.append("")
    if errors:
        lines.append("## Erreurs")
        lines += [f"- {e}" for e in errors]
    with open("jorf.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(containers)} JO, {len(errors)} erreurs")


if __name__ == "__main__":
    main()
