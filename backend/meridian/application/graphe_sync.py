"""Synchronisation canonique des Twins et relations vers le `GraphStore`.

Postgres reste propriétaire de l'identité, des Claims et des preuves ; le graphe possède la topologie. Ce module ne
lit ni Postgres ni Mongo et n'ouvre aucune connexion : il traduit des documents déjà chargés en modèles du port
`meridian.domain.graphe`, puis délègue les écritures au store injecté.

Le mapping est volontairement pauvre :

- un Twin ne porte que son id, son type, son label et quelques propriétés d'affichage (mission, domaine, équipe,
  statut) ; les Claims et les preuves restent dans Postgres ;
- une relation ne porte que ses extrémités, son type, son état, sa confiance, sa période de validité et des
  `preuve_ids` — jamais le contenu des preuves.

Limites assumées :

- l'id d'un Twin et d'une relation est obligatoire : il porte l'idempotence, on ne l'invente pas ;
- une relation dont une extrémité n'existe ni dans le lot de Twins ni déjà dans le store est ignorée, jamais
  écrite ;
- une relation Mongo marquée `active: false` sans date de fermeture est fermée avec le sentinelle `inactive` ;
- `synchroniser` ne supprime rien : une relation retirée du lot reste dans le store (`reconcilier` la signale
  seulement si elle pointe vers un Twin absent) ;
- en `dry_run`, le rapport compte ce qui aurait été écrit, mais aucune méthode d'écriture du store n'est appelée.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime

from meridian.domain.graphe import ETATS_RELATION, TYPES_TWIN, Arete, NoeudTwin

CHAMPS_TWIN_MINIMAUX = ("mission", "domaine", "equipe", "statut")
VALID_TO_INACTIF = "inactive"

_CLES_ID_TWIN = ("id", "twin_id", "jumeau_id")
_CLES_ID_RELATION = ("id", "relation_id")
_CLES_SOURCE = ("source", "source_id", "sujet_id", "de_id")
_CLES_TARGET = ("target", "target_id", "cible", "cible_id", "objet_id", "vers_id")
_CLES_TYPE_RELATION = ("type", "predicat", "predicate")
_CLES_ETAT = ("etat", "état", "state", "statut")
_CLES_VALID_FROM = ("valid_from", "valide_depuis", "decouverte_quand")
_CLES_VALID_TO = ("valid_to", "valide_jusqua", "fin_validite", "desactivee_quand", "obsolete_depuis")
_CLES_PREUVES = ("preuve_ids", "evidence_ids", "preuves")

_ETATS_ALIAS = {
    "suppose": "supposee",
    "proposee": "supposee",
    "proposed": "supposee",
    "observe": "observee",
    "observed": "observee",
    "en_validation": "validation",
    "under_review": "validation",
    "confirme": "confirmee",
    "confirmed": "confirmee",
    "conteste": "contestee",
    "contested": "contestee",
    "deprecated": "obsolete",
    "obsolescente": "obsolete",
}
_RE_TYPE_RELATION = re.compile(r"^[^\W_][\w .:+/'-]{0,63}$", re.UNICODE)


def _texte(valeur, champ, obligatoire=True):
    texte = str(valeur or "").strip()
    if obligatoire and not texte:
        raise ValueError(f"{champ} vide")
    return texte


def _sans_accents(texte):
    decompose = unicodedata.normalize("NFKD", str(texte or ""))
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _premier(objet, cles):
    for cle in cles:
        valeur = objet.get(cle)
        if valeur is not None and str(valeur).strip():
            return str(valeur).strip()
    return ""


def _optionnel(valeur):
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def _date_iso(valeur):
    """Une période du graphe est ISO ou absente : un libellé comme « il y a 8 mois » n'est pas une date."""
    texte = _optionnel(valeur)
    if texte is None or texte == VALID_TO_INACTIF:
        return texte
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    try:
        datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return texte


def _identifiant_brut(objet, position, relation=False):
    if isinstance(objet, Mapping):
        cles = _CLES_ID_RELATION if relation else _CLES_ID_TWIN
        identifiant = _premier(objet, cles)
        if identifiant:
            return identifiant
    return f"#{position}"


def _verifier_tenant(objet, tenant, nature, identifiant):
    declare = str(objet.get("tenant_id") or "").strip()
    if declare and declare != tenant:
        raise PermissionError(f"{nature} {identifiant} appartient à un autre tenant")


def _type_twin(valeur):
    texte = _sans_accents(_texte(valeur or "APPLICATION", "type")).upper()
    if texte not in TYPES_TWIN:
        raise ValueError(f"type de Twin inconnu : {valeur}")
    return texte


def _type_relation(valeur):
    texte = _texte(valeur or "structurante", "type")
    if not _RE_TYPE_RELATION.fullmatch(texte):
        raise ValueError("type de relation invalide")
    return texte


def _etat_relation(valeur):
    texte = _sans_accents(_texte(valeur or "supposee", "etat")).lower().replace(" ", "_")
    texte = _ETATS_ALIAS.get(texte, texte)
    if texte not in ETATS_RELATION:
        raise ValueError(f"état de relation inconnu : {valeur}")
    return texte


def _preuve_ids(relation):
    brut = next((relation.get(cle) for cle in _CLES_PREUVES if relation.get(cle) is not None), None)
    if brut is None:
        return ()
    if isinstance(brut, Mapping):
        brut = [brut]
    elif isinstance(brut, (str, bytes)):
        brut = [brut]
    identifiants = []
    for element in brut:
        valeur = element
        if isinstance(element, Mapping):
            valeur = element.get("id") or element.get("preuve_id") or element.get("evidence_id")
        texte = str(valeur or "").strip()
        if texte and texte not in identifiants:
            identifiants.append(texte)
    return tuple(identifiants)


def twin_depuis_identite(tenant_id, twin: dict) -> NoeudTwin:
    """Traduit l'identité Postgres d'un Twin en nœud du graphe, sans copier sa fiche."""
    tenant = _texte(tenant_id, "tenant_id")
    if not isinstance(twin, Mapping):
        raise ValueError("twin : objet attendu")
    identifiant = _texte(_premier(twin, _CLES_ID_TWIN), "id")
    _verifier_tenant(twin, tenant, "twin", identifiant)
    proprietes = {}
    for champ in CHAMPS_TWIN_MINIMAUX:
        valeur = twin.get(champ)
        if valeur not in (None, "", [], {}):
            proprietes[champ] = valeur
    return NoeudTwin(
        id=identifiant,
        tenant_id=tenant,
        type=_type_twin(twin.get("type") or twin.get("type_twin")),
        label=_texte(twin.get("label") or twin.get("nom") or twin.get("name") or identifiant, "label"),
        proprietes=proprietes,
    )


def arete_depuis_relation(tenant_id, relation: dict) -> Arete:
    """Traduit une relation Mongo legacy (ou un lien du modèle Entreprise) en arête du graphe."""
    tenant = _texte(tenant_id, "tenant_id")
    if not isinstance(relation, Mapping):
        raise ValueError("relation : objet attendu")
    identifiant = _texte(_premier(relation, _CLES_ID_RELATION), "id")
    _verifier_tenant(relation, tenant, "relation", identifiant)

    confiance = relation.get("confiance", relation.get("confidence"))
    try:
        confiance = 0.5 if confiance in (None, "") else float(confiance)
    except (TypeError, ValueError) as exc:
        raise ValueError("confiance invalide") from exc
    if 1 < confiance <= 100:
        confiance /= 100

    valid_from = _date_iso(_premier(relation, _CLES_VALID_FROM))
    valid_to = _date_iso(_premier(relation, _CLES_VALID_TO))
    if valid_to is None and relation.get("active") is False:
        valid_to = VALID_TO_INACTIF

    return Arete(
        id=identifiant,
        tenant_id=tenant,
        source=_premier(relation, _CLES_SOURCE),
        target=_premier(relation, _CLES_TARGET),
        type=_type_relation(_premier(relation, _CLES_TYPE_RELATION)),
        etat=_etat_relation(_premier(relation, _CLES_ETAT)),
        confiance=confiance,
        valid_from=valid_from,
        valid_to=valid_to,
        preuve_ids=_preuve_ids(relation),
    )


def _twins_presents(store, tenant_id):
    """Lit les Twins déjà présents quand l'adaptateur expose un audit ; sinon le lot courant fait foi."""
    noeuds = getattr(store, "noeuds", None)
    if isinstance(noeuds, Mapping):
        return {
            str(noeud.id)
            for noeud in noeuds.values()
            if getattr(noeud, "tenant_id", None) == tenant_id
        }
    as_dict = getattr(store, "as_dict", None)
    if callable(as_dict):
        try:
            etat = as_dict(tenant_id)
        except Exception:
            return set()
        if isinstance(etat, Mapping):
            return {
                str(noeud.get("id"))
                for noeud in etat.get("noeuds") or []
                if isinstance(noeud, Mapping) and noeud.get("id")
            }
    return set()


def _erreur(nature, identifiant, exc):
    return {"type": nature, "id": identifiant, "raison": str(exc)}


def _preparer_twins(tenant_id, twins):
    noeuds, erreurs = [], []
    for position, twin in enumerate(twins or []):
        try:
            noeuds.append(twin_depuis_identite(tenant_id, twin))
        except Exception as exc:
            erreurs.append(_erreur("twin", _identifiant_brut(twin, position), exc))
    return noeuds, erreurs


def _absents(arete, connus):
    return [extremite for extremite in dict.fromkeys((arete.source, arete.target)) if extremite not in connus]


def synchroniser(store, tenant_id, twins, relations, dry_run=False) -> dict:
    """Upsert idempotent : Twins d'abord, relations ensuite, sans jamais supprimer ni écrire une arête orpheline."""
    tenant = _texte(tenant_id, "tenant_id")
    if store is None:
        raise ValueError("store attendu")
    rapport = {"twins": 0, "relations": 0, "ignores": [], "erreurs": []}

    noeuds, erreurs = _preparer_twins(tenant, twins)
    rapport["erreurs"].extend(erreurs)
    connus = _twins_presents(store, tenant)
    for noeud in noeuds:
        try:
            if not dry_run:
                store.upsert_twin(noeud)
            connus.add(noeud.id)
            rapport["twins"] += 1
        except Exception as exc:
            rapport["erreurs"].append(_erreur("twin", noeud.id, exc))

    for position, relation in enumerate(relations or []):
        identifiant = _identifiant_brut(relation, position, relation=True)
        try:
            arete = arete_depuis_relation(tenant, relation)
        except Exception as exc:
            rapport["erreurs"].append(_erreur("relation", identifiant, exc))
            continue
        absents = _absents(arete, connus)
        if absents:
            rapport["ignores"].append({
                "type": "relation",
                "id": arete.id,
                "raison": "Twin absent du graphe",
                "absents": absents,
            })
            continue
        try:
            if not dry_run:
                store.upsert_relation(arete)
            rapport["relations"] += 1
        except Exception as exc:
            rapport["erreurs"].append(_erreur("relation", arete.id, exc))

    return rapport


def reconcilier(store, tenant_id, twins, relations) -> dict:
    """Détecte les relations qui pointent vers un Twin absent, sans rien écrire dans le store."""
    tenant = _texte(tenant_id, "tenant_id")
    if store is None:
        raise ValueError("store attendu")
    noeuds, erreurs = _preparer_twins(tenant, twins)
    connus = _twins_presents(store, tenant) | {noeud.id for noeud in noeuds}
    ecarts = []
    relations_lues = 0
    for position, relation in enumerate(relations or []):
        try:
            arete = arete_depuis_relation(tenant, relation)
        except Exception as exc:
            erreurs.append(_erreur("relation", _identifiant_brut(relation, position, relation=True), exc))
            continue
        relations_lues += 1
        absents = _absents(arete, connus)
        if absents:
            ecarts.append({
                "type": "relation",
                "id": arete.id,
                "raison": "Twin absent du graphe",
                "absents": absents,
            })
    return {
        "tenant_id": tenant,
        "twins": len({noeud.id for noeud in noeuds}),
        "relations": relations_lues,
        "ecarts": ecarts,
        "erreurs": erreurs,
    }


def ecarts(store, tenant_id, twins, relations) -> list[dict]:
    """Raccourci de `reconcilier` : rend seulement la liste des relations orphelines."""
    return reconcilier(store, tenant_id, twins, relations)["ecarts"]
