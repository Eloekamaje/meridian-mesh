"""Capitalisation d'un Outcome mesuré en Learning réutilisable, sans invention.

Ce module ferme la boucle P1 : une Initiative déjà persistée produit un Outcome mesuré, puis un Learning
explicitement énoncé par un acteur. La mesure ne fabrique jamais d'enseignement : sans texte de leçon, aucune
écriture n'est effectuée. Les liens de source (situation, Twin, décision, investigation) sont conservés dans
``donnees`` pour que la réutilisation reste traçable et tenant-scopée.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from jumeau import boucle, calibration, entreprise_depot, tenant as tenant_module

__all__ = [
    "EnseignementRequis",
    "LearningIntrouvable",
    "NonSupporte",
    "ReutilisationRefusee",
    "mesurer_et_capitaliser",
    "learnings_pour",
    "marquer_reutilise",
]

_CHAMPS_TABLE = frozenset({
    "id", "tenant_id", "famille", "type", "mode", "titre", "donnees", "version",
    "observe_le", "valide_depuis", "valide_jusqua", "cree_le", "maj_le",
})
_MAX_LECTURE = 1000


class NonSupporte(RuntimeError):
    """Le dépôt canonique ne permet pas l'audit demandé sans altérer le sens de l'objet."""


class EnseignementRequis(boucle.BoucleInvalide):
    """Aucun enseignement n'a été fourni : le Learning ne peut pas être fabriqué à partir de la mesure."""


class LearningIntrouvable(boucle.BoucleInvalide):
    """Le Learning demandé n'existe pas dans le tenant."""


class ReutilisationRefusee(boucle.BoucleInvalide):
    """La réutilisation ne peut pas être tracée sur l'objet demandé."""


def _tenant(tenant_id: Any) -> str:
    return tenant_module.exiger_tenant(tenant_id).id


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _texte_obligatoire(valeur: Any, champ: str) -> str:
    texte = _texte(valeur)
    if not texte:
        raise boucle.BoucleInvalide(f"{champ} obligatoire")
    return texte


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, Mapping)) or not isinstance(valeur, Iterable):
        return [valeur]
    return list(valeur)


def _liste_ids(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = element.get("id")
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _liste_textes(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _donnees(ligne: Any) -> Mapping[str, Any]:
    if not isinstance(ligne, Mapping):
        return {}
    donnees = ligne.get("donnees")
    return donnees if isinstance(donnees, Mapping) else {}


def _valeur_lien(ligne: Any, *noms: str) -> Any:
    if not isinstance(ligne, Mapping):
        return None
    donnees = _donnees(ligne)
    for nom in noms:
        for conteneur in (donnees, ligne):
            valeur = conteneur.get(nom)
            if valeur not in (None, "", [], ()):
                return valeur
    return None


def _ids_lies(ligne: Any, *noms: str) -> list[str]:
    resultat: list[str] = []
    for nom in noms:
        for conteneur in (_donnees(ligne), ligne):
            if isinstance(conteneur, Mapping) and nom in conteneur:
                for identifiant in _liste_ids(conteneur[nom]):
                    if identifiant not in resultat:
                        resultat.append(identifiant)
    return resultat


def _recence(ligne: Any) -> tuple[float, float, float, float]:
    valeurs: list[float] = []
    for champ in ("cree_le", "observe_le", "maj_le", "valide_depuis"):
        instant = 0.0
        for conteneur in (ligne, _donnees(ligne)):
            if not isinstance(conteneur, Mapping):
                continue
            valeur = conteneur.get(champ)
            if not valeur:
                continue
            try:
                instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00")).timestamp()
            except ValueError:
                instant = 0.0
            break
        valeurs.append(instant)
    return tuple(valeurs)


def _limite(limite: Any) -> int:
    if isinstance(limite, bool):
        raise boucle.BoucleInvalide("limite doit être un entier positif")
    try:
        borne = int(limite)
    except (TypeError, ValueError) as exc:
        raise boucle.BoucleInvalide("limite doit être un entier positif") from exc
    if borne < 1:
        raise boucle.BoucleInvalide("limite doit être un entier positif")
    return min(borne, _MAX_LECTURE)


def _lire_attendu(conn: Any, tenant: str, objet_id: Any, type_attendu: str, role: str) -> dict:
    identifiant = _texte_obligatoire(objet_id, f"{role}_id")
    ligne = boucle.lire_par_id(conn, tenant, identifiant)
    if ligne is None:
        raise boucle.BoucleInvalide(f"{role} introuvable dans le tenant {tenant!r} : {identifiant}")
    type_lu = _texte(ligne.get("type")).upper()
    if type_lu != type_attendu:
        raise boucle.BoucleInvalide(
            f"{role} {identifiant} n'est pas un {type_attendu} (reçu {type_lu or 'inconnu'})"
        )
    return ligne


def _payload_learning(learning: boucle.Learning, extra: Mapping[str, Any]) -> dict:
    payload = learning.to_dict()
    donnees = {
        cle: valeur for cle, valeur in payload.items()
        if cle not in _CHAMPS_TABLE and cle != "donnees"
    }
    donnees.update(extra)
    payload["donnees"] = donnees
    return payload


def mesurer_et_capitaliser(
    conn: Any, tenant_id: Any, initiative_id: Any, mesure: Any, *,
    cible: Any = None, periode: Any = None, preuve_ids: Any = (),
    decision_id: Any = None, prediction_id: Any = None,
    situation_ids: Any = (), twin_ids: Any = (),
    enseignement: Any = None, conditions_reutilisation: Any = (),
    acteur: Any = "système",
) -> dict:
    """Mesure une Initiative et capitalise un Learning explicitement énoncé.

    L'Initiative doit exister dans le tenant. Aucun Outcome n'est écrit sans ``enseignement`` : la mesure seule
    ne suffit pas à produire une leçon. Le Learning est relié à l'Outcome, à l'Investigation et aux situations,
    Twins et preuves fournis ; ``conditions_reutilisation`` est conservé à la fois comme conditions
    d'applicabilité canoniques et comme métadonnée de réutilisation. ``prediction_id``, s'il est fourni, doit
    exister dans le tenant et porter la même décision : il est alors relié au Learning avec la mesure. Rend
    ``{"outcome": ligne, "learning": ligne}``.
    """
    tenant = _tenant(tenant_id)
    initiative = _lire_attendu(conn, tenant, initiative_id, "INITIATIVE", "initiative")
    if not _texte(enseignement):
        raise EnseignementRequis(
            "enseignement obligatoire : aucune leçon ne peut être déduite de la seule mesure"
        )

    acteur_final = _texte(acteur) or "système"
    situations = _liste_ids(situation_ids)
    twins = _liste_ids(twin_ids)
    conditions = _liste_textes(conditions_reutilisation)
    preuves = _liste_textes(preuve_ids)

    initiative_decision_id = _texte(_valeur_lien(initiative, "decision_id"))
    if decision_id is not None:
        decision_id = _texte(decision_id)
        if initiative_decision_id and decision_id != initiative_decision_id:
            raise boucle.BoucleInvalide(
                f"decision_id {decision_id!r} incompatible avec l'initiative {initiative_id!r}"
            )
    else:
        decision_id = initiative_decision_id or None

    decision = None
    if decision_id:
        decision = _lire_attendu(conn, tenant, decision_id, "DECISION", "décision")

    if prediction_id is not None:
        prediction_id = _texte_obligatoire(prediction_id, "prediction_id")
        prediction = calibration.lire(conn, tenant, prediction_id)
        if prediction is None:
            raise boucle.BoucleInvalide(
                f"prédiction introuvable dans le tenant {tenant!r} : {prediction_id}"
            )
        if decision_id is None:
            decision_id = prediction.decision_id
            decision = _lire_attendu(conn, tenant, decision_id, "DECISION", "décision")
        elif prediction.decision_id != decision_id:
            raise boucle.BoucleInvalide(
                f"prediction_id {prediction_id!r} liée à la décision "
                f"{prediction.decision_id!r}, attendu {decision_id!r}"
            )
    else:
        prediction_id = None

    if not situations:
        situation_derivee = _texte(_valeur_lien(decision, "situation_id")) if decision else ""
        if not situation_derivee:
            situation_derivee = _texte(_valeur_lien(initiative, "situation_id"))
        if situation_derivee:
            situations = [situation_derivee]

    investigation_id = _texte(_valeur_lien(decision, "investigation_id")) if decision else ""
    if investigation_id:
        _lire_attendu(conn, tenant, investigation_id, "INVESTIGATION", "investigation")

    outcome = boucle.mesurer_outcome(
        initiative, mesure, valeur_attendue=cible, periode=periode or "",
        preuves=preuves or None,
    )
    champs: dict[str, Any] = {}
    if investigation_id:
        champs["investigation_ids"] = [investigation_id]
    if situations:
        champs["situation_id"] = situations[0]
    learning = boucle.capitaliser_learning(
        outcome, enonce=enseignement, conditions_applicabilite=conditions, **champs,
    )

    extra = {
        "initiative_id": _texte(initiative.get("id")),
        "decision_id": decision_id,
        "prediction_id": prediction_id,
        "situation_ids": situations,
        "twin_ids": twins,
        "conditions_reutilisation": conditions,
        "preuve_ids": preuves,
        "acteur": acteur_final,
    }
    payload = _payload_learning(learning, extra)
    stockes = boucle.enregistrer_boucle(conn, tenant, [outcome, payload])
    par_type = {ligne["type"]: ligne for ligne in stockes}
    return {"outcome": par_type["OUTCOME"], "learning": par_type["LEARNING"]}


def learnings_pour(
    conn: Any, tenant_id: Any, *, situation_id: Any = None, twin_ids: Any = (),
    limite: Any = 20,
) -> list[dict]:
    """Rend les Learnings du tenant liés à une situation exacte ou à des Twins communs.

    Les liens sont lus dans ``donnees`` (``situation_id``, ``situation_ids``, ``twin_ids`` et alias de source).
    Le classement est déterministe : situation exacte d'abord, puis nombre de Twins partagés, puis récence de
    création, puis identifiant. Aucun Learning d'un autre tenant n'est retourné.
    """
    tenant = _tenant(tenant_id)
    situation = _texte(situation_id)
    twins = set(_liste_ids(twin_ids))
    borne = _limite(limite)

    lignes = entreprise_depot.lister_objets(conn, tenant, type_="LEARNING", limite=_MAX_LECTURE)
    resultats: list[tuple] = []
    for ligne in lignes:
        if _texte(ligne.get("tenant_id")) != tenant:
            continue
        situations_liees = _ids_lies(ligne, "situation_id", "situation_ids", "source_situation_ids")
        twins_lies = set(_ids_lies(ligne, "twin_ids", "source_twin_ids"))
        exacte = bool(situation and situation in situations_liees)
        chevauchement = len(twins & twins_lies)
        if (situation or twins) and not (exacte or chevauchement):
            continue
        recence = tuple(-valeur for valeur in _recence(ligne))
        resultats.append((
            0 if exacte else 1,
            -chevauchement,
            *recence,
            _texte(ligne.get("id")),
            ligne,
        ))
    resultats.sort(key=lambda element: element[:-1])
    return [element[-1] for element in resultats[:borne]]


def marquer_reutilise(
    conn: Any, tenant_id: Any, learning_id: Any, situation_id: Any, acteur: Any,
) -> dict:
    """Ajoute une trace de réutilisation dans ``donnees`` sans modifier le sens canonique du Learning.

    Le dépôt canonique accepte la mise à jour complète d'un objet : les champs du Learning sont préservés et
    seule la liste ``reutilisations`` est complétée. La situation peut être une situation nouvelle pas encore
    persistée ; si elle existe dans le tenant, son type est vérifié.
    """
    tenant = _tenant(tenant_id)
    identifiant = _texte_obligatoire(learning_id, "learning_id")
    situation = _texte_obligatoire(situation_id, "situation_id")
    acteur_final = _texte_obligatoire(acteur, "acteur")

    learning = entreprise_depot.lire_objet(conn, tenant, identifiant)
    if learning is None:
        raise LearningIntrouvable(f"learning introuvable dans le tenant {tenant!r} : {identifiant}")
    if _texte(learning.get("type")).upper() != "LEARNING":
        raise ReutilisationRefusee(
            f"l'objet {identifiant} n'est pas un LEARNING (reçu {_texte(learning.get('type')) or 'inconnu'})"
        )

    situation_lue = entreprise_depot.lire_objet(conn, tenant, situation)
    if situation_lue is not None and _texte(situation_lue.get("type")).upper() != "SITUATION":
        raise ReutilisationRefusee(
            f"l'objet {situation} n'est pas une SITUATION "
            f"(reçu {_texte(situation_lue.get('type')) or 'inconnu'})"
        )

    donnees = dict(_donnees(learning))
    existantes = donnees.get("reutilisations")
    reutilisations = list(existantes) if isinstance(existantes, (list, tuple)) else []
    entree = {
        "situation_id": situation,
        "acteur": acteur_final,
        "le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    reutilisations.append(entree)
    donnees["reutilisations"] = reutilisations

    payload = {cle: valeur for cle, valeur in learning.items() if cle != "version"}
    payload["donnees"] = donnees
    return entreprise_depot.enregistrer_objet(conn, tenant, payload)
