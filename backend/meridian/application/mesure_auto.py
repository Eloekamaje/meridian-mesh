"""Mesure automatique : observation → Outcome canonique, sans jamais créer de Learning.

Ce module est **pur** : il ne lit ni Mongo ni Postgres. Il normalise une observation déjà
collectée (source, Twin ou veille legacy), refuse tout ce qui est incomplet ou ambigu, puis
construit un événement d'outbox C1 signé via
:func:`meridian.application.pont_canonique.evenement_outcome`.

Deux formes d'observation sont acceptées :

1. **Observation générique** (collection Mongo ``mesure_auto_observations``) ::

       {
         "id": "obs-2026-11-05-1",          # identifiant stable de l'observation
         "tenant_id": "banque",
         "maj_le": "2026-11-05T09:01:00+00:00",   # curseur d'ingestion (worker)
         "initiative_id": "ini-dec-case-c1-1",    # ou decision_id
         "metrique": "delai_moyen_jours",
         "attendu": 5,
         "observe": 7,
         "effets_secondaires": [{"type": "rework", "observe": 3}],
         "periode": "2026-11",                    # sinon dérivée de ``quand``
         "quand": "2026-11-05T09:00:00+00:00",    # date de la mesure (idempotence)
         "source": {"type": "twin", "nom": "tbt"},
         "interpretation": "Le délai augmente"
       }

2. **Observation de veille legacy** : un document qui embarque la ``case`` et son observation
   (``case.veille.passation`` + ``observation``). La cible est un attendu, un risque ou une
   inconnue de la note de passation ; la période est dérivée de ``quand``.

Règles structurantes :

- aucune mesure vide, booléenne, non numérique quand la veille l'exige, ni de cible inconnue ;
  une observation incomplète ne produit **rien** et expose sa raison ;
- le tenant est normalisé et jamais deviné : un document sans tenant, ou dont les tenants se
  contredisent, est refusé ;
- l'identifiant d'événement est déterministe (tenant + Outcome canonique + source + empreinte de
  la mesure) ; un rejeu produit le même événement, une mesure modifiée produit un nouvel
  événement qui met à jour le même Outcome ;
- l'origine canonique est ``exploitation`` : ce n'est ni un backfill ni une saisie API ;
- **aucun Learning n'est produit** : la capitalisation reste une décision humaine.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from datetime import timezone
import math
from typing import Any

from meridian.application import pont_canonique as pont
from meridian.domain.mesure import mesure_renseignee

__all__ = [
    "ObservationIncomplete",
    "ObservationMesure",
    "ResultatMesure",
    "empreinte_observation",
    "evenement_depuis_observation",
    "mesurer_observation",
    "normaliser_observation",
    "outcome_depuis_observation",
]

_MAX_INTERPRETATION = 5000
_TOLERANCE_FUTUR_SECONDES = 300

# Mêmes statuts de décision proposée que le pont C1 : une décision non tranchée ne produit
# jamais d'initiative canonique, donc aucune mesure ne peut lui être rattachée.
_STATUTS_DECISION_PROPOSEE = frozenset({
    "proposee", "propose", "proposed", "en attente", "a trancher", "a decider", "brouillon",
})
_CLES_VALEUR = ("valeur_observee", "valeur", "observed_value", "value", "resultat", "résultat")
_CLES_ATTENDU = ("attendu", "valeur_attendue", "expected")
_CLES_OBSERVE = ("observe", "valeur_observee", "observed", "resultat")


class MesureAutoInvalide(ValueError):
    """Une observation ne peut pas être transformée en Outcome sans inventer de sémantique."""


class ObservationIncomplete(MesureAutoInvalide):
    """L'observation est incomplète ou ambiguë : aucun Outcome ne doit être produit."""

    def __init__(self, raison: str):
        self.raison = str(raison).strip() or "observation incomplète"
        super().__init__(self.raison)


@dataclass(frozen=True)
class ObservationMesure:
    """Observation normalisée, prête à être transformée en Outcome canonique."""

    tenant_id: str
    observation_id: str
    source: dict[str, Any]
    initiative_id: str
    metrique: str
    attendu: Any
    observe: Any
    effets_secondaires: tuple[dict[str, Any], ...]
    periode: str
    mesure_le: str
    interpretation: str
    valeur_attendue: Any
    valeur_observee: Any
    type_observation: str
    decision_id: str | None = None

    @property
    def mesure(self) -> dict[str, Any]:
        """Mesure structurée conservée dans ``Outcome.donnees.mesure``."""
        mesure: dict[str, Any] = {
            "metrique": self.metrique,
            "valeur_observee": self.valeur_observee,
            "attendu": self.attendu,
            "observe": self.observe,
            "effets_secondaires": list(self.effets_secondaires),
            "source_observation": dict(self.source),
            "observation_id": self.observation_id,
            "type_observation": self.type_observation,
            "quand": self.mesure_le,
        }
        if self.periode:
            mesure["periode"] = self.periode
        return pont.assainir(mesure)


@dataclass(frozen=True)
class ResultatMesure:
    """Résultat d'une mesure : soit un événement, soit une raison de ne rien produire."""

    mesure: ObservationMesure | None = None
    evenement: dict[str, Any] | None = None
    raison: str | None = None

    @property
    def produit(self) -> bool:
        return self.mesure is not None and self.evenement is not None


# ---------------------------------------------------------------------------
# Helpers purs
# ---------------------------------------------------------------------------


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _mapping(valeur: Any) -> dict[str, Any]:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _instant(valeur: Any) -> str | None:
    """ISO UTC à la seconde, ou ``None`` si la valeur n'est pas une date lisible."""
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        horodatage = valeur
    elif isinstance(valeur, date):
        horodatage = datetime.combine(valeur, time.min)
    else:
        texte = _texte(valeur)
        if not texte:
            return None
        try:
            horodatage = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError:
            return None
    if horodatage.tzinfo is None:
        horodatage = horodatage.replace(tzinfo=timezone.utc)
    return horodatage.astimezone(timezone.utc).isoformat(timespec="seconds")


def _est_futur(instant: str, reference: str | None) -> bool:
    if not reference:
        return False
    try:
        gauche = datetime.fromisoformat(instant.replace("Z", "+00:00"))
        droite = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    except ValueError:
        return False
    return gauche.timestamp() > droite.timestamp() + _TOLERANCE_FUTUR_SECONDES


def _nombre(valeur: Any) -> float | None:
    """Nombre fini ou ``None`` ; refuse les booléens et les chaînes non numériques."""
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, (int, float)):
        nombre = float(valeur)
    else:
        texte = _texte(valeur).replace(",", ".")
        if not texte:
            return None
        try:
            nombre = float(texte)
        except ValueError:
            return None
    return nombre if math.isfinite(nombre) else None


def _nombre_ou_none(valeur: Any) -> int | float | None:
    nombre = _nombre(valeur)
    if nombre is None:
        return None
    return int(nombre) if nombre.is_integer() else nombre


def _avec_unite(valeur: Any, unite: Any = "") -> str:
    nombre = _nombre_ou_none(valeur)
    if nombre is None:
        return _texte(valeur)
    return f"{nombre} {_texte(unite)}".strip()


def _valeur_dans(conteneur: Any) -> Any:
    if isinstance(conteneur, Mapping):
        for cle in _CLES_VALEUR:
            if cle in conteneur and _valeur_mesurable(conteneur[cle]):
                return conteneur[cle]
        return None
    return conteneur


def _valeur_mesurable(valeur: Any) -> bool:
    if not mesure_renseignee(valeur):
        return False
    if isinstance(valeur, float) and not math.isfinite(valeur):
        return False
    return True


def _premier_texte(conteneur: Any, cles: tuple[str, ...]) -> str:
    if not isinstance(conteneur, Mapping):
        return _texte(conteneur)
    for cle in cles:
        texte = _texte(conteneur.get(cle))
        if texte:
            return texte
    return ""


def _tenant_depuis(candidats: list[Any], explicite: Any = None) -> str:
    valeurs = [_texte(candidat) for candidat in [*candidats, explicite] if _texte(candidat)]
    if not valeurs:
        raise ObservationIncomplete("tenant_id absent")
    normalises: set[str] = set()
    for valeur in valeurs:
        try:
            normalises.add(pont.normaliser_tenant(valeur))
        except pont.PontInvalide as exc:
            raise ObservationIncomplete(f"tenant_id invalide : {exc}") from exc
    if len(normalises) != 1:
        raise ObservationIncomplete("tenant_id incohérent entre observation et contexte")
    return normalises.pop()


def _source(document: Mapping[str, Any], observation_id: str,
            type_defaut: str = "observation") -> dict[str, Any]:
    brut = document.get("source")
    if isinstance(brut, Mapping):
        source = dict(brut)
    elif _texte(brut):
        source = {"nom": _texte(brut)}
    else:
        source = {}
    source.setdefault("type", type_defaut)
    source.setdefault("id", observation_id)
    source.setdefault("collection", _texte(document.get("_collection"))
                       or "mesure_auto_observations")
    return dict(pont.assainir(source))


def _quand(document: Mapping[str, Any], maintenant: Any = None) -> str:
    brut = document.get("quand") or document.get("observe_le") or document.get("mesure_le")
    instant = _instant(brut)
    if instant is None:
        raise ObservationIncomplete("quand absent ou illisible")
    reference = _instant(maintenant) or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if _est_futur(instant, reference):
        raise ObservationIncomplete("quand dans le futur")
    return instant


def _periode(document: Mapping[str, Any], quand: str) -> str:
    explicite = _texte(document.get("periode"))
    if explicite:
        return explicite
    horodatage = datetime.fromisoformat(quand.replace("Z", "+00:00"))
    return horodatage.strftime("%Y-%m")


def _effets_secondaires(document: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    brut = document.get("effets_secondaires")
    if brut in (None, "", [], {}, ()):
        return ()
    if isinstance(brut, Mapping):
        brut = [brut]
    if not isinstance(brut, (list, tuple)):
        raise ObservationIncomplete("effets_secondaires doit être une liste")
    effets: list[dict[str, Any]] = []
    for element in brut:
        if isinstance(element, Mapping):
            propre = pont.assainir(dict(element))
            if not isinstance(propre, Mapping):
                raise ObservationIncomplete("effet secondaire illisible")
            effets.append(dict(propre))
        elif _texte(element):
            effets.append({"libelle": _texte(element)})
        else:
            raise ObservationIncomplete("effet secondaire illisible")
    return tuple(effets)


def _decision_tranchee(decision: Any) -> bool:
    if not isinstance(decision, Mapping):
        return bool(_texte(decision))
    statut = _texte(decision.get("statut") or decision.get("etat")).lower()
    if statut in _STATUTS_DECISION_PROPOSEE:
        return False
    choix = _texte(decision.get("texte") or decision.get("decision") or decision.get("choix"))
    options = [element for element in _liste(decision.get("options")) if _texte(element)]
    acteur = _texte(decision.get("par") or decision.get("acteur") or decision.get("acteur_id"))
    return bool((choix or options) and acteur)


def _initiative(document: Mapping[str, Any], *, explicite: Any = None,
                case: Mapping[str, Any] | None = None,
                decisions: Any = None) -> tuple[str, str | None]:
    candidats = [
        _texte(candidat)
        for candidat in (explicite, document.get("initiative_id"),
                         document.get("initiative_ref"))
        if _texte(candidat)
    ]
    if len(set(candidats)) > 1:
        raise ObservationIncomplete("initiative_id incohérent entre observation et contexte")
    if candidats:
        return candidats[0], None
    decision_id = _texte(document.get("decision_id") or document.get("decision_ref"))
    if decision_id:
        return pont.initiative_id(decision_id), decision_id
    case = _mapping(case)
    case_id = _texte(document.get("case_id") or case.get("id"))
    liste_decisions = _liste(decisions if decisions is not None else case.get("decisions"))
    if case_id and liste_decisions:
        rang = len(liste_decisions)
        if not _decision_tranchee(liste_decisions[-1]):
            raise ObservationIncomplete(
                "décision non tranchée : aucune initiative canonique à mesurer")
        identifiant = pont.decision_case_id(case_id, rang)
        return pont.initiative_id(identifiant), identifiant
    raise ObservationIncomplete(
        "initiative_id introuvable : fournir initiative_id, decision_id ou une décision "
        "tranchée reliée au case")


def _metrique(document: Mapping[str, Any], attendu: Any = None) -> str:
    texte = _texte(document.get("metrique"))
    if texte:
        return texte
    if isinstance(attendu, Mapping):
        texte = _texte(attendu.get("indicateur") or attendu.get("metrique")
                       or attendu.get("metric"))
        if texte:
            return texte
    raise ObservationIncomplete("métrique absente")


def _interpretation(document: Mapping[str, Any], metrique: str, attendu: Any,
                    observe: Any, effets: tuple[dict[str, Any], ...]) -> str:
    texte = _premier_texte(document, ("interpretation", "conclusion", "resume", "résumé"))
    if texte:
        return texte[:_MAX_INTERPRETATION]
    observe_lisible = _premier_texte(observe, ("conclusion", "texte", "libelle")) or _texte(
        _valeur_dans(observe))
    morceaux = [f"{metrique} : {observe_lisible or _texte(observe) or 'valeur observée'}"]
    valeur_attendue = _valeur_dans(attendu)
    if valeur_attendue is not None:
        morceaux.append(f"attendu {_texte(valeur_attendue)}")
    if effets:
        morceaux.append(f"{len(effets)} effet(s) secondaire(s)")
    return " ; ".join(morceaux)[:_MAX_INTERPRETATION]


# ---------------------------------------------------------------------------
# Observation générique
# ---------------------------------------------------------------------------


def _observation_id_generique(document: Mapping[str, Any]) -> str:
    identifiant = _texte(document.get("id") or document.get("_id")
                         or document.get("observation_id"))
    if not identifiant:
        raise ObservationIncomplete("id d'observation absent")
    return identifiant


def _normaliser_generique(document: Mapping[str, Any], *, tenant_id: Any = None,
                          initiative_id: Any = None, maintenant: Any = None) -> ObservationMesure:
    tenant = _tenant_depuis([document.get("tenant_id"), document.get("tenant")], tenant_id)
    identifiant = _observation_id_generique(document)
    quand = _quand(document, maintenant)
    periode = _periode(document, quand)
    attendu = next(
        (document[cle] for cle in _CLES_ATTENDU if document.get(cle) is not None), None)
    observe = next(
        (document[cle] for cle in _CLES_OBSERVE
         if cle in document and _valeur_mesurable(_valeur_dans(document[cle]))), None)
    if observe is None:
        raise ObservationIncomplete("mesure observée absente")
    valeur_observee = _valeur_dans(observe)
    if not _valeur_mesurable(valeur_observee):
        raise ObservationIncomplete("mesure observée absente, vide ou non finie")
    metrique = _metrique(document, attendu)
    effets = _effets_secondaires(document)
    initiative, decision_id = _initiative(document, explicite=initiative_id)
    source = _source(document, identifiant)
    valeur_attendue = attendu
    interpretation = _interpretation(document, metrique, attendu, observe, effets)
    return ObservationMesure(
        tenant_id=tenant,
        observation_id=identifiant,
        source=source,
        initiative_id=initiative,
        metrique=metrique,
        attendu=attendu,
        observe=observe,
        effets_secondaires=effets,
        periode=periode,
        mesure_le=quand,
        interpretation=interpretation,
        valeur_attendue=valeur_attendue,
        valeur_observee=valeur_observee,
        type_observation="generique",
        decision_id=decision_id,
    )


# ---------------------------------------------------------------------------
# Observation de veille legacy
# ---------------------------------------------------------------------------


def _est_observation_veille(document: Mapping[str, Any]) -> bool:
    return isinstance(document.get("observation"), Mapping) and (
        isinstance(document.get("case"), Mapping)
        or isinstance(document.get("veille"), Mapping)
    )


def _entrees(passation: Mapping[str, Any], cle: str) -> dict[str, dict[str, Any]]:
    resultat: dict[str, dict[str, Any]] = {}
    for element in _liste(passation.get(cle)):
        if not isinstance(element, Mapping):
            continue
        identifiant = _texte(element.get("id"))
        if identifiant:
            resultat[identifiant] = dict(element)
    return resultat


def _normaliser_veille(document: Mapping[str, Any], *, tenant_id: Any = None,
                      initiative_id: Any = None, maintenant: Any = None) -> ObservationMesure:
    case = _mapping(document.get("case"))
    veille = document.get("veille")
    if not isinstance(veille, Mapping):
        veille = case.get("veille")
    if not isinstance(veille, Mapping):
        raise ObservationIncomplete("veille absente")
    passation = veille.get("passation")
    if not isinstance(passation, Mapping):
        raise ObservationIncomplete("passation absente de la veille")
    observation = _mapping(document.get("observation"))
    identifiant = _texte(observation.get("id") or document.get("observation_id"))
    if not identifiant:
        raise ObservationIncomplete("id d'observation absent")
    tenant = _tenant_depuis(
        [document.get("tenant_id"), observation.get("tenant_id"), case.get("tenant_id")],
        tenant_id,
    )
    quand = _quand(observation, maintenant)
    periode = _periode(document, quand)
    cible = _texte(observation.get("cible"))
    if not cible:
        raise ObservationIncomplete("cible de veille absente")

    attendus = _entrees(passation, "attendus")
    risques = _entrees(passation, "risques")
    inconnues = _entrees(passation, "inconnues")

    effets: tuple[dict[str, Any], ...] = ()
    decision_id: str | None = None
    if cible in attendus:
        attendu_brut = attendus[cible]
        metrique = _texte(attendu_brut.get("indicateur"))
        if not metrique:
            raise ObservationIncomplete("attendu de veille sans indicateur")
        valeur = _nombre(observation.get("valeur"))
        if valeur is None:
            raise ObservationIncomplete("valeur observée non numérique pour un attendu")
        depart = _nombre(attendu_brut.get("depart"))
        cible_valeur = _nombre(attendu_brut.get("cible"))
        if depart is None or cible_valeur is None:
            raise ObservationIncomplete("attendu de veille non numérique (départ/cible)")
        unite = _texte(attendu_brut.get("unite")) or _texte(observation.get("unite"))
        attendu = {
            "id": cible,
            "indicateur": metrique,
            "sens": _texte(attendu_brut.get("sens")) or "hausse",
            "depart": _nombre_ou_none(depart),
            "cible": _nombre_ou_none(cible_valeur),
            "unite": unite,
        }
        observe = {
            "valeur": _nombre_ou_none(valeur),
            "unite": _texte(observation.get("unite")) or unite,
            "conclusion": _texte(observation.get("conclusion")),
        }
        valeur_observee = _nombre_ou_none(valeur)
        valeur_attendue = _nombre_ou_none(cible_valeur)
        type_observation = "attendu"
        attendu_texte = _avec_unite(cible_valeur, unite)
        observe_texte = _avec_unite(valeur, unite)
        sens = attendu["sens"]
        atteint = valeur >= cible_valeur if sens == "hausse" else valeur <= cible_valeur
        interpretation = (
            f"{metrique} : {observe_texte} observé, "
            f"{'objectif atteint' if atteint else 'objectif non atteint'} "
            f"(cible {attendu_texte}, départ {_avec_unite(depart, unite)})."
        )
    elif cible in risques:
        risque = risques[cible]
        libelle = _texte(risque.get("texte"))
        if not libelle:
            raise ObservationIncomplete("risque de veille sans libellé")
        valeur = _nombre(observation.get("valeur"))
        if valeur is None:
            raise ObservationIncomplete("valeur observée non numérique pour un risque")
        seuil = _nombre(risque.get("seuil"))
        if seuil is None:
            raise ObservationIncomplete("seuil de risque non numérique")
        sens = "baisse" if _texte(risque.get("sens")).lower() == "baisse" else "hausse"
        unite = _texte(risque.get("unite")) or _texte(observation.get("unite"))
        franchi = valeur > seuil if sens == "hausse" else valeur < seuil
        metrique = f"risque:{libelle}"
        attendu = {
            "id": cible,
            "texte": libelle,
            "seuil": _nombre_ou_none(seuil),
            "sens": sens,
            "unite": unite,
        }
        observe = {
            "valeur": _nombre_ou_none(valeur),
            "unite": _texte(observation.get("unite")) or unite,
            "conclusion": _texte(observation.get("conclusion")),
        }
        valeur_observee = _nombre_ou_none(valeur)
        valeur_attendue = _nombre_ou_none(seuil)
        type_observation = "risque"
        effets = ({
            "type": "risque_materialise" if franchi else "risque_maitrise",
            "libelle": libelle,
            "attendu": {"seuil": _nombre_ou_none(seuil), "sens": sens, "unite": unite},
            "observe": _nombre_ou_none(valeur),
            "seuil": _nombre_ou_none(seuil),
            "sens": sens,
            "unite": unite,
            **({"jumeau": _texte(observation.get("jumeau"))}
               if _texte(observation.get("jumeau")) else {}),
        },)
        interpretation = (
            f"Risque « {libelle} » : {_avec_unite(valeur, unite)} observé, "
            f"seuil {_avec_unite(seuil, unite)} "
            f"({'matérialisé' if franchi else 'maîtrisé'})."
        )
    elif cible in inconnues:
        inconnue = inconnues[cible]
        libelle = _texte(inconnue.get("texte"))
        if not libelle:
            raise ObservationIncomplete("inconnue de veille sans libellé")
        conclusion = _texte(observation.get("conclusion"))
        if not conclusion:
            raise ObservationIncomplete("conclusion absente pour une inconnue levée")
        metrique = f"inconnue:{libelle}"
        attendu = None
        observe = conclusion
        valeur_observee = conclusion
        valeur_attendue = None
        type_observation = "inconnue"
        interpretation = f"Inconnue levée — {libelle} : {conclusion}"
    else:
        raise ObservationIncomplete(f"cible de veille inconnue : {cible}")

    initiative, decision_id = _initiative(
        document, explicite=initiative_id, case=case, decisions=case.get("decisions"))
    source = _source(document, identifiant, type_defaut="veille")
    nom_source = _texte(observation.get("source"))
    if nom_source and not _texte(source.get("nom")):
        source["nom"] = nom_source
    jumeau = _texte(observation.get("jumeau"))
    if jumeau:
        source.setdefault("jumeau", jumeau)
    return ObservationMesure(
        tenant_id=tenant,
        observation_id=identifiant,
        source=dict(pont.assainir(source)),
        initiative_id=initiative,
        metrique=metrique,
        attendu=attendu,
        observe=observe,
        effets_secondaires=effets,
        periode=periode,
        mesure_le=quand,
        interpretation=interpretation[:_MAX_INTERPRETATION],
        valeur_attendue=valeur_attendue,
        valeur_observee=valeur_observee,
        type_observation=type_observation,
        decision_id=decision_id,
    )


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def normaliser_observation(document: Any, *, tenant_id: Any = None,
                           initiative_id: Any = None,
                           maintenant: Any = None) -> ObservationMesure:
    """Normalise une observation ou lève :class:`ObservationIncomplete`."""
    if not isinstance(document, Mapping):
        raise ObservationIncomplete("observation absente : document attendu")
    if _est_observation_veille(document):
        return _normaliser_veille(
            document, tenant_id=tenant_id, initiative_id=initiative_id,
            maintenant=maintenant)
    return _normaliser_generique(
        document, tenant_id=tenant_id, initiative_id=initiative_id, maintenant=maintenant)


def empreinte_observation(observation: ObservationMesure) -> str:
    """Empreinte stable du contenu mesuré : identifie une version de l'observation."""
    return pont.hash_contenu({
        "tenant_id": observation.tenant_id,
        "observation_id": observation.observation_id,
        "initiative_id": observation.initiative_id,
        "metrique": observation.metrique,
        "attendu": observation.attendu,
        "observe": observation.observe,
        "effets_secondaires": list(observation.effets_secondaires),
        "periode": observation.periode,
        "mesure_le": observation.mesure_le,
    })[:16]


def outcome_depuis_observation(observation: ObservationMesure) -> dict[str, Any]:
    """Payload C1 de l'Outcome (attendu, observé, effets secondaires, période)."""
    return {
        "initiative_id": observation.initiative_id,
        "mesure": observation.mesure,
        "metrique": observation.metrique,
        "periode": observation.periode,
        "valeur_attendue": observation.valeur_attendue,
        "interpretation": observation.interpretation,
        "mesure_le": observation.mesure_le,
        "decision_id": observation.decision_id,
        "effets_secondaires": list(observation.effets_secondaires),
    }


def evenement_depuis_observation(observation: ObservationMesure, *,
                                 maintenant: Any = None) -> dict[str, Any]:
    """Événement d'outbox C1 signé, d'origine ``exploitation``."""
    return pont.evenement_outcome(
        tenant_id=observation.tenant_id,
        initiative_id=observation.initiative_id,
        mesure=observation.mesure,
        metrique=observation.metrique,
        periode=observation.periode,
        valeur_attendue=observation.valeur_attendue,
        interpretation=observation.interpretation,
        mesure_le=observation.mesure_le,
        decision_id=observation.decision_id,
        effets_secondaires=list(observation.effets_secondaires),
        origine=pont.ORIGINE_EXPLOITATION,
        source_event_id=(
            f"mesure-auto:{observation.type_observation}:{observation.observation_id}:"
            f"{empreinte_observation(observation)}"
        ),
        maintenant=maintenant,
    )


def mesurer_observation(document: Any, *, tenant_id: Any = None,
                        initiative_id: Any = None,
                        maintenant: Any = None) -> ResultatMesure:
    """Produit un Outcome si l'observation est complète, sinon expose la raison du refus."""
    try:
        observation = normaliser_observation(
            document, tenant_id=tenant_id, initiative_id=initiative_id,
            maintenant=maintenant)
    except ObservationIncomplete as exc:
        return ResultatMesure(raison=exc.raison)
    except pont.PontInvalide as exc:
        return ResultatMesure(raison=str(exc))
    try:
        evenement = evenement_depuis_observation(observation, maintenant=maintenant)
    except pont.PontInvalide as exc:
        return ResultatMesure(mesure=observation, raison=str(exc))
    return ResultatMesure(mesure=observation, evenement=evenement)
