#!/usr/bin/env python3
"""Écrit marees.txt : pleines mers et basses mers de Perros-Guirec (heure de Paris).

Plusieurs sources sont essayées dans l'ordre ; la première qui donne un résultat
cohérent est retenue. Le fichier est toujours écrit : en cas d'échec il commence par
« INDISPONIBLE » et contient un extrait de ce qui a été lu, pour comprendre pourquoi.
Format d'une ligne : AAAA-MM-JJ HH:MM PM|BM hauteur_en_m [coef=NN]
"""
import html
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
        "septembre", "octobre", "novembre", "decembre"]
MOIS_ACC = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]


def sources(today):
    liens = []
    for d in (today, today.replace(day=1) + timedelta(days=32)):
        liens.append("https://marine.meteoconsult.fr/meteo-marine/horaires-des-marees/"
                     f"perros-guirec-962/{MOIS[d.month - 1]}-{d.year}")
    liens.append("https://maree.info/66")
    liens.append("https://point-maree.fr/port/perros-guirec/")
    return liens


def telecharger(url, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def vers_texte(h):
    h = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


JOURS_RE = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|lun|mar|mer|jeu|ven|sam|dim)"
MOIS_RE = r"(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)"
TOKEN = re.compile(
    rf"(?P<date>\b{JOURS_RE}\b\.?\s+(?P<jour>0?[1-9]|[12]\d|3[01])\b(?![h:.,]\d)(?:\s+(?P<mois>{MOIS_RE})\b)?)"
    r"|(?P<heure>\b(?P<hh>[01]?\d|2[0-3])\s?[h:]\s?(?P<mm>[0-5]\d)\b)"
    r"|(?P<haut>\b(?P<m>\d{1,2}[.,]\d{1,2})\s?m\b)"
    r"|(?P<coef>\b(?P<c>\d{2,3})\b)",
    re.I)


def analyser(texte, today):
    """Découpe le texte par jour ; dans chaque jour, apparie les heures et les hauteurs
    dans l'ordre (que la page les range en colonnes ou ligne par ligne). Les coefficients
    sont les nombres qui suivent directement une hauteur."""
    blocs, cur, mois_cur, dernier = {}, None, None, None
    for m in TOKEN.finditer(texte):
        if m.group("date"):
            j = int(m.group("jour"))
            if m.group("mois"):
                nom = m.group("mois").lower().replace("é", "e").replace("û", "u").replace("è", "e")
                mo = MOIS.index(nom) + 1
            elif mois_cur is None:
                mo = today.month
            else:
                mo = mois_cur
            if mois_cur is not None and not m.group("mois") and cur is not None and j < cur.day - 15:
                mo = mois_cur % 12 + 1
            an = today.year
            if mo < today.month - 6:
                an += 1
            if mo > today.month + 6:
                an -= 1
            try:
                cur = date(an, mo, j)
            except ValueError:
                cur = None
            mois_cur = mo
            dernier = None
            if cur is not None:
                blocs.setdefault(cur, {"t": [], "h": [], "c": []})
        elif cur is None:
            continue
        elif m.group("heure"):
            blocs[cur]["t"].append((int(m.group("hh")), int(m.group("mm"))))
            dernier = "t"
        elif m.group("haut"):
            blocs[cur]["h"].append(float(m.group("m").replace(",", ".")))
            dernier = "h"
        elif m.group("coef"):
            c = int(m.group("c"))
            if dernier in ("h", "c") and 20 <= c <= 120:
                blocs[cur]["c"].append(c)
                dernier = "c"
            else:
                dernier = None
    evts = []
    for d, b in blocs.items():
        if not b["t"] or len(b["t"]) != len(b["h"]):
            continue
        jour = []
        for (hh, mm), h in zip(b["t"], b["h"]):
            jour.append({"dt": datetime(d.year, d.month, d.day, hh, mm), "h": h, "coef": None})
        b["evts"] = jour
        evts.extend(jour)
    evts.sort(key=lambda e: e["dt"])
    uniques = []
    for e in evts:
        if not uniques or e["dt"] != uniques[-1]["dt"]:
            uniques.append(e)
    classer(uniques)
    for d, b in blocs.items():
        pm = [e for e in b.get("evts", []) if e["type"] == "PM"]
        if b["c"] and len(b["c"]) == len(pm):
            for e, c in zip(pm, b["c"]):
                e["coef"] = c
    return uniques


def classer(evts):
    for i, e in enumerate(evts):
        voisins = [evts[j]["h"] for j in (i - 1, i + 1) if 0 <= j < len(evts)]
        e["type"] = "PM" if e["h"] > sum(voisins) / len(voisins) else "BM"


def coherent(evts, today):
    if len(evts) < 6:
        return "moins de 6 marées lues"
    jours = {e["dt"].date() for e in evts}
    if today not in jours:
        return "le jour même n'apparaît pas"
    if not all(0 <= e["h"] <= 15 for e in evts):
        return "hauteurs hors plage"
    alt = sum(1 for a, b in zip(evts, evts[1:]) if a["type"] != b["type"])
    if alt < 0.8 * (len(evts) - 1):
        return "alternance pleine mer / basse mer incohérente"
    ecarts = [(b["dt"] - a["dt"]).total_seconds() / 3600 for a, b in zip(evts, evts[1:])]
    if any(not (3.5 <= x <= 9.0) for x in ecarts if x < 24):
        return "écarts entre marées incohérents"
    return None


def main():
    now = datetime.now(PARIS)
    today = now.date()
    rapport, retenu, evts = [], None, []
    for url in sources(today):
        try:
            texte = vers_texte(telecharger(url))
        except Exception as e:
            rapport.append(f"{url} : inaccessible ({e})")
            continue
        brut = analyser(texte, today)
        pb = coherent(brut, today)
        if pb is None:
            retenu, evts = url, brut
            break
        i = texte.find("h")
        rapport.append(f"{url} : {pb} ; extrait : {texte[max(0, i - 200):i + 600]!r}")
    lignes = []
    if retenu:
        debut = today - timedelta(days=1)
        fin = today + timedelta(days=10)
        lignes.append(f"MARÉES — Perros-Guirec — généré le {now:%Y-%m-%d %H:%M} (heure de Paris)")
        lignes.append(f"Source : {retenu}")
        for e in evts:
            if debut <= e["dt"].date() <= fin:
                c = f" coef={e['coef']}" if e["coef"] else ""
                lignes.append(f"{e['dt']:%Y-%m-%d %H:%M} {e['type']} {e['h']:.2f}{c}")
    else:
        lignes.append(f"MARÉES — Perros-Guirec — généré le {now:%Y-%m-%d %H:%M} (heure de Paris)")
        lignes.append("INDISPONIBLE : aucune source exploitable")
        lignes.extend(rapport)
    with open("marees.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")


if __name__ == "__main__":
    main()
