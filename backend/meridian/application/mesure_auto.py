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

- ``id`` et ``maj_le`` sont obligatoires ; ``maj_le`` est la date d'ingestion UTC qui arbitre les
  corrections (``quand`` reste la date de la mesure) ;
- aucune mesure vide, booléenne, non numérique quand la veille l'exige, ni de cible inconnue ;
  une observation incomplète ne produit **rien** et expose sa raison ;
- le tenant est normalisé et jamais deviné : un document sans tenant, ou dont les tenants se
  contredisent, est refusé ;
- l'identifiant d'événement est déterministe (tenant + Outcome canonique + source + empreinte du
  payload complet) ; un rejeu produit le même événement, une correction (même ``quand``, nouveau
  ``maj_le`` ou contenu modifié) produit un nouvel événement qui met à jour le même Outcome ;
- une observation de veille doit porter un lien canonique **explicite** (``initiative_id`` ou
  ``decision_id``) : aucune décision legacy n'est devinée ;
- le payload sérialisé est borné à 256 Kio ;
- l'origine canonique est ``exploitation`` : ce n'est ni un backfill ni une saisie API ;
- **aucun Learning n'est produit** : la capitalisation reste une décision humaine.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from datetime import timezone
import json
import math
import re
from typing import Any

from meridian.application import pont_canonique as pont
from meridian.domain.mesure import mesure_renseignee

__all__ = [
    "ObservationIncomplete",
    "ObservationMesure",
    "ObservationTransitoire",
    "ResultatMesure",
    "empreinte_observation",
    "evenement_depuis_observation",
    "mesurer_observation",
    "normaliser_observation",
    "outcome_depuis_observation",
]

_MAX_INTERPRETATION = 5000
_MAX_SERIALISE = 256 * 1024
_TOLERANCE_FUTUR_SECONDES = 300
_RE_PERIODE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_RE_PLAGE = re.compile(
    r"^(\d{4}-(?:0[1-9]|1[0-2])-\d{2})/(\d{4}-(?:0[1-9]|1[0-2])-\d{2})$")

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


class ObservationTransitoire(MesureAutoInvalide):
    """L'observation est valide mais momentanément inexploitable (horloge, signature).

    Le worker ne doit pas avancer son checkpoint : la mesure sera retentée. ``horloge``
    distingue une horloge producteur en avance (ne jamais dead-letterer) d'une panne
    d'infrastructure (reprises bornées).
    """

    def __init__(self, raison: str, *, horloge: bool = False):
        self.raison = str(raison).strip() or "observation momentanément inexploitable"
        self.horloge = bool(horloge)
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
    maj_le: str
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
    transitoire: bool = False
    horloge: bool = False

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


def _instant(valeur: Any, *, precis: bool = False) -> str | None:
    """ISO UTC (secondes ou microsecondes), ou ``None`` si la valeur est illisible."""
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
    return horodatage.astimezone(timezone.utc).isoformat(
        timespec="microseconds" if precis else "seconds")


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


def _reference(maintenant: Any = None) -> str:
    return _instant(maintenant) or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _quand(document: Mapping[str, Any], maintenant: Any = None) -> str:
    brut = document.get("quand") or document.get("observe_le") or document.get("mesure_le")
    instant = _instant(brut)
    if instant is None:
        raise ObservationIncomplete("quand absent ou illisible")
    if _est_futur(instant, _reference(maintenant)):
        # Une horloge producteur en avance peut se corriger : ne pas perdre la mesure.
        raise ObservationTransitoire("quand dans le futur", horloge=True)
    return instant


def _maj_le(document: Mapping[str, Any], maintenant: Any = None) -> str:
    instant = _instant(document.get("maj_le"), precis=True)
    if instant is None:
        raise ObservationIncomplete("maj_le absent ou illisible")
    if _est_futur(instant, _reference(maintenant)):
        raise ObservationTransitoire("maj_le dans le futur", horloge=True)
    return instant


def _periode(document: Mapping[str, Any], quand: str) -> str:
    explicite = _texte(document.get("periode"))
    if explicite:
        if _RE_PERIODE.fullmatch(explicite):
            return explicite
        plage = _RE_PLAGE.fullmatch(explicite)
        if plage:
            try:
                debut = date.fromisoformat(plage.group(1))
                fin = date.fromisoformat(plage.group(2))
            except ValueError as exc:
                raise ObservationIncomplete(f"periode invalide : {explicite}") from exc
            if debut <= fin:
                return explicite
        raise ObservationIncomplete(
            f"periode invalide : {explicite!r} (attendu AAAA-MM ou AAAA-MM-JJ/AAAA-MM-JJ)")
    # `quand` est déjà normalisé en UTC : la période par défaut est le mois UTC.
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


def _initiative(document: Mapping[str, Any], *, explicite: Any = None) -> tuple[str, str | None]:
    """Lien canonique explicite uniquement : aucune devinette de décision legacy.

    Le producteur fournit soit ``initiative_id``, soit ``decision_id`` (l'identifiant
    d'initiative est alors dérivé exactement comme C1). Une observation projetée depuis la
    veille legacy doit donc embarquer ce lien ; les règles de « dernière décision » ne sont pas
    dupliquées ici.
    """
    candidats = [
        _texte(candidat)
        for candidat in (explicite, document.get("initiative_id"),
                         document.get("initiative_ref"))
        if _texte(candidat)
    ]
    if len(set(candidats)) > 1:
        raise ObservationIncomplete("initiative_id incohérent entre observation et contexte")
    decision_id = _texte(document.get("decision_id") or document.get("decision_ref"))
    if candidats:
        initiative = candidats[0]
        if decision_id and pont.initiative_id(decision_id) != initiative:
            raise ObservationIncomplete(
                "initiative_id incohérent avec decision_id")
        return initiative, decision_id or None
    if decision_id:
        return pont.initiative_id(decision_id), decision_id
    raise ObservationIncomplete(
        "initiative_id ou decision_id explicite requis pour rattacher la mesure")


def _metrique(document: Mapping[str, Any], attendu: Any = None) -> str:
    texte = _texte(document.get("metrique"))
    if texte:
        return texte
    if isinstance(attendu, Mapping):
        cible = _texte(attendu.get("id") or attendu.get("cible_id"))
        if cible:
            # L'identifiant de cible est stable ; l'indicateur reste dans le payload.
            return f"attendu:{cible}"
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
    maj_le = _maj_le(document, maintenant)
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
    valeur_attendue = _valeur_dans(attendu)
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
        maj_le=maj_le,
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


def _normaliser_unite(valeur: Any) -> str:
    return _texte(valeur).casefold()


def _unite_commune(reference: Mapping[str, Any], observation: Mapping[str, Any],
                   role: str) -> str:
    unite_reference = _texte(reference.get("unite"))
    unite_observation = _texte(observation.get("unite"))
    if (unite_reference and unite_observation
            and _normaliser_unite(unite_reference) != _normaliser_unite(unite_observation)):
        raise ObservationIncomplete(
            f"unités incompatibles pour {role} : {unite_reference!r} vs "
            f"{unite_observation!r}")
    unite = unite_reference or unite_observation
    if not unite:
        raise ObservationIncomplete(f"unité absente pour {role}")
    return unite


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
    maj_le = _maj_le(document, maintenant)
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
        indicateur = _texte(attendu_brut.get("indicateur"))
        if not indicateur:
            raise ObservationIncomplete("attendu de veille sans indicateur")
        # La métrique canonique reste stable même si le libellé de l'indicateur change.
        metrique = f"attendu:{cible}"
        valeur = _nombre(observation.get("valeur"))
        if valeur is None:
            raise ObservationIncomplete("valeur observée non numérique pour un attendu")
        depart = _nombre(attendu_brut.get("depart"))
        cible_valeur = _nombre(attendu_brut.get("cible"))
        if depart is None or cible_valeur is None:
            raise ObservationIncomplete("attendu de veille non numérique (départ/cible)")
        sens = _texte(attendu_brut.get("sens")).lower()
        if sens not in {"hausse", "baisse"}:
            raise ObservationIncomplete("sens d'attendu invalide (hausse/baisse requis)")
        unite = _unite_commune(attendu_brut, observation, "attendu")
        attendu = {
            "id": cible,
            "indicateur": indicateur,
            "sens": sens,
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
            f"{indicateur} : {observe_texte} observé, "
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
        sens = _texte(risque.get("sens")).lower()
        if sens not in {"hausse", "baisse"}:
            raise ObservationIncomplete("sens de risque invalide (hausse/baisse requis)")
        unite = _unite_commune(risque, observation, "risque")
        franchi = valeur > seuil if sens == "hausse" else valeur < seuil
        metrique = f"risque:{cible}"
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
        metrique = f"inconnue:{cible}"
        attendu = None
        observe = conclusion
        valeur_observee = conclusion
        valeur_attendue = None
        type_observation = "inconnue"
        interpretation = f"Inconnue levée — {libelle} : {conclusion}"
    else:
        raise ObservationIncomplete(f"cible de veille inconnue : {cible}")

    initiative, decision_id = _initiative(document, explicite=initiative_id)
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
        maj_le=maj_le,
        interpretation=interpretation[:_MAX_INTERPRETATION],
        valeur_attendue=valeur_attendue,
        valeur_observee=valeur_observee,
        type_observation=type_observation,
        decision_id=decision_id,
    )


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def _verifier_taille(observation: ObservationMesure) -> None:
    payload = outcome_depuis_observation(observation)
    taille = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
    if taille > _MAX_SERIALISE:
        raise ObservationIncomplete(
            f"observation trop volumineuse ({taille} octets > {_MAX_SERIALISE})")


def normaliser_observation(document: Any, *, tenant_id: Any = None,
                           initiative_id: Any = None,
                           maintenant: Any = None) -> ObservationMesure:
    """Normalise une observation ou lève :class:`ObservationIncomplete`.

    Une observation valide mais momentanément inexploitable (``quand`` futur) lève
    :class:`ObservationTransitoire` : le worker ne doit pas avancer son checkpoint.
    """
    if not isinstance(document, Mapping):
        raise ObservationIncomplete("observation absente : document attendu")
    if _est_observation_veille(document):
        observation = _normaliser_veille(
            document, tenant_id=tenant_id, initiative_id=initiative_id,
            maintenant=maintenant)
    else:
        observation = _normaliser_generique(
            document, tenant_id=tenant_id, initiative_id=initiative_id,
            maintenant=maintenant)
    _verifier_taille(observation)
    return observation


def outcome_depuis_observation(observation: ObservationMesure) -> dict[str, Any]:
    """Payload C1 complet de l'Outcome (attendu, observé, effets, période, ingestion)."""
    return {
        "initiative_id": observation.initiative_id,
        "mesure": observation.mesure,
        "metrique": observation.metrique,
        "periode": observation.periode,
        "valeur_attendue": observation.valeur_attendue,
        "interpretation": observation.interpretation,
        "mesure_le": observation.mesure_le,
        "maj_le": observation.maj_le,
        "decision_id": observation.decision_id,
        "effets_secondaires": list(observation.effets_secondaires),
    }


def empreinte_observation(observation: ObservationMesure) -> str:
    """Empreinte du payload complet : toute correction change l'identifiant d'événement."""
    return pont.hash_contenu(outcome_depuis_observation(observation))[:16]


def evenement_depuis_observation(observation: ObservationMesure, *,
                                 maintenant: Any = None) -> dict[str, Any]:
    """Événement d'outbox C1 signé, d'origine ``exploitation``."""
    payload = outcome_depuis_observation(observation)
    return pont.evenement_outcome(
        tenant_id=observation.tenant_id,
        initiative_id=payload["initiative_id"],
        mesure=payload["mesure"],
        metrique=payload["metrique"],
        periode=payload["periode"],
        valeur_attendue=payload["valeur_attendue"],
        interpretation=payload["interpretation"],
        mesure_le=payload["mesure_le"],
        maj_le=payload["maj_le"],
        decision_id=payload["decision_id"],
        effets_secondaires=payload["effets_secondaires"],
        origine=pont.ORIGINE_EXPLOITATION,
        source_event_id=(
            f"mesure-auto:{observation.type_observation}:{observation.observation_id}:"
            f"{empreinte_observation(observation)}"
        ),
        maintenant=maintenant,
    )


def _classer_erreur_pont(exc: BaseException) -> tuple[bool, bool]:
    """Rend ``(transitoire, horloge)`` pour une erreur du pont C1.

    Une signature indisponible est environnementale (transitoire, pas horloge). Un
    ``source_maj_le`` futur est une horloge en avance : il ne doit jamais être dead-letteré.
    """
    if isinstance(exc, pont.SignatureInvalide):
        return True, False
    message = str(exc).lower()
    horloge = any(mot in message for mot in ("futur", "future", "horloge"))
    return (horloge or "signature" in message), horloge


def mesurer_observation(document: Any, *, tenant_id: Any = None,
                        initiative_id: Any = None,
                        maintenant: Any = None) -> ResultatMesure:
    """Produit un Outcome si l'observation est complète, sinon expose la raison du refus."""
    try:
        observation = normaliser_observation(
            document, tenant_id=tenant_id, initiative_id=initiative_id,
            maintenant=maintenant)
    except ObservationTransitoire as exc:
        return ResultatMesure(
            raison=exc.raison, transitoire=True, horloge=exc.horloge)
    except ObservationIncomplete as exc:
        return ResultatMesure(raison=exc.raison)
    except pont.PontInvalide as exc:
        return ResultatMesure(raison=str(exc))
    except Exception as exc:  # noqa: BLE001 - dead-letter, jamais de blocage silencieux
        return ResultatMesure(
            raison=f"erreur inattendue : {type(exc).__name__} : {exc}")
    try:
        evenement = evenement_depuis_observation(observation, maintenant=maintenant)
    except pont.SignatureInvalide as exc:
        return ResultatMesure(mesure=observation, raison=str(exc), transitoire=True)
    except pont.PontInvalide as exc:
        transitoire, horloge = _classer_erreur_pont(exc)
        return ResultatMesure(
            mesure=observation, raison=str(exc),
            transitoire=transitoire, horloge=horloge)
    except Exception as exc:  # noqa: BLE001 - dead-letter, jamais de blocage silencieux
        return ResultatMesure(
            mesure=observation,
            raison=f"erreur inattendue : {type(exc).__name__} : {exc}")
    return ResultatMesure(mesure=observation, evenement=evenement)
