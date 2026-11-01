"""Adaptateur Neo4j du port `GraphStore` : topologie tenant-scoped, Cypher paramétré.

L'adaptateur ne dépend pas du driver `neo4j` : il reçoit une session (ou une transaction) exposant
`run(requete, params)`. Le domaine ne voit ni Cypher ni Neo4j ; seuls les modèles de `meridian.domain.graphe`
entrent et sortent. Toutes les valeurs variables passent par des paramètres Cypher ; les étiquettes
sont statiques (`:Twin`, `:RELATION`) et le type métier d'une relation reste une propriété, jamais une
étiquette dynamique.

Les nœuds portent `proprietes` sous forme de texte JSON : Neo4j n'accepte pas une map imbriquée comme
valeur de propriété. La lecture (`as_dict`) la redécode en dictionnaire.

Limites assumées :
- la vérification d'existence des extrémités d'une relation est une lecture suivie d'une écriture ;
  l'appelant fournit une transaction s'il veut l'atomicité complète ;
- une relation ne change pas d'extrémités (même identité topologique) ;
- les parcours sont bornés par `MAX_PROFONDEUR` (8) et `chemins` rend au plus `MAX_CHEMINS` résultats ;
- `supprimer_relation` est une suppression physique ; `fermer_relation` conserve la période de validité
  pour l'audit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone

from meridian.domain.graphe import MAX_PROFONDEUR, Arete, NoeudTwin

MAX_CHEMINS = 100
_TYPE_RELATION = re.compile(r"^[^\W_][\w .:+/'-]{0,63}$", re.UNICODE)


def _requete(texte: str) -> str:
    """Fixe les bornes de parcours depuis les constantes du port, sans valeur utilisateur."""
    return texte.replace("__MAX_PROFONDEUR__", str(MAX_PROFONDEUR)).replace(
        "__MAX_CHEMINS__", str(MAX_CHEMINS)
    )


_REQ_UPSERT_TWIN = _requete("""
    MERGE (n:Twin {tenant_id: $tenant_id, id: $id})
    ON CREATE SET n.type = $type
    WITH n, coalesce(n.type, '') = $type AS type_ok
    FOREACH (_ IN CASE WHEN type_ok THEN [1] ELSE [] END |
        SET n.label = $label,
            n.proprietes = $proprietes
    )
    RETURN n.type AS type, type_ok AS type_ok
    """)

_REQ_ETAT_RELATION = _requete("""
    OPTIONAL MATCH (s:Twin {tenant_id: $tenant_id, id: $source})
    OPTIONAL MATCH (t:Twin {tenant_id: $tenant_id, id: $target})
    OPTIONAL MATCH (x:Twin {tenant_id: $tenant_id})
        -[r:RELATION {tenant_id: $tenant_id, id: $id}]->
        (y:Twin {tenant_id: $tenant_id})
    RETURN s IS NOT NULL AS source_present,
           t IS NOT NULL AS target_present,
           r IS NOT NULL AS relation_present,
           x.id AS existing_source,
           y.id AS existing_target
    """)

_REQ_UPSERT_RELATION = _requete("""
    MATCH (s:Twin {tenant_id: $tenant_id, id: $source})
    MATCH (t:Twin {tenant_id: $tenant_id, id: $target})
    MERGE (s)-[r:RELATION {tenant_id: $tenant_id, id: $id}]->(t)
    SET r.type = $type,
        r.etat = $etat,
        r.confiance = $confiance,
        r.valid_from = $valid_from,
        r.valid_to = $valid_to,
        r.preuve_ids = $preuve_ids,
        r.source = $source,
        r.target = $target
    RETURN r.id AS id
    """)

_REQ_VOISINS_SORTANT = _requete("""
    MATCH p = (depart:Twin {tenant_id: $tenant_id, id: $twin_id})
        -[:RELATION*1..__MAX_PROFONDEUR__]->
        (voisin:Twin {tenant_id: $tenant_id})
    WHERE length(p) <= $profondeur
      AND voisin.id <> $twin_id
      AND all(r IN relationships(p) WHERE r.tenant_id = $tenant_id AND r.valid_to IS NULL)
      AND all(n IN nodes(p) WHERE n.tenant_id = $tenant_id)
      AND all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
    RETURN voisin.id AS id,
           length(p) AS profondeur,
           [n IN nodes(p) | n.id] AS chemin,
           last(relationships(p)).id AS relation,
           last(relationships(p)).etat AS etat
    """)

_REQ_VOISINS_ENTRANT = _requete("""
    MATCH p = (depart:Twin {tenant_id: $tenant_id, id: $twin_id})
        <-[:RELATION*1..__MAX_PROFONDEUR__]-
        (voisin:Twin {tenant_id: $tenant_id})
    WHERE length(p) <= $profondeur
      AND voisin.id <> $twin_id
      AND all(r IN relationships(p) WHERE r.tenant_id = $tenant_id AND r.valid_to IS NULL)
      AND all(n IN nodes(p) WHERE n.tenant_id = $tenant_id)
      AND all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
    RETURN voisin.id AS id,
           length(p) AS profondeur,
           [n IN nodes(p) | n.id] AS chemin,
           last(relationships(p)).id AS relation,
           last(relationships(p)).etat AS etat
    """)

_REQ_VOISINS_LES_DEUX = _requete("""
    MATCH p = (depart:Twin {tenant_id: $tenant_id, id: $twin_id})
        -[:RELATION*1..__MAX_PROFONDEUR__]-
        (voisin:Twin {tenant_id: $tenant_id})
    WHERE length(p) <= $profondeur
      AND voisin.id <> $twin_id
      AND all(r IN relationships(p) WHERE r.tenant_id = $tenant_id AND r.valid_to IS NULL)
      AND all(n IN nodes(p) WHERE n.tenant_id = $tenant_id)
      AND all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
    RETURN voisin.id AS id,
           length(p) AS profondeur,
           [n IN nodes(p) | n.id] AS chemin,
           last(relationships(p)).id AS relation,
           last(relationships(p)).etat AS etat
    """)

_VOISINS_PAR_SENS = {
    "sortant": _REQ_VOISINS_SORTANT,
    "entrant": _REQ_VOISINS_ENTRANT,
    "les_deux": _REQ_VOISINS_LES_DEUX,
}

_REQ_CHEMINS = _requete("""
    MATCH p = (source:Twin {tenant_id: $tenant_id, id: $source})
        -[:RELATION*1..__MAX_PROFONDEUR__]->
        (cible:Twin {tenant_id: $tenant_id, id: $cible})
    WHERE length(p) <= $profondeur
      AND all(r IN relationships(p) WHERE r.tenant_id = $tenant_id AND r.valid_to IS NULL)
      AND all(n IN nodes(p) WHERE n.tenant_id = $tenant_id)
      AND all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
    RETURN [n IN nodes(p) | n.id] AS chemin
    ORDER BY length(p), chemin
    LIMIT __MAX_CHEMINS__
    """)

_REQ_FERMER_RELATION = _requete("""
    MATCH (:Twin {tenant_id: $tenant_id})
        -[r:RELATION {tenant_id: $tenant_id, id: $relation_id}]->
        (:Twin {tenant_id: $tenant_id})
    SET r.valid_to = $valid_to
    RETURN r.id AS id, r.valid_to AS valid_to
    """)

_REQ_SUPPRIMER_RELATION = _requete("""
    MATCH (:Twin {tenant_id: $tenant_id})
        -[r:RELATION {tenant_id: $tenant_id, id: $relation_id}]->
        (:Twin {tenant_id: $tenant_id})
    WITH r
    DELETE r
    RETURN 1 AS supprimee
    """)

_REQ_AUDIT_NOEUDS = _requete("""
    MATCH (n:Twin {tenant_id: $tenant_id})
    RETURN n.id AS id, n.tenant_id AS tenant_id, n.type AS type,
           n.label AS label, n.proprietes AS proprietes
    ORDER BY id
    """)

_REQ_AUDIT_RELATIONS = _requete("""
    MATCH (s:Twin {tenant_id: $tenant_id})
        -[r:RELATION {tenant_id: $tenant_id}]->
        (t:Twin {tenant_id: $tenant_id})
    RETURN r.id AS id, r.tenant_id AS tenant_id, s.id AS source, t.id AS target,
           r.type AS type, r.etat AS etat, r.confiance AS confiance,
           r.valid_from AS valid_from, r.valid_to AS valid_to, r.preuve_ids AS preuve_ids
    ORDER BY id
    """)


def _texte(valeur, champ: str) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise ValueError(f"{champ} vide")
    return texte


def _profondeur(valeur) -> int:
    try:
        return max(1, min(int(valeur), MAX_PROFONDEUR))
    except (TypeError, ValueError) as exc:
        raise ValueError("profondeur invalide") from exc


def _type_relation(valeur) -> str:
    type_ = _texte(valeur, "type")
    if not _TYPE_RELATION.fullmatch(type_):
        raise ValueError("type de relation invalide")
    return type_


def _encoder_proprietes(proprietes) -> str:
    try:
        return json.dumps(
            dict(proprietes or {}), ensure_ascii=False, sort_keys=True, default=str
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("proprietes non sérialisables") from exc


def _decoder_proprietes(valeur) -> dict:
    if isinstance(valeur, Mapping):
        return dict(valeur)
    if valeur in (None, ""):
        return {}
    if isinstance(valeur, str):
        try:
            charge = json.loads(valeur)
        except (TypeError, ValueError):
            return {"valeur": valeur}
        return charge if isinstance(charge, dict) else {"valeur": charge}
    return {"valeur": valeur}


def _lignes(resultat) -> list:
    if resultat is None:
        return []
    if isinstance(resultat, Mapping) or isinstance(resultat, (str, bytes)):
        return [resultat]
    try:
        return list(resultat)
    except TypeError:
        single = getattr(resultat, "single", None)
        if callable(single):
            try:
                ligne = single()
            except Exception:
                ligne = None
            if ligne is not None:
                return [ligne]
        donnees = getattr(resultat, "data", None)
        if callable(donnees):
            donnees = donnees()
        return list(donnees or [])


def _premier(resultat):
    lignes = _lignes(resultat)
    return lignes[0] if lignes else None


def _valeur(record, cle: str, defaut=None):
    if isinstance(record, Mapping):
        return record.get(cle, defaut)
    try:
        return record[cle]
    except (KeyError, IndexError, TypeError):
        pass
    donnees = getattr(record, "data", None)
    if callable(donnees):
        try:
            donnees = donnees()
        except Exception:
            donnees = None
        if isinstance(donnees, Mapping):
            return donnees.get(cle, defaut)
    return getattr(record, cle, defaut)


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GrapheNeo4j:
    """Adaptateur injectable du port `GraphStore` sur une session Neo4j."""

    def __init__(self, session):
        if session is None or not callable(getattr(session, "run", None)):
            raise ValueError("session Neo4j attendue : run(requete, params)")
        self.session = session

    def _executer(self, requete: str, params: dict):
        return self.session.run(requete, params)

    def upsert_twin(self, noeud: NoeudTwin) -> NoeudTwin:
        if not isinstance(noeud, NoeudTwin):
            raise ValueError("NoeudTwin attendu")
        params = {
            "tenant_id": noeud.tenant_id,
            "id": noeud.id,
            "type": noeud.type,
            "label": noeud.label,
            "proprietes": _encoder_proprietes(noeud.proprietes),
        }
        ligne = _premier(self._executer(_REQ_UPSERT_TWIN, params))
        if ligne is not None:
            type_ok = _valeur(ligne, "type_ok")
            type_stocke = _valeur(ligne, "type")
            if (type_ok is not None and not bool(type_ok)) or (
                type_stocke is not None and type_stocke != noeud.type
            ):
                raise ValueError("le type d'un Twin ne change pas")
        return noeud

    def upsert_relation(self, arete: Arete) -> Arete:
        if not isinstance(arete, Arete):
            raise ValueError("Arete attendue")
        _type_relation(arete.type)
        etat = _premier(
            self._executer(
                _REQ_ETAT_RELATION,
                {
                    "tenant_id": arete.tenant_id,
                    "id": arete.id,
                    "source": arete.source,
                    "target": arete.target,
                },
            )
        )
        if etat is None:
            raise ValueError(f"Twin absent du graphe : {arete.source}, {arete.target}")
        presents = {
            "source": bool(_valeur(etat, "source_present", False)),
            "target": bool(_valeur(etat, "target_present", False)),
        }
        absents = [extremite for extremite, present in presents.items() if not present]
        if absents:
            noms = [
                arete.source if extremite == "source" else arete.target
                for extremite in absents
            ]
            raise ValueError(f"Twin absent du graphe : {', '.join(noms)}")
        if bool(_valeur(etat, "relation_present", False)):
            source_existant = _valeur(etat, "existing_source")
            target_existant = _valeur(etat, "existing_target")
            if source_existant != arete.source or target_existant != arete.target:
                raise ValueError("les extrémités d'une relation ne changent pas")
        self._executer(
            _REQ_UPSERT_RELATION,
            {
                "tenant_id": arete.tenant_id,
                "id": arete.id,
                "source": arete.source,
                "target": arete.target,
                "type": arete.type,
                "etat": arete.etat,
                "confiance": float(arete.confiance),
                "valid_from": arete.valid_from,
                "valid_to": arete.valid_to,
                "preuve_ids": list(arete.preuve_ids),
            },
        )
        return arete

    def voisins(
        self, tenant_id: str, twin_id: str, profondeur: int = 1, sens: str = "sortant"
    ) -> list[dict]:
        tenant, identifiant = _texte(tenant_id, "tenant_id"), _texte(twin_id, "twin_id")
        sens = str(sens or "").strip()
        if sens not in _VOISINS_PAR_SENS:
            raise ValueError("sens attendu : sortant, entrant ou les_deux")
        niveau_max = _profondeur(profondeur)
        lignes = _lignes(
            self._executer(
                _VOISINS_PAR_SENS[sens],
                {"tenant_id": tenant, "twin_id": identifiant, "profondeur": niveau_max},
            )
        )
        resultats = {}
        for ligne in lignes:
            voisin = _valeur(ligne, "id")
            if voisin is None:
                continue
            voisin = str(voisin)
            if voisin == identifiant:
                continue
            try:
                niveau = int(_valeur(ligne, "profondeur", 0) or 0)
            except (TypeError, ValueError):
                continue
            if niveau < 1 or niveau > niveau_max:
                continue
            chemin = _valeur(ligne, "chemin") or [identifiant, voisin]
            if not isinstance(chemin, (list, tuple)):
                chemin = [identifiant, voisin]
            chemin = [str(x) for x in chemin]
            if len(set(chemin)) != len(chemin):
                continue
            candidat = {
                "id": voisin,
                "profondeur": niveau,
                "chemin": chemin,
                "relation": _valeur(ligne, "relation"),
                "etat": _valeur(ligne, "etat"),
            }
            precedent = resultats.get(voisin)
            if precedent is None or (candidat["profondeur"], candidat["chemin"]) < (
                precedent["profondeur"],
                precedent["chemin"],
            ):
                resultats[voisin] = candidat
        return sorted(resultats.values(), key=lambda x: (x["profondeur"], x["id"]))

    def chemins(
        self, tenant_id: str, source: str, cible: str, profondeur: int = 6
    ) -> list[list[str]]:
        tenant, depart, arrivee = (
            _texte(tenant_id, "tenant_id"),
            _texte(source, "source"),
            _texte(cible, "cible"),
        )
        niveau_max = _profondeur(profondeur)
        if depart == arrivee:
            return [[depart]]
        lignes = _lignes(
            self._executer(
                _REQ_CHEMINS,
                {
                    "tenant_id": tenant,
                    "source": depart,
                    "cible": arrivee,
                    "profondeur": niveau_max,
                },
            )
        )
        trouves, vus = [], set()
        for ligne in lignes:
            chemin = _valeur(ligne, "chemin")
            if not isinstance(chemin, (list, tuple)) or not chemin:
                continue
            chemin = [str(x) for x in chemin]
            if chemin[0] != depart or chemin[-1] != arrivee:
                continue
            if len(chemin) - 1 > niveau_max:
                continue
            if len(set(chemin)) != len(chemin):
                continue
            cle = tuple(chemin)
            if cle in vus:
                continue
            vus.add(cle)
            trouves.append(chemin)
        return sorted(trouves, key=lambda c: (len(c), c))[:MAX_CHEMINS]

    def impact(self, tenant_id: str, twin_id: str, profondeur: int = 3) -> dict:
        return {
            "aval": self.voisins(tenant_id, twin_id, profondeur, "sortant"),
            "amont": self.voisins(tenant_id, twin_id, profondeur, "entrant"),
        }

    def fermer_relation(
        self, tenant_id: str, relation_id: str, valid_to: str | None = None
    ) -> str:
        tenant, identifiant = _texte(tenant_id, "tenant_id"), _texte(
            relation_id, "relation_id"
        )
        date = _texte(valid_to, "valid_to") if valid_to is not None else _maintenant()
        self._executer(
            _REQ_FERMER_RELATION,
            {"tenant_id": tenant, "relation_id": identifiant, "valid_to": date},
        )
        return date

    def supprimer_relation(self, tenant_id: str, relation_id: str) -> int:
        tenant, identifiant = _texte(tenant_id, "tenant_id"), _texte(
            relation_id, "relation_id"
        )
        return len(
            _lignes(
                self._executer(
                    _REQ_SUPPRIMER_RELATION,
                    {"tenant_id": tenant, "relation_id": identifiant},
                )
            )
        )

    def as_dict(self, tenant_id: str) -> dict:
        """Audit tenant-scoped : nœuds et relations, propriétés JSON redécodées."""
        tenant = _texte(tenant_id, "tenant_id")
        params = {"tenant_id": tenant}
        noeuds = [
            {
                "id": _valeur(ligne, "id"),
                "tenant_id": _valeur(ligne, "tenant_id"),
                "type": _valeur(ligne, "type"),
                "label": _valeur(ligne, "label"),
                "proprietes": _decoder_proprietes(_valeur(ligne, "proprietes")),
            }
            for ligne in _lignes(self._executer(_REQ_AUDIT_NOEUDS, params))
        ]
        aretes = [
            {
                "id": _valeur(ligne, "id"),
                "tenant_id": _valeur(ligne, "tenant_id"),
                "source": _valeur(ligne, "source"),
                "target": _valeur(ligne, "target"),
                "type": _valeur(ligne, "type"),
                "etat": _valeur(ligne, "etat"),
                "confiance": _valeur(ligne, "confiance"),
                "valid_from": _valeur(ligne, "valid_from"),
                "valid_to": _valeur(ligne, "valid_to"),
                "preuve_ids": list(_valeur(ligne, "preuve_ids") or []),
            }
            for ligne in _lignes(self._executer(_REQ_AUDIT_RELATIONS, params))
        ]
        return {"noeuds": noeuds, "aretes": aretes}
