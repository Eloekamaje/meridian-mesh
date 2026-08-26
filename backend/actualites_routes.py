import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header

ETATS_REL = {
    "observee": "observée", "supposee": "supposée", "validation": "en validation A2A",
    "confirmee": "confirmée", "contestee": "contestée", "obsolete": "obsolète",
}

GENRES_SITUATION = {
    "relation": "relation", "contradiction": "contradiction", "connaissance": "connaissance",
    "changement": "changement", "incident": "incident", "comportement": "comportement",
}

TITRES_GENRE = {
    "relation": "Relation", "contradiction": "Contradiction", "connaissance": "Connaissance",
    "changement": "Changement", "incident": "Incident", "comportement": "Comportement",
    "travail": "Travail", "decision": "Décision", "gouvernance": "Gouvernance",
}

BOOST_PRIORITE = {"critique": 40, "haute": 20, "moyenne": 8, "basse": 0}


def parse_quand(s, now):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    hm = re.search(r"(\d{1,2})\s*h\s*(\d{2})", s)

    def avec_heure(jours):
        d = now - timedelta(days=jours)
        if hm:
            d = d.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
        return d

    if s.startswith("aujourd'hui"):
        return avec_heure(0)
    if s.startswith("hier"):
        return avec_heure(1)
    m = re.search(r"il y a (\d+)\s*(min|h|jours?|j|sem(?:aines?)?\.?|mois|ans?)", s)
    if not m:
        return None
    n = int(m.group(1))
    u = m.group(2)
    if u == "min":
        return now - timedelta(minutes=n)
    if u == "h":
        return now - timedelta(hours=n)
    if u.startswith("sem"):
        return now - timedelta(weeks=n)
    if u.startswith("mois"):
        return now - timedelta(days=n * 30)
    if u.startswith("an"):
        return now - timedelta(days=n * 365)
    return now - timedelta(days=n)


def build_actualites_router(deps):
    db = deps["db"]
    resoudre_perimetre = deps["resoudre_perimetre"]
    autorisations = deps["autorisations"]
    filtre_situation = deps["filtre_situation"]
    ESPACES = deps["ESPACES"]
    NO_ID = deps["NO_ID"]
    timezone = deps["timezone"]

    router = APIRouter()

    @router.get("/actualites")
    async def actualites(
        date: Optional[str] = None,
        jours: int = 1,
        portee: str = "personnel",
        x_persona: str = Header("architecte"),
        x_espace: Optional[str] = Header(None),
    ):
        now = datetime.now(timezone.utc)
        try:
            cible = datetime.fromisoformat(date).date() if date else now.date()
        except ValueError:
            cible = now.date()
        jours = min(max(int(jours), 1), 31)
        debut = datetime.combine(cible - timedelta(days=jours - 1), datetime.min.time(), tzinfo=timezone.utc)
        fin = datetime.combine(cible + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        est_aujourdhui = cible >= now.date() and jours == 1

        espace_id = x_espace
        note_portee = None
        if portee == "global":
            glob = next((e for e in ESPACES if e.get("global") and e["id"] in persona_espaces(x_persona)), None)
            if glob:
                espace_id = glob["id"]
            else:
                note_portee = "Mesh global non autorisé — vue limitée à votre espace"
        persona, espace = resoudre_perimetre(x_persona, espace_id)

        tous = await db.jumeaux.find({}, NO_ID).to_list(200)
        ids = [j["id"] for j in tous]
        aut = autorisations(espace, ids)
        id_vers_nom = {j["id"]: j["nom"] for j in tous}
        nom_vers_id = {j["nom"]: j["id"] for j in tous}

        histoires = []

        def dedans(ts):
            return ts is not None and debut <= ts < fin

        # --- Situations : découvertes, contradictions, incidents ---
        async for s in db.situations.find({}, NO_ID):
            f = filtre_situation(s, aut, nom_vers_id)
            if not f:
                continue
            ts = parse_quand(s.get("detectee", ""), now)
            if not dedans(ts):
                continue
            nature = s.get("nature", "connaissance")
            histoires.append({
                "id": f"sit-{s['id']}",
                "genre": GENRES_SITUATION.get(nature, "connaissance"),
                "titre": s["titre"],
                "recit": s.get("resume") or s.get("decouverte_quoi") or "",
                "quand": ts.isoformat(),
                "jumeaux": f.get("jumeaux", []),
                "restreinte": f.get("restreinte", False),
                "score": (s.get("score") or 50) + BOOST_PRIORITE.get(s.get("priorite"), 0),
                "verbe": s.get("verbe"),
                "liens": {"investigation": f"/investigations/{s['id']}", "atlas": f"/atlas?situation={s['id']}"},
            })

        # --- Relations : découvertes et changements d'état ---
        async for r in db.relations.find({}, NO_ID):
            if r["source"] not in aut or r["cible"] not in aut:
                continue
            ns = id_vers_nom.get(r["source"], r["source"])
            nc = id_vers_nom.get(r["cible"], r["cible"])
            etat = ETATS_REL.get(r.get("etat"), r.get("etat", ""))
            ts = parse_quand(r.get("decouverte_quand", ""), now)
            if dedans(ts):
                histoires.append({
                    "id": f"rel-{r['id']}",
                    "genre": "relation",
                    "titre": f"Relation découverte : {ns} → {nc}",
                    "recit": f"Découverte via {r.get('source_decouverte', 'le Mesh')} — état « {etat} »"
                             + (f", confiance {r['confiance']} %" if r.get("confiance") else "") + ".",
                    "quand": ts.isoformat(),
                    "jumeaux": [r["source"], r["cible"]],
                    "score": 68,
                    "liens": {"atlas": f"/atlas?sel={r['source']}"},
                })
            for k, ev in enumerate((r.get("evolution") or [])[1:]):
                tev = parse_quand(ev.get("quand", ""), now)
                if dedans(tev):
                    histoires.append({
                        "id": f"rel-{r['id']}-ev-{k}",
                        "genre": "relation",
                        "titre": f"Relation {ns} → {nc} : désormais {ev.get('etat', '')}",
                        "recit": f"L'état de la relation a évolué vers « {ev.get('etat', '')} ».",
                        "quand": tev.isoformat(),
                        "jumeaux": [r["source"], r["cible"]],
                        "score": 60,
                        "liens": {"atlas": f"/atlas?sel={r['source']}"},
                    })

        # --- Travaux (cases) : création et activité ---
        async for c in db.cases.find({}, NO_ID):
            if c.get("jumeaux") and not any(j in aut for j in c["jumeaux"]):
                continue
            personnel = x_persona in (c.get("participants") or []) or c.get("responsable") == x_persona
            boost = 30 if (portee == "personnel" and personnel) else 0
            lien = f"/travaux/{c['id']}"
            jumeaux_visibles = [j for j in c.get("jumeaux", []) if j in aut]
            tc = parse_quand(c.get("cree_le", ""), now)
            if dedans(tc):
                histoires.append({
                    "id": f"case-{c['id']}-creation",
                    "genre": "travail",
                    "titre": f"Nouveau travail : {c['titre']}",
                    "recit": c.get("objectif") or "Un travail a été conservé.",
                    "quand": tc.isoformat(),
                    "jumeaux": jumeaux_visibles,
                    "score": 66 + boost,
                    "liens": {"travail": lien},
                })
            for k, h in enumerate(c.get("historique", [])):
                ts = parse_quand(h.get("quand", ""), now)
                if not dedans(ts) or (tc and ts == tc):
                    continue
                histoires.append({
                    "id": f"case-{c['id']}-h-{k}",
                    "genre": "decision" if h.get("texte", "").startswith("Décision") else "travail",
                    "titre": c["titre"],
                    "recit": h.get("texte", ""),
                    "quand": ts.isoformat(),
                    "jumeaux": jumeaux_visibles,
                    "score": 52 + boost,
                    "liens": {"travail": lien},
                })

        # --- Journal de gouvernance (admissions, confirmations) ---
        idx_jrn = 0
        async for j in db.journal.find({}, NO_ID).sort("quand", -1).limit(80):
            ts = parse_quand(j.get("quand", ""), now)
            if not dedans(ts):
                continue
            idx_jrn += 1
            histoires.append({
                "id": f"jrn-{idx_jrn}-{j.get('action','')[:8]}",
                "genre": "gouvernance",
                "titre": f"{j.get('action', '')} — {j.get('cible', '')}",
                "recit": j.get("detail") or "",
                "quand": ts.isoformat(),
                "jumeaux": [],
                "score": 30,
                "liens": {},
            })

        histoires.sort(key=lambda h: (h["score"], h["quand"]), reverse=True)

        # Résumé de Flore (simulé, déterministe)
        par_genre = {}
        for h in histoires:
            par_genre[h["genre"]] = par_genre.get(h["genre"], 0) + 1
        if histoires:
            morceaux = [f"{n} {TITRES_GENRE.get(g, g).lower()}{'s' if n > 1 else ''}" for g, n in sorted(par_genre.items(), key=lambda x: -x[1])]
            texte = (
                f"Sur cette période, j'ai relevé {len(histoires)} événement{'s' if len(histoires) > 1 else ''} significatif{'s' if len(histoires) > 1 else ''} "
                f"dans votre périmètre : {', '.join(morceaux)}. "
                f"L'événement le plus important : « {histoires[0]['titre']} »."
            )
        else:
            texte = "Aucun événement significatif sur cette période dans votre périmètre — le Mesh est resté calme."

        return {
            "date": cible.isoformat(),
            "jours": jours,
            "portee": portee,
            "est_aujourdhui": est_aujourdhui,
            "note_portee": note_portee,
            "espace_label": espace["label"],
            "histoires": histoires,
            "resume_flore": {"texte": texte, "par_genre": par_genre},
        }

    def persona_espaces(persona_id):
        from seed_data import PERSONAS
        p = next((x for x in PERSONAS if x["id"] == persona_id), PERSONAS[0])
        return p["espaces"]

    return router
