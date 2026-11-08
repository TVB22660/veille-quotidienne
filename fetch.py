#!/usr/bin/env python3
"""Lit des flux RSS publics et écrit veille.txt (titres, liens, dates, chapôs)."""
import re
import html
import unicodedata
import urllib.request
from urllib.parse import urlparse
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
    # armées : un flux spécialisé (un flux en panne ne bloque pas les autres)
    ("Gendarmerie-police-justice", "Zone Militaire", "https://www.opex360.com/feed/"),
]

# --- Tri par rubrique -------------------------------------------------------
# Les flux « généraux » des journaux mélangent tout. On reclasse chaque article d'après
# la première partie de son adresse (rubrique du journal), sans liste de sujets.
SEG_INTERNATIONAL = {"international", "monde"}
SEG_JUSTICE = {"faits-divers", "justice", "police-justice"}
SEG_ECARTES = {"sport", "sports", "football", "rugby", "tennis", "cyclisme", "culture", "videos", "video",
               "replay-radio", "podcasts", "jeux", "loisirs", "route-du-rhum", "voile", "sortir", "gastronomie", "idees"}

# Titres du genre « États-Unis : … » : un pays étranger en tête, suivi de deux-points (liste stable, sans lien avec l'actualité)
PAYS_ETRANGERS = ("États-Unis|Etats-Unis|Chine|Russie|Ukraine|Israël|Iran|Irak|Gaza|Liban|Syrie|Turquie|Royaume-Uni|"
                  "Allemagne|Espagne|Italie|Portugal|Pologne|Hongrie|Roumanie|Moldavie|Belgique|Suisse|Pays-Bas|Grèce|"
                  "Japon|Inde|Pakistan|Corée du Nord|Corée du Sud|Taïwan|Brésil|Argentine|Venezuela|Colombie|Canada|"
                  "Mexique|Cuba|Haïti|Algérie|Maroc|Tunisie|Égypte|Soudan|Éthiopie|Afrique du Sud|Nigeria|Mali|Niger|"
                  "Arabie saoudite|Australie|Birmanie|Thaïlande|Philippines|Indonésie")
RE_PAYS_EN_TETE = re.compile(r"^(?:%s)\s*:" % PAYS_ETRANGERS)

# Mots trop courants pour caractériser une affaire (comparaison entre articles)
MOTS_VIDES = set(("apres avant contre selon entre depuis pendant cette leurs ainsi alors dans sous cinq trois "
                  "quatre france francais francaise aussi encore toute toutes tous leur dont cela comme plus moins "
                  "avoir etre fait faire pour sans vers chez notre votre pourquoi comment direct video apres").split())


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def segment(url):
    p = [x for x in urlparse(url).path.split("/") if x]
    return p[0] if p else ""


def jetons(titre):
    """{mot: poids} : 2 pour un nom propre (majuscule hors début de titre), 1 sinon ; mots de 5 lettres et plus."""
    res = {}
    mots = re.findall(r"[A-Za-zÀ-ÿ]+", titre)
    for i, w in enumerate(mots):
        k = sans_accents(w)
        if k.endswith("s") and len(k) > 5:
            k = k[:-1]                      # démocrate / démocrates : même mot
        if len(k) < 5 or k in MOTS_VIDES:
            continue
        propre = i > 0 and w[0].isupper()
        res[k] = max(res.get(k, 0), 2 if propre else 1)
    return res


def meme_affaire(a, b, seuil=3):
    """Deux titres traitent la même affaire si leurs mots communs pèsent au moins `seuil`
    (par exemple un nom propre + un autre mot, ou deux noms propres)."""
    return sum(max(a[k], b[k]) for k in a if k in b) >= seuil


def rubrique_reelle(rubrique, url, titre=""):
    """None = article écarté (sport, culture...) ; sinon la rubrique d'après l'adresse."""
    seg = segment(url)
    if seg in SEG_ECARTES:
        return None
    if seg in SEG_INTERNATIONAL or RE_PAYS_EN_TETE.match(titre):
        return "International"
    if seg in SEG_JUSTICE and rubrique == "France":
        return "Gendarmerie-police-justice"
    return rubrique


def trier_rubriques(sections):
    """Reclasse par adresse, puis renvoie vers International tout article France / Gendarmerie
    qui traite la même affaire qu'un article déjà international. Retourne (sections, stats)."""
    neuf, ecartes, deplaces = {}, 0, 0
    for rubrique, items in sections.items():
        for it in items:
            r = rubrique_reelle(rubrique, it[3], it[2])
            if r is None:
                ecartes += 1
                continue
            neuf.setdefault(r, []).append(it)
    refs = [jetons(it[2]) for it in neuf.get("International", [])]
    # un mot présent dans au moins un quart des titres internationaux du jour (4 au minimum) est le sujet du jour : il suffit à rattacher un article
    freq = {}
    for r in refs:
        for k in r:
            freq[k] = freq.get(k, 0) + 1
    for r in refs:
        for k in r:
            if freq[k] >= max(4, len(refs) / 4):
                r[k] = 3
    for rubrique in ("France", "Gendarmerie-police-justice"):
        gardes = []
        for it in neuf.get(rubrique, []):
            j = jetons(it[2])
            if any(meme_affaire(j, r) for r in refs):
                neuf.setdefault("International", []).append(it)
                deplaces += 1
            else:
                gardes.append(it)
        neuf[rubrique] = gardes
    return neuf, f"{ecartes} article(s) écartés (sport, culture…), {deplaces} renvoyé(s) vers International"


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
            cle = link.split("#")[0]
            if cle in seen:
                continue
            seen.add(cle)
            sections.setdefault(rubrique, []).append((date, media, title, link, desc))

    sections, tri = trier_rubriques(sections)
    stats.append(f"Tri : {tri}")

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
        lines.append("## Diagnostic")
        lines += [f"- {e}" for e in stats]
    if errors:
        lines.append("## Flux en erreur")
        lines += [f"- {e}" for e in errors]
    with open("veille.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{sum(len(v) for v in sections.values())} articles, {len(errors)} flux en erreur")


if __name__ == "__main__":
    main()
