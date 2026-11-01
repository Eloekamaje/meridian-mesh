"""Adapter Postgres du port TravailStore : read model alimenté depuis Mongo.

`donnees` conserve le document de cas complet ; le `_id` Mongo y est sérialisé en texte
pour servir de départage au curseur de synchronisation. L'upsert est idempotent : la version n'avance que si le
document change. Aucune suppression n'est faite ici.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _quand(travail: dict[str, Any]) -> datetime:
    valeur = travail.get("maj_le") or travail.get("cree_le")
    if isinstance(valeur, datetime):
        quand = valeur
    else:
        try:
            quand = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            quand = datetime.now(timezone.utc)
    return quand if quand.tzinfo else quand.replace(tzinfo=timezone.utc)


def _public(donnees: dict[str, Any]) -> dict[str, Any]:
    return {cle: valeur for cle, valeur in donnees.items() if cle != "_id"}


class TravailDepot:
    def __init__(self, dsn: str | None = None, tenant_id: str = "local", conn=None):
        self.dsn = dsn
        self.tenant_id = tenant_id
        self._conn = conn

    def _connexion(self):
        if self._conn is not None:
            return self._conn, False
        if not self.dsn:
            raise RuntimeError("DSN Postgres requis pour le store Travail")
        return psycopg.connect(self.dsn, autocommit=True), True

    async def lister(self, filtre: dict[str, Any] | None = None,
                     limite: int = 200) -> list[dict[str, Any]]:
        conn, fermer = self._connexion()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                if filtre:
                    cur.execute(
                        "SELECT donnees FROM travail WHERE tenant_id = %s AND donnees @> %s "
                        "ORDER BY maj_le DESC, id DESC LIMIT %s",
                        (self.tenant_id, Jsonb(filtre), int(limite)))
                else:
                    cur.execute(
                        "SELECT donnees FROM travail WHERE tenant_id = %s "
                        "ORDER BY maj_le DESC, id DESC LIMIT %s",
                        (self.tenant_id, int(limite)))
                return [_public(ligne["donnees"]) for ligne in cur.fetchall()]
        finally:
            if fermer:
                conn.close()

    async def lister_recents(self, limite: int | None = 500) -> list[dict[str, Any]]:
        conn, fermer = self._connexion()
        try:
            sql = ("SELECT donnees FROM travail WHERE tenant_id = %s "
                   "ORDER BY maj_le DESC, id DESC")
            params: list[Any] = [self.tenant_id]
            if limite:
                sql += " LIMIT %s"
                params.append(int(limite))
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return [_public(ligne["donnees"]) for ligne in cur.fetchall()]
        finally:
            if fermer:
                conn.close()

    async def lire(self, cid: str) -> dict[str, Any] | None:
        conn, fermer = self._connexion()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                ligne = cur.execute(
                    "SELECT donnees FROM travail WHERE tenant_id = %s AND id = %s",
                    (self.tenant_id, cid)).fetchone()
                return _public(ligne["donnees"]) if ligne else None
        finally:
            if fermer:
                conn.close()

    async def compter(self) -> int:
        conn, fermer = self._connexion()
        try:
            return int(conn.execute(
                "SELECT count(*) FROM travail WHERE tenant_id = %s",
                (self.tenant_id,)).fetchone()[0])
        finally:
            if fermer:
                conn.close()

    async def upsert(self, travail: dict[str, Any]) -> bool:
        document = dict(travail)
        identifiant = str(document.get("id") or document.get("_id") or "").strip()
        if not identifiant:
            raise ValueError("travail sans identifiant")
        document["id"] = identifiant
        document["tenant_id"] = self.tenant_id
        if document.get("_id") is not None:
            document["_id"] = str(document["_id"])
        conn, fermer = self._connexion()
        try:
            with conn.cursor() as cur:
                ligne = cur.execute(
                    "INSERT INTO travail (id, tenant_id, donnees, version, maj_le) "
                    "VALUES (%s, %s, %s, 1, %s) "
                    "ON CONFLICT (tenant_id, id) DO UPDATE SET "
                    "donnees = EXCLUDED.donnees, maj_le = EXCLUDED.maj_le, "
                    "version = travail.version + CASE "
                    "WHEN travail.donnees IS DISTINCT FROM EXCLUDED.donnees THEN 1 ELSE 0 END "
                    "RETURNING (xmax = 0)",
                    (identifiant, self.tenant_id, Jsonb(document), _quand(document))).fetchone()
                return bool(ligne[0])
        finally:
            if fermer:
                conn.close()

    async def mettre_a_jour(self, cid: str, champs: dict[str, Any]) -> bool:
        conn, fermer = self._connexion()
        try:
            ligne = conn.execute(
                "UPDATE travail SET donnees = donnees || %s, maj_le = now(), version = version + 1 "
                "WHERE tenant_id = %s AND id = %s RETURNING id",
                (Jsonb(champs), self.tenant_id, cid)).fetchone()
            return ligne is not None
        finally:
            if fermer:
                conn.close()

    async def supprimer(self, cid: str) -> bool:
        """Retire un cas du read model (double écriture) ; le tenant limite la portée."""
        conn, fermer = self._connexion()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM travail WHERE tenant_id = %s AND id = %s",
                            (self.tenant_id, cid))
                return cur.rowcount > 0
        finally:
            if fermer:
                conn.close()

    def identifiants(self) -> set[str]:
        conn, fermer = self._connexion()
        try:
            return {str(ligne[0]) for ligne in conn.execute(
                "SELECT id FROM travail WHERE tenant_id = %s", (self.tenant_id,)).fetchall()}
        finally:
            if fermer:
                conn.close()

    async def supprimer_plusieurs(self, ids: list[str]) -> int:
        identifiants = [str(i) for i in ids if i is not None]
        if not identifiants:
            return 0
        conn, fermer = self._connexion()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM travail WHERE tenant_id = %s AND id = ANY(%s)",
                            (self.tenant_id, identifiants))
                return cur.rowcount
        finally:
            if fermer:
                conn.close()

    def dernier_curseur(self):
        """Curseur exact `(maj_le, _id)` du document le plus récent, pour reprendre sans trou."""
        conn, fermer = self._connexion()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                ligne = cur.execute(
                    "SELECT donnees->>'maj_le' AS maj_le, donnees->>'_id' AS _id "
                    "FROM travail WHERE tenant_id = %s "
                    "AND donnees->>'maj_le' IS NOT NULL AND donnees->>'_id' IS NOT NULL "
                    "ORDER BY maj_le DESC, donnees->>'_id' DESC LIMIT 1",
                    (self.tenant_id,)).fetchone()
                from meridian.application.travail_sync import Curseur
                if not ligne:
                    return Curseur()
                return Curseur(maj_le=ligne["maj_le"], id=ligne["_id"])
        finally:
            if fermer:
                conn.close()

    def fermer(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
