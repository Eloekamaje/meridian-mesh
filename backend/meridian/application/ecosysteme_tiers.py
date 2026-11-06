"""Projection pure des responsabilités de l'écosystème tiers (ADR-0030).

Aucune base, aucun réseau, aucun modèle : la projection ne lit que les Twins fournis et leurs
Claims. Elle n'invente ni entité, ni responsabilité : un Twin absent des entrées reste absent
de la matrice et devient une inconnue explicite ; un Claim ``INCONNU`` ou ``CONTESTE`` est
conservé et exposé, jamais promu. Une vue transverse est une projection de plusieurs Twins,
jamais un Twin supplémentaire, et elle référence les Claims d'origine sans les copier.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from meridian.domain.ecosysteme_tiers import (
    STATUTS,
    TYPES_TIERS,
    ClaimTiers,
    ClaimTiersInvalide,
    est_application_candidate,
    est_application_non_resolue,
    etat_a_date,
    identifiant_canonique,
    normaliser_autorite,
    normaliser_predicat,
    normaliser_statut,
    normaliser_type_twin,
    preuve_de,
    valider_claim,
)

__all__ = ["EcosystemeTiersInvalide", "couverture", "responsabilites", "vue_transverse"]

ROLES = ("compte", "equipe", "fournisseur", "ressource", "application")

ROLE_PAR_TYPE = {
    "TEAM": "equipe",
    "SUPPLIER": "fournisseur",
    "RESOURCE": "ressource",
    "APPLICATION": "application",
}

PREDICATS_LIMITABLES = (
    "EQUIPE_EST_ACCOUNTABLE_DE",
    "EQUIPE_EST_RESPONSABLE_DE",
    "FOURNISSEUR_FOURNIT",
)


class EcosystemeTiersInvalide(ValueError):
    """La projection ne peut pas être construite à partir des entrées fournies."""


def _valeur(objet: Any, nom: str, defaut: Any = None) -> Any:
    if isinstance(objet, Mapping):
        return objet.get(nom, defaut)
    return getattr(objet, nom, defaut)


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bytes, bytearray, Mapping)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, bytes, bytearray, Mapping, ClaimTiers)):
        return [valeur]
    return list(valeur)


def _iter_twins(twins: Any) -> list[Any]:
    if twins is None:
        return []
    if isinstance(twins, (str, bytes, bytearray, Mapping)) or hasattr(twins, "twin_id"):
        return [twins]
    return list(twins)


def _type_twin(twin: Any) -> str:
    type_twin = normaliser_type_twin(_valeur(twin, "type", ""))
    if type_twin not in TYPES_TIERS:
        raise EcosystemeTiersInvalide(
            f"type de Twin inconnu : {_valeur(twin, 'type')!r} "
            f"(attendus : {', '.join(TYPES_TIERS)})"
        )
    return type_twin


def _identifiants(twin: Any) -> dict[str, str]:
    from meridian.domain.ecosysteme_tiers import IdentifiantsTiers

    return IdentifiantsTiers.depuis(_valeur(twin, "identifiants")).comme_dict()


def _candidat(twin: Any, type_twin: str) -> bool:
    return type_twin == "APPLICATION" and est_application_candidate(twin)


def _non_resolue(twin: Any, type_twin: str) -> bool:
    return type_twin == "APPLICATION" and est_application_non_resolue(twin)


def _sources_de(twin: Any) -> list[str]:
    return [texte for texte in (_texte(s) for s in _liste(_valeur(twin, "sources", ()))) if texte]


def _claims_de(twin: Any) -> list[Any]:
    valeur = _valeur(twin, "claims", ())
    if valeur is None:
        return []
    if isinstance(valeur, (str, bytes, bytearray)):
        return []
    if isinstance(valeur, (ClaimTiers, Mapping)):
        return [valeur]
    return list(valeur)


def _claim_depuis(brut: Any) -> ClaimTiers:
    if isinstance(brut, ClaimTiers):
        return brut
    if not isinstance(brut, Mapping):
        raise ClaimTiersInvalide("ClaimTiers ou mapping de Claim attendu")
    return ClaimTiers(
        sujet=brut.get("sujet", ""),
        predicat=brut.get("predicat", ""),
        objet=brut.get("objet", ""),
        statut=brut.get("statut", "SUPPOSE"),
        preuve=brut.get("preuve") or brut.get("preuve_localisee"),
        autorite=brut.get("autorite") or brut.get("autorite_source") or brut.get("source"),
        valid_from=brut.get("valid_from", brut.get("valide_depuis")),
        valid_to=brut.get("valid_to", brut.get("valide_jusqua")),
        confiance=brut.get("confiance"),
        texte=brut.get("texte", ""),
        id=brut.get("id"),
    )


def _cle_claim(claim: ClaimTiers) -> tuple[str, Any]:
    if claim.id:
        return ("id", claim.id)
    return ("objet", id(claim))


def _verifier_date(reference: Any) -> Any:
    if reference is None:
        return None
    if isinstance(reference, (date, datetime)):
        return reference
    if isinstance(reference, str) and reference.strip():
        try:
            datetime.fromisoformat(reference.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise EcosystemeTiersInvalide("date de référence invalide") from exc
        return reference
    raise EcosystemeTiersInvalide("date de référence invalide")


def _reference(claim: ClaimTiers, twin_id: str) -> bool:
    return _texte(claim.sujet) == twin_id or _texte(claim.objet) == twin_id


def _relation(
    sujet: str,
    predicat: str,
    objet: str,
    enregistrements: list[dict],
) -> dict:
    etats = [enregistrement["etat"] for enregistrement in enregistrements]
    if "CONTESTE" in etats:
        statut = "CONTESTE"
    elif "ETABLI" in etats:
        statut = "ETABLI"
    elif "SUPPOSE" in etats:
        statut = "SUPPOSE"
    elif "INCONNU" in etats:
        statut = "INCONNU"
    else:
        statut = "HISTORIQUE"

    preuves = []
    for enregistrement in enregistrements:
        preuve = enregistrement["preuve"]
        if preuve is not None and not any(preuve is p for p in preuves):
            preuves.append(preuve)
    autorites = []
    for enregistrement in enregistrements:
        autorite = enregistrement["autorite"]
        if autorite and autorite not in autorites:
            autorites.append(autorite)
    claims = []
    for enregistrement in enregistrements:
        claim = enregistrement["claim"]
        if not any(claim is c for c in claims):
            claims.append(claim)
    statuts_declares = []
    for enregistrement in enregistrements:
        statut_declare = enregistrement["statut_declare"]
        if statut_declare not in statuts_declares:
            statuts_declares.append(statut_declare)
    return {
        "sujet": sujet,
        "predicat": predicat,
        "objet": objet,
        "statut": statut,
        "statuts_declares": statuts_declares,
        "preuve": preuves[0] if preuves else None,
        "preuves": preuves,
        "autorite": autorites[0] if autorites else None,
        "autorites": autorites,
        "claim": claims[0],
        "claims": claims,
        "limite": False,
        "portee": None,
        "resolu": True,
        "contradiction": "CONTESTE" in etats,
    }


def _carte(
    twin: Any,
    twin_id: str,
    type_twin: str,
    claims: list[ClaimTiers],
    relations: list[dict],
) -> dict:
    impliquees = [claim for claim in claims if _reference(claim, twin_id)]
    etablies = [
        relation for relation in relations
        if relation["statut"] == "ETABLI"
        and relation.get("resolu", True)
        and (relation["sujet"] == twin_id or relation["objet"] == twin_id)
    ]
    return {
        "id": twin_id,
        "type": type_twin,
        "nom": _texte(_valeur(twin, "nom", "")),
        "twin": twin,
        "identifiants": _identifiants(twin),
        "sources": _sources_de(twin),
        "claims": impliquees,
        "relations_etablies": etablies,
        "sans_claim": not impliquees,
        "candidat": _candidat(twin, type_twin),
        "non_resolue": _non_resolue(twin, type_twin),
    }


def responsabilites(twins: Any, *, a_date: Any = None) -> dict:
    """Matrice compte/équipe/fournisseur/ressource/application, sans inventer.

    Les Cards de la matrice ne contiennent que des Twins réellement fournis. Les relations
    établies viennent uniquement de Claims validés. Les Claims ``INCONNU``, ``CONTESTE``,
    ``SUPPOSE`` et ``HISTORIQUE`` restent visibles dans les listes dédiées ; une référence à un
    Twin absent ne crée jamais ce Twin et devient une inconnue explicite.
    """
    reference = _verifier_date(a_date)
    twins_par_id: dict[str, Any] = {}
    ordre: list[str] = []
    for twin in _iter_twins(twins):
        twin_id = identifiant_canonique(twin)
        _type_twin(twin)
        if twin_id in twins_par_id and twins_par_id[twin_id] is not twin:
            raise EcosystemeTiersInvalide(f"twin_id dupliqué dans la projection : {twin_id}")
        if twin_id not in twins_par_id:
            twins_par_id[twin_id] = twin
            ordre.append(twin_id)

    claims: list[ClaimTiers] = []
    vus: set[tuple[str, Any]] = set()
    attachements: dict[str, list[ClaimTiers]] = {twin_id: [] for twin_id in ordre}
    for twin_id in ordre:
        twin = twins_par_id[twin_id]
        for brut in _claims_de(twin):
            claim = _claim_depuis(brut)
            valider_claim(claim)
            cle = _cle_claim(claim)
            if cle not in vus:
                vus.add(cle)
                claims.append(claim)
            else:
                claim = next(c for c in claims if _cle_claim(c) == cle)
            if not any(claim is c for c in attachements[twin_id]):
                attachements[twin_id].append(claim)

    groupes: dict[tuple[str, str, str], list[dict]] = {}
    for claim in claims:
        sujet = _texte(claim.sujet)
        predicat = normaliser_predicat(claim.predicat)
        objet = _texte(claim.objet)
        enregistrement = {
            "claim": claim,
            "etat": etat_a_date(claim, reference),
            "statut_declare": normaliser_statut(claim.statut),
            "preuve": preuve_de(claim),
            "autorite": normaliser_autorite(claim.autorite),
        }
        groupes.setdefault((sujet, predicat, objet), []).append(enregistrement)

    relations = [
        _relation(sujet, predicat, objet, enregistrements)
        for (sujet, predicat, objet), enregistrements in groupes.items()
    ]

    inconnues: list[dict] = []
    contradictions: list[dict] = []
    supposes: list[dict] = []
    historiques: list[dict] = []
    for (sujet, predicat, objet), enregistrements in groupes.items():
        contestes = [
            enregistrement["claim"] for enregistrement in enregistrements
            if enregistrement["etat"] == "CONTESTE"
        ]
        etablis = [
            enregistrement["claim"] for enregistrement in enregistrements
            if enregistrement["etat"] == "ETABLI"
        ]
        for enregistrement in enregistrements:
            claim = enregistrement["claim"]
            etat = enregistrement["etat"]
            entree = {
                "sujet": sujet,
                "predicat": predicat,
                "objet": objet,
                "claim": claim,
                "preuve": enregistrement["preuve"],
                "autorite": enregistrement["autorite"],
            }
            if etat == "INCONNU":
                inconnues.append({"type": "claim_inconnu", "motif": "statut INCONNU", **entree})
            elif etat == "SUPPOSE":
                supposes.append({"type": "claim_suppose", "motif": "supposition non établie", **entree})
            elif etat == "HISTORIQUE":
                historiques.append({"type": "claim_historique", "motif": "hors période de validité", **entree})
        for claim in contestes:
            contradictions.append({
                "type": "claim_conteste",
                "sujet": sujet,
                "predicat": predicat,
                "objet": objet,
                "claim": claim,
                "motif": "statut CONTESTE",
            })
        if contestes and etablis:
            contradictions.append({
                "type": "relation_contradictoire",
                "sujet": sujet,
                "predicat": predicat,
                "objet": objet,
                "contestes": contestes,
                "etablis": etablis,
                "motif": "des Claims établis et contestés portent sur la même relation",
            })

    limitations = [
        claim for claim in claims
        if normaliser_predicat(claim.predicat) == "RESPONSABILITE_LIMITEE_A"
        and etat_a_date(claim, reference) == "ETABLI"
    ]
    limites = [
        {
            "sujet": _texte(claim.sujet),
            "objet": _texte(claim.objet),
            "claim": claim,
            "preuve": preuve_de(claim),
            "autorite": normaliser_autorite(claim.autorite),
        }
        for claim in limitations
    ]
    for limitation in limites:
        exactes = [
            relation for relation in relations
            if relation["predicat"] in PREDICATS_LIMITABLES
            and relation["sujet"] == limitation["sujet"]
            and relation["objet"] == limitation["objet"]
        ]
        par_sujet = [
            relation for relation in relations
            if relation["predicat"] in PREDICATS_LIMITABLES
            and relation["sujet"] == limitation["sujet"]
        ]
        # Une limitation qui porte exactement sur le même couple (sujet, objet) borne cette
        # responsabilité. Sinon, un objet de limitation peut être un périmètre : il ne
        # s'applique que si le sujet n'a qu'une seule responsabilité, pour ne pas inventer.
        cibles = exactes or (par_sujet if len(par_sujet) == 1 else [])
        limitation["appliquee"] = bool(cibles)
        limitation["cibles"] = cibles
        if not cibles:
            inconnues.append({
                "type": "limitation_sans_responsabilite",
                "motif": (
                    "plusieurs responsabilités pour ce sujet : limitation non appliquée"
                    if len(par_sujet) > 1
                    else "aucune responsabilité correspondante pour cette limitation"
                ),
                "sujet": limitation["sujet"],
                "objet": limitation["objet"],
                "claim": limitation["claim"],
            })
            continue
        for relation in cibles:
            relation["limite"] = True
            relation["portee"] = "LIMITEE"
            relation["limite_a"] = limitation["objet"]

    non_resolues: set[tuple[str, str, str]] = set()
    for claim in claims:
        sujet = _texte(claim.sujet)
        predicat = normaliser_predicat(claim.predicat)
        objet = _texte(claim.objet)
        if sujet not in twins_par_id:
            non_resolues.add((sujet, predicat, objet))
            inconnues.append({
                "type": "reference_absente",
                "motif": "sujet absent de la projection",
                "champ": "sujet",
                "valeur": sujet,
                "claim": claim,
            })
        if predicat != "RESPONSABILITE_LIMITEE_A" and objet not in twins_par_id:
            non_resolues.add((sujet, predicat, objet))
            inconnues.append({
                "type": "reference_absente",
                "motif": "objet absent de la projection",
                "champ": "objet",
                "valeur": objet,
                "claim": claim,
            })
    for relation in relations:
        relation["resolu"] = (
            relation["sujet"], relation["predicat"], relation["objet"]
        ) not in non_resolues

    impliques: set[str] = set()
    for claim in claims:
        for valeur in (_texte(claim.sujet), _texte(claim.objet)):
            if valeur in twins_par_id:
                impliques.add(valeur)
    for twin_id in ordre:
        if twin_id not in impliques:
            inconnues.append({
                "type": "twin_sans_claim",
                "motif": "aucun Claim ne référence ce Twin",
                "twin_id": twin_id,
                "twin": twins_par_id[twin_id],
            })

    matrice = {
        "compte": [
            relation for relation in relations
            if relation["predicat"] == "EQUIPE_EST_ACCOUNTABLE_DE"
            and relation["statut"] == "ETABLI"
            and relation.get("resolu", True)
        ],
        "equipe": [],
        "fournisseur": [],
        "ressource": [],
        "application": [],
    }
    candidats = []
    perimetres = []
    for twin_id in ordre:
        twin = twins_par_id[twin_id]
        type_twin = _type_twin(twin)
        carte = _carte(twin, twin_id, type_twin, claims, relations)
        role = ROLE_PAR_TYPE.get(type_twin)
        if role:
            matrice[role].append(carte)
        if type_twin == "ECOSYSTEM":
            perimetres.append({
                "id": twin_id,
                "twin": twin,
                "perimetre": _texte(_valeur(twin, "perimetre", "")),
                "claims": carte["claims"],
            })
        if _candidat(twin, type_twin) or _non_resolue(twin, type_twin):
            candidats.append({
                "twin_id": twin_id,
                "twin": twin,
                "statut": "CANDIDAT" if _candidat(twin, type_twin) else "NON_RESOLU",
                "application_id": None,
            })

    return {
        "date": a_date.isoformat() if isinstance(a_date, (date, datetime)) else a_date,
        "twins": {twin_id: twins_par_id[twin_id] for twin_id in ordre},
        "claims": claims,
        "attachements": attachements,
        "relations": relations,
        "matrice": matrice,
        "limites": limites,
        "supposes": supposes,
        "historiques": historiques,
        "inconnues": inconnues,
        "contradictions": contradictions,
        "candidats": candidats,
        "perimetres": perimetres,
    }


def couverture(source: Any, *, a_date: Any = None) -> dict:
    """Couverture d'une projection : inconnues et contradictions restent explicites.

    ``source`` peut être le résultat de ``responsabilites`` ou directement des Twins. Le
    résultat ne remplace jamais une inconnue par une valeur par défaut et ne masque aucune
    contradiction.
    """
    if (isinstance(source, Mapping) and "matrice" in source and "relations" in source
            and "inconnues" in source and "contradictions" in source):
        resultat = source
    else:
        resultat = responsabilites(source, a_date=a_date)

    relations = list(resultat.get("relations") or ())
    inconnues = list(resultat.get("inconnues") or ())
    contradictions = list(resultat.get("contradictions") or ())
    supposes = list(resultat.get("supposes") or ())
    historiques = list(resultat.get("historiques") or ())
    candidats = list(resultat.get("candidats") or ())
    limites = list(resultat.get("limites") or ())
    par_statut = {statut: 0 for statut in STATUTS}
    for relation in relations:
        statut = relation.get("statut")
        if statut in par_statut:
            par_statut[statut] += 1
    par_type: dict[str, int] = {}
    for twin in (resultat.get("twins") or {}).values():
        type_twin = normaliser_type_twin(_valeur(twin, "type", "")) or "INCONNU"
        par_type[type_twin] = par_type.get(type_twin, 0) + 1
    motifs = sorted({
        entree.get("motif") for entree in inconnues + contradictions
        if isinstance(entree, Mapping) and entree.get("motif")
    })
    return {
        "date": resultat.get("date"),
        "twins": {
            "total": len(resultat.get("twins") or {}),
            "par_type": par_type,
            "sans_claim": sum(
                1 for entree in inconnues
                if isinstance(entree, Mapping) and entree.get("type") == "twin_sans_claim"
            ),
        },
        "claims": {"total": len(resultat.get("claims") or ())},
        "relations": {"total": len(relations), **par_statut},
        "etabli": sum(
            1 for relation in relations
            if relation.get("statut") == "ETABLI" and relation.get("resolu", True)
        ),
        "non_resolues_total": sum(
            1 for relation in relations if not relation.get("resolu", True)
        ),
        "partiel": bool(inconnues or contradictions),
        "inconnues_total": len(inconnues),
        "contradictions_total": len(contradictions),
        "supposes_total": len(supposes),
        "historiques_total": len(historiques),
        "limites_total": len(limites),
        "inconnues": inconnues,
        "contradictions": contradictions,
        "supposes": supposes,
        "historiques": historiques,
        "limites": limites,
        "candidats": candidats,
        "motifs": motifs,
    }


def vue_transverse(twins: Any, *, a_date: Any = None) -> dict:
    """Projection autorisée de plusieurs Twins : pas un Twin, pas une copie des Claims.

    Les listes ``claims``, les Cards de la matrice et les relations référencent les mêmes
    objets Claim que les entrées ; seuls les contenants de projection sont nouveaux.
    """
    resultat = responsabilites(twins, a_date=a_date)
    sources: list[str] = []
    for twin in resultat["twins"].values():
        for source in _sources_de(twin):
            if source not in sources:
                sources.append(source)
    return {
        "type": "VUE_TRANSVERSE",
        "est_twin": False,
        "twin_ids": list(resultat["twins"]),
        "twins": resultat["twins"],
        "claims": resultat["claims"],
        "attachements": resultat["attachements"],
        "relations": resultat["relations"],
        "matrice": resultat["matrice"],
        "limites": resultat["limites"],
        "supposes": resultat["supposes"],
        "historiques": resultat["historiques"],
        "inconnues": resultat["inconnues"],
        "contradictions": resultat["contradictions"],
        "perimetres": resultat["perimetres"],
        "sources": sources,
        "couverture": couverture(resultat),
    }
