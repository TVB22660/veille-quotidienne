#!/usr/bin/env python3
"""Relève la météo (Issy-les-Moulineaux, Trélévern) et écrit meteo.txt.

Source principale : Open-Meteo (gratuit, sans clé) ; secours : MET Norway (api.met.no).
Les appels sont retentés en cas de refus temporaire (HTTP 429, erreurs serveur).
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
LIEUX = {"issy": (48.8245, 2.2733), "trelevern": (48.8217, -3.3797)}
UA = "veille-quotidienne/1.0 (https://github.com/TVB22660/veille-quotidienne)"
PAUSES = (5, 20, 45)   # secondes entre deux essais


def get_json(url, essais=4, pauses=PAUSES):
    derniere = "erreur inconnue"
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            derniere = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:
            derniere = type(e).__name__
        if i < essais - 1:
            time.sleep(pauses[min(i, len(pauses) - 1)])
    raise RuntimeError(derniere)


# --- Open-Meteo -------------------------------------------------------------

def open_meteo():
    cles = list(LIEUX)
    lat = ",".join(str(LIEUX[k][0]) for k in cles)
    lon = ",".join(str(LIEUX[k][1]) for k in cles)
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
           "wind_speed_10m_max,wind_gusts_10m_max&timezone=Europe%%2FParis&forecast_days=2" % (lat, lon))
    return lire_open_meteo(get_json(url), cles)


def lire_open_meteo(data, cles):
    blocs = data if isinstance(data, list) else [data]
    if len(blocs) != len(cles):
        raise RuntimeError("réponse Open-Meteo inattendue")
    res = {}
    for cle, bloc in zip(cles, blocs):
        d = bloc["daily"]
        res[cle] = [{
            "date": d["time"][i],
            "code": d["weather_code"][i],
            "min": d["temperature_2m_min"][i],
            "max": d["temperature_2m_max"][i],
            "pluie": (d.get("precipitation_probability_max") or [None] * 9)[i],
            "vent": d["wind_speed_10m_max"][i],
            "rafales": d["wind_gusts_10m_max"][i],
        } for i in range(len(d["time"]))]
    return res


# --- MET Norway (secours) ---------------------------------------------------

def code_depuis_symbole(symbole):
    s = re.sub(r"_(day|night|polartwilight)$", "", symbole or "")
    if "thunder" in s:
        return 95
    table = {"clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3, "fog": 45,
             "lightrain": 61, "rain": 63, "heavyrain": 65,
             "lightrainshowers": 80, "rainshowers": 80, "heavyrainshowers": 82,
             "lightsleet": 67, "sleet": 67, "heavysleet": 67,
             "lightsleetshowers": 67, "sleetshowers": 67, "heavysleetshowers": 67,
             "lightsnow": 71, "snow": 73, "heavysnow": 75,
             "lightsnowshowers": 85, "snowshowers": 85, "heavysnowshowers": 86}
    return table.get(s, 3)


def met_norvege(cle):
    lat, lon = LIEUX[cle]
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%s&lon=%s" % (lat, lon)
    return lire_met(get_json(url))


def lire_met(data):
    par_jour = {}
    for pt in data["properties"]["timeseries"]:
        t = datetime.fromisoformat(pt["time"].replace("Z", "+00:00")).astimezone(PARIS)
        par_jour.setdefault(t.strftime("%Y-%m-%d"), []).append((t, pt["data"]))
    jours = []
    for jour in sorted(par_jour)[:2]:
        pts = par_jour[jour]
        temps = [p["instant"]["details"]["air_temperature"] for _, p in pts
                 if "air_temperature" in p["instant"]["details"]]
        vents = [p["instant"]["details"]["wind_speed"] * 3.6 for _, p in pts
                 if "wind_speed" in p["instant"]["details"]]
        rafales = [p["instant"]["details"]["wind_speed_of_gust"] * 3.6 for _, p in pts
                   if "wind_speed_of_gust" in p["instant"]["details"]]
        probas = []
        symboles = []
        for t, p in pts:
            for bloc in ("next_1_hours", "next_6_hours"):
                if bloc in p:
                    pr = p[bloc].get("details", {}).get("probability_of_precipitation")
                    if pr is not None:
                        probas.append(pr)
            if 7 <= t.hour <= 21:
                for bloc in ("next_1_hours", "next_6_hours"):
                    if bloc in p and "summary" in p[bloc]:
                        symboles.append(code_depuis_symbole(p[bloc]["summary"]["symbol_code"]))
                        break
        if not temps or len(pts) < 4:
            continue    # journée trop partielle
        code = Counter(symboles).most_common(1)[0][0] if symboles else 3
        jours.append({"date": jour, "code": code, "min": min(temps), "max": max(temps),
                      "pluie": max(probas) if probas else None,
                      "vent": max(vents) if vents else None,
                      "rafales": max(rafales) if rafales else None})
    if not jours:
        raise RuntimeError("réponse MET Norway sans journée exploitable")
    return jours


# --- Fichier ----------------------------------------------------------------

def num(x):
    return "-" if x is None else ("%.1f" % x).rstrip("0").rstrip(".")


def ligne(cle, j, source):
    return "%s %s code=%s min=%s max=%s pluie=%s vent=%s rafales=%s src=%s" % (
        cle, j["date"], j["code"], num(j["min"]), num(j["max"]), num(j["pluie"]),
        num(j["vent"]), num(j["rafales"]), source)


def ancien_valide(chemin, maintenant):
    try:
        texte = open(chemin, encoding="utf-8").read()
    except OSError:
        return False
    g = re.search(r"généré le (\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})", texte)
    if not g or "INDISPONIBLE" in texte:
        return False
    gen = datetime(*map(int, g.groups()), tzinfo=PARIS)
    return maintenant - gen < timedelta(hours=24)


def main():
    maintenant = datetime.now(PARIS)
    erreurs, lignes, source = [], [], None
    try:
        res = open_meteo()
        source = "open-meteo"
    except Exception as e:
        erreurs.append("open-meteo : %s" % e)
        res = {}
        try:
            for cle in LIEUX:
                res[cle] = met_norvege(cle)
            source = "met.no"
        except Exception as e2:
            erreurs.append("met.no : %s" % e2)
            res = None
    if res:
        for cle, jours in res.items():
            lignes += [ligne(cle, j, source) for j in jours]
    entete = "MÉTÉO — généré le %s (heure de Paris)" % maintenant.strftime("%Y-%m-%d %H:%M")
    if not lignes:
        if ancien_valide("meteo.txt", maintenant):
            print("Météo indisponible (%s) : fichier précédent conservé" % " ; ".join(erreurs))
            return
        sortie = [entete, "INDISPONIBLE : " + " ; ".join(erreurs)]
    else:
        sortie = [entete, "Source : %s%s" % (source, " (secours ; " + erreurs[0] + ")" if erreurs else "")] + lignes
    with open("meteo.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sortie) + "\n")
    print("\n".join(sortie))


if __name__ == "__main__":
    main()
