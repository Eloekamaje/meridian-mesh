"""Vue transverse de fédération : projection autorisée de plusieurs Twins.

La vue ne crée pas de Twin, ne copie aucun Claim et n'accède ni à la base, ni au réseau,
ni à un LLM. Elle consolide les entités par identifiant canonique et conserve les références
locales aux Claims, les sources non visibles, les inconnues et les contradictions.

Une source absente de l'ACL est traitée comme non visible (fail-closed). Une source non
visible est exposée avec l'état ``non_visible`` et jamais comme absente.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

__all__ = [
    "FederationInvalide",
    "FederationRefusee",
    "PREDICATS_MULTIVALUES",
    "VueTransverse",
]

PREDICATS_MULTIVALUES = frozenset({
    "APPLICATION_DEPEND_DE_RESSOURCE",
    "CHANGEMENT_IMPACTE",
    "CONTRAT_COUVRE",
    "CONTRAINTE_S_APPLIQUE",
    "DECISION_PRISE",
    "DEPEND_DE",
    "ECHANGE_AVEC",
    "EQUIPE_EST_ACCOUNTABLE_DE",
    "EQUIPE_EST_RESPONSABLE_DE",
    "EXPOSE",
    "INCIDENT_AFFECTE",
    "REALISE_CAPACITE",
    "RESOURCE_SUPPORTE_APPLICATION",
    "SERVICE_RENDU_PAR",
})

_CATEGORIES = (
    (
        ("ressources", "resources", "resource"),
        "RESOURCE",
        ("id_canonique", "identifiant_canonique", "resource_id", "ressource_id", "cmdb_id", "ci", "id"),
    ),
    (
        ("applications", "apps", "application"),
        "APPLICATION",
        ("id_canonique", "identifiant_canonique", "application_id", "app_id", "id"),
    ),
    (
        ("fournisseurs", "suppliers", "supplier"),
        "SUPPLIER",
        ("id_canonique", "identifiant_canonique", "supplier_id", "fournisseur_id", "id"),
    ),
    (
        ("equipes", "teams", "team"),
        "TEAM",
        ("id_canonique", "identifiant_canonique", "team_id", "equipe_id", "id"),
    ),
)

_SOURCES_VISIBLES = (
    "sources_visibles",
    "sources_autorisees",
    "sources_autorises",
    "sources_permises",
    "visible",
    "visibles",
    "autorisees",
    "autorises",
    "allowed",
)
_SOURCES_CACHEES = (
    "sources_non_visibles",
    "sources_cachees",
    "sources_refusees",
    "sources_interdites",
    "non_visibles",
    "cachees",
    "refusees",
    "interdites",
    "denied",
)
_SOURCES_LISTE = ("sources", "acls", "acces")
_CLES_ACL = frozenset(_SOURCES_VISIBLES + _SOURCES_CACHEES + _SOURCES_LISTE)


class FederationInvalide(ValueError):
    """Entrée de fédération incohérente ou incomplète."""


class FederationRefusee(PermissionError):
    """Twin hors du tenant ou de l'espace autorisé."""


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _optionnel(valeur: Any) -> str | None:
    texte = _texte(valeur)
    return texte or None


def _valeur(objet: Any, *noms: str, defaut: Any = None) -> Any:
    for nom in noms:
        if isinstance(objet, Mapping):
            if nom in objet and objet[nom] is not None:
                return objet[nom]
        else:
            valeur = getattr(objet, nom, None)
            if valeur is not None:
                return valeur
    return defaut


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, Mapping):
        return [valeur]
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _canonique(record: Any) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _trier(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uniques = {_canonique(record): record for record in records}
    return [uniques[cle] for cle in sorted(uniques)]


def _identifiant(brut: Any, champs: tuple[str, ...]) -> str:
    for champ in champs:
        identifiant = _texte(_valeur(brut, champ))
        if identifiant:
            return identifiant
    identifiants = _valeur(brut, "identifiants", "identifiers")
    if isinstance(identifiants, Mapping):
        for champ in champs:
            identifiant = _texte(identifiants.get(champ))
            if identifiant:
                return identifiant
    return ""


def _nom(brut: Any) -> str | None:
    return _optionnel(_valeur(brut, "nom", "name", "label", "libelle"))


def _source_id(valeur: Any) -> str | None:
    if isinstance(valeur, Mapping):
        return _optionnel(_valeur(valeur, "source_id", "id", "nom", "source"))
    return _optionnel(valeur)


def _source_entite(brut: Any) -> str | None:
    return _source_id(_valeur(brut, "source_id", "source", "provenance"))


def _source_claim(brut: Any) -> str | None:
    return _source_id(_valeur(brut, "source_id", "source", "provenance", "preuve_source"))


def _etat_acl(valeur: Any) -> str:
    if isinstance(valeur, Mapping):
        for nom in ("etat", "statut", "visible", "autorise", "allowed", "acces"):
            if nom in valeur:
                return _etat_acl(valeur[nom])
        return "non_visible"
    if isinstance(valeur, bool):
        return "visible" if valeur else "non_visible"
    texte = _texte(valeur).lower()
    if texte in {
        "visible", "visibles", "autorise", "autorisé", "autorisee", "autorisée",
        "allowed", "true", "1", "oui", "yes", "ok", "lecture",
    }:
        return "visible"
    return "non_visible"


def _ajouter_acl(valeur: Any, visibles: set[str], cachees: set[str], defaut: str) -> None:
    if isinstance(valeur, Mapping):
        descripteur = any(
            nom in valeur
            for nom in ("id", "source_id", "source", "nom", "etat", "statut", "visible", "autorise", "allowed")
        )
        if descripteur:
            identifiant = _source_id(valeur)
            if identifiant:
                etat = _etat_acl(_valeur(valeur, "etat", "statut", "visible", "autorise", "allowed", defaut=defaut))
                (visibles if etat == "visible" else cachees).add(identifiant)
            return
        for cle, etat in valeur.items():
            identifiant = _texte(cle)
            if not identifiant:
                continue
            (visibles if _etat_acl(etat) == "visible" else cachees).add(identifiant)
        return
    for item in _liste(valeur):
        if isinstance(item, Mapping):
            _ajouter_acl(item, visibles, cachees, defaut)
            continue
        identifiant = _source_id(item)
        if identifiant:
            (visibles if defaut == "visible" else cachees).add(identifiant)


def _acl(twin: Any) -> tuple[set[str], set[str]]:
    acl = _valeur(twin, "acl", "acls", "acces")
    visibles: set[str] = set()
    cachees: set[str] = set()
    if acl is None:
        return visibles, cachees
    if isinstance(acl, Mapping):
        for nom in _SOURCES_VISIBLES:
            if nom in acl:
                _ajouter_acl(acl[nom], visibles, cachees, "visible")
        for nom in _SOURCES_CACHEES:
            if nom in acl:
                _ajouter_acl(acl[nom], visibles, cachees, "non_visible")
        for nom in _SOURCES_LISTE:
            if nom in acl:
                _ajouter_acl(acl[nom], visibles, cachees, "visible")
        for cle, valeur in acl.items():
            if cle in _CLES_ACL:
                continue
            identifiant = _texte(cle)
            if not identifiant:
                continue
            (visibles if _etat_acl(valeur) == "visible" else cachees).add(identifiant)
    else:
        _ajouter_acl(acl, visibles, cachees, "visible")
    return visibles - cachees, cachees


def _entites_categorie(twin: Any, cles: tuple[str, ...]) -> list[Any]:
    resultat: list[Any] = []
    for cle in cles:
        resultat.extend(_liste(_valeur(twin, cle)))
    return resultat


def _sources_declarees(twin: Any) -> set[str]:
    sources: set[str] = set()
    for cles, _type, _champs in _CATEGORIES:
        for brut in _entites_categorie(twin, cles):
            source = _source_entite(brut)
            if source:
                sources.add(source)
    for brut in _liste(_valeur(twin, "claims", "claims_locaux")):
        source = _source_claim(brut)
        if source:
            sources.add(source)
    return sources


def _normaliser_twins(twins: Any) -> list[Any]:
    if twins is None:
        return []
    if isinstance(twins, Mapping):
        cles_twin = ("twin_id", "jumeau_id", "tenant_id", "ressources", "applications",
                     "fournisseurs", "equipes", "claims", "acl")
        if any(cle in twins for cle in cles_twin):
            return [twins]
        resultat = []
        for cle, twin in twins.items():
            if isinstance(twin, Mapping):
                copie = dict(twin)
                if not _texte(_valeur(copie, "twin_id", "jumeau_id")):
                    copie["twin_id"] = _texte(cle)
                resultat.append(copie)
            else:
                resultat.append(twin)
        return resultat
    if isinstance(twins, (str, bytes)):
        raise FederationInvalide("twins doit être une collection de Twins")
    return list(twins)


class VueTransverse:
    """Fusion pure de Twins autorisés, sans copie de Claims ni accès externe."""

    def __init__(
        self,
        twins: Any = None,
        tenant_id: str | None = None,
        *,
        tenant: str | None = None,
        espace: str | None = None,
        predicats_fonctionnels: Any = None,
    ) -> None:
        if isinstance(twins, str) and tenant_id is not None and not isinstance(tenant_id, str):
            twins, tenant_id = tenant_id, twins
        tenant_id = _texte(tenant_id if tenant_id is not None else tenant)
        if not tenant_id:
            raise FederationInvalide("tenant_id obligatoire")
        espace = _optionnel(espace)
        self._predicats_fonctionnels = frozenset(
            _texte(valeur).upper() for valeur in _liste(predicats_fonctionnels)
        )
        self._vue = self._construire(twins, tenant_id, espace)

    def _construire(self, twins: Any, tenant_id: str, espace: str | None) -> dict[str, Any]:
        normalises: list[tuple[str, Any]] = []
        vus: set[str] = set()
        for position, twin in enumerate(_normaliser_twins(twins)):
            twin_id = _texte(_valeur(twin, "twin_id", "jumeau_id", "id"))
            if not twin_id:
                raise FederationInvalide(f"Twin sans twin_id à la position {position}")
            if twin_id in vus:
                raise FederationInvalide(f"twin_id en double : {twin_id}")
            vus.add(twin_id)
            twin_tenant = _texte(_valeur(twin, "tenant_id", "tenant"))
            if twin_tenant != tenant_id:
                raise FederationRefusee(f"Twin {twin_id!r} hors du tenant {tenant_id!r}")
            twin_espace = _optionnel(_valeur(twin, "espace", "space"))
            if espace is not None and twin_espace != espace:
                raise FederationRefusee(f"Twin {twin_id!r} hors de l'espace {espace!r}")
            normalises.append((twin_id, twin))
        normalises.sort(key=lambda item: item[0])

        entites: dict[tuple[str, str], dict[str, Any]] = {}
        index_ids: dict[str, set[tuple[str, str]]] = {}
        refs_par_entite: dict[tuple[str, str], set[tuple[str, str, str | None]]] = {}
        claims_refs: list[dict[str, Any]] = []
        claims_visibles: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        sources_non_visibles: list[dict[str, Any]] = []
        inconnues: list[dict[str, Any]] = []

        for twin_id, twin in normalises:
            visibles, cachees = _acl(twin)
            univers = _sources_declarees(twin) | visibles | cachees
            for source in sorted(univers):
                etat = "visible" if source in visibles else "non_visible"
                entree = {"twin_id": twin_id, "source_id": source, "etat": etat}
                provenance.append(entree)
                if etat == "non_visible":
                    sources_non_visibles.append(entree)

            for cles, type_entite, champs in _CATEGORIES:
                for brut in _entites_categorie(twin, cles):
                    source = _source_entite(brut)
                    if source and source not in visibles:
                        continue
                    identifiant = _identifiant(brut, champs)
                    nom = _nom(brut)
                    if not identifiant:
                        inconnues.append({
                            "type": type_entite,
                            "raison": "identifiant_canonique_absent",
                            "twin_id": twin_id,
                            "nom": nom,
                            "source_id": source,
                        })
                        continue
                    cle = (type_entite, identifiant)
                    entree = entites.setdefault(cle, {
                        "id": identifiant,
                        "type": type_entite,
                        "noms": set(),
                        "provenance": set(),
                        "sources": set(),
                    })
                    if nom:
                        entree["noms"].add(nom)
                    entree["provenance"].add((twin_id, source))
                    if source:
                        entree["sources"].add(source)
                    index_ids.setdefault(identifiant, set()).add(cle)

            claims_twin: set[str] = set()
            for brut in _liste(_valeur(twin, "claims", "claims_locaux")):
                source = _source_claim(brut)
                if source and source not in visibles:
                    continue
                claim_id = _optionnel(_valeur(brut, "claim_id", "id"))
                if not claim_id:
                    inconnues.append({
                        "type": "CLAIM",
                        "raison": "identifiant_claim_absent",
                        "twin_id": twin_id,
                        "source_id": source,
                    })
                    continue
                if claim_id in claims_twin:
                    raise FederationInvalide(f"claim_id en double dans {twin_id!r} : {claim_id}")
                claims_twin.add(claim_id)
                sujet = _texte(_valeur(brut, "sujet", "subject", "sujet_id", "de_id"))
                predicat = _texte(_valeur(brut, "predicat", "predicate", "type"))
                objet = _texte(_valeur(brut, "objet", "object", "objet_id", "cible"))
                if not sujet or not predicat or not objet:
                    raise FederationInvalide(f"Claim incomplet dans {twin_id!r} : {claim_id}")
                fonctionnel = bool(_valeur(brut, "fonctionnel", "functional", "unique", defaut=False))
                reference = {"claim_id": claim_id, "twin_id": twin_id, "source_id": source}
                claims_refs.append(reference)
                claims_visibles.append({
                    **reference,
                    "sujet": sujet,
                    "predicat": predicat.upper(),
                    "objet": objet,
                    "fonctionnel": fonctionnel,
                })

        for claim in claims_visibles:
            reference = {
                "claim_id": claim["claim_id"],
                "twin_id": claim["twin_id"],
                "source_id": claim["source_id"],
            }
            for role, valeur in (("sujet", claim["sujet"]), ("objet", claim["objet"])):
                cibles = index_ids.get(valeur, set())
                if not cibles:
                    inconnues.append({
                        "type": "REFERENCE",
                        "raison": f"{role}_non_resolu",
                        "role": role,
                        "valeur": valeur,
                        "twin_id": claim["twin_id"],
                        "claim_id": claim["claim_id"],
                    })
                for cle in cibles:
                    refs_par_entite.setdefault(cle, set()).add(
                        (claim["twin_id"], claim["claim_id"], claim["source_id"])
                    )

        contradictions: list[dict[str, Any]] = []
        for sens, cle_ancre, cle_valeur in (
            ("sujet_commun", "sujet", "objet"),
            ("objet_commun", "objet", "sujet"),
        ):
            groupes: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for claim in claims_visibles:
                predicat = claim["predicat"]
                fonctionnel = (
                    claim["fonctionnel"]
                    or predicat in self._predicats_fonctionnels
                    or predicat not in PREDICATS_MULTIVALUES
                )
                if not fonctionnel:
                    continue
                groupes.setdefault((claim[cle_ancre], predicat), []).append(claim)
            for (ancre, predicat), groupe in groupes.items():
                valeurs = sorted({claim[cle_valeur] for claim in groupe})
                if len(valeurs) < 2:
                    continue
                refs = sorted(
                    {
                        (claim["twin_id"], claim["claim_id"], claim["source_id"])
                        for claim in groupe
                    },
                    key=lambda item: (_texte(item[0]), _texte(item[1]), _texte(item[2])),
                )
                contradictions.append({
                    "predicat": predicat,
                    "sens": sens,
                    "ancre": ancre,
                    "valeurs": valeurs,
                    "claims": [
                        {"twin_id": twin_id, "claim_id": claim_id, "source_id": source}
                        for twin_id, claim_id, source in refs
                    ],
                })

        entites_finales = []
        for cle, entree in entites.items():
            refs = sorted(
                refs_par_entite.get(cle, set()),
                key=lambda item: (_texte(item[0]), _texte(item[1]), _texte(item[2])),
            )
            provenance_entite = sorted(
                entree["provenance"],
                key=lambda item: (_texte(item[0]), _texte(item[1])),
            )
            entites_finales.append({
                "id": entree["id"],
                "type": entree["type"],
                "noms": sorted(entree["noms"]),
                "provenance": [
                    {"twin_id": twin_id, "source_id": source}
                    for twin_id, source in provenance_entite
                ],
                "sources": sorted(entree["sources"]),
                "claims_locaux": [
                    {"twin_id": twin_id, "claim_id": claim_id, "source_id": source}
                    for twin_id, claim_id, source in refs
                ],
            })

        return {
            "tenant_id": tenant_id,
            "espace": espace,
            "entites": _trier(entites_finales),
            "provenance": _trier(provenance),
            "claims_locaux": _trier(claims_refs),
            "sources_non_visibles": _trier(sources_non_visibles),
            "inconnues": _trier(inconnues),
            "contradictions": _trier(contradictions),
        }

    def vue(self) -> dict[str, Any]:
        """Copie indépendante de la projection consolidée."""
        return copy.deepcopy(self._vue)

    def vers_dict(self) -> dict[str, Any]:
        return self.vue()

    def as_dict(self) -> dict[str, Any]:
        return self.vue()

    def to_dict(self) -> dict[str, Any]:
        return self.vue()

    def vers_json(self, *, indent: int | None = None) -> str:
        return json.dumps(
            self._vue,
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
            separators=(",", ":") if indent is None else None,
        )

    def to_json(self, *, indent: int | None = None) -> str:
        return self.vers_json(indent=indent)

    def json(self, *, indent: int | None = None) -> str:
        return self.vers_json(indent=indent)

    @property
    def tenant_id(self) -> str:
        return self._vue["tenant_id"]

    @property
    def espace(self) -> str | None:
        return self._vue["espace"]

    @property
    def entites(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._vue["entites"])

    @property
    def provenance(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._vue["provenance"])

    @property
    def claims_locaux(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._vue["claims_locaux"])

    @property
    def sources_non_visibles(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._vue["sources_non_visibles"])

    @property
    def inconnues(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._vue["inconnues"])

    @property
    def contradictions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._vue["contradictions"])
