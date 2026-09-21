"""Veille après décision — comparer ce qui était attendu à ce qui est observé.

Quand une décision est prise, on en garde la NOTE DE PASSATION (Continuous Improvement & Learning Model, « Decision
Handoff ») : hypothèses, résultats attendus, risques à surveiller, inconnues à surveiller, date de revue. Les jumeaux
observent ensuite ; Méridian confronte chaque observation à cette note et n'écrit dans le fil du travail que ce qui change
la compréhension de la décision — jamais un simple dépassement de seuil isolé.

    passation = {
      "hypotheses": ["…"],
      "attendus":  [{"id", "indicateur", "sens": "baisse"|"hausse", "depart", "cible", "unite"}],
      "risques":   [{"id", "texte", "jumeau", "sens": "hausse"|"baisse", "seuil", "unite"}],
      "inconnues": [{"id", "texte"}],
      "revue_le":  "2026-09-19T00:00:00+00:00",
    }
    observation = {"id", "quand", "jumeau", "source", "cible": <id d'un attendu / risque / inconnue>, "valeur", "unite", "conclusion"}

Niveaux de mouvement (budget d'attention) :
    1 — la décision est remise en question : écart contre l'attendu, effet secondaire matérialisé, revue due ;
    2 — un fait nouveau significatif : objectif atteint, inconnue levée ;
    3 — information mineure : progression partielle, risque sous son seuil.

Le module est pur (aucun accès base) : il prend la veille et l'instant, et rend des événements déterministes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _instant(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _nombre(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).replace(".", ",")


def _avec_unite(v, unite: str) -> str:
    return f"{_nombre(v)} {unite}".strip()


def progression(attendu: dict, valeur: float) -> float:
    """Part du chemin parcouru entre le départ et la cible : 0 = au départ, 1 = cible atteinte, < 0 = à contresens."""
    depart, cible = float(attendu["depart"]), float(attendu["cible"])
    if cible == depart:
        return 1.0
    return (float(valeur) - depart) / (cible - depart)


def evaluer(veille: dict, maintenant: datetime) -> list[dict]:
    """Événements de veille dus à ce jour, du plus ancien au plus récent (les observations futures sont ignorées)."""
    if not veille or veille.get("statut") not in ("en_veille", None):
        return []
    passation = veille.get("passation") or {}
    attendus = {a["id"]: a for a in passation.get("attendus", [])}
    risques = {r["id"]: r for r in passation.get("risques", [])}
    inconnues = {i["id"]: i for i in passation.get("inconnues", [])}
    evenements: list[dict] = []
    bilan = {"conformes": 0, "ecarts": 0, "effets": 0, "leves": 0}

    for o in sorted(veille.get("observations", []), key=lambda o: o.get("quand", "")):
        t = _instant(o.get("quand"))
        if t is None or t > maintenant:
            continue
        cible = o.get("cible")
        base = {"id": f"obs-{o['id']}", "quand": o["quand"], "jumeau": o.get("jumeau"), "source": o.get("source"), "cible": cible}

        if cible in attendus:
            a = attendus[cible]
            p = progression(a, o["valeur"])
            unite = a.get("unite", "")
            obs, att = _avec_unite(o["valeur"], unite), _avec_unite(a["cible"], unite)
            if p >= 1:
                bilan["conformes"] += 1
                evenements.append({**base, "type": "conforme", "niveau": 2, "indicateur": a["indicateur"], "attendu": att, "observe": obs,
                                   "titre": f"Objectif atteint — {a['indicateur']}",
                                   "texte": f"{a['indicateur']} : {obs} observé, l'objectif de la décision ({att}) est atteint."})
            elif p < 0:
                bilan["ecarts"] += 1
                evenements.append({**base, "type": "ecart", "niveau": 1, "indicateur": a["indicateur"], "attendu": att, "observe": obs,
                                   "titre": f"Écart avec l'attendu — {a['indicateur']}",
                                   "texte": f"{a['indicateur']} : {obs} observé, alors que la décision attendait {att} (départ : {_avec_unite(a['depart'], unite)}). "
                                            "L'indicateur évolue à contresens de l'hypothèse."})
            else:
                evenements.append({**base, "type": "progression", "niveau": 3, "indicateur": a["indicateur"], "attendu": att, "observe": obs,
                                   "titre": f"Progression — {a['indicateur']}",
                                   "texte": f"{a['indicateur']} : {obs} observé, soit {round(p * 100)} % du chemin vers {att}."})
        elif cible in risques:
            r = risques[cible]
            unite = r.get("unite", "")
            franchi = float(o["valeur"]) > float(r["seuil"]) if r.get("sens", "hausse") == "hausse" else float(o["valeur"]) < float(r["seuil"])
            obs, seuil = _avec_unite(o["valeur"], unite), _avec_unite(r["seuil"], unite)
            if franchi:
                bilan["effets"] += 1
                evenements.append({**base, "type": "effet_secondaire", "niveau": 1, "indicateur": r["texte"], "attendu": f"sous {seuil}" if r.get("sens", "hausse") == "hausse" else f"au-dessus de {seuil}", "observe": obs,
                                   "titre": f"Risque surveillé matérialisé — {r['texte']}",
                                   "texte": f"Risque surveillé : {r['texte']}. Valeur observée {obs}, au-delà du seuil retenu ({seuil})."})
            else:
                evenements.append({**base, "type": "risque_maitrise", "niveau": 3, "indicateur": r["texte"], "attendu": seuil, "observe": obs,
                                   "titre": f"Risque maîtrisé — {r['texte']}",
                                   "texte": f"Risque surveillé : {r['texte']}. Valeur observée {obs}, sous le seuil retenu ({seuil})."})
        elif cible in inconnues:
            i = inconnues[cible]
            bilan["leves"] += 1
            evenements.append({**base, "type": "inconnue_levee", "niveau": 2, "indicateur": i["texte"], "attendu": None, "observe": o.get("conclusion", ""),
                               "titre": f"Inconnue levée — {i['texte']}",
                               "texte": f"Inconnue levée : {i['texte']} {o.get('conclusion', '')}".strip()})

    revue = _instant(passation.get("revue_le"))
    if revue and revue <= maintenant and not veille.get("revue_faite_le"):
        r = bilan
        evenements.append({
            "id": f"revue-{passation['revue_le'][:10]}", "type": "revue_due", "niveau": 1, "quand": passation["revue_le"], "jumeau": None, "source": None,
            "cible": None, "indicateur": "Revue de la décision", "attendu": None, "observe": None,
            "titre": "Date de revue atteinte",
            "texte": f"La date de revue est atteinte : {r['conformes']} objectif(s) atteint(s), {r['ecarts']} écart(s), "
                     f"{r['effets']} effet(s) secondaire(s), {r['leves']} inconnue(s) levée(s).",
        })
    evenements.sort(key=lambda e: e["quand"])
    return evenements


def mouvement(evenements: list[dict], depuis: Optional[str]) -> Optional[dict]:
    """Synthèse du mouvement non lu : niveau le plus fort, nombre, dernier fait. `depuis` = dernière visite de la personne."""
    nouveaux = [e for e in evenements if not depuis or e.get("quand", "") > depuis]
    if not nouveaux:
        return None
    return {"niveau": min(e["niveau"] for e in nouveaux), "nb": len(nouveaux), "texte": nouveaux[-1].get("titre") or nouveaux[-1].get("texte", "")}


REPONSES_REVUE = [
    {"action": "rouvrir", "label": "Rouvrir la décision"},
    {"action": "maintenir", "label": "Maintenir la décision"},
    {"action": "clore", "label": "Clore la veille"},
]


def est_veille(m: dict) -> bool:
    """Un message du fil issu de la veille : un fait observé, ou la revue posée par Flore."""
    return m.get("role") == "evenement" or m.get("type") == "revue_due"


def _pluriel(n: int, un: str, plusieurs: str) -> str:
    return f"{n} {un if n == 1 else plusieurs}"


def message_flore_revue(evenement: dict, faits: list[dict]) -> dict:
    """La revue est une QUESTION posée à l'humain : elle vient de Flore, à la première personne, avec une recommandation et
    les réponses possibles — pas d'une carte ni d'un bandeau."""
    n = lambda t: sum(1 for f in faits if f["type"] == t)
    morceaux = [m for m in (
        _pluriel(n("conforme"), "objectif atteint", "objectifs atteints") if n("conforme") else "",
        _pluriel(n("ecart"), "écart avec l'attendu", "écarts avec l'attendu") if n("ecart") else "",
        _pluriel(n("effet_secondaire"), "risque surveillé matérialisé", "risques surveillés matérialisés") if n("effet_secondaire") else "",
        _pluriel(n("inconnue_levee"), "inconnue levée", "inconnues levées") if n("inconnue_levee") else "",
    ) if m]
    bilan = "Depuis la décision : " + ", ".join(morceaux) + "." if morceaux else "Depuis la décision, rien de notable n'a été observé."
    graves = [f for f in faits if f["niveau"] == 1 and f["type"] != "revue_due"]
    if graves:
        details = " ; ".join(f["indicateur"] for f in graves)
        reco = f"Je vous suggère de rouvrir la décision, à cause de : {details}."
    else:
        reco = "Aucun écart majeur : je vous suggère de la maintenir."
    return {
        "role": "flore", "comportement": "recommander", "id": evenement["id"], "type": "revue_due", "niveau": 1, "quand": evenement["quand"], "titre": evenement["titre"],
        "texte": f"La date de revue de cette décision est atteinte. {bilan}\n\n{reco}\n\nQue souhaitez-vous faire ?",
        "reponses": REPONSES_REVUE,
    }


def _jour(iso: str) -> str:
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    d = _instant(iso)
    return f"{d.day} {mois[d.month - 1]}" if d else ""


def message_flore_decision(texte: str, passation: dict, quand: str) -> dict:
    """La décision entre dans la CONVERSATION : Flore l'enregistre, dit ce qu'elle va surveiller et quand elle reviendra."""
    lignes = [f"J'ai enregistré votre décision : « {texte} »."]
    if passation.get("hypotheses"):
        lignes.append("Elle repose sur : " + " ; ".join(h.rstrip(".") for h in passation["hypotheses"]) + ".")
    veille = []
    for a in passation.get("attendus", []):
        veille.append(f"— {a['indicateur']} : de {_nombre(a['depart'])} à {_nombre(a['cible'])} {a.get('unite', '')}".rstrip())
    for r in passation.get("risques", []):
        veille.append(f"— risque : {r['texte']} (seuil {_nombre(r['seuil'])} {r.get('unite', '')})".rstrip())
    for i in passation.get("inconnues", []):
        veille.append(f"— à lever : {i['texte']}")
    if veille:
        lignes.append("Je la mets en veille. Voici ce que j'observerai :\n" + "\n".join(veille))
    if passation.get("revue_le"):
        lignes.append(f"Je reviendrai vers vous à la revue, le {_jour(passation['revue_le'])}, ou avant si un risque surveillé se matérialise.")
    return {"role": "flore", "comportement": "recommander", "type": "decision", "quand": quand, "texte": "\n\n".join(lignes)}
