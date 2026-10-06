#!/usr/bin/env python3
"""Génère un calendrier iCalendar (.ics) d'événements sportifs choisis.

Sources : API publique de la LNH (api-web.nhle.com), données publiques
d'ESPN (site.api.espn.com) et une liste manuelle dans config.yaml.

Usage : python generate.py --config config.yaml --out public/sports.ics
Variable optionnelle PREVIOUS_ICS_URL : si une source échoue, ses événements
sont repris de la version publiée précédente au lieu de disparaître.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import yaml

UTC = dt.timezone.utc
UID_DOMAIN = "calendrier-sports"
USER_AGENT = "calendrier-sports/1.0 (usage personnel)"

DUREES = {  # durée approximative en minutes
    "hockey": 165,
    "football": 195,
    "basketball": 150,
    "baseball": 180,
    "soccer": 120,
}
EMOJIS = {"hockey": "🏒", "football": "🏈", "basketball": "🏀",
          "baseball": "⚾", "soccer": "⚽"}


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_utc(s: str) -> dt.datetime:
    """Accepte '2026-10-08T23:00:00Z' ou '2026-10-08T23:00Z'."""
    s = s.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s).astimezone(UTC)


def nhl_season(today: dt.date) -> str:
    y = today.year if today.month >= 7 else today.year - 1
    return f"{y}{y + 1}"


class Event:
    def __init__(self, uid, titre, debut=None, duree_min=None, date=None,
                 date_fin=None, lieu="", description="", source="manuel"):
        self.uid = uid
        self.titre = titre
        self.debut = debut          # datetime UTC (événement horodaté)
        self.duree_min = duree_min
        self.date = date            # date (journée entière)
        self.date_fin = date_fin    # date incluse
        self.lieu = lieu
        self.description = description
        self.source = source


# --------------------------------------------------------------------------
# LNH
# --------------------------------------------------------------------------
def nom_equipe_lnh(team: dict) -> str:
    cn = team.get("commonName") or {}
    return cn.get("fr") or cn.get("default") or team.get("abbrev", "?")


def evenement_lnh(g: dict, source: str, prefixe_titre: str = "") -> Event:
    away, home = g["awayTeam"], g["homeTeam"]
    a, h = nom_equipe_lnh(away), nom_equipe_lnh(home)
    titre = f"🏒 {prefixe_titre}{a} @ {h}"
    desc = []
    etat = g.get("gameState", "")
    if etat in ("OFF", "FINAL") and "score" in away and "score" in home:
        titre = f"🏒 {prefixe_titre}{a} {away['score']} @ {h} {home['score']} (final)"
    if g.get("gameType") == 3:
        desc.append("Séries éliminatoires")
    tele = [b.get("network") for b in g.get("tvBroadcasts", [])
            if b.get("countryCode") in ("CA", None) and b.get("network")]
    if tele:
        desc.append("Télé : " + ", ".join(dict.fromkeys(tele)))
    if g.get("gameScheduleState") not in (None, "OK"):
        desc.append(f"Statut : {g['gameScheduleState']}")
    lieu = (g.get("venue") or {}).get("default", "")
    return Event(uid=f"nhl-{g['id']}", titre=titre, debut=parse_utc(g["startTimeUTC"]),
                 duree_min=DUREES["hockey"], lieu=lieu,
                 description="\n".join(desc), source=source)


def source_canadiens(today: dt.date) -> list[Event]:
    url = f"https://api-web.nhle.com/v1/club-schedule-season/MTL/{nhl_season(today)}"
    data = fetch_json(url)
    return [evenement_lnh(g, "canadiens") for g in data.get("games", [])
            if g.get("gameType") in (2, 3)]


def source_finale_coupe_stanley(today: dt.date) -> list[Event]:
    url = f"https://api-web.nhle.com/v1/schedule/playoff-series/{nhl_season(today)}/o"
    try:
        data = fetch_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:   # finale pas encore programmée : normal
            return []
        raise
    return [evenement_lnh(g, "finale_coupe_stanley", "Finale Coupe Stanley – ")
            for g in data.get("games", [])]


# --------------------------------------------------------------------------
# ESPN
# --------------------------------------------------------------------------
def espn_events(ligue: str, today: dt.date, mois: int = 13) -> list[dict]:
    """Tous les événements ESPN d'une ligue, de 14 jours avant à ~13 mois après."""
    out, vus = [], set()
    debut = today - dt.timedelta(days=14)
    for i in range(mois):
        d1 = debut + dt.timedelta(days=31 * i)
        d2 = d1 + dt.timedelta(days=30)
        url = (f"https://site.api.espn.com/apis/site/v2/sports/{ligue}/scoreboard"
               f"?dates={d1:%Y%m%d}-{d2:%Y%m%d}&limit=1000")
        for ev in fetch_json(url).get("events", []):
            if ev["id"] not in vus:
                vus.add(ev["id"])
                out.append(ev)
    return out


def note_espn(ev: dict) -> str:
    comp = (ev.get("competitions") or [{}])[0]
    return " ".join(n.get("headline", "") for n in comp.get("notes", []))


def evenement_espn(ev: dict, ligue: str, source: str, prefixe: str = "",
                   emoji: str | None = None) -> Event:
    sport = ligue.split("/")[0]
    comp = (ev.get("competitions") or [{}])[0]
    equipes = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    away = equipes.get("away", {}).get("team", {}).get("displayName", "À déterminer")
    home = equipes.get("home", {}).get("team", {}).get("displayName", "À déterminer")
    e = emoji or EMOJIS.get(sport, "🏟️")
    titre = f"{e} {prefixe}{away} @ {home}"
    etat = comp.get("status", ev.get("status", {})).get("type", {})
    if etat.get("completed"):
        sa = equipes.get("away", {}).get("score", "")
        sh = equipes.get("home", {}).get("score", "")
        titre = f"{e} {prefixe}{away} {sa} @ {home} {sh} (final)"
    desc = []
    note = note_espn(ev)
    if note:
        desc.append(note)
    reseaux = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]
    if reseaux:
        desc.append("Diffusion (É.-U.) : " + ", ".join(dict.fromkeys(reseaux)))
    if etat.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"):
        desc.append("Statut : " + etat.get("description", etat["name"]))
    lieu = (comp.get("venue") or {}).get("fullName", "")
    return Event(uid=f"espn-{ligue.replace('/', '-')}-{ev['id']}", titre=titre,
                 debut=parse_utc(ev["date"]), duree_min=DUREES.get(sport, 150),
                 lieu=lieu, description="\n".join(desc), source=source)


def source_nfl(today, tz, sunday_night: bool, series: bool) -> dict[str, list[Event]]:
    res = {"nfl_sunday_night": [], "nfl_series": []}
    for ev in espn_events("football/nfl", today):
        stype = (ev.get("season") or {}).get("type")
        nom = ev.get("name", "") + " " + note_espn(ev)
        if series and stype == 3 and "Pro Bowl" not in nom:
            prefixe = "Super Bowl – " if "Super Bowl" in nom else "Séries NFL – "
            res["nfl_series"].append(evenement_espn(ev, "football/nfl", "nfl_series", prefixe))
        elif sunday_night and stype == 2:
            local = parse_utc(ev["date"]).astimezone(tz)
            if local.weekday() == 6 and local.hour >= 19:
                res["nfl_sunday_night"].append(
                    evenement_espn(ev, "football/nfl", "nfl_sunday_night", "SNF – "))
    return res


FINALES = {
    # source : (ligue ESPN, test sur la note de l'événement, préfixe du titre)
    "finale_nba": ("basketball/nba", lambda n: "NBA Finals" in n, "Finale NBA – "),
    "finale_wnba": ("basketball/wnba", lambda n: "WNBA Finals" in n, "Finale WNBA – "),
    "serie_mondiale_mlb": ("baseball/mlb", lambda n: "World Series" in n, "Série mondiale – "),
    "coupe_mls": ("soccer/usa.1",
                  lambda n: "MLS Cup" in n and re.search(r"\bFinal\b", n)
                  and "Conference" not in n and "Semi" not in n and "Quarter" not in n,
                  "Coupe MLS – "),
}


def source_finale(cle: str, today) -> list[Event]:
    ligue, test, prefixe = FINALES[cle]
    return [evenement_espn(ev, ligue, cle, prefixe)
            for ev in espn_events(ligue, today)
            if (ev.get("season") or {}).get("type") == 3 and test(note_espn(ev))]


def source_equipe_espn(spec: dict, today) -> list[Event]:
    ligue, abr = spec["ligue"], spec["equipe"].upper()
    out = []
    for ev in espn_events(ligue, today):
        comp = (ev.get("competitions") or [{}])[0]
        abrs = {c.get("team", {}).get("abbreviation", "").upper()
                for c in comp.get("competitors", [])}
        if abr in abrs:
            out.append(evenement_espn(ev, ligue, f"equipe:{ligue}:{abr}",
                                      emoji=spec.get("emoji")))
    return out


# --------------------------------------------------------------------------
# Manuel
# --------------------------------------------------------------------------
def source_manuel(items: list[dict], tz) -> list[Event]:
    out = []
    for it in items or []:
        cle = re.sub(r"[^a-z0-9]+", "-", it["titre"].lower()).strip("-")
        if "debut" in it:
            debut = dt.datetime.strptime(str(it["debut"]), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            out.append(Event(uid=f"manuel-{cle}-{debut:%Y%m%d}", titre=it["titre"],
                             debut=debut.astimezone(UTC),
                             duree_min=int(it.get("duree_min", 120)),
                             lieu=it.get("lieu", ""), description=it.get("description", "")))
        else:
            d = it["date"] if isinstance(it["date"], dt.date) else dt.date.fromisoformat(str(it["date"]))
            fin = it.get("date_fin", d)
            fin = fin if isinstance(fin, dt.date) else dt.date.fromisoformat(str(fin))
            out.append(Event(uid=f"manuel-{cle}-{d:%Y%m%d}", titre=it["titre"], date=d,
                             date_fin=fin, lieu=it.get("lieu", ""),
                             description=it.get("description", "")))
    return out


# --------------------------------------------------------------------------
# Écriture iCalendar (RFC 5545)
# --------------------------------------------------------------------------
def esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line: str) -> str:
    """Plie les lignes à 75 octets, sans couper un caractère UTF-8."""
    out, cur = [], ""
    for ch in line:
        limite = 75 if not out else 74
        if len((cur + ch).encode("utf-8")) > limite:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def vevent(e: Event, stamp: str) -> str:
    l = ["BEGIN:VEVENT", f"UID:{e.uid}@{UID_DOMAIN}", f"DTSTAMP:{stamp}",
         f"X-SOURCE-CALENDRIER:{e.source}"]
    if e.debut:
        fin = e.debut + dt.timedelta(minutes=e.duree_min or 120)
        l += [f"DTSTART:{e.debut:%Y%m%dT%H%M%SZ}", f"DTEND:{fin:%Y%m%dT%H%M%SZ}"]
    else:
        fin = (e.date_fin or e.date) + dt.timedelta(days=1)  # DTEND exclusif
        l += [f"DTSTART;VALUE=DATE:{e.date:%Y%m%d}", f"DTEND;VALUE=DATE:{fin:%Y%m%d}",
              "TRANSP:TRANSPARENT"]
    l.append(f"SUMMARY:{esc(e.titre)}")
    if e.lieu:
        l.append(f"LOCATION:{esc(e.lieu)}")
    if e.description:
        l.append(f"DESCRIPTION:{esc(e.description)}")
    l.append("END:VEVENT")
    return "\r\n".join(fold(x) for x in l)


def ecrire_ics(events: list[Event], nom: str, fuseau: str, reprises: list[str]) -> str:
    stamp = dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    tete = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//calendrier-sports//FR",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(nom)}",
            f"X-WR-TIMEZONE:{fuseau}", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
            "X-PUBLISHED-TTL:PT6H"]
    def tri(e):
        return e.debut or dt.datetime.combine(e.date, dt.time(), UTC)
    corps = [vevent(e, stamp) for e in sorted(events, key=tri)] + reprises
    return "\r\n".join([fold(x) for x in tete] + corps + ["END:VCALENDAR"]) + "\r\n"


def reprendre_anciens(url: str, sources_echouees: set[str]) -> list[str]:
    """Récupère, dans l'ancien .ics publié, les VEVENT des sources en échec."""
    if not url or not sources_echouees:
        return []
    try:
        ancien = fetch_text(url)
    except Exception as e:  # noqa: BLE001
        print(f"  ! impossible de lire l'ancien calendrier : {e}", file=sys.stderr)
        return []
    blocs = re.findall(r"BEGIN:VEVENT\r?\n.*?END:VEVENT", ancien, flags=re.S)
    garde = []
    for b in blocs:
        m = re.search(r"X-SOURCE-CALENDRIER:(.*)", b)
        if m and m.group(1).strip() in sources_echouees:
            garde.append(b.replace("\r\n", "\n").replace("\n", "\r\n"))
    return garde


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--out", default="public/sports.ics")
    args = p.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tz = ZoneInfo(cfg.get("fuseau", "America/Toronto"))
    today = dt.datetime.now(tz).date()
    actives = cfg.get("sources", {})

    taches = []  # (nom de source, fonction)
    if actives.get("canadiens"):
        taches.append((["canadiens"], lambda: {"canadiens": source_canadiens(today)}))
    if actives.get("finale_coupe_stanley"):
        taches.append((["finale_coupe_stanley"],
                       lambda: {"finale_coupe_stanley": source_finale_coupe_stanley(today)}))
    snf, srs = actives.get("nfl_sunday_night"), actives.get("nfl_series")
    if snf or srs:
        noms = [n for n, a in (("nfl_sunday_night", snf), ("nfl_series", srs)) if a]
        taches.append((noms, lambda: source_nfl(today, tz, bool(snf), bool(srs))))
    for cle in FINALES:
        if actives.get(cle):
            taches.append(([cle], lambda c=cle: {c: source_finale(c, today)}))
    for spec in cfg.get("equipes_espn") or []:
        nom = f"equipe:{spec['ligue']}:{spec['equipe'].upper()}"
        taches.append(([nom], lambda s=spec, n=nom: {n: source_equipe_espn(s, today)}))

    events, echecs = [], set()
    for noms, fn in taches:
        try:
            res = fn()
            for n in noms:
                lst = res.get(n, [])
                print(f"  ✓ {n} : {len(lst)} événement(s)")
                events += lst
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {', '.join(noms)} : {e}", file=sys.stderr)
            echecs.update(noms)

    manuels = source_manuel(cfg.get("manuel"), tz)
    print(f"  ✓ manuel : {len(manuels)} événement(s)")
    events += manuels

    # Dédoublonnage (ex. Canadiens en finale de la Coupe Stanley)
    uniques = {}
    for e in events:
        uniques.setdefault(e.uid, e)
    events = list(uniques.values())

    reprises = reprendre_anciens(os.environ.get("PREVIOUS_ICS_URL", ""), echecs)
    if reprises:
        print(f"  ↺ {len(reprises)} événement(s) repris de la version précédente")

    if taches and len(echecs) == len(sum((n for n, _ in taches), [])) and not reprises:
        print("Toutes les sources automatiques ont échoué : publication annulée.",
              file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(ecrire_ics(events, cfg.get("nom_calendrier", "Sports"),
                           cfg.get("fuseau", "America/Toronto"), reprises))
    print(f"→ {args.out} : {len(events) + len(reprises)} événements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
