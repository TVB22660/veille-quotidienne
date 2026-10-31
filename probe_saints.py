#!/usr/bin/env python3
"""Sondage TEMPORAIRE n°2 : formats Nominis (RSS, HTML) et martyrologe français (écrit probe_saints.txt)."""
import re
import urllib.request

UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"
RAW = "https://raw.githubusercontent.com/DivinumOfficium/divinum-officium/master/obsolete/martyrologium-source"
out = []


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def block(title, fn):
    out.append(f"===== {title}")
    try:
        fn()
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")


def rss():
    out.append(get("https://nominis.cef.fr/rss/nominis.php")[:3500])


def home_html():
    h = get("https://nominis.cef.fr/")
    i = h.find("couvrir")
    out.append(f"position 'couvrir' : {i}")
    out.append(h[max(0, i - 300): i + 2500])


def martyrologe():
    for d in ("10-31", "11-01", "11-02"):
        out.append(f"-- Francais/Martyrologium/{d}.txt")
        t = get(f"{RAW}/Francais/Martyrologium/{d}.txt")
        out.append(t[:2200] if d == "10-31" else t[:500])
    out.append("-- Latin/Martyrologium1960/10-31.txt")
    out.append(get(f"{RAW}/Latin/Martyrologium1960/10-31.txt")[:1200])


block("Nominis RSS", rss)
block("Nominis HTML autour de 'A découvrir'", home_html)
block("Martyrologe (DoF, obsolete)", martyrologe)

with open("probe_saints.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("probe_saints.txt écrit")
