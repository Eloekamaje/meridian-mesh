"""Backfill contrôlé des identités légacy `jumeaux` vers Postgres.

Postgres est propriétaire de l'identité canonique ; le graphe ne fait que référencer son id.
Ce module lit les documents Mongo `jumeaux` (en lecture seule) et insère les lignes `jumeau`
manquantes, sans écraser une identité déjà canonique ni changer de tenant.

Limites assumées :
- l'id reste la clé primaire globale de la table `jumeau` ; un id déjà présent sous un autre
  tenant n'est pas déplacé et est signalé comme ignoré ;
- `equipe` est dérivée de `equipe` ou, à défaut, de `proprietaire` ;
- un type inconnu est refusé plutôt que remplacé silencieusement par `APPLICATION`.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import os

from meridian.domain.graphe import TYPES_TWIN
from meridian.adapters.outbound.postgres.migration_canonique import _collection, _documents, _identifiant_souple, _meme_tenant, _raison

__all__ = ["identite_depuis_jumeau", "migrer"]

_EQUIPE_DEFAUT = "À confirmer"
_DOMAINE_DEFAUT = "À confirmer"
_SQL = (
    "INSERT INTO jumeau (id, tenant_id, nom, equipe, type, domaine, mission) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (id) DO NOTHING RETURNING id"
)


def _texte(valeur, defaut=None):
    if valeur is None:
        return defaut
    texte = str(valeur).strip()
    return texte or defaut


def identite_depuis_jumeau(doc, tenant) -> dict:
    """Traduit un document `jumeaux` en ligne d'identité Postgres, sans copier ses secrets."""
    if not isinstance(doc, Mapping):
        raise ValueError("document jumeau attendu")
    tenant_id = _texte(tenant)
    if not tenant_id:
        raise ValueError("tenant_id obligatoire")
    if not _meme_tenant(doc, tenant_id):
        raise PermissionError("document hors du tenant demandé")
    identifiant = _texte(doc.get("id"))
    if not identifiant:
        raise ValueError("id obligatoire")
    nom = _texte(doc.get("nom") or doc.get("name"), identifiant)
    type_ = _texte(doc.get("type"), "APPLICATION").upper()
    if type_ not in TYPES_TWIN:
        raise ValueError(f"type de Twin inconnu : {doc.get('type')!r}")
    equipe = _texte(doc.get("equipe") or doc.get("proprietaire"), _EQUIPE_DEFAUT)
    domaine = _texte(doc.get("domaine"), _DOMAINE_DEFAUT)
    mission = _texte(doc.get("mission"))
    return {
        "id": identifiant,
        "tenant_id": tenant_id,
        "nom": nom,
        "equipe": equipe,
        "type": type_,
        "domaine": domaine,
        "mission": mission,
    }


def _ecrire(conn, identite) -> bool:
    ligne = conn.execute(
        _SQL,
        (
            identite["id"],
            identite["tenant_id"],
            identite["nom"],
            identite["equipe"],
            identite["type"],
            identite["domaine"],
            identite["mission"],
        ),
    ).fetchone()
    return ligne is not None


async def _jumeaux(db):
    return await _documents(_collection(db, "jumeaux"))


async def migrer(db, tenant, conn=None, dry_run=True, ecrire=None) -> dict:
    """Insère les identités manquantes ; rend un rapport stable et ne supprime jamais rien."""
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run doit être un booléen")
    tenant_id = _texte(tenant)
    if not tenant_id:
        raise ValueError("tenant_id obligatoire")
    if not dry_run and conn is None:
        raise ValueError("connexion Postgres requise hors dry-run")
    ecrire = ecrire or _ecrire
    rapport = {
        "tenant": tenant_id,
        "dry_run": dry_run,
        "jumeaux": 0,
        "inseres": 0,
        "ignores": [],
        "erreurs": [],
    }
    for position, doc in enumerate(await _jumeaux(db)):
        identifiant = _identifiant_souple(doc, position)
        if not isinstance(doc, Mapping):
            rapport["ignores"].append({"type": "jumeau", "id": identifiant, "raison": "document non objet"})
            continue
        if not _meme_tenant(doc, tenant_id):
            rapport["ignores"].append({"type": "jumeau", "id": identifiant, "raison": "autre tenant"})
            continue
        try:
            identite = identite_depuis_jumeau(doc, tenant_id)
        except PermissionError as exc:
            rapport["ignores"].append({"type": "jumeau", "id": identifiant, "raison": _raison(exc, doc)})
            continue
        except Exception as exc:
            rapport["erreurs"].append({"type": "jumeau", "id": identifiant, "raison": _raison(exc, doc)})
            continue
        rapport["jumeaux"] += 1
        if dry_run:
            continue
        try:
            if ecrire(conn, identite):
                rapport["inseres"] += 1
            else:
                rapport["ignores"].append(
                    {"type": "jumeau", "id": identifiant, "raison": "identité déjà canonique ou id d'un autre tenant"}
                )
        except Exception as exc:
            rapport["erreurs"].append({"type": "jumeau", "id": identifiant, "raison": _raison(exc, doc)})
    return rapport


def main():
    import argparse

    import psycopg
    from motor.motor_asyncio import AsyncIOMotorClient

    parseur = argparse.ArgumentParser(description="Backfill des identités Mongo vers Postgres")
    parseur.add_argument("--tenant", required=True)
    parseur.add_argument("--dry-run", action="store_true")
    arguments = parseur.parse_args()

    async def lancer():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            if arguments.dry_run:
                rapport = await migrer(db, arguments.tenant)
            else:
                with psycopg.connect(os.environ["JUMEAU_PG_DSN"]) as conn:
                    rapport = await migrer(db, arguments.tenant, conn=conn, dry_run=False)
                    conn.commit()
            print(json.dumps(rapport, ensure_ascii=False, indent=2))
        finally:
            client.close()

    import asyncio

    asyncio.run(lancer())


if __name__ == "__main__":
    main()
