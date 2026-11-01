#!/usr/bin/env python3
"""Lit des flux RSS publics et écrit veille.txt (titres, liens, dates, chapôs)."""
import re
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
MAX_AGE_H = 30          # on garde les articles de moins de 30 h
MAX_PER_FEED = 12
UA = "Mozilla/5.0 (compatible; veille-quotidienne/1.0; +https://github.com)"

# (rubrique, média, URL du flux)
FEEDS = [
    ("France", "Le Monde", "https://www.lemonde.fr/rss/une.xml"),
    ("France", "Le Monde", "https://www.lemonde.fr/rss/en_continu.xml"),
    ("France", "Le Monde", "https://www.lemonde.fr/politique/rss_full.xml"),
    ("Gendarmerie-police-justice", "Le Monde", "https://www.lemonde.fr/police-justice/rss_full.xml"),
    ("International", "Le Monde", "https://www.lemonde.fr/international/rss_full.xml"),
    ("France", "Le Figaro", "https://www.lefigaro.fr/rss/figaro_actualites.xml"),
    ("France", "Le Figaro", "https://www.lefigaro.fr/rss/figaro_actualite-france.xml"),
    ("France", "Le Figaro", "https://www.lefigaro.fr/rss/figaro_politique.xml"),
    ("International", "Le Figaro", "https://www.lefigaro.fr/rss/figaro_international.xml"),
    ("France", "franceinfo", "https://www.francetvinfo.fr/titres.rss"),
    ("International", "franceinfo", "https://www.francetvinfo.fr/monde.rss"),
    ("France", "franceinfo", "https://www.francetvinfo.fr/politique.rss"),
    ("Gendarmerie-police-justice", "franceinfo", "https://www.francetvinfo.fr/faits-divers.rss"),
    ("Gendarmerie-police-justice", "franceinfo", "https://www.francetvinfo.fr/justice.rss"),
    ("France", "Ouest-France", "https://www.ouest-france.fr/rss/une"),
]


def clean(text, limit=220):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        d = parsedate_to_datetime(value)
    except Exception:
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(data):
    """Retourne une liste de (date, titre, lien, chapô), RSS ou Atom."""
    root = ET.fromstring(data)
    out = []
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        f = {}
        for child in item:
            name = local(child.tag)
            if name == "link":
                f.setdefault("link", child.attrib.get("href") or (child.text or "").strip())
            elif name in ("title", "pubDate", "published", "updated", "date",
                          "description", "summary"):
                f.setdefault(name, (child.text or "").strip())
        date = parse_date(f.get("pubDate") or f.get("published")
                          or f.get("updated") or f.get("date"))
        out.append((date, clean(f.get("title", ""), 200), f.get("link", ""),
                    clean(f.get("description") or f.get("summary", ""))))
    return out


def main():
    now = datetime.now(timezone.utc)
    limit = now - timedelta(hours=MAX_AGE_H)
    sections, errors, seen, stats = {}, [], set(), []
    for rubrique, media, url in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                items = parse_feed(r.read())
        except Exception as e:  # un flux en panne ne bloque pas les autres
            errors.append(f"{media} {url} : {type(e).__name__} {e}")
            continue
        kept = [i for i in items if i[0] and i[0] >= limit and i[1] and i[2]]
        if media == "AFP":
            nodate = sum(1 for i in items if not i[0])
            stats.append(f"AFP {url} : {len(items)} entrées, {nodate} sans date, {len(kept)} récentes ; plus récente : {max((i[0] for i in items if i[0]), default=None)} ; ex. : {items[0][1] if items else '-'}")
        kept.sort(key=lambda i: i[0], reverse=True)
        for date, title, link, desc in kept[:MAX_PER_FEED]:
            if link in seen:
                continue
            seen.add(link)
            sections.setdefault(rubrique, []).append((date, media, title, link, desc))

    lines = [f"VEILLE — généré le {now.astimezone(PARIS):%Y-%m-%d %H:%M} (heure de Paris)",
             f"Articles publiés depuis moins de {MAX_AGE_H} h, du plus récent au plus ancien.", ""]
    for rubrique in ("International", "France", "Gendarmerie-police-justice"):
        lines.append(f"## {rubrique}")
        for date, media, title, link, desc in sorted(sections.get(rubrique, []),
                                                    key=lambda i: i[0], reverse=True):
            lines.append(f"- [{date.astimezone(PARIS):%d/%m %H:%M}] {media} — {title}")
            lines.append(f"  {link}")
            if desc:
                lines.append(f"  {desc}")
        lines.append("")
    if stats:
        lines.append("## Diagnostic AFP")
        lines += [f"- {e}" for e in stats]
    if errors:
        lines.append("## Flux en erreur")
        lines += [f"- {e}" for e in errors]
    with open("veille.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{sum(len(v) for v in sections.values())} articles, {len(errors)} flux en erreur")


if __name__ == "__main__":
    main()
