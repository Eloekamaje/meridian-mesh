"""Spécialistes en lecture seule : impact topologique et réutilisation d'outcomes.

Les deux spécialistes ne détiennent aucune autorité : ils lisent un store de graphe ou une connexion
canonique déjà bornés au tenant, puis rendent des propositions traçables. Aucun réseau, aucune
écriture canonique et aucune invention : quand la source manque, le résultat est partiel et le dit.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jumeau import outcomes
from jumeau.specialistes import ContexteSpecialiste, Proposition, ResultatSpecialiste
from jumeau.temporalite import fraicheur

__all__ = ["SpecialisteImpact", "SpecialisteOutcome"]

_MAX_IDS = 8
_LIMITE_LEARNINGS = 10
_ACTIONS_IMPACT = ("ouvrir_impact", "verifier_relations")
_ACTIONS_REUTILISER = ("reutiliser_learning", "verifier_conditions")


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bytes, bytearray, Mapping)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _valeur(objet: Any, *noms: str, defaut: Any = None) -> Any:
    """Lit un champ sur un mapping, un objet ou son bloc ``donnees``, sans effet de bord."""
    if objet is None:
        return defaut
    for nom in noms:
        if isinstance(objet, Mapping):
            if nom in objet and objet[nom] is not None:
                return objet[nom]
        else:
            valeur = getattr(objet, nom, None)
            if valeur is not None:
                return valeur
    donnees = objet.get("donnees") if isinstance(objet, Mapping) else None
    if isinstance(donnees, Mapping):
        for nom in noms:
            if nom in donnees and donnees[nom] is not None:
                return donnees[nom]
    return defaut


def _elements(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, bytes, bytearray, Mapping)):
        return [valeur]
    try:
        return list(valeur)
    except TypeError:
        return [valeur]


def _identifiants(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _elements(valeur):
        if isinstance(element, Mapping):
            element = _valeur(element, "id", "identifiant", "twin_id")
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _direction(impact: Any, noms: tuple[str, ...]) -> list[Any]:
    if not isinstance(impact, Mapping):
        return []
    for nom in noms:
        if nom in impact:
            brut = impact[nom]
            if isinstance(brut, Mapping) and "ids" in brut:
                return _elements(brut.get("ids"))
            return _elements(brut)
    return []


def _confiance_learning(ligne: Any, maintenant: Any) -> tuple[float, dict]:
    try:
        confiance = float(_valeur(ligne, "confiance", "confidence", defaut=0.6))
    except (TypeError, ValueError):
        confiance = 0.6
    confiance = max(0.0, min(1.0, confiance))
    etat = fraicheur(ligne, maintenant=maintenant)
    if etat.get("connu") and etat.get("stale"):
        confiance = max(0.1, confiance - 0.1)
    elif not etat.get("connu"):
        confiance = max(0.1, confiance - 0.05)
    return confiance, etat


class SpecialisteImpact:
    """Lit l'impact amont/aval d'un ou plusieurs Twins, sans modifier le graphe."""

    nom = "impact"
    autorite = "proposition"

    def __init__(self, *, inclure_chemins: bool = True):
        self.inclure_chemins = bool(inclure_chemins)

    def _proposition_impact(self, twin_id: str, impact: Any, profondeur: int) -> Proposition:
        amont_brut = _direction(impact, ("amont", "upstream", "entrant"))
        aval_brut = _direction(impact, ("aval", "downstream", "sortant"))
        amont = _identifiants(amont_brut)
        aval = _identifiants(aval_brut)
        total_amont, total_aval = len(amont_brut), len(aval_brut)
        ids: list[str] = []
        for identifiant in amont + aval:
            if identifiant not in ids:
                ids.append(identifiant)
        visibles = ids[:_MAX_IDS]
        tronque = len(ids) > _MAX_IDS
        visibles_amont = [identifiant for identifiant in visibles if identifiant in amont]
        visibles_aval = [identifiant for identifiant in visibles if identifiant in aval
                         and identifiant not in visibles_amont]
        titre = f"Impact de {twin_id} : {total_amont} amont, {total_aval} aval"
        resume = (
            f"À profondeur {profondeur}, {twin_id} compte {total_amont} dépendance(s) amont et "
            f"{total_aval} dépendance(s) aval observées dans le graphe."
        )
        if tronque:
            resume += f" Seuls {_MAX_IDS} identifiants sont exposés."
        donnees = {
            "twin_id": twin_id,
            "profondeur": profondeur,
            "amont": total_amont,
            "aval": total_aval,
            "total": total_amont + total_aval,
            "ids": visibles,
            "amont_ids": visibles_amont,
            "aval_ids": visibles_aval,
            "tronque": tronque,
        }
        confiance = 0.7 if total_amont + total_aval else 0.55
        return Proposition(
            specialiste=self.nom, type="IMPACT", titre=titre, resume=resume,
            preuves=visibles, confiance=confiance, actions=_ACTIONS_IMPACT, donnees=donnees,
        )

    def _proposition_chemin(
        self, source: str, cible: str, chemins: Any, profondeur: int,
    ) -> Proposition | None:
        valides: list[list[str]] = []
        for brut in _elements(chemins):
            identifiants = _identifiants(brut)
            if len(identifiants) < 2 or identifiants[0] != source or identifiants[-1] != cible:
                continue
            if identifiants not in valides:
                valides.append(identifiants)
        if not valides:
            return None
        premier = valides[0]
        titre = f"Chemin d'impact entre {source} et {cible}"
        resume = f"Chemin observé à profondeur {profondeur} : {' -> '.join(premier)}."
        donnees = {
            "source": source,
            "cible": cible,
            "profondeur": profondeur,
            "chemin": premier,
            "chemins": valides[:5],
            "nombre_chemins": len(valides),
        }
        return Proposition(
            specialiste=self.nom, type="IMPACT", titre=titre, resume=resume,
            preuves=premier, confiance=0.65, actions=_ACTIONS_IMPACT, donnees=donnees,
        )

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        if not isinstance(contexte, ContexteSpecialiste):
            return ResultatSpecialiste(
                specialiste=self.nom, statut="erreur", erreur="TypeError",
                limites=["ContexteSpecialiste attendu"],
            )
        store = contexte.store
        if store is None:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                limites=["store de graphe absent : aucun impact calculé, aucune donnée inventée"],
            )
        impact = getattr(store, "impact", None)
        if not callable(impact):
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                limites=["store sans opération impact : aucun impact calculé, aucune donnée inventée"],
            )
        if not contexte.twin_ids:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                limites=["aucun twin_id fourni : aucun impact calculé"],
            )

        propositions: list[Proposition] = []
        limites: list[str] = []
        erreurs: list[str] = []
        for twin_id in contexte.twin_ids:
            try:
                resultat = impact(contexte.tenant, twin_id, contexte.profondeur)
            except Exception as exc:  # noqa: BLE001 - une lecture en échec ne bloque pas les autres
                erreurs.append(type(exc).__name__)
                limites.append(f"impact indisponible pour {twin_id} : {type(exc).__name__}")
                continue
            if not isinstance(resultat, Mapping) or not any(
                cle in resultat for cle in ("amont", "aval", "upstream", "downstream", "entrant", "sortant")
            ):
                limites.append(f"impact vide ou invalide pour {twin_id} : aucun résultat exploitable")
                continue
            propositions.append(self._proposition_impact(twin_id, resultat, contexte.profondeur))

        if self.inclure_chemins and len(contexte.twin_ids) >= 2:
            chemins = getattr(store, "chemins", None)
            if callable(chemins):
                source, cible = contexte.twin_ids[0], contexte.twin_ids[1]
                try:
                    trouves = chemins(contexte.tenant, source, cible, contexte.profondeur)
                except Exception as exc:  # noqa: BLE001 - le chemin est optionnel
                    erreurs.append(type(exc).__name__)
                    limites.append(f"chemins indisponibles entre {source} et {cible} : {type(exc).__name__}")
                else:
                    proposition = self._proposition_chemin(
                        source, cible, trouves, contexte.profondeur)
                    if proposition is not None:
                        propositions.append(proposition)

        if not propositions:
            statut = "erreur" if erreurs else "partiel"
            return ResultatSpecialiste(
                specialiste=self.nom, statut=statut, propositions=[],
                limites=limites, erreur=erreurs[-1] if erreurs else None,
            )
        return ResultatSpecialiste(
            specialiste=self.nom, statut="partiel" if limites else "ok",
            propositions=propositions, limites=limites, erreur=erreurs[-1] if erreurs else None,
        )


class SpecialisteOutcome:
    """Cherche des Learnings réutilisables pour une situation ou des Twins, sans en inventer."""

    nom = "outcome"
    autorite = "proposition"

    def __init__(self, *, limite: int = _LIMITE_LEARNINGS):
        try:
            self.limite = max(1, min(int(limite), 100))
        except (TypeError, ValueError):
            self.limite = _LIMITE_LEARNINGS

    def _proposition_learning(self, ligne: Any, contexte: ContexteSpecialiste) -> Proposition:
        identifiant = _texte(_valeur(ligne, "id", "identifiant"))
        enonce = _texte(_valeur(ligne, "enonce", "resume", "description", "titre"))
        titre = enonce or (f"Learning {identifiant}" if identifiant else "Learning réutilisable")
        resume = (
            f"Learning réutilisable : {enonce}. Vérifier les conditions d'applicabilité avant réutilisation."
            if enonce else
            "Learning réutilisable dans le périmètre courant ; vérifier ses conditions d'applicabilité."
        )
        confiance, etat = _confiance_learning(ligne, contexte.maintenant)
        outcome_ids = _identifiants(_valeur(ligne, "outcome_ids"))
        donnees = {
            "learning_id": identifiant or None,
            "situation_id": contexte.situation_id,
            "twin_ids": list(contexte.twin_ids),
            "outcome_ids": outcome_ids,
            "fraicheur": etat,
        }
        return Proposition(
            specialiste=self.nom, type="LEARNING", titre=titre, resume=resume,
            preuves=(identifiant,) if identifiant else (), confiance=confiance,
            actions=_ACTIONS_REUTILISER, donnees=donnees,
        )

    def _proposition_question(self, contexte: ContexteSpecialiste) -> Proposition:
        situation = _texte(contexte.situation_id) or None
        perimetre = f"situation {situation}" if situation else "Twins " + ", ".join(contexte.twin_ids)
        titre = "Aucun learning réutilisable"
        resume = (
            f"Aucun learning réutilisable n'a été trouvé pour la {perimetre} ; "
            "mesurer un outcome avant toute réutilisation."
        )
        donnees = {
            "learnings": 0,
            "situation_id": situation,
            "twin_ids": list(contexte.twin_ids),
            "limite": self.limite,
        }
        return Proposition(
            specialiste=self.nom, type="QUESTION", titre=titre, resume=resume,
            confiance=0.6, actions=("mesurer_outcome",), donnees=donnees,
        )

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        if not isinstance(contexte, ContexteSpecialiste):
            return ResultatSpecialiste(
                specialiste=self.nom, statut="erreur", erreur="TypeError",
                limites=["ContexteSpecialiste attendu"],
            )
        if contexte.conn is None:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                limites=["connexion canonique absente : aucun learning lu, aucune donnée inventée"],
            )
        situation = _texte(contexte.situation_id) or None
        if not situation and not contexte.twin_ids:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                limites=["aucun ancrage (situation_id ou twin_ids) : aucun learning recherché"],
            )
        try:
            lignes = outcomes.learnings_pour(
                contexte.conn, contexte.tenant, situation_id=situation,
                twin_ids=contexte.twin_ids, limite=self.limite,
            )
        except Exception as exc:  # noqa: BLE001 - une lecture en échec est signalée sans invention
            return ResultatSpecialiste(
                specialiste=self.nom, statut="erreur", erreur=type(exc).__name__,
                limites=[f"lecture des learnings impossible : {type(exc).__name__}"],
            )
        lignes = list(lignes or [])
        if not lignes:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="ok",
                propositions=[self._proposition_question(contexte)],
            )
        propositions = [
            self._proposition_learning(ligne, contexte) for ligne in lignes[:self.limite]
        ]
        limites = []
        if len(lignes) > self.limite:
            limites.append(
                f"learnings tronqués à {self.limite} sur {len(lignes)} lus : aucune promotion automatique"
            )
        return ResultatSpecialiste(
            specialiste=self.nom, statut="partiel" if limites else "ok",
            propositions=propositions, limites=limites,
        )
