"""Lecture de portefeuille : situations, décisions, initiatives, outcomes et learnings.

Le portefeuille n'est pas une projection de tout le graphe : il agrège des objets canoniques bornés au
tenant et, si demandé, à un domaine. Aucun chargement de tous les nœuds, aucune causalité inventée. Les
faits sont rendus comme propositions utilisables par AnswerComposer et les compteurs comme valeur métier.
"""
from __future__ import annotations

from collections.abc import Mapping

from meridian.domain import attention
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import valeur

__all__ = ["agreger"]

_MAX = 1000


def _texte(valeur, maximum=500) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _donnees(objet) -> Mapping:
    if isinstance(objet, Mapping) and isinstance(objet.get("donnees"), Mapping):
        return objet["donnees"]
    return {}


def _domaine(objet) -> str:
    donnees = _donnees(objet)
    return _texte(objet.get("domaine") if isinstance(objet, Mapping) else "", 120) or \
        _texte(donnees.get("domaine"), 120)


def _domaines_twins(conn, tenant):
    try:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            lignes = cur.execute(
                "SELECT id, domaine FROM jumeau WHERE tenant_id = %s", (tenant,)).fetchall()
        return {str(ligne["id"]): _texte(ligne.get("domaine"), 120) for ligne in lignes}
    except Exception:
        return {}


def _filtre_domaine(objets, domaine, domaines_twins=None):
    if not domaine:
        return list(objets or ())
    cible = _texte(domaine, 120).casefold()
    domaines_twins = domaines_twins or {}
    retenus = []
    for objet in objets or ():
        if _domaine(objet).casefold() == cible:
            retenus.append(objet)
            continue
        liens = _donnees(objet).get("twin_ids") or _donnees(objet).get("jumeaux") or ()
        if isinstance(liens, str):
            liens = [liens]
        if any(_texte(domaines_twins.get(_texte(twin)), 120).casefold() == cible for twin in liens):
            retenus.append(objet)
    return retenus


def _preuves(objet):
    donnees = _donnees(objet)
    valeurs = []
    for source in (objet.get("preuves") if isinstance(objet, Mapping) else None,
                   donnees.get("preuves"), donnees.get("preuve_ids")):
        if isinstance(source, Mapping):
            source = [source]
        if not isinstance(source, (list, tuple, set, frozenset)):
            continue
        for preuve in source:
            if isinstance(preuve, Mapping):
                preuve = preuve.get("id") or preuve.get("locator")
            texte = _texte(preuve, 300)
            if texte and texte not in valeurs:
                valeurs.append(texte)
    return tuple(valeurs)


def _proposition(objet, type_, titre, resume, confiance=0.6, actions=("ouvrir_objet",)):
    return {
        "specialiste": "portefeuille",
        "type": type_,
        "titre": _texte(titre, 240),
        "resume": _texte(resume, 2000),
        "preuves": list(_preuves(objet)),
        "confiance": max(0.0, min(1.0, float(confiance))),
        "actions": list(actions),
        "donnees": {
            "id": _texte(objet.get("id") if isinstance(objet, Mapping) else "", 160),
            "domaine": _domaine(objet) or None,
        },
    }


def agreger(conn, tenant_id, *, domaine=None, limite=50) -> dict:
    """Agrège un portefeuille borné et rend des propositions + compteurs de valeur."""
    tenant = _texte(tenant_id, 128)
    if not tenant:
        raise ValueError("tenant_id obligatoire")
    try:
        borne = max(1, min(int(limite), 500))
    except (TypeError, ValueError) as exc:
        raise ValueError("limite invalide") from exc

    def lire(type_):
        return entreprise_depot.lister_objets(conn, tenant, type_=type_, limite=_MAX)

    domaines_twins = _domaines_twins(conn, tenant) if domaine else {}
    situations = _filtre_domaine(lire("SITUATION"), domaine, domaines_twins)
    decisions = _filtre_domaine(lire("DECISION"), domaine, domaines_twins)
    initiatives = _filtre_domaine(lire("INITIATIVE"), domaine, domaines_twins)
    outcomes = _filtre_domaine(lire("OUTCOME"), domaine, domaines_twins)
    learnings = _filtre_domaine(lire("LEARNING"), domaine, domaines_twins)
    classes = attention.classer(situations, limite=borne)

    propositions = []
    for situation in classes:
        priorite = _texte(situation.get("priorite"), 20).upper()
        propositions.append(_proposition(
            situation, "RISQUE" if priorite == "HAUTE" else "CONSTAT",
            situation.get("titre") or "Situation",
            situation.get("resume") or "Situation du portefeuille",
            0.75 if priorite == "HAUTE" else 0.6,
            ("ouvrir_situation", "verifier_preuve") if priorite == "HAUTE" else ("ouvrir_situation",)))
    for initiative in initiatives:
        propositions.append(_proposition(
            initiative, "ACTION", initiative.get("titre") or "Initiative",
            _donnees(initiative).get("resume") or "Initiative du portefeuille",
            0.6, ("ouvrir_initiative", "mesurer_outcome")))
    for outcome in outcomes:
        propositions.append(_proposition(
            outcome, "OUTCOME", outcome.get("titre") or "Outcome",
            _donnees(outcome).get("resume") or "Outcome mesuré", 0.7, ("ouvrir_outcome",)))
    for learning in learnings:
        propositions.append(_proposition(
            learning, "LEARNING", learning.get("titre") or "Learning",
            _donnees(learning).get("resume") or _donnees(learning).get("enonce") or "Learning",
            0.65, ("reutiliser_learning",)))
    for decision in decisions:
        propositions.append(_proposition(
            decision, "CONSTAT", decision.get("titre") or "Décision",
            _donnees(decision).get("resume") or "Décision du portefeuille",
            0.65, ("ouvrir_decision",)))

    def _priorite(objet):
        valeur = objet.get("priorite") if isinstance(objet, Mapping) else None
        if valeur is None:
            valeur = _donnees(objet).get("priorite")
        return _texte(valeur, 20).upper()

    haute = sum(1 for situation in situations if _priorite(situation) == "HAUTE")
    try:
        valeur_ledger = valeur.resume(conn, tenant, domaine=domaine)
    except Exception:
        valeur_ledger = None
    return {
        "tenant": tenant,
        "scope": {"kind": "portfolio" if domaine else "enterprise", "domaine": domaine or None},
        "propositions": propositions,
        "attention": classes,
        "valeur_ledger": valeur_ledger,
        "valeur": {
            "situations": len(situations),
            "situations_haute": haute,
            "decisions": len(decisions),
            "initiatives": len(initiatives),
            "outcomes": len(outcomes),
            "learnings": len(learnings),
            "benefices_renseignes": sum(1 for outcome in outcomes
                                        if _donnees(outcome).get("valeur_observee") is not None),
        },
        "limites": [
            "agrégat borné au tenant et au domaine demandé",
            "aucune causalité déduite entre situation, décision et outcome",
            "un objet est rattaché par son domaine explicite ou celui de ses Twins liés",
        ],
    }
