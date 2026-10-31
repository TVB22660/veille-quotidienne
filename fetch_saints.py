#!/usr/bin/env python3
"""Écrit saints.txt : saint du jour et rang liturgique (calendrier romain, France).

Source : API publique de l'AELF (Association épiscopale liturgique pour les pays
francophones), https://api.aelf.org. Le fichier est toujours écrit, même en cas
d'échec (ligne « indisponible »), pour que le récap sache quoi dire.
"""
import json
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
# Champs utiles de l'API, dans l'ordre d'affichage
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


def main():
    now = datetime.now(PARIS)
    iso = f"{now:%Y-%m-%d}"
    date_fr = f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}"
    lines = [f"SAINTS — généré le {now:%Y-%m-%d %H:%M} (heure de Paris)",
             f"Date : {date_fr} ({iso})",
             "Source : AELF, calendrier liturgique romain pour la France "
             f"(https://api.aelf.org/v1/informations/{iso}/france)", ""]
    try:
        data = get_json(f"https://api.aelf.org/v1/informations/{iso}/france")
        info = data.get("informations", data)
        if not isinstance(info, dict):
            raise ValueError("réponse inattendue")
        wrote = 0
        for key, label in CHAMPS:
            value = info.get(key)
            if isinstance(value, str) and value.strip():
                lines.append(f"- {label} : {value.strip()}")
                wrote += 1
        if not wrote:
            raise ValueError("aucun champ exploitable dans la réponse")
        print(f"saints.txt : {wrote} champs pour {iso}")
    except Exception as e:  # ne bloque jamais le reste du workflow
        lines.append(f"INDISPONIBLE : {type(e).__name__} {e}")
        print(f"saints.txt : indisponible ({type(e).__name__} {e})")
    with open("saints.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
