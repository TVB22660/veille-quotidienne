#!/usr/bin/env python3
"""Script de sondage TEMPORAIRE : écrit debug_dof.txt (début du HTML de pages Divinum Officium)."""
import re
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"
now = datetime.now(ZoneInfo("Europe/Paris"))
d = f"{now.month}-{now.day}-{now.year}"
v = urllib.parse.quote("Rubrics 1960 - 1960")
BASE = "https://www.divinumofficium.com/cgi-bin"
URLS = [
    f"{BASE}/missa/missa.pl?date={d}&version={v}&lang2=English",
    f"{BASE}/horas/officium.pl?date={d}&command=prayLaudes&version={v}&lang2=English",
    f"{BASE}/horas/kalendar.pl?kyear={now.year}&browsekal=Browse%20Calendar&version={v}",
]
out = []
for url in URLS:
    out.append(f"===== {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode("utf-8", "replace")
        out.append(f"status OK, {len(raw)} octets")
        body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", raw)
        out.append("--- HTML (4000 premiers caractères) ---")
        out.append(body[:4000])
        txt = re.sub(r"<[^>]+>", " ", body)
        txt = re.sub(r"\s+", " ", txt)
        out.append("--- TEXTE (1500 premiers caractères) ---")
        out.append(txt[:1500])
    except Exception as e:
        out.append(f"ERREUR {type(e).__name__} {e}")
    out.append("")
with open("debug_dof.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("debug_dof.txt écrit")
