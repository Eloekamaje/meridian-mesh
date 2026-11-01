"""Audit persistant des appels d'outils (ADR-0004) : journal append-only et expurgé.

Chaque ligne décrit un appel : outil, capacité, acteur, arguments expurgés, durée, statut et erreur. Aucun contenu
métier ni secret n'est conservé : les clés et jetons sensibles deviennent « *** ». L'écriture ne lève jamais : une
base indisponible rend un statut `erreur` sans empêcher l'outil de rendre son résultat. Un même événement rejoué
avec le même horodatage n'est écrit qu'une fois ; deux appels distincts restent deux lignes. Le lot ouvre sa propre
connexion Postgres courte et la referme ; aucun autre accès réseau n'est effectué, aucun code n'est chargé ni
exécuté ici.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import math
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.llm.harness import expurger

_MAX_CACHE = 256
_MAX_ERREUR = 2048
_LIMITE_MAX = 500


class ErreurAudit(ValueError):
    """Ligne d'audit refusée avant toute écriture."""


def _texte(valeur: Any, limite: int = 512) -> str | None:
    if valeur is None:
        return None
    texte = " ".join(str(expurger(str(valeur))).split())
    return texte[:limite] or None


def _tenant(tenant_id: Any) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ErreurAudit("tenant_id obligatoire")
    return tenant_id.strip()[:128]


def _acteur(acteur: Any) -> str:
    texte = _texte(acteur, 128)
    if texte is None:
        raise ErreurAudit("acteur obligatoire")
    return texte


def _duree(valeur: Any) -> float:
    if valeur is None:
        return 0.0
    if isinstance(valeur, bool):
        raise ErreurAudit("duree_ms invalide")
    try:
        duree = float(valeur)
    except (TypeError, ValueError) as erreur:
        raise ErreurAudit("duree_ms invalide") from erreur
    if not math.isfinite(duree) or duree < 0:
        raise ErreurAudit("duree_ms invalide")
    return round(duree, 3)


def _arguments(valeur: Any) -> Any:
    if valeur is None:
        return {}
    if not isinstance(valeur, Mapping):
        raise ErreurAudit("arguments : objet attendu")
    return expurger(valeur)


def _quand(valeur: Any) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo is not None else valeur.replace(tzinfo=timezone.utc)
    if isinstance(valeur, bool):
        raise ErreurAudit("quand invalide")
    if isinstance(valeur, (int, float)):
        try:
            return datetime.fromtimestamp(float(valeur), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as erreur:
            raise ErreurAudit("quand invalide") from erreur
    if isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            raise ErreurAudit("quand invalide")
        try:
            instant = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError as erreur:
            raise ErreurAudit("quand invalide") from erreur
        return instant if instant.tzinfo is not None else instant.replace(tzinfo=timezone.utc)
    raise ErreurAudit("quand invalide")


def _limite(limite: Any) -> int:
    if isinstance(limite, bool):
        raise ErreurAudit("limite invalide")
    try:
        valeur = int(limite)
    except (TypeError, ValueError) as erreur:
        raise ErreurAudit("limite invalide") from erreur
    return max(1, min(valeur, _LIMITE_MAX))


def _empreinte(valeurs: Mapping) -> str:
    return json.dumps(valeurs, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _valeur(valeur: Any) -> Any:
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    return valeur


def _ligne(ligne: Mapping) -> dict:
    return {cle: _valeur(valeur) for cle, valeur in ligne.items()}


class AuditPostgres:
    """Écrit et relit le journal `outil_audit`, toujours borné au tenant et à l'acteur du sink."""

    def __init__(self, conn: Any, tenant_id: Any, acteur: Any) -> None:
        self.conn = conn
        self.tenant_id = _tenant(tenant_id)
        self.acteur = _acteur(acteur)
        self._recents: OrderedDict[str, datetime] = OrderedDict()

    def _preparer(self, ligne: Any) -> dict:
        if not isinstance(ligne, Mapping):
            raise ErreurAudit("ligne objet attendu")
        outil = _texte(ligne.get("outil") or ligne.get("nom"), 128)
        if outil is None:
            raise ErreurAudit("outil obligatoire")
        erreur = ligne.get("erreur")
        if erreur is None:
            erreur = ligne.get("motif")
        return {
            "tenant_id": self.tenant_id,
            "outil": outil,
            "capacite": _texte(ligne.get("capacite"), 128),
            "acteur": self.acteur,
            "arguments": _arguments(ligne.get("arguments")),
            "duree_ms": _duree(ligne.get("duree_ms")),
            "statut": _texte(ligne.get("statut"), 32) or "inconnu",
            "erreur": _texte(erreur, _MAX_ERREUR),
        }

    def _memoriser(self, cle: str, quand: datetime) -> None:
        self._recents[cle] = quand
        self._recents.move_to_end(cle)
        while len(self._recents) > _MAX_CACHE:
            self._recents.popitem(last=False)

    def enregistrer(self, ligne: Any) -> dict:
        """Écrit une ligne expurgée ; rend toujours un statut, même si la base échoue."""
        try:
            valeurs = self._preparer(ligne)
        except ErreurAudit as erreur:
            return {"statut": "refuse", "insere": False, "id": None, "erreur": str(erreur)}
        except Exception as erreur:
            return {"statut": "refuse", "insere": False, "id": None, "erreur": type(erreur).__name__}

        explicite = isinstance(ligne, Mapping) and ligne.get("quand") is not None
        try:
            if explicite:
                quand = _quand(ligne.get("quand"))
                cle = _empreinte({**valeurs, "quand": quand.isoformat()})
            else:
                cle = _empreinte(valeurs)
                quand = self._recents.get(cle) or datetime.now(timezone.utc)
        except ErreurAudit as erreur:
            return {"statut": "refuse", "insere": False, "id": None, "erreur": str(erreur)}

        try:
            with self.conn.transaction():
                with self.conn.cursor(row_factory=dict_row) as cur:
                    inseree = cur.execute(
                        "INSERT INTO outil_audit "
                        "(tenant_id, outil, capacite, acteur, arguments, duree_ms, statut, erreur, quand) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT DO NOTHING RETURNING id",
                        (valeurs["tenant_id"], valeurs["outil"], valeurs["capacite"], valeurs["acteur"],
                         Jsonb(valeurs["arguments"]), valeurs["duree_ms"], valeurs["statut"],
                         valeurs["erreur"], quand)).fetchone()
        except Exception as erreur:
            return {"statut": "erreur", "insere": False, "id": None, "erreur": type(erreur).__name__}

        if not explicite:
            self._memoriser(cle, quand)
        return {
            "statut": "ok",
            "insere": inseree is not None,
            "id": inseree["id"] if inseree is not None else None,
        }

    def derniers(self, tenant_id: Any = None, limite: Any = 50) -> list[dict]:
        """Les dernières lignes du tenant, de la plus récente à la plus ancienne."""
        return derniers(self.conn, self.tenant_id if tenant_id is None else tenant_id, limite)


def enregistrer_lignes(dsn: Any, tenant_id: Any, acteur: Any, lignes: Any) -> dict:
    """Persiste un lot d'audit dans une connexion courte, expurgée et silencieuse.

    Le lot est borné au tenant et à l'acteur fournis ; chaque ligne passe par `AuditPostgres`. Une base
    indisponible, un tenant invalide ou une ligne refusée ne lèvent pas : ils comptent une erreur et le lot
    continue. Le résultat ne contient aucun contenu de ligne, aucune erreur technique et aucun DSN.
    """
    try:
        lot = list(lignes or ())
    except Exception:
        return {"ecrits": 0, "erreurs": 1}
    if not lot:
        return {"ecrits": 0, "erreurs": 0}
    if not isinstance(dsn, str) or not dsn.strip():
        return {"ecrits": 0, "erreurs": len(lot)}

    ecrits = 0
    erreurs = 0
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            audit = AuditPostgres(conn, tenant_id, acteur)
            for ligne in lot:
                statut = audit.enregistrer(ligne)
                if statut.get("statut") == "ok":
                    ecrits += 1
                else:
                    erreurs += 1
    except Exception:
        return {"ecrits": ecrits, "erreurs": len(lot) - ecrits}
    return {"ecrits": ecrits, "erreurs": erreurs}


def derniers(conn: Any, tenant_id: Any, limite: Any = 50) -> list[dict]:
    """Lecture bornée du journal d'un tenant ; jamais de ligne d'un autre tenant."""
    tenant = _tenant(tenant_id)
    borne = _limite(limite)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, tenant_id, outil, capacite, acteur, arguments, duree_ms, statut, erreur, quand "
            "FROM outil_audit WHERE tenant_id = %s ORDER BY quand DESC, id DESC LIMIT %s",
            (tenant, borne)).fetchall()
    return [_ligne(ligne) for ligne in lignes]


__all__ = [
    "AuditPostgres",
    "ErreurAudit",
    "derniers",
    "enregistrer_lignes",
]
