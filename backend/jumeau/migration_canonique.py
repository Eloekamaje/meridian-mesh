"""Migration contrôlée Mongo → canonique, sans suppression ni double canonique.

Ce module prépare et effectue un backfill rejouable des collections Mongo historiques vers les deux stores
canoniques :

- `situations` et `initiatives` deviennent des objets `objet_entreprise` (familles `emergence` et `decision`) ;
- `jumeaux` et `relations` alimentent la topologie du `GraphStore` via les mapping de `jumeau.graphe_sync`.

Les fonctions de mapping sont pures, testables et volontairement pauvres : elles ne copient que des champs
d'affichage, normalisent ids, dates et statuts, retirent les clés sensibles et ne déduisent aucun lien. Un lien
n'existe que s'il est déclaré dans le document source.

`inspecter` lit une interface Mongo injectée, ne supprime jamais rien et écrit un rapport stable
`{tenant, dry_run, situations, initiatives, relations, ignores, erreurs}`. En dry-run, aucune méthode d'écriture
n'est appelée. En mode réel, les objets sont upsertés par `(tenant_id, id)` et les arêtes par `(tenant_id, id)`,
ce qui rend le backfill rejouable.

Limites assumées :

- les documents `cases` ne sont pas projetés dans ce lot : leur forme de travail n'a pas d'équivalent canonique
  direct et les convertir inventerait une sémantique ;
- une relation dont une extrémité n'existe ni dans `jumeaux` ni déjà dans le store est comptée comme orpheline,
  jamais écrite ;
- la version source, quand elle existe, est conservée ; sinon la version canonique reste `1` pour qu'un second
  passage ne fasse pas monter les versions ;
- aucune collection Mongo n'est modifiée : le backfill est strictement en lecture sur le legacy.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import inspect
import math
import unicodedata
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from jumeau import entreprise_depot
from jumeau.graphe_sync import arete_depuis_relation, twin_depuis_identite

__all__ = [
    "DocumentInvalide",
    "objet_depuis_situation",
    "objet_depuis_initiative",
    "twin_depuis_jumeau",
    "relations_vers_graphe",
    "inspecter",
]

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})

_CHAMPS_SITUATION = (
    "resume", "description", "question", "nature", "verbe", "score", "detectee", "indicateurs",
    "decouverte_quoi", "decouverte_pourquoi", "reste_a_comprendre", "decisions_attendues",
    "chronologie", "hypotheses", "contributions", "preuves", "synthese", "actions_proposees",
    "opportunite", "decision", "relation_id",
)
_CHAMPS_INITIATIVE = (
    "niveau", "genre", "declencheur", "raison", "quand", "periode", "perimetre", "preuves",
    "confiance", "impact", "destinataire", "pourquoi_vous", "attendu", "travail_titre", "options",
    "autonomie", "interruption", "reponse",
)
_CHAMPS_LIEN_INITIATIVE = (
    "travail_id", "jumeau_cible", "decision_id", "decision_ref", "situation_id", "investigation_id",
    "case_id",
)
_CHAMPS_RELATION = (
    "id", "relation_id", "tenant_id", "source", "source_id", "sujet_id", "de_id", "cible", "cible_id",
    "target", "target_id", "objet_id", "vers_id", "type", "predicat", "predicate", "etat", "state",
    "statut", "confiance", "confidence", "valid_from", "valide_depuis", "decouverte_quand", "valid_to",
    "valide_jusqua", "fin_validite", "desactivee_quand", "obsolete_depuis", "active",
)
_CLES_VALID_FROM = ("valid_from", "valide_depuis", "decouverte_quand")
_CLES_VALID_TO = ("valid_to", "valide_jusqua", "fin_validite", "desactivee_quand", "obsolete_depuis")


class DocumentInvalide(ValueError):
    """Document legacy impossible à projeter sans deviner son contenu."""


def _sans_accents(valeur) -> str:
    decompose = unicodedata.normalize("NFKD", str(valeur or ""))
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _normaliser_code(valeur) -> str:
    texte = _sans_accents(valeur)
    texte = "".join(c if c.isalnum() else "_" for c in texte).strip("_")
    while "__" in texte:
        texte = texte.replace("__", "_")
    return texte.upper()


def _texte_scalaire(valeur, champ: str, *, obligatoire: bool = True):
    if valeur is None:
        if obligatoire:
            raise DocumentInvalide(f"{champ} obligatoire")
        return None
    if isinstance(valeur, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
        raise DocumentInvalide(f"{champ} invalide")
    texte = str(valeur).strip()
    if not texte:
        if obligatoire:
            raise DocumentInvalide(f"{champ} obligatoire")
        return None
    return texte


def _tenant(tenant) -> str:
    return _texte_scalaire(tenant, "tenant_id")


def _document_et_tenant(document, tenant):
    """Accepte `(document, tenant)` comme les mappings du module, et `(tenant, document)` par symétrie avec
    `graphe_sync`."""
    if tenant is None:
        raise DocumentInvalide("tenant_id obligatoire")
    if not isinstance(document, Mapping) and isinstance(tenant, Mapping):
        document, tenant = tenant, document
    return document, _tenant(tenant)


def _verifier_tenant(doc: Mapping, tenant: str) -> None:
    declare = doc.get("tenant_id")
    if declare is None:
        return
    texte = _texte_scalaire(declare, "tenant_id", obligatoire=False)
    if texte and texte != tenant:
        raise PermissionError("document hors du tenant demandé")


def _meme_tenant(doc: Mapping, tenant: str) -> bool:
    declare = doc.get("tenant_id")
    if declare is None:
        return True
    if isinstance(declare, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
        return False
    texte = str(declare).strip()
    return not texte or texte == tenant


def _identifiant(doc: Mapping) -> str:
    return _texte_scalaire(doc.get("id"), "id")


def _identifiant_souple(doc, position: int = 0) -> str:
    if isinstance(doc, Mapping):
        valeur = doc.get("id")
        if not isinstance(valeur, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
            texte = str(valeur or "").strip()
            if texte:
                return texte
    return f"#{position}"


def _titre_doc(doc: Mapping, identifiant: str) -> str:
    for cle in ("titre", "resume", "nom", "name"):
        valeur = doc.get(cle)
        if valeur is None:
            continue
        if isinstance(valeur, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
            raise DocumentInvalide("titre invalide")
        texte = str(valeur).strip()
        if texte:
            return texte
    return identifiant


def _cle_sensible(cle) -> bool:
    normalisee = unquote_plus(str(cle)).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    if compacte in _CLES_SECRETES:
        return True
    if compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _url_porte_un_secret(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        return True
    return any(_cle_sensible(cle) and valeur not in ("", "***")
               for cle, valeur in parse_qsl(parties.query, keep_blank_values=True))


def _jsonable(valeur):
    if valeur is None or isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, float):
        if not math.isfinite(valeur):
            raise DocumentInvalide("nombre non fini")
        return valeur
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, str):
        return "[redacted]" if _url_porte_un_secret(valeur) else valeur
    if isinstance(valeur, Mapping):
        sortie = {}
        for cle, element in valeur.items():
            if str(cle) == "_id" or _cle_sensible(cle):
                continue
            sortie[str(cle)] = _jsonable(element)
        return sortie
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_jsonable(element) for element in valeur]
    raise DocumentInvalide("valeur non sérialisable")


def _copier(doc: Mapping, champs) -> dict:
    return {champ: _jsonable(doc[champ]) for champ in champs if champ in doc}


def _liste_ids(valeur) -> list[str]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, int, float)) and not isinstance(valeur, bool):
        elements = [valeur]
    elif isinstance(valeur, (list, tuple, set, frozenset)):
        elements = list(valeur)
    else:
        return []
    identifiants = []
    for element in elements:
        if isinstance(element, Mapping):
            element = element.get("id")
        if isinstance(element, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
            continue
        texte = str(element or "").strip()
        if texte and texte not in identifiants:
            identifiants.append(texte)
    return identifiants


def _iso(valeur):
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return None
        try:
            return datetime.fromisoformat(texte.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    return None


def _premiere_date(doc: Mapping, cles):
    for cle in cles:
        date_iso = _iso(doc.get(cle))
        if date_iso:
            return date_iso
    return None


def _version(doc: Mapping) -> int:
    valeur = doc.get("version")
    if isinstance(valeur, bool):
        return 1
    try:
        version = int(valeur)
    except (TypeError, ValueError):
        return 1
    return max(1, version)


def _temporalite(doc: Mapping, cles_observation, cles_validite) -> dict:
    champs = {}
    observe_le = _premiere_date(doc, cles_observation)
    valide_depuis = _premiere_date(doc, cles_validite)
    if observe_le:
        champs["observe_le"] = observe_le
    if valide_depuis:
        champs["valide_depuis"] = valide_depuis
    for champ in ("valide_jusqua", "cree_le"):
        date_iso = _iso(doc.get(champ))
        if date_iso:
            champs[champ] = date_iso
    return champs


def objet_depuis_situation(doc, tenant) -> dict:
    """Projette une situation Mongo en objet canonique `emergence/SITUATION`.

    Le mode est toujours `DECLARED` : la migration déclare ce que Mongo contenait, elle ne prétend pas l'avoir
    observé. Les statuts et priorités sont normalisés en codes ; les liens `twin_ids` ne viennent que du champ
    `jumeaux` (ou `twin_ids`) et jamais du texte libre.
    """
    if not isinstance(doc, Mapping):
        raise DocumentInvalide("document attendu")
    tenant_id = _tenant(tenant)
    _verifier_tenant(doc, tenant_id)
    identifiant = _identifiant(doc)

    donnees = _copier(doc, _CHAMPS_SITUATION)
    statut = _normaliser_code(doc.get("statut"))
    if statut:
        donnees["statut"] = statut
    priorite = _normaliser_code(doc.get("priorite"))
    if priorite:
        donnees["priorite"] = priorite
    twin_ids = _liste_ids(doc.get("twin_ids") if doc.get("twin_ids") is not None else doc.get("jumeaux"))
    if twin_ids:
        donnees["twin_ids"] = twin_ids

    objet = {
        "id": identifiant,
        "famille": "emergence",
        "type": "SITUATION",
        "mode": "DECLARED",
        "titre": _titre_doc(doc, identifiant),
        "donnees": donnees,
        "version": _version(doc),
    }
    objet.update(_temporalite(
        doc,
        ("observe_le", "detectee", "cree_le", "maj_le"),
        ("valide_depuis", "observe_le", "detectee", "cree_le", "maj_le"),
    ))
    return objet


def _liens_initiative(doc: Mapping) -> dict:
    liens = {}
    for champ in _CHAMPS_LIEN_INITIATIVE:
        if champ not in doc:
            continue
        valeur = _texte_scalaire(doc[champ], champ, obligatoire=False)
        if valeur:
            liens[champ] = valeur
    return liens


def objet_depuis_initiative(doc, tenant) -> dict:
    """Projette une initiative Mongo en objet canonique `decision/INITIATIVE`.

    Les liens éventuels (`travail_id`, `jumeau_cible`, `decision_id`, etc.) ne sont copiés que s'ils sont présents
    dans le document. Aucun `decision_id` n'est déduit d'un texte ou d'un titre.
    """
    if not isinstance(doc, Mapping):
        raise DocumentInvalide("document attendu")
    tenant_id = _tenant(tenant)
    _verifier_tenant(doc, tenant_id)
    identifiant = _identifiant(doc)

    donnees = _copier(doc, _CHAMPS_INITIATIVE)
    statut = _normaliser_code(doc.get("statut"))
    if statut:
        donnees["statut"] = statut
    urgence = _normaliser_code(doc.get("urgence"))
    if urgence:
        donnees["urgence"] = urgence
    twin_ids = _liste_ids(doc.get("twin_ids") if doc.get("twin_ids") is not None else doc.get("jumeaux"))
    if twin_ids:
        donnees["twin_ids"] = twin_ids
    donnees.update(_liens_initiative(doc))

    objet = {
        "id": identifiant,
        "famille": "decision",
        "type": "INITIATIVE",
        "mode": "DECLARED",
        "titre": _titre_doc(doc, identifiant),
        "donnees": donnees,
        "version": _version(doc),
    }
    objet.update(_temporalite(
        doc,
        ("observe_le", "quand", "cree_le", "maj_le"),
        ("valide_depuis", "quand", "cree_le", "maj_le"),
    ))
    return objet


def twin_depuis_jumeau(doc, tenant):
    """Traduit un jumeau Mongo en `NoeudTwin` via `graphe_sync.twin_depuis_identite`.

    Les propriétés restent limitées à mission, domaine, équipe et statut. Le type par défaut est `APPLICATION`,
    jamais déduit du nom du jumeau. L'ordre `(tenant, document)` est aussi accepté, comme dans `graphe_sync`.
    """
    doc, tenant_id = _document_et_tenant(doc, tenant)
    if not isinstance(doc, Mapping):
        raise DocumentInvalide("document attendu")
    _verifier_tenant(doc, tenant_id)
    identifiant = _identifiant(doc)
    candidat = dict(doc)
    candidat["id"] = identifiant
    if not candidat.get("tenant_id"):
        candidat["tenant_id"] = tenant_id
    if not candidat.get("label") and not candidat.get("nom") and not candidat.get("name"):
        candidat["nom"] = identifiant
    if not candidat.get("type") and not candidat.get("type_twin"):
        candidat["type"] = "APPLICATION"
    return twin_depuis_identite(tenant_id, candidat)


def _confiance(valeur):
    if valeur is None:
        return None
    if isinstance(valeur, str):
        texte = valeur.strip().replace("%", "")
        if not texte:
            return None
        try:
            valeur = float(texte)
        except ValueError as exc:
            raise DocumentInvalide("confiance invalide") from exc
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise DocumentInvalide("confiance invalide") from exc
    if 1 < nombre <= 100:
        nombre /= 100
    return nombre


def _preuve_ids(doc: Mapping) -> list[str]:
    brut = None
    for cle in ("preuve_ids", "evidence_ids", "preuves"):
        if cle in doc:
            brut = doc.get(cle)
            break
    if brut is None:
        return []
    if isinstance(brut, Mapping) or isinstance(brut, (str, bytes)):
        elements = [brut]
    elif isinstance(brut, (list, tuple, set, frozenset)):
        elements = list(brut)
    else:
        return []
    identifiants = []
    for element in elements:
        if isinstance(element, Mapping):
            element = element.get("id") or element.get("preuve_id") or element.get("evidence_id")
        if isinstance(element, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
            continue
        texte = str(element or "").strip()
        if texte and texte not in identifiants:
            identifiants.append(texte)
    return identifiants


def _relation_normalisee(doc: Mapping) -> dict:
    sortie = _copier(doc, _CHAMPS_RELATION)
    if "confiance" in sortie:
        sortie["confiance"] = _confiance(sortie["confiance"])
    elif "confidence" in sortie:
        sortie["confidence"] = _confiance(sortie["confidence"])
    preuve_ids = _preuve_ids(doc)
    if preuve_ids:
        sortie["preuve_ids"] = preuve_ids
    for cle in _CLES_VALID_FROM + _CLES_VALID_TO:
        if cle not in sortie:
            continue
        date_iso = _iso(sortie[cle])
        if date_iso:
            sortie[cle] = date_iso
        elif str(sortie[cle]).strip().lower() == "inactive":
            sortie[cle] = "inactive"
        else:
            sortie.pop(cle)
    return sortie


def relations_vers_graphe(relations, tenant):
    """Traduit des relations Mongo en arêtes du graphe ; rend `(aretes, erreurs)`.

    Les confiances exprimées en pourcentage sont ramenées entre 0 et 1 et les dates non ISO sont retirées plutôt
    que stockées telles quelles. Une relation invalide ne bloque pas les suivantes. L'ordre `(tenant, relations)`
    est aussi accepté.
    """
    if tenant is None:
        raise DocumentInvalide("tenant_id obligatoire")
    if isinstance(relations, str) and not isinstance(tenant, str):
        relations, tenant = tenant, relations
    tenant_id = _tenant(tenant)
    aretes, erreurs = [], []
    for position, doc in enumerate(relations or []):
        identifiant = _identifiant_souple(doc, position)
        try:
            if not isinstance(doc, Mapping):
                raise DocumentInvalide("relation attendue")
            _verifier_tenant(doc, tenant_id)
            aretes.append(arete_depuis_relation(tenant_id, _relation_normalisee(doc)))
        except Exception as exc:
            erreurs.append({
                "type": "relation",
                "id": identifiant,
                "raison": _raison(exc, doc),
            })
    return aretes, erreurs


def _valeurs_sensibles(valeur):
    if isinstance(valeur, Mapping):
        for cle, element in valeur.items():
            if _cle_sensible(cle):
                yield from _scalaires(element)
            else:
                yield from _valeurs_sensibles(element)
    elif isinstance(valeur, (list, tuple, set, frozenset)):
        for element in valeur:
            yield from _valeurs_sensibles(element)
    elif isinstance(valeur, str) and _url_porte_un_secret(valeur):
        yield valeur


def _scalaires(valeur):
    if isinstance(valeur, Mapping):
        for element in valeur.values():
            yield from _scalaires(element)
    elif isinstance(valeur, (list, tuple, set, frozenset)):
        for element in valeur:
            yield from _scalaires(element)
    elif valeur is not None and not isinstance(valeur, bool):
        yield str(valeur)


def _raison(exc, doc=None) -> str:
    texte = str(exc) or exc.__class__.__name__
    if isinstance(doc, Mapping):
        for secret in _valeurs_sensibles(doc):
            if secret and secret != "[redacted]":
                texte = texte.replace(secret, "[redacted]")
    return texte[:240]


def _ignorer(rapport: dict, nature: str, identifiant: str, raison: str) -> None:
    rapport["ignores"].append({"type": nature, "id": identifiant, "raison": raison})


def _erreur(rapport: dict, nature: str, identifiant: str, exc, doc=None) -> None:
    rapport["erreurs"].append({
        "type": nature,
        "id": identifiant,
        "raison": _raison(exc, doc),
    })


def _collection(db, nom: str):
    if db is None:
        return None
    try:
        collection = getattr(db, nom)
    except Exception:
        collection = None
    if collection is not None:
        return collection
    try:
        return db[nom]
    except Exception:
        return None


async def _documents(collection) -> list:
    if collection is None:
        return []
    if isinstance(collection, (list, tuple)):
        return list(collection)
    find = getattr(collection, "find", None)
    if not callable(find):
        if hasattr(collection, "__aiter__"):
            return [document async for document in collection]
        return []
    try:
        curseur = find({})
    except TypeError:
        curseur = find()
    if inspect.isawaitable(curseur):
        curseur = await curseur
    if isinstance(curseur, (list, tuple)):
        return list(curseur)
    to_list = getattr(curseur, "to_list", None)
    if callable(to_list):
        try:
            resultat = to_list(None)
        except TypeError:
            resultat = to_list()
        if inspect.isawaitable(resultat):
            resultat = await resultat
        return list(resultat or [])
    if hasattr(curseur, "__aiter__"):
        return [document async for document in curseur]
    try:
        return list(curseur or [])
    except TypeError:
        return []


def _twins_connus(store, tenant: str) -> set[str]:
    if store is None:
        return set()
    noeuds = getattr(store, "noeuds", None)
    if isinstance(noeuds, Mapping):
        connus = set()
        for cle, noeud in noeuds.items():
            if isinstance(cle, tuple) and len(cle) == 2:
                if str(cle[0]) == tenant:
                    connus.add(str(cle[1]))
            elif getattr(noeud, "tenant_id", None) == tenant:
                connus.add(str(getattr(noeud, "id", "")))
        return connus
    as_dict = getattr(store, "as_dict", None)
    if callable(as_dict):
        try:
            etat = as_dict(tenant)
        except Exception:
            return set()
        if isinstance(etat, Mapping):
            return {
                str(noeud.get("id"))
                for noeud in etat.get("noeuds") or []
                if isinstance(noeud, Mapping) and noeud.get("id")
            }
    return set()


def _migrer_objets(documents, nature, mapper, cle, rapport, tenant, dry_run, conn, ecrire) -> None:
    for position, doc in enumerate(documents):
        identifiant = _identifiant_souple(doc, position)
        if not isinstance(doc, Mapping):
            _ignorer(rapport, nature, identifiant, "document non objet")
            continue
        if not _meme_tenant(doc, tenant):
            _ignorer(rapport, nature, identifiant, "autre tenant")
            continue
        try:
            objet = mapper(doc, tenant)
        except PermissionError as exc:
            _ignorer(rapport, nature, identifiant, _raison(exc, doc))
            continue
        except DocumentInvalide as exc:
            _ignorer(rapport, nature, identifiant, _raison(exc, doc))
            continue
        except Exception as exc:
            _erreur(rapport, nature, identifiant, exc, doc)
            continue
        if not dry_run:
            try:
                ecrire(conn, tenant, objet)
            except Exception as exc:
                _erreur(rapport, nature, identifiant, exc, doc)
                continue
        rapport[cle] += 1


async def inspecter(db, tenant, dry_run=True, conn=None, store=None, enregistrer=None, *,
                    connexion=None, graphe=None) -> dict:
    """Inspecte le legacy Mongo et backfill les objets et la topologie canoniques.

    `db` est une base Mongo-like injectée (attributs `situations`, `initiatives`, `relations`, `jumeaux`).
    `conn` est une connexion Postgres pour `entreprise_depot.enregistrer_objet` et `store` un `GraphStore`.
    En dry-run (défaut) aucun de ces deux stores n'est requis et aucune écriture n'est effectuée. Les alias
    `connexion` et `graphe` sont acceptés par commodité.
    """
    conn = conn if conn is not None else connexion
    store = store if store is not None else graphe
    tenant_id = _tenant(tenant)
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run doit être un booléen")
    ecrire = enregistrer or entreprise_depot.enregistrer_objet
    rapport = {
        "tenant": tenant_id,
        "dry_run": dry_run,
        "situations": 0,
        "initiatives": 0,
        "relations": 0,
        "ignores": [],
        "erreurs": [],
    }

    situations = await _documents(_collection(db, "situations"))
    initiatives = await _documents(_collection(db, "initiatives"))
    jumeaux = await _documents(_collection(db, "jumeaux"))
    relations = await _documents(_collection(db, "relations"))

    if not dry_run and conn is None and enregistrer is None and (situations or initiatives):
        raise ValueError("connexion Postgres requise pour écrire les objets canoniques")
    if not dry_run and store is None and (jumeaux or relations):
        raise ValueError("GraphStore requis pour écrire la topologie canonique")

    _migrer_objets(situations, "situation", objet_depuis_situation, "situations",
                   rapport, tenant_id, dry_run, conn, ecrire)
    _migrer_objets(initiatives, "initiative", objet_depuis_initiative, "initiatives",
                   rapport, tenant_id, dry_run, conn, ecrire)

    connus = _twins_connus(store, tenant_id)
    for position, doc in enumerate(jumeaux):
        identifiant = _identifiant_souple(doc, position)
        if not isinstance(doc, Mapping):
            _ignorer(rapport, "jumeau", identifiant, "document non objet")
            continue
        if not _meme_tenant(doc, tenant_id):
            _ignorer(rapport, "jumeau", identifiant, "autre tenant")
            continue
        try:
            noeud = twin_depuis_jumeau(doc, tenant_id)
        except PermissionError as exc:
            _ignorer(rapport, "jumeau", identifiant, _raison(exc, doc))
            continue
        except DocumentInvalide as exc:
            _ignorer(rapport, "jumeau", identifiant, _raison(exc, doc))
            continue
        except Exception as exc:
            _erreur(rapport, "jumeau", identifiant, exc, doc)
            continue
        if not dry_run:
            try:
                store.upsert_twin(noeud)
            except Exception as exc:
                _erreur(rapport, "twin", noeud.id, exc, doc)
                continue
        connus.add(noeud.id)

    relations_du_tenant = []
    for position, doc in enumerate(relations):
        identifiant = _identifiant_souple(doc, position)
        if not isinstance(doc, Mapping):
            _ignorer(rapport, "relation", identifiant, "document non objet")
            continue
        if not _meme_tenant(doc, tenant_id):
            _ignorer(rapport, "relation", identifiant, "autre tenant")
            continue
        relations_du_tenant.append(doc)

    aretes, erreurs = relations_vers_graphe(relations_du_tenant, tenant_id)
    rapport["erreurs"].extend(erreurs)
    for arete in aretes:
        absents = [extremite for extremite in dict.fromkeys((arete.source, arete.target))
                   if extremite not in connus]
        if absents:
            _ignorer(rapport, "relation", arete.id, "Twin absent du graphe")
            rapport["ignores"][-1]["absents"] = absents
            continue
        if not dry_run:
            try:
                store.upsert_relation(arete)
            except Exception as exc:
                _erreur(rapport, "relation", arete.id, exc)
                continue
        rapport["relations"] += 1

    return rapport
