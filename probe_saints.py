#!/usr/bin/env python3
"""Sondage TEMPORAIRE : sources de saints du jour (écrit probe_saints.txt)."""
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"
now = datetime.now(ZoneInfo("Europe/Paris"))
MD = f"{now.month:02d}-{now.day:02d}"
out = []


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def text_of(h):
    h = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def block(title, fn):
    out.append(f"===== {title}")
    try:
        fn()
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")


# B. AELF : JSON complet
def aelf():
    data = json.loads(get(f"https://api.aelf.org/v1/informations/{now:%Y-%m-%d}/france"))
    out.append(json.dumps(data, ensure_ascii=False)[:2500])


# A. Nominis
def nominis():
    for url in ("https://nominis.cef.fr/", "https://nominis.cef.fr/contenus/accueil.html"):
        out.append(f"-- {url}")
        try:
            h = get(url)
            out.append(f"{len(h)} octets")
            m = re.search(r"(?is)(saint du jour|saints? du jour).{0,1500}", text_of(h))
            out.append((m.group(0) if m else text_of(h))[:1500])
            links = re.findall(r'href="([^"]*(?:saint|jour|nominis)[^"]*)"', h, re.I)[:15]
            out.append("liens : " + " | ".join(links))
        except Exception as e:
            out.append(f"ERREUR {type(e).__name__} {e}")


# C. Divinum Officium : martyrologe
def dof_martyrologe():
    tree = json.loads(get("https://api.github.com/repos/DivinumOfficium/divinum-officium/git/trees/master?recursive=1", 60))
    paths = [t["path"] for t in tree.get("tree", []) if "artyrolog" in t["path"] and MD in t["path"]]
    out.append("fichiers : " + " | ".join(paths[:12]))
    for p in paths[:3]:
        out.append(f"-- {p}")
        out.append(get(f"https://raw.githubusercontent.com/DivinumOfficium/divinum-officium/master/{p}")[:1800])


# D. Wikipédia FR
def wikipedia():
    page = f"{now.day}{'er' if now.day == 1 else ''}_{['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'][now.month-1]}"
    url = "https://fr.wikipedia.org/w/api.php?action=parse&format=json&prop=wikitext&page=" + urllib.parse.quote(page)
    wt = json.loads(get(url))["parse"]["wikitext"]["*"]
    out.append(f"page {page}, {len(wt)} caractères")
    i = wt.find("Célébrations")
    out.append(wt[i:i + 3500] if i >= 0 else wt[:2000])


block("AELF JSON complet", aelf)
block("Nominis", nominis)
block("Divinum Officium martyrologe", dof_martyrologe)
block("Wikipédia fr", wikipedia)

with open("probe_saints.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("probe_saints.txt écrit")
