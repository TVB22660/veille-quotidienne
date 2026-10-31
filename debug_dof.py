#!/usr/bin/env python3
"""Script de sondage TEMPORAIRE : écrit debug_dof.txt (données Divinum Officium sur GitHub)."""
import json
import urllib.request

UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"
REPO = "DivinumOfficium/divinum-officium"
RAW = f"https://raw.githubusercontent.com/{REPO}/master"
API = f"https://api.github.com/repos/{REPO}/contents"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


out = []
# 1. Contenu des dossiers de calendriers
for d in ("web/www/horas/Latin/Tabulae/Kalendaria", "web/www/horas/Latin/Tabulae"):
    out.append(f"===== LISTE {d}")
    try:
        data = json.loads(get(f"{API}/{d}"))
        out.append(", ".join(f"{x['name']}({x['type']})" for x in data))
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")

# 2. Fichier du calendrier 1960
for name in ("1960.txt", "1962.txt"):
    url = f"{RAW}/web/www/horas/Latin/Tabulae/Kalendaria/{name}"
    out.append(f"===== {url}")
    try:
        txt = get(url)
        lines = txt.splitlines()
        out.append(f"{len(lines)} lignes")
        out.append("--- 25 premières lignes ---")
        out += lines[:25]
        out.append("--- lignes 10-30 à 11-03 ---")
        out += [l for l in lines if l.startswith(("10-30", "10-31", "11-01", "11-02", "11-03"))]
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")

# 3. Fichiers de fête du 31 octobre (latin et anglais)
for url in (f"{RAW}/web/www/missa/Latin/Sancti/10-31.txt",
            f"{RAW}/web/www/missa/English/Sancti/10-31.txt",
            f"{RAW}/web/www/horas/Latin/Sancti/10-31.txt"):
    out.append(f"===== {url}")
    try:
        txt = get(url)
        out.append(txt[:1800])
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")

with open("debug_dof.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("debug_dof.txt écrit")
