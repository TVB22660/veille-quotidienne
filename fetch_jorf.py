#!/usr/bin/env python3
"""Lit les données officielles de la DILA (Journal officiel) et écrit jorf.txt :
textes publiés pour la Présidence, le Premier ministre, l'Intérieur, la Justice
et les Armées, avec lien Légifrance de chaque texte."""
import ftplib
import io
import os
import re
import sys
import time
import tarfile
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = "https://echanges.dila.gouv.fr/OPENDATA/JORF/"
UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0)"
DAYS_BACK = 3

ENTITIES = [  # (libellé, mots-clés cherchés dans le ministère / l'autorité)
    ("Présidence de la République", ["president de la republique", "presidence de la republique"]),
    ("Premier ministre", ["premier ministre"]),
    ("Intérieur", ["interieur"]),
    ("Justice", ["justice"]),
    ("Armées", ["armees", "defense", "anciens combattants"]),
]
NOR_PREFIX = {"INT": 2, "JUS": 3, "ARM": 4, "DEF": 4, "PRM": 1, "PRE": 0}  # secours si pas de ministère
NOMINATIVE = re.compile(
    r"nomination|nomm|cessation|promotion|admission|détachement|detachement|"
    r"mise à disposition|affectation|mutation|décoration|titularisation|"
    r"renouvellement|délégation de signature|delegation de signature|intérim|interim|"
    r"démission|demission|radiation|réintégration|reintegration", re.I)
FIELDS = {"ID", "NATURE", "TITRE", "TITREFULL", "DATE_PUBLI", "NUM_PARUTION",
          "NOR", "MINISTERE", "AUTORITE"}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def http(url, tries=5):
    """GET avec relances : le serveur de la DILA coupe parfois la connexion
    (RemoteDisconnected) quand on enchaîne les téléchargements."""
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": UA}), timeout=180)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise last


def http_read(url, tries=5):
    """Télécharge et lit tout le corps, avec relances (la coupure peut survenir pendant la lecture)."""
    last = None
    for i in range(tries):
        try:
            return http(url, 1).read()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  essai {i + 1}/{tries} HTTPS échoué : {url.rsplit('/', 1)[-1] or url} : "
                  f"{type(e).__name__} {e}", flush=True)
            time.sleep(5 * (i + 1))
    raise last


FTP_HOST = "echanges.dila.gouv.fr"
FTP_DIR = "/OPENDATA/JORF/"


def ftps_read(name):
    """Repli : même dépôt de la DILA en FTPS (mêmes données, autre protocole)."""
    ftp = ftplib.FTP_TLS(FTP_HOST, timeout=180)
    try:
        ftp.login()
        ftp.prot_p()
        if name is None:
            return "\n".join(f'href="{n.rsplit("/", 1)[-1]}"' for n in ftp.nlst(FTP_DIR)).encode()
        buf = io.BytesIO()
        ftp.retrbinary("RETR " + FTP_DIR + name, buf.write)
        return buf.getvalue()
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001
            pass


def fetch(name=None):
    """HTTPS avec relances, puis FTPS si le serveur continue de couper."""
    try:
        return http_read(BASE + (name or ""))
    except Exception as e1:  # noqa: BLE001
        print(f"  HTTPS définitivement en échec ({type(e1).__name__}) : repli FTPS", flush=True)
        try:
            return ftps_read(name)
        except Exception as e2:  # noqa: BLE001
            raise RuntimeError(f"HTTPS : {type(e1).__name__} {e1} ; FTPS : {type(e2).__name__} {e2}")


def parse_text(data):
    """Retourne un dict des champs utiles d'un fichier JORFTEXT."""
    root = ET.fromstring(data)
    f = {}
    for el in root.iter():
        n = local(el.tag)
        if n in FIELDS and n not in f:
            t = "".join(el.itertext()).strip()
            if t:
                f[n] = re.sub(r"\s+", " ", t)
    return f


def entity_of(f):
    hay = norm(f.get("MINISTERE", "") + " " + f.get("AUTORITE", ""))
    for idx, (_, keys) in enumerate(ENTITIES):
        if any(k in hay for k in keys):
            return idx
    nor = f.get("NOR", "")[:3].upper()
    return NOR_PREFIX.get(nor)


def main():
    now = datetime.now(PARIS)
    since_day = (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
    since_file = since_day.replace("-", "")
    today_plus1 = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    listing = fetch().decode("utf-8", "replace")
    files = sorted({m.group(1) for m in re.finditer(r'href="(JORF_(\d{8})-\d{6}\.tar\.gz)"', listing)
                    if m.group(2) >= since_file})
    texts, errors, ministeres, sample = {}, [], Counter(), []
    for name in files:
        try:
            raw = fetch(name)
            time.sleep(2)
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
                for member in tf:
                    base = member.name.rsplit("/", 1)[-1]
                    if not (member.isfile() and base.startswith("JORFTEXT") and base.endswith(".xml")):
                        continue
                    data = tf.extractfile(member).read()
                    f = parse_text(data)
                    if f.get("DATE_PUBLI", "") < since_day or not f.get("ID"):
                        continue
                    if f["DATE_PUBLI"] > today_plus1:  # ex. 2999-01-01 : texte sans date de parution
                        continue
                    texts[f["ID"]] = f
                    ministeres[f.get("MINISTERE") or f.get("AUTORITE") or "(vide)"] += 1
                    if len(sample) < 2:
                        sample.append(data[:1800].decode("utf-8", "replace"))
        except Exception as e:
            errors.append(f"{name} : {type(e).__name__} {e}")

    by_day = {}
    for f in texts.values():
        by_day.setdefault(f["DATE_PUBLI"], []).append(f)

    lines = [f"JORF — généré le {now:%Y-%m-%d %H:%M} (heure de Paris)",
             f"Archives lues : {len(files)} ; textes retenus : {len(texts)} ; "
             f"JO trouvés : {', '.join(sorted(by_day, reverse=True)) or 'aucun'}", ""]
    for day in sorted(by_day, reverse=True):
        items = by_day[day]
        num = next((i.get("NUM_PARUTION") for i in items if i.get("NUM_PARUTION")), "?")
        lines.append(f"# JO du {day} (n° {num}) — {len(items)} textes au total")
        for idx, (label, _) in enumerate(ENTITIES):
            hits = [i for i in items if entity_of(i) == idx]
            lines.append(f"## {label}")
            if not hits:
                lines.append("- rien")
            for kind, flag in (("Textes", False), ("Mesures nominatives", True)):
                sel = [h for h in hits
                       if bool(NOMINATIVE.search(h.get("TITREFULL") or h.get("TITRE", ""))) == flag]
                if sel:
                    lines.append(f"{kind} :")
                    for h in sel:
                        lines.append(f"- {h.get('TITREFULL') or h.get('TITRE', '')}")
                        lines.append(f"  https://www.legifrance.gouv.fr/jorf/id/{h['ID']}")
            lines.append("")
    if errors:
        lines += ["", "## Erreurs"] + [f"- {e}" for e in errors]
    out = "\n".join(lines) + "\n"
    if not by_day and os.path.exists("jorf.txt"):
        with open("jorf.txt", encoding="utf-8") as fh:
            if "# JO du" in fh.read():
                # rien d'exploitable aujourd'hui : on garde la dernière version valable
                print(f"AUCUN JO exploitable ({len(errors)} erreurs) : jorf.txt conservé", file=sys.stderr)
                sys.exit(1)
    with open("jorf.txt", "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"{len(texts)} textes, {len(errors)} erreurs")


if __name__ == "__main__":
    main()
