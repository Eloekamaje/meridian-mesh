"""Veille AVANT la décision — une situation qui mûrit.

Quand on suit un phénomène possible (relation supposée, signal encore incertain), Méridian n'attend pas une décision : il
observe si les preuves s'accumulent ou s'effritent, et ne revient vers la personne que lorsque sa compréhension change.

    maturation = {
      "sujet": "Relation Fraude → Conformité",
      "confiance_depart": 64,            # % au moment où on décide de suivre
      "seuil": 75,                       # au-dessus : assez étayé pour être confirmé
      "plancher": 40,                    # en dessous : assez contredit pour être écarté
      "relation_id": "r12",              # (facultatif) la relation à confirmer
      "observations": [{"id", "quand", "jumeau", "source", "effet": +/- points de confiance, "texte"}],
    }

Niveaux de mouvement (même budget d'attention que la veille après décision) :
    1 — une décision devient possible : seuil de confirmation atteint, ou phénomène assez contredit pour être écarté ;
    3 — un indice de plus, dans un sens ou dans l'autre.

Le module est pur (aucun accès base) : il prend la maturation et l'instant, et rend des événements déterministes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

REPONSES_MATURATION = [
    {"action": "confirmer", "label": "Confirmer"},
    {"action": "continuer", "label": "Continuer d'observer"},
    {"action": "ecarter", "label": "Écarter"},
]
TYPES_QUESTION = ("seuil_atteint", "affaiblie")


def _instant(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def bornes(depart: float) -> tuple[float, float]:
    """Seuil de confirmation et seuil d'abandon par défaut, à partir de la confiance de départ."""
    seuil = 75.0 if depart < 70 else min(95.0, depart + 10.0)
    return seuil, max(15.0, depart - 25.0)


def confiance_depuis_libelle(libelle: str, defaut: float = 50.0) -> float:
    """« Élevée · 18 observations » → 75 ; « Modérée » → 55 ; « Faible » → 35."""
    t = (libelle or "").lower()
    return 75.0 if t.startswith("élev") else 55.0 if t.startswith("mod") else 35.0 if t.startswith("faib") else defaut


def nouvelle_veille(sujet: str, depart: float, relation_id: Optional[str] = None) -> dict:
    """La veille d'un travail qui suit un phénomène encore incertain."""
    seuil, plancher = bornes(depart)
    return {"mode": "maturation", "statut": "en_veille", "maturation": {"sujet": sujet, "confiance_depart": depart, "seuil": seuil, "plancher": plancher,
            "relation_id": relation_id, "observations": []}, "observations": [], "emis": []}


def _pct(v) -> str:
    return f"{round(v)} %"


def _borne(v: float) -> float:
    return max(0.0, min(100.0, v))


def confiance_a(mat: dict, maintenant: datetime) -> float:
    """Confiance courante : le départ, plus l'effet de chaque observation déjà due."""
    c = float(mat["confiance_depart"])
    for o in sorted(mat.get("observations", []), key=lambda o: o.get("quand", "")):
        t = _instant(o.get("quand"))
        if t is not None and t <= maintenant:
            c = _borne(c + float(o.get("effet", 0)))
    return c


def evaluer(mat: dict, maintenant: datetime) -> list[dict]:
    """Événements dus à ce jour, du plus ancien au plus récent. Chaque franchissement de seuil n'est signalé qu'une fois."""
    if not mat:
        return []
    seuil, plancher = float(mat.get("seuil", 75)), float(mat.get("plancher", 40))
    c = float(mat["confiance_depart"])
    evenements: list[dict] = []
    a_franchi_seuil = a_franchi_plancher = False
    for o in sorted(mat.get("observations", []), key=lambda o: o.get("quand", "")):
        t = _instant(o.get("quand"))
        if t is None or t > maintenant:
            continue
        avant = c
        c = _borne(c + float(o.get("effet", 0)))
        pour = float(o.get("effet", 0)) >= 0
        base = {"quand": o["quand"], "jumeau": o.get("jumeau"), "source": o.get("source"), "cible": None, "confiance": round(c),
                "indicateur": mat.get("sujet", ""), "attendu": None, "observe": f"{_pct(avant)} → {_pct(c)}"}
        evenements.append({
            **base, "id": f"mat-{o['id']}", "type": "preuve_pour" if pour else "preuve_contre", "niveau": 3,
            "titre": ("Un indice de plus — " if pour else "Un indice contraire — ") + mat.get("sujet", ""),
            "texte": f"{o.get('texte', '')} Ma confiance passe de {_pct(avant)} à {_pct(c)}.".strip(),
        })
        if not a_franchi_seuil and avant < seuil <= c:
            a_franchi_seuil = True
            evenements.append({
                **base, "id": f"seuil-{o['id']}", "type": "seuil_atteint", "niveau": 1, "jumeau": None, "source": None,
                "titre": f"Assez étayé pour être confirmé — {mat.get('sujet', '')}",
                "texte": f"La confiance atteint {_pct(c)}, au-dessus de mon seuil de confirmation ({_pct(seuil)}).",
            })
        if not a_franchi_plancher and avant > plancher >= c:
            a_franchi_plancher = True
            evenements.append({
                **base, "id": f"plancher-{o['id']}", "type": "affaiblie", "niveau": 1, "jumeau": None, "source": None,
                "titre": f"Assez contredit pour être écarté — {mat.get('sujet', '')}",
                "texte": f"La confiance tombe à {_pct(c)}, sous mon seuil d'abandon ({_pct(plancher)}).",
            })
    evenements.sort(key=lambda e: (e["quand"], e["id"]))
    return evenements


def message_flore_maturation(evenement: dict, mat: dict, faits: list[dict]) -> dict:
    """Le franchissement d'un seuil est une QUESTION de Flore, à la première personne, avec sa recommandation et les réponses possibles."""
    pour = [f for f in faits if f["type"] == "preuve_pour" and f["quand"] <= evenement["quand"]]
    contre = [f for f in faits if f["type"] == "preuve_contre" and f["quand"] <= evenement["quand"]]
    depart = _pct(mat["confiance_depart"])
    bilan = f"Depuis que je la suis : {len(pour)} indice{'s' if len(pour) > 1 else ''} en sa faveur, {len(contre)} contraire{'s' if len(contre) > 1 else ''} (confiance {depart} au départ, {_pct(evenement['confiance'])} maintenant)."
    if evenement["type"] == "seuil_atteint":
        texte = (f"Ce que je vérifiais s'étaye : {mat.get('sujet', '')}. {bilan}\n\n"
                 f"Je vous suggère de la confirmer : elle entrerait dans la mémoire du Mesh comme une vérité, non plus comme un phénomène possible.\n\nQue souhaitez-vous faire ?")
        comportement = "recommander"
    else:
        texte = (f"Ce que je vérifiais s'effrite : {mat.get('sujet', '')}. {bilan}\n\n"
                 f"Je vous suggère de l'écarter, en gardant la trace des indices contraires pour ne pas la reproposer sans élément nouveau.\n\nQue souhaitez-vous faire ?")
        comportement = "recommander"
    return {"role": "flore", "comportement": comportement, "id": evenement["id"], "type": evenement["type"], "niveau": 1, "quand": evenement["quand"],
            "titre": evenement["titre"], "texte": texte, "reponses": REPONSES_MATURATION}


def message_flore_suivi(sujet: str, depart: float, seuil: float, plancher: float, quand: str) -> dict:
    """Ce que Flore annonce quand on lui confie la vérification : ce qu'elle guette, et à quel moment elle reviendra."""
    return {"role": "flore", "comportement": "expliquer", "type": "suivi", "quand": quand,
            "texte": (f"Je vérifie : {sujet}.\n\nMa confiance est de {_pct(depart)}. J'observe si les preuves s'accumulent ou s'effritent avec les jumeaux concernés :\n"
                      f"— au-dessus de {_pct(seuil)}, je vous propose de la confirmer ;\n— sous {_pct(plancher)}, je vous propose de l'écarter.\n\n"
                      "Entre les deux, je ne vous dérange pas : les indices s'ajoutent au fil de ce travail.")}
