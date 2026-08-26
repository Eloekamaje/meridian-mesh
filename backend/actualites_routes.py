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

SECTIONS_ORDRE = ["essentiel", "travaux", "decouvertes", "transformations", "surveillance", "espace", "global"]

TITRES_SECTION = {
    "essentiel": "L'essentiel",
    "travaux": "Vos travaux",
    "decouvertes": "Découvertes",
    "transformations": "Transformations",
    "surveillance": "À surveiller",
    "espace": "Dans votre espace",
    "global": "Mesh global",
}

SECTION_PAR_GENRE = {
    "relation": "decouvertes", "connaissance": "decouvertes", "contradiction": "surveillance",
    "changement": "transformations", "comportement": "transformations", "phenomene": "surveillance",
    "travail": "travaux", "decision": "travaux", "gouvernance": "espace",
}

# Le briefing varie selon le rôle : la priorité et la formulation changent, jamais la vérité.
PROFILS = {
    "architecte": {
        "label": "Lecture architecte",
        "phrase": "Dépendances, transformations et risques structurels d'abord.",
        "boost": {"relation": 18, "changement": 14, "connaissance": 8, "incident": 6, "travail": 4},
    },
    "exploitant": {
        "label": "Lecture exploitation",
        "phrase": "Comportements et dégradations transversales d'abord.",
        "boost": {"incident": 18, "comportement": 14, "contradiction": 8, "travail": 6},
    },
    "decideur": {
        "label": "Lecture décideur",
        "phrase": "Décisions attendues, risques et impacts d'abord.",
        "boost": {"decision": 18, "travail": 12, "contradiction": 8, "incident": 6},
    },
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


def profil_de(role: str):
    r = (role or "").lower()
    if "architect" in r or "urbanisation" in r:
        return PROFILS["architecte"]
    if "exploitation" in r or "support" in r or "production" in r or "équipe" in r:
        return PROFILS["exploitant"]
    if "direction" in r or "décision" in r or "manager" in r or "responsable" in r:
        return PROFILS["decideur"]
    return PROFILS["architecte"]


def confiance_label(score):
    return "élevée" if score >= 70 else "modérée" if score >= 40 else "faible"


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
        profil = profil_de(persona.get("role"))

        tous = await db.jumeaux.find({}, NO_ID).to_list(200)
        ids = [j["id"] for j in tous]
        aut = autorisations(espace, ids)
        id_vers_nom = {j["id"]: j["nom"] for j in tous}
        nom_vers_id = {j["nom"]: j["id"] for j in tous}
        id_vers_dom = {j["id"]: j.get("domaine") for j in tous}

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
            genre = GENRES_SITUATION.get(nature, "connaissance")
            prioritaire = s.get("priorite") in ("critique", "haute")
            section = "essentiel" if (nature == "incident" and prioritaire) else SECTION_PAR_GENRE.get(genre, "decouvertes")
            histoires.append({
                "id": f"sit-{s['id']}",
                "genre": genre,
                "section": section,
                "titre": s["titre"],
                "recit": s.get("resume") or s.get("decouverte_quoi") or "",
                "quand": ts.isoformat(),
                "jumeaux": f.get("jumeaux", []),
                "restreinte": f.get("restreinte", False),
                "confiance": confiance_label(s.get("score") or 50),
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
            incertain = r.get("etat") == "supposee"
            ts = parse_quand(r.get("decouverte_quand", ""), now)
            if dedans(ts):
                recit = (
                    f"Découverte via {r.get('source_decouverte', 'le Mesh')} — état « {etat} »"
                    + (f", confiance {r['confiance']} %" if r.get("confiance") else "") + "."
                )
                if incertain:
                    recit = ("Méridian observe des signaux concordants entre ces deux jumeaux, "
                             "mais ne dispose pas encore de preuves suffisantes pour conclure. " + recit)
                histoires.append({
                    "id": f"rel-{r['id']}",
                    "genre": "phenomene" if incertain else "relation",
                    "section": "surveillance" if incertain else "decouvertes",
                    "titre": f"Relation {'possible : ' if incertain else 'découverte : '}{ns} → {nc}",
                    "recit": recit,
                    "quand": ts.isoformat(),
                    "jumeaux": [r["source"], r["cible"]],
                    "incertain": incertain,
                    "confiance": confiance_label(r.get("confiance") or (35 if incertain else 75)),
                    "score": 68 if not incertain else 42,
                    "liens": {"atlas": f"/atlas?sel={r['source']}"},
                })
            for k, ev in enumerate((r.get("evolution") or [])[1:]):
                tev = parse_quand(ev.get("quand", ""), now)
                if dedans(tev):
                    histoires.append({
                        "id": f"rel-{r['id']}-ev-{k}",
                        "genre": "relation",
                        "section": "transformations",
                        "titre": f"Relation {ns} → {nc} : désormais {ev.get('etat', '')}",
                        "recit": f"L'état de la relation a évolué vers « {ev.get('etat', '')} ».",
                        "quand": tev.isoformat(),
                        "jumeaux": [r["source"], r["cible"]],
                        "confiance": confiance_label(r.get("confiance") or 70),
                        "score": 60,
                        "liens": {"atlas": f"/atlas?sel={r['source']}"},
                    })

        # --- Travaux : une histoire par travail et par période (événements regroupés) ---
        async for c in db.cases.find({}, NO_ID):
            if c.get("jumeaux") and not any(j in aut for j in c["jumeaux"]):
                continue
            personnel = x_persona in (c.get("participants") or []) or c.get("responsable") == x_persona
            boost = 30 if (portee == "personnel" and personnel) else 0
            lien = f"/travaux/{c['id']}"
            jumeaux_visibles = [j for j in c.get("jumeaux", []) if j in aut]
            entrees = []
            tc = parse_quand(c.get("cree_le", ""), now)
            if dedans(tc):
                entrees.append((tc, f"Travail conservé — {c.get('objectif') or 'mémoire ouverte'}"))
            for h in c.get("historique", []):
                ts = parse_quand(h.get("quand", ""), now)
                if dedans(ts) and not (tc and ts == tc):
                    entrees.append((ts, h.get("texte", "")))
            if not entrees:
                continue
            entrees.sort(key=lambda e: e[0])
            recit = entrees[0][1] if len(entrees) == 1 else f"{entrees[0][1]} — puis {entrees[-1][1].lower()}"
            a_decision = any("Décision" in t for _, t in entrees)
            histoires.append({
                "id": f"case-{c['id']}",
                "genre": "decision" if a_decision else "travail",
                "section": "travaux",
                "titre": c["titre"],
                "recit": recit,
                "quand": entrees[-1][0].isoformat(),
                "jumeaux": jumeaux_visibles,
                "confiance": confiance_label(70),
                "score": 52 + boost + (12 if a_decision else 0) + min(len(entrees), 3) * 3,
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
                "id": f"jrn-{idx_jrn}-{j.get('action', '')[:8]}",
                "genre": "gouvernance",
                "section": "global" if portee == "global" else "espace",
                "titre": f"{j.get('action', '')} — {j.get('cible', '')}",
                "recit": j.get("detail") or "",
                "quand": ts.isoformat(),
                "jumeaux": [],
                "confiance": confiance_label(80),
                "score": 30,
                "liens": {},
            })

        # Classement adapté au rôle : priorité et formulation, jamais la vérité
        for h in histoires:
            h["score"] += profil["boost"].get(h["genre"], 0)
            if portee == "espace" and h["section"] == "global":
                h["score"] -= 20
        histoires.sort(key=lambda h: (h["score"], h["quand"]), reverse=True)

        sections = [{"id": sid, "titre": TITRES_SECTION[sid], "histoires": [h for h in histoires if h["section"] == sid]}
                    for sid in SECTIONS_ORDRE]
        sections = [s for s in sections if s["histoires"]]

        # --- Briefing de Flore (rédaction déterministe, adaptée au rôle) ---
        prenom = persona.get("nom", "").split(" ")[-1] if persona.get("nom") else ""
        salutation = f"Bonjour {persona.get('nom', '')}".strip()
        top = histoires[:3]
        if histoires:
            top1 = histoires[0]
            accroche = (
                f"{len(histoires)} évolution{'s' if len(histoires) > 1 else ''} mérite{'nt' if len(histoires) > 1 else ''} votre attention. "
                f"La plus importante : {top1['titre']}"
                + (" — encore supposée, non confirmée." if top1.get("incertain") else ".")
            )
            texte = f"{accroche} {profil['phrase']}"
            points = [h["titre"] for h in top]
        else:
            accroche = "Rien d'important ne nécessite votre attention aujourd'hui."
            texte = f"{accroche} Le Mesh reste actif."
            points = []
        briefing = {
            "salutation": salutation,
            "titre": "L'essentiel aujourd'hui" if est_aujourdhui else "L'essentiel de la période",
            "accroche": accroche,
            "detail": profil["phrase"],
            "texte": texte,
            "points": points,
            "lecture": profil["label"],
        }

        # --- Synthèse de période (7/30 jours) : pas sept feeds collés ---
        synthese = None
        if jours > 1:
            compte = {"relations": 0, "transformations": 0, "decisions": 0, "surveillance": 0}
            couples = {}
            for h in histoires:
                if h["genre"] in ("relation", "phenomene"):
                    compte["relations"] += 1
                    if len(h.get("jumeaux", [])) == 2:
                        da, db_ = sorted([id_vers_dom.get(h["jumeaux"][0], "?"), id_vers_dom.get(h["jumeaux"][1], "?")])
                        couples[(da, db_)] = couples.get((da, db_), 0) + 1
                if h["section"] == "transformations":
                    compte["transformations"] += 1
                if h["genre"] == "decision":
                    compte["decisions"] += 1
                if h["section"] == "surveillance":
                    compte["surveillance"] += 1
            tendance = None
            if couples:
                (da, db_), _ = max(couples.items(), key=lambda x: x[1])
                tendance = f"Le domaine {da} se rapproche progressivement du domaine {db_}."
            synthese = {**compte, "tendance": tendance, "debut": (cible - timedelta(days=jours - 1)).isoformat(), "fin": cible.isoformat()}

        return {
            "date": cible.isoformat(),
            "jours": jours,
            "portee": portee,
            "est_aujourdhui": est_aujourdhui,
            "note_portee": note_portee,
            "espace_label": espace["label"],
            "briefing": briefing,
            "sections": sections,
            "histoires": histoires,
            "synthese": synthese,
            "mesh": {
                "jumeaux_actifs": sum(1 for j in tous if j.get("statut") == "actif" and j["id"] in aut),
                "relations_confirmees": 0,
            },
        }

    def persona_espaces(persona_id):
        from seed_data import PERSONAS
        p = next((x for x in PERSONAS if x["id"] == persona_id), PERSONAS[0])
        return p["espaces"]

    return router
