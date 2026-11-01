#!/usr/bin/env python3
"""Écrit saints.txt : saint du jour et rang liturgique, selon DEUX calendriers.

1. Calendrier romain actuel (France) : API publique de l'AELF (https://api.aelf.org)
   pour le jour liturgique et le rang, flux RSS de Nominis (CEF) pour le(s) saint(s).
2. Calendrier traditionnel de 1962 : moteur Divinum Officium (rubriques de 1960),
   exécuté localement (dépôt cloné dans /tmp/dof par le workflow), car le site
   public refuse les accès automatiques, pour le jour et le rang ; martyrologe
   romain (texte français du même dépôt) pour les saints du jour.

Le fichier est toujours écrit ; chaque section dit « INDISPONIBLE » en cas d'échec,
indépendamment de l'autre.
"""
import html
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"
DOF_DIR = "/tmp/dof"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
# Champs utiles de l'API AELF, dans l'ordre d'affichage
CHAMPS = [
    ("jour_liturgique_nom", "Jour liturgique"),
    ("fete", "Fête / saint"),
    ("degre", "Rang"),
    ("ligne1", "Ligne 1"),
    ("ligne2", "Ligne 2"),
    ("ligne3", "Ligne 3"),
    ("couleur", "Couleur liturgique"),
    ("temps_liturgique", "Temps liturgique"),
]


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def section_aelf(iso):
    """Calendrier romain actuel, via l'API AELF. Retourne une liste de lignes."""
    data = get_json(f"https://api.aelf.org/v1/informations/{iso}/france")
    info = data.get("informations", data)
    if not isinstance(info, dict):
        raise ValueError("réponse inattendue")
    lines = []
    for key, label in CHAMPS:
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label} : {value.strip()}")
    if not lines:
        raise ValueError("aucun champ exploitable dans la réponse")
    return lines


def get_text(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def section_nominis():
    """Saint(s) du jour selon Nominis (Conférence des évêques de France), via son flux RSS."""
    xml = get_text("https://nominis.cef.fr/rss/nominis.php")
    items = re.findall(r"(?is)<item>.*?<title>(.*?)</title>.*?</item>", xml)
    lines = []
    for t in items:
        t = text_of(re.sub(r"(?is)<!\[CDATA\[(.*?)\]\]>", r"\1", t))
        t = re.sub(r"\s+", " ", t)
        if t:
            lines.append(f"- Saint du jour (Nominis) : {t}")
    if not lines:
        raise ValueError("aucun saint dans le flux Nominis")
    return lines


def section_martyrologe(now):
    """Martyrologe romain du jour (texte français du dépôt Divinum Officium)."""
    rel = f"obsolete/martyrologium-source/Francais/Martyrologium/{now:%m-%d}.txt"
    local = os.path.join(DOF_DIR, rel)
    if os.path.isfile(local):
        with open(local, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    else:
        raw = get_text("https://raw.githubusercontent.com/DivinumOfficium/"
                       f"divinum-officium/master/{rel}")
    lines = []
    rows = [e.strip() for e in raw.splitlines() if e.strip()]
    # la 1re ligne est la date en calendes/nones/ides ; « _ » sépare les blocs
    for entry in rows[1:]:
        if entry == "_":
            continue
        if len(entry) > 230:
            entry = entry[:227].rstrip() + "…"
        lines.append(f"- Martyrologe : {entry}")
    if not lines:
        raise ValueError("martyrologe vide")
    return lines[:8]


def text_of(fragment):
    txt = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(txt)).strip()


def parse_dof(page):
    """Extrait l'en-tête de la page de la messe : titre du jour + rang, puis compléments."""
    m = re.search(r"(?is)<FORM[^>]*>\s*(<P[^>]*>.*?</P>)", page)
    if not m:
        raise ValueError("en-tête du jour introuvable dans la page Divinum Officium")
    parts = re.split(r"(?i)<br\s*/?>", m.group(1))
    lines = []
    title = text_of(parts[0])
    if not title:
        raise ValueError("titre du jour vide")
    lines.append(f"- Jour : {title}")
    for extra in parts[1:]:
        t = text_of(extra)
        if t:
            lines.append(f"- {t}")
    return lines


def section_1962(now):
    """Calendrier de 1962 : moteur Divinum Officium en local (rubriques de 1960)."""
    cgi = f"{DOF_DIR}/web/cgi-bin/missa"
    if not os.path.isdir(cgi):
        raise FileNotFoundError("moteur Divinum Officium non installé")
    env = dict(
        os.environ,
        REQUEST_METHOD="GET",
        QUERY_STRING=f"date={now.month}-{now.day}-{now.year}"
                     "&version=Rubrics%201960%20-%201960&lang2=English",
        SCRIPT_NAME="/cgi-bin/missa/missa.pl",
    )
    p = subprocess.run(["perl", "missa.pl"], cwd=cgi, env=env, capture_output=True,
                       text=True, timeout=180)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError(f"moteur en erreur (code {p.returncode}) {p.stderr[-200:]}")
    return parse_dof(p.stdout)


def main():
    now = datetime.now(PARIS)
    iso = f"{now:%Y-%m-%d}"
    date_fr = f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}"
    lines = [f"SAINTS — généré le {now:%Y-%m-%d %H:%M} (heure de Paris)",
             f"Date : {date_fr} ({iso})", ""]

    lines.append("## Calendrier romain actuel (AELF, France)")
    try:
        lines += section_aelf(iso)
        print("AELF : ok")
    except Exception as e:  # ne bloque jamais le reste du workflow
        lines.append(f"- Jour liturgique et rang : INDISPONIBLE : {type(e).__name__} {e}")
        print(f"AELF : indisponible ({type(e).__name__} {e})")
    try:
        lines += section_nominis()
        print("Nominis : ok")
    except Exception as e:
        lines.append(f"- Saint du jour (Nominis) : INDISPONIBLE : {type(e).__name__} {e}")
        print(f"Nominis : indisponible ({type(e).__name__} {e})")
    lines.append("")

    lines.append("## Calendrier traditionnel de 1962 (Divinum Officium, rubriques de 1960)")
    try:
        lines += section_1962(now)
        print("1962 : ok")
    except Exception as e:
        lines.append(f"- Jour et rang : INDISPONIBLE : {type(e).__name__} {e}")
        print(f"1962 : indisponible ({type(e).__name__} {e})")
    try:
        lines += section_martyrologe(now)
        print("Martyrologe : ok")
    except Exception as e:
        lines.append(f"- Martyrologe : INDISPONIBLE : {type(e).__name__} {e}")
        print(f"Martyrologe : indisponible ({type(e).__name__} {e})")

    with open("saints.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
