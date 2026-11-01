"""Alimentation continue pull-first des jumeaux, sans webhook.

Chaque source suivie possède une ligne ``source_schedule`` durable : le worker relit les échéances, crée au plus
un ``ingestion_run`` vivant par source, le réclame sous bail puis exécute la passe du gardien. Aucun événement
entrant n'est nécessaire : la boucle est un polling réconcilié avec l'état Postgres.

Le module ne dépend ni de FastAPI ni de Motor. Il prend une connexion psycopg et, pour l'exécution, une base
Mongo (ou ``None`` quand l'appelant monkeypatche ``gardien.veiller``). Les URLs, chemins et références de secret
ne sortent jamais des fonctions publiques de santé : seuls le nom, le type, les états, le lag et une erreur
assainie sont rendus.
"""
from __future__ import annotations

import logging
import os
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

journal = logging.getLogger("meridian.ingestion")

ETATS_RUN = ("QUEUED", "FETCHING", "INDEXING", "EXTRACTING", "PROJECTING",
             "SUCCEEDED", "FAILED", "RETRY_WAIT", "CANCELLED")
ETATS_ACTIFS = ("QUEUED", "FETCHING", "INDEXING", "EXTRACTING", "PROJECTING", "RETRY_WAIT")
ETATS_TERMINAUX = ("SUCCEEDED", "FAILED", "CANCELLED")
ETAPES = ("FETCHING", "INDEXING", "EXTRACTING", "PROJECTING")
ORDRE_ETAPES = {etape: rang for rang, etape in enumerate(ETAPES)}

INTERVALLE_DEFAUT = 3600
BAIL_DEFAUT = 300
MAX_TENTATIVES_DEFAUT = 5
BACKOFF_BASE_DEFAUT = 30
BACKOFF_MAX_DEFAUT = 3600
ERREUR_MAX = 500


class SourceIntrouvable(LookupError):
    """Source absente ou hors du tenant : l'existence n'est pas révélée à l'autre tenant."""


class TransitionInvalide(RuntimeError):
    """Le run n'est pas dans l'état, le bail ou le fencing attendus."""


def _tenant(tenant) -> str:
    valeur = str(tenant or "").strip()
    if not valeur:
        raise ValueError("tenant requis")
    return valeur


def _entier_positif(valeur, nom="valeur") -> int:
    if isinstance(valeur, bool):
        raise ValueError(f"{nom} doit être un entier positif")
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        raise ValueError(f"{nom} doit être un entier positif") from None
    if entier <= 0:
        raise ValueError(f"{nom} doit être un entier positif")
    return entier


def _borne_limite(limite, defaut=50, maximum=500) -> int:
    try:
        valeur = int(limite)
    except (TypeError, ValueError):
        valeur = defaut
    return max(1, min(valeur, maximum))


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _date_publique(valeur):
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {cle: _date_publique(valeur_) for cle, valeur_ in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_date_publique(valeur_) for valeur_ in valeur]
    return valeur


def _cur(conn):
    return conn.cursor(row_factory=dict_row)


def _une(conn, sql: str, params: Iterable[Any] = ()) -> dict | None:
    with _cur(conn) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _toutes(conn, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _cur(conn) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+")
_SECRET = re.compile(
    r"(?i)\b(bearer|token|secret|password|passwd|api[_-]?key|authorization)\b\s*[:=]?\s*[^\s,;]+")
_JETON = re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]{10,})")


def assainir_erreur(erreur) -> str | None:
    """Message borné, sans URL ni valeur ressemblant à un secret (une erreur peut citer l'emplacement)."""
    texte = " ".join(str(erreur or "").split())
    if not texte:
        return None
    texte = _URL.sub("<url>", texte)
    texte = _JETON.sub("<secret>", texte)
    texte = _SECRET.sub(r"\1=<masqué>", texte)
    return texte[:ERREUR_MAX] or None


def _source(conn, source_id, tenant: str | None = None) -> dict:
    try:
        identifiant = int(source_id)
    except (TypeError, ValueError):
        raise SourceIntrouvable("source introuvable") from None
    if identifiant <= 0:
        raise SourceIntrouvable("source introuvable")
    source = _une(
        conn,
        "SELECT id, tenant_id, jumeau_id, type, nom, emplacement, curseur FROM source WHERE id = %s",
        (identifiant,),
    )
    if source is None or (tenant is not None and source["tenant_id"] != tenant):
        raise SourceIntrouvable("source introuvable")
    return source


def _schedule_publique(schedule: Mapping[str, Any] | None) -> dict | None:
    if schedule is None:
        return None
    champs = ("tenant_id", "source_id", "jumeau_id", "intervalle_s", "next_run_at", "last_run_at",
              "last_success_at", "etat", "tentative", "max_tentatives", "cree_le", "maj_le")
    return {champ: _date_publique(schedule.get(champ)) for champ in champs} | {
        "last_error": assainir_erreur(schedule.get("last_error"))}


def run_public(run: Mapping[str, Any] | None) -> dict | None:
    """Vue d'un run qui ne porte ni bail, ni fencing, ni URL : utilisable par l'API telle quelle."""
    if run is None:
        return None
    champs = ("id", "tenant_id", "source_id", "jumeau_id", "previous_sha", "observed_sha", "etat",
              "tentative", "max_tentatives", "cree_le", "demarre_le", "fini_le", "maj_le",
              "next_attempt_at", "metriques")
    public = {champ: _date_publique(run.get(champ)) for champ in champs}
    public["erreur"] = assainir_erreur(run.get("erreur"))
    return public


def planifier_source(conn, source_id, intervalle_s=INTERVALLE_DEFAUT, tenant=None) -> dict:
    """Planifie (ou replanifie) une source, sans doublon et sans remettre l'échéance à zéro.

    La source doit appartenir au tenant : un identifiant d'un autre tenant se comporte comme un identifiant
    inconnu. Appeler deux fois avec le même intervalle ne crée qu'une ligne et ne déclenche pas de run.
    """
    tenant = _tenant(tenant)
    intervalle = _entier_positif(intervalle_s, "intervalle_s")
    source = _source(conn, source_id, tenant)
    with conn.transaction():
        schedule = _une(
            conn,
            "INSERT INTO source_schedule (tenant_id, source_id, jumeau_id, intervalle_s, next_run_at) "
            "VALUES (%s, %s, %s, %s, now()) "
            "ON CONFLICT (tenant_id, source_id) DO UPDATE SET "
            "  intervalle_s = EXCLUDED.intervalle_s, "
            "  jumeau_id = EXCLUDED.jumeau_id, "
            "  maj_le = now() "
            "RETURNING *",
            (tenant, source["id"], source["jumeau_id"], intervalle),
        )
    return _schedule_publique(schedule)


def planifier_sources(conn, intervalle_s=None) -> int:
    """Bootstrap : planifie toutes les sources GIT qui n'ont pas encore de schedule.

    Le worker peut appeler cette fonction à chaque tour ; elle est idempotente et ne remet jamais
    à zéro une échéance existante. Les sources OTLP gardent leur tirage propre.
    """
    intervalle = _entier_positif(intervalle_s or INTERVALLE_DEFAUT, "intervalle_s")
    sources = _toutes(
        conn,
        "SELECT s.id, s.tenant_id FROM source s "
        "LEFT JOIN source_schedule ss ON ss.tenant_id = s.tenant_id AND ss.source_id = s.id "
        "WHERE s.type = 'GIT' AND ss.source_id IS NULL ORDER BY s.tenant_id, s.id",
    )
    for source in sources:
        planifier_source(conn, source["id"], intervalle, tenant=source["tenant_id"])
    return len(sources)


def _run_actif(conn, tenant: str, source_id: int) -> dict | None:
    return _une(
        conn,
        "SELECT * FROM ingestion_run WHERE tenant_id = %s AND source_id = %s "
        "AND etat = ANY(%s) ORDER BY cree_le LIMIT 1",
        (tenant, source_id, list(ETATS_ACTIFS)),
    )


def _creer_run(conn, schedule: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[dict | None, bool]:
    """Crée un run pour une échéance déjà verrouillée ; rend le run vivant existant s'il y en a un."""
    actif = _run_actif(conn, schedule["tenant_id"], schedule["source_id"])
    if actif is not None:
        return actif, False
    run = _une(
        conn,
        "INSERT INTO ingestion_run "
        "(id, tenant_id, source_id, jumeau_id, previous_sha, etat, tentative, max_tentatives) "
        "VALUES (%s, %s, %s, %s, %s, 'QUEUED', 0, %s) "
        "ON CONFLICT DO NOTHING RETURNING *",
        (uuid.uuid4().hex, schedule["tenant_id"], schedule["source_id"], schedule["jumeau_id"],
         source.get("curseur"), int(schedule.get("max_tentatives") or MAX_TENTATIVES_DEFAUT)),
    )
    if run is None:  # course avec un autre planificateur : l'index partiel a déjà un run vivant
        return _run_actif(conn, schedule["tenant_id"], schedule["source_id"]), False
    conn.execute(
        "UPDATE source_schedule SET last_run_at = now(), "
        "next_run_at = now() + (%s * interval '1 second'), maj_le = now() "
        "WHERE tenant_id = %s AND source_id = %s",
        (int(schedule["intervalle_s"]), schedule["tenant_id"], schedule["source_id"]),
    )
    journal.info("ingestion %s/%s : run %s enfilé", schedule["tenant_id"], schedule["source_id"], run["id"])
    return run, True


def enfiler_du(conn, limite=50) -> list[dict]:
    """Crée un run pour chaque échéance active due, sans jamais doubler une source déjà en cours."""
    limite = _borne_limite(limite)
    crees: list[dict] = []
    with conn.transaction():
        dues = _toutes(
            conn,
            "SELECT * FROM source_schedule ss "
            "WHERE ss.etat = 'active' AND ss.next_run_at <= now() "
            "AND NOT EXISTS (SELECT 1 FROM ingestion_run ir "
            "                WHERE ir.tenant_id = ss.tenant_id AND ir.source_id = ss.source_id "
            "                AND ir.etat = ANY(%s)) "
            "ORDER BY ss.next_run_at, ss.source_id "
            "FOR UPDATE SKIP LOCKED LIMIT %s",
            (list(ETATS_ACTIFS), limite),
        )
        for schedule in dues:
            try:
                source = _source(conn, schedule["source_id"], schedule["tenant_id"])
            except SourceIntrouvable:
                continue
            run, cree = _creer_run(conn, schedule, source)
            if cree and run is not None:
                crees.append(run)
    return crees


def enfiler_source(conn, source_id, tenant, *, force=True) -> dict:
    """Enfile explicitement une source planifiée (ingestion manuelle). Rend le run vivant, réutilisé si besoin."""
    tenant = _tenant(tenant)
    source = _source(conn, source_id, tenant)
    with conn.transaction():
        schedule = _une(
            conn,
            "SELECT * FROM source_schedule WHERE tenant_id = %s AND source_id = %s FOR UPDATE",
            (tenant, source["id"]),
        )
        if schedule is None:
            conn.execute(
                "INSERT INTO source_schedule (tenant_id, source_id, jumeau_id, intervalle_s, next_run_at) "
                "VALUES (%s, %s, %s, %s, now()) ON CONFLICT DO NOTHING",
                (tenant, source["id"], source["jumeau_id"], INTERVALLE_DEFAUT),
            )
            schedule = _une(
                conn,
                "SELECT * FROM source_schedule WHERE tenant_id = %s AND source_id = %s FOR UPDATE",
                (tenant, source["id"]),
            )
        if not force and schedule["next_run_at"] > _maintenant():
            return {"run": None, "cree": False, "schedule": _schedule_publique(schedule)}
        run, cree = _creer_run(conn, schedule, source)
        schedule = _une(
            conn, "SELECT * FROM source_schedule WHERE tenant_id = %s AND source_id = %s",
            (tenant, source["id"])) or schedule
        return {"run": run, "cree": cree, "schedule": _schedule_publique(schedule)}


def reclamer_run(conn, worker_id, bail_secondes=BAIL_DEFAUT) -> dict | None:
    """Réserve atomiquement le prochain run dû et pose le bail. Un run n'est jamais réclamé deux fois."""
    worker_id = str(worker_id or "").strip()
    if not worker_id:
        raise ValueError("worker_id requis")
    bail = _entier_positif(bail_secondes, "bail_secondes")
    with conn.transaction():
        run = _une(
            conn,
            "WITH candidat AS ("
            "  SELECT tenant_id, id FROM ingestion_run "
            "  WHERE etat = ANY(%s) "
            "    AND (next_attempt_at IS NULL OR next_attempt_at <= now()) "
            "    AND (bail_jusqu_a IS NULL OR bail_jusqu_a <= now()) "
            "  ORDER BY cree_le, id "
            "  FOR UPDATE SKIP LOCKED LIMIT 1"
            ") "
            "UPDATE ingestion_run r SET "
            "  etat = 'FETCHING', bail_proprietaire = %s, "
            "  bail_jusqu_a = now() + (%s * interval '1 second'), "
            "  fencing_token = r.fencing_token + 1, tentative = r.tentative + 1, "
            "  demarre_le = coalesce(r.demarre_le, now()), next_attempt_at = NULL, maj_le = now() "
            "FROM candidat c WHERE r.tenant_id = c.tenant_id AND r.id = c.id RETURNING r.*",
            (list(ETATS_ACTIFS), worker_id, bail),
        )
        if run is None:
            return None
        conn.execute(
            "UPDATE source_schedule SET bail_proprietaire = %s, "
            "bail_jusqu_a = now() + (%s * interval '1 second'), fencing_token = %s, maj_le = now() "
            "WHERE tenant_id = %s AND source_id = %s",
            (worker_id, bail, int(run["fencing_token"]), run["tenant_id"], run["source_id"]),
        )
    journal.info("ingestion run %s réclamé par %s (tentative %s)", run["id"], worker_id, run["tentative"])
    return run


def _verrou_run(conn, run_id, tenant_id: str | None = None) -> dict:
    run = _une(conn, "SELECT * FROM ingestion_run WHERE id = %s FOR UPDATE", (str(run_id),))
    if run is None or (tenant_id is not None and run["tenant_id"] != tenant_id):
        raise TransitionInvalide("run introuvable")
    return run


def _proprietaire(run: Mapping[str, Any], worker_id: str, fencing_token: int, *, bail=True) -> None:
    if run["etat"] in ETATS_TERMINAUX:
        raise TransitionInvalide("run déjà terminé")
    if run.get("bail_proprietaire") != worker_id:
        raise TransitionInvalide("run non possédé par ce worker")
    if int(run.get("fencing_token") or 0) != int(fencing_token):
        raise TransitionInvalide("fencing token périmé")
    if bail and (run.get("bail_jusqu_a") is None or run["bail_jusqu_a"] <= _maintenant()):
        raise TransitionInvalide("bail expiré")


def marquer_etape(conn, run_id, worker_id, fencing_token, etape, *, tenant_id=None,
                  bail_secondes=BAIL_DEFAUT) -> dict:
    """Fait avancer un run d'une étape observable, en renouvelant son bail."""
    etape = str(etape or "").upper()
    if etape not in ORDRE_ETAPES:
        raise ValueError(f"étape inconnue : {etape!r}")
    bail = _entier_positif(bail_secondes, "bail_secondes")
    with conn.transaction():
        run = _verrou_run(conn, run_id, tenant_id)
        if run["etat"] == etape:
            return run
        if run["etat"] in ETATS_TERMINAUX:
            raise TransitionInvalide("run déjà terminé")
        if run["etat"] == "QUEUED" and etape == "FETCHING":
            pass
        elif run["etat"] not in ORDRE_ETAPES:
            raise TransitionInvalide(f"étape refusée depuis {run['etat']}")
        elif ORDRE_ETAPES[etape] <= ORDRE_ETAPES[run["etat"]]:
            raise TransitionInvalide("les étapes ne reculent pas")
        _proprietaire(run, worker_id, fencing_token)
        run = _une(
            conn,
            "UPDATE ingestion_run SET etat = %s, bail_jusqu_a = now() + (%s * interval '1 second'), "
            "maj_le = now() WHERE id = %s RETURNING *",
            (etape, bail, run["id"]),
        )
        conn.execute(
            "UPDATE source_schedule SET bail_jusqu_a = now() + (%s * interval '1 second'), maj_le = now() "
            "WHERE tenant_id = %s AND source_id = %s",
            (bail, run["tenant_id"], run["source_id"]),
        )
    return run


def renouveler_bail(conn, run_id, worker_id, fencing_token, bail_secondes=BAIL_DEFAUT) -> bool:
    """Prolonge le bail d'un run vivant ; faux si le worker a perdu la propriété."""
    bail = _entier_positif(bail_secondes, "bail_secondes")
    with conn.transaction():
        run = _une(
            conn,
            "UPDATE ingestion_run SET bail_jusqu_a = now() + (%s * interval '1 second'), maj_le = now() "
            "WHERE id = %s AND etat = ANY(%s) AND bail_proprietaire = %s AND fencing_token = %s "
            "RETURNING tenant_id, source_id",
            (bail, str(run_id), list(ETAPES), str(worker_id), int(fencing_token)),
        )
        if run is None:
            return False
        conn.execute(
            "UPDATE source_schedule SET bail_jusqu_a = now() + (%s * interval '1 second'), maj_le = now() "
            "WHERE tenant_id = %s AND source_id = %s",
            (bail, run["tenant_id"], run["source_id"]),
        )
    return True


def terminer(conn, run_id, worker_id, fencing_token, resultat=None, metriques=None,
             observed_sha=None, tenant_id=None) -> dict:
    """Clôt un run en SUCCEEDED, libère le bail et remet la source au repos jusqu'à la prochaine échéance."""
    with conn.transaction():
        run = _verrou_run(conn, run_id, tenant_id)
        if run["etat"] in ETATS_TERMINAUX:
            return run
        _proprietaire(run, worker_id, fencing_token)
        run = _une(
            conn,
            "UPDATE ingestion_run SET etat = 'SUCCEEDED', observed_sha = coalesce(%s, observed_sha), "
            "metriques = coalesce(metriques, '{}'::jsonb) || %s, erreur = NULL, fini_le = now(), "
            "bail_proprietaire = NULL, bail_jusqu_a = NULL, next_attempt_at = NULL, maj_le = now() "
            "WHERE id = %s RETURNING *",
            (observed_sha, Jsonb(dict(resultat or {}) | dict(metriques or {})), run["id"]),
        )
        conn.execute(
            "UPDATE source_schedule SET last_success_at = now(), last_error = NULL, tentative = 0, "
            "bail_proprietaire = NULL, bail_jusqu_a = NULL, "
            "next_run_at = now() + (intervalle_s * interval '1 second'), maj_le = now() "
            "WHERE tenant_id = %s AND source_id = %s",
            (run["tenant_id"], run["source_id"]),
        )
    journal.info("ingestion run %s : SUCCEEDED", run["id"])
    return run


def backoff_secondes(tentative, base=None, plafond=None, rng=None) -> int:
    """Délai exponentiel avec jitter (50 %), borné : 1re reprise ≈ base, puis 2×, 4×… jusqu'au plafond."""
    try:
        t = max(1, int(tentative or 1))
    except (TypeError, ValueError):
        t = 1
    if base is None:
        base = _entier_env("JUMEAU_INGESTION_BACKOFF_S", BACKOFF_BASE_DEFAUT)
    if plafond is None:
        plafond = _entier_env("JUMEAU_INGESTION_BACKOFF_MAX_S", BACKOFF_MAX_DEFAUT)
    base, plafond = max(0, int(base)), max(1, int(plafond))
    if base == 0:
        return 0
    brut = min(plafond, base * (2 ** min(t - 1, 20)))
    jitter = (rng or random).uniform(0.0, brut * 0.5)
    return int(min(plafond, brut + jitter))


def _entier_env(nom: str, defaut: int) -> int:
    try:
        return max(0, int(str(os.environ.get(nom) or defaut).strip()))
    except (TypeError, ValueError):
        return defaut


def echouer(conn, run_id, worker_id, fencing_token, erreur, *, tenant_id=None) -> dict:
    """Consigne l'échec : RETRY_WAIT avec backoff tant que max_tentatives n'est pas atteint, sinon FAILED.

    La source garde son échéance, son erreur assainie et son compteur d'échecs consécutifs. Le run reste actif
    en RETRY_WAIT : aucun second run n'est créé pour la même source avant sa reprise ou son abandon.
    """
    message = assainir_erreur(erreur) or "ingestion impossible"
    with conn.transaction():
        run = _verrou_run(conn, run_id, tenant_id)
        if run["etat"] in ETATS_TERMINAUX:
            return run
        _proprietaire(run, worker_id, fencing_token, bail=False)
        tentative = int(run["tentative"])
        max_tentatives = int(run["max_tentatives"])
        delai = backoff_secondes(tentative)
        if tentative < max_tentatives:
            run = _une(
                conn,
                "UPDATE ingestion_run SET etat = 'RETRY_WAIT', erreur = %s, "
                "next_attempt_at = now() + (%s * interval '1 second'), "
                "bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                "WHERE id = %s RETURNING *",
                (message, delai, run["id"]),
            )
            etat_schedule, prochaine = "active", run["next_attempt_at"]
        else:
            run = _une(
                conn,
                "UPDATE ingestion_run SET etat = 'FAILED', erreur = %s, fini_le = now(), "
                "next_attempt_at = NULL, bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                "WHERE id = %s RETURNING *",
                (message, run["id"]),
            )
            etat_schedule, prochaine = "active", None
        conn.execute(
            "UPDATE source_schedule SET last_error = %s, tentative = tentative + 1, "
            "bail_proprietaire = NULL, bail_jusqu_a = NULL, "
            "next_run_at = coalesce(%s, now() + (intervalle_s * interval '1 second')), maj_le = now() "
            "WHERE tenant_id = %s AND source_id = %s",
            (message, prochaine, run["tenant_id"], run["source_id"]),
        )
    journal.warning("ingestion run %s : %s (%s)", run["id"], run["etat"], message)
    return run


def reprendre_baux_expires(conn, limite=50, *, bail_secondes=BAIL_DEFAUT) -> list[dict]:
    """Requeue les runs dont le bail a expiré ; ceux qui ont épuisé leurs tentatives finissent FAILED.

    Le fencing n'est pas incrémenté ici : il le sera au prochain claim, ce qui invalide définitivement
    l'ancien worker. Un run repris repart de son état QUEUED sans consommer une tentative supplémentaire.
    """
    limite = _borne_limite(limite)
    repris: list[dict] = []
    with conn.transaction():
        expires = _toutes(
            conn,
            "SELECT * FROM ingestion_run WHERE etat = ANY(%s) "
            "AND bail_jusqu_a IS NOT NULL AND bail_jusqu_a <= now() "
            "ORDER BY bail_jusqu_a FOR UPDATE SKIP LOCKED LIMIT %s",
            (list(ETAPES), limite),
        )
        for run in expires:
            if int(run["tentative"]) >= int(run["max_tentatives"]):
                message = "bail expiré : tentatives épuisées"
                run = _une(
                    conn,
                    "UPDATE ingestion_run SET etat = 'FAILED', erreur = %s, fini_le = now(), "
                    "bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                    "WHERE id = %s RETURNING *",
                    (message, run["id"]),
                )
                conn.execute(
                    "UPDATE source_schedule SET last_error = %s, tentative = tentative + 1, "
                    "bail_proprietaire = NULL, bail_jusqu_a = NULL, "
                    "next_run_at = now() + (intervalle_s * interval '1 second'), maj_le = now() "
                    "WHERE tenant_id = %s AND source_id = %s",
                    (message, run["tenant_id"], run["source_id"]),
                )
            else:
                run = _une(
                    conn,
                    "UPDATE ingestion_run SET etat = 'QUEUED', erreur = %s, "
                    "next_attempt_at = now(), bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                    "WHERE id = %s RETURNING *",
                    ("bail expiré : reprise", run["id"]),
                )
                conn.execute(
                    "UPDATE source_schedule SET bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                    "WHERE tenant_id = %s AND source_id = %s",
                    (run["tenant_id"], run["source_id"]),
                )
            repris.append(run)
    for run in repris:
        journal.warning("ingestion run %s : bail expiré, état %s", run["id"], run["etat"])
    return repris


def _sante(ligne: Mapping[str, Any]) -> str:
    if ligne.get("etat") == "paused":
        return "en_pause"
    if ligne.get("run_etat") == "RETRY_WAIT":
        return "en_attente_reprise"
    if ligne.get("last_error"):
        return "en_erreur"
    if ligne.get("last_success_at") is None:
        return "jamais_ingeree"
    intervalle = int(ligne.get("intervalle_s") or INTERVALLE_DEFAUT)
    if (ligne.get("lag_s") or 0) > 2 * intervalle:
        return "en_retard"
    return "saine"


def sante_sources(conn, tenant) -> dict:
    """Santé des sources planifiées du tenant : états, lag, dernière erreur assainie, run courant.

    La requête ne projette jamais `emplacement`, `url`, `secret_ref` ni `configuration` : le contrat de cette
    fonction est qu'aucun chemin, URL ou secret ne puisse sortir par l'API de santé.
    """
    tenant = _tenant(tenant)
    lignes = _toutes(
        conn,
        "SELECT ss.tenant_id, ss.source_id, ss.jumeau_id, ss.intervalle_s, ss.next_run_at, "
        "       ss.last_run_at, ss.last_success_at, ss.last_error, ss.etat, ss.tentative, ss.max_tentatives, "
        "       s.nom, s.type, "
        "       EXTRACT(EPOCH FROM (now() - ss.last_success_at)) AS lag_s, "
        "       r.id AS run_id, r.etat AS run_etat, r.tentative AS run_tentative "
        "FROM source_schedule ss "
        "JOIN source s ON s.id = ss.source_id AND s.tenant_id = ss.tenant_id "
        "LEFT JOIN LATERAL ("
        "  SELECT id, etat, tentative FROM ingestion_run ir "
        "  WHERE ir.tenant_id = ss.tenant_id AND ir.source_id = ss.source_id "
        "  ORDER BY ir.cree_le DESC LIMIT 1"
        ") r ON true "
        "WHERE ss.tenant_id = %s ORDER BY s.nom, ss.source_id",
        (tenant,),
    )
    sources = []
    for ligne in lignes:
        lag = ligne.get("lag_s")
        lag_s = max(0, int(lag)) if lag is not None else None
        sources.append({
            "tenant_id": tenant,
            "source_id": ligne["source_id"],
            "jumeau_id": ligne["jumeau_id"],
            "nom": ligne["nom"],
            "type": ligne["type"],
            "etat": ligne["etat"],
            "sante": _sante({**ligne, "lag_s": lag_s}),
            "intervalle_s": ligne["intervalle_s"],
            "next_run_at": _date_publique(ligne.get("next_run_at")),
            "last_run_at": _date_publique(ligne.get("last_run_at")),
            "last_success_at": _date_publique(ligne.get("last_success_at")),
            "lag_s": lag_s,
            "last_error": assainir_erreur(ligne.get("last_error")),
            "tentative": ligne["tentative"],
            "max_tentatives": ligne["max_tentatives"],
            "run": ({"id": ligne["run_id"], "etat": ligne["run_etat"],
                     "tentative": ligne["run_tentative"]} if ligne.get("run_id") else None),
        })
    resume = {"total": len(sources), "saines": 0, "en_erreur": 0, "en_retard": 0,
              "en_pause": 0, "jamais_ingerees": 0, "en_attente_reprise": 0, "run_actifs": 0}
    cle = {"saine": "saines", "en_erreur": "en_erreur", "en_retard": "en_retard",
           "en_pause": "en_pause", "jamais_ingeree": "jamais_ingerees",
           "en_attente_reprise": "en_attente_reprise"}
    for source in sources:
        resume[cle[source["sante"]]] += 1
        if source["run"] and source["run"]["etat"] in ETATS_ACTIFS:
            resume["run_actifs"] += 1
    return {"tenant": tenant, "sources": sources, "resume": resume}


def runs_source(conn, source_id, tenant, limite=20) -> list[dict]:
    """Derniers runs d'une source du tenant, du plus récent au plus ancien, sans bail ni secret."""
    tenant = _tenant(tenant)
    source = _source(conn, source_id, tenant)
    limite = _borne_limite(limite, defaut=20, maximum=200)
    lignes = _toutes(
        conn,
        "SELECT * FROM ingestion_run WHERE tenant_id = %s AND source_id = %s "
        "ORDER BY cree_le DESC LIMIT %s",
        (tenant, source["id"], limite),
    )
    return [run_public(ligne) for ligne in lignes]


def pause_source(conn, source_id, tenant) -> dict:
    """Suspend la planification ; un run déjà en cours n'est pas annulé."""
    tenant = _tenant(tenant)
    source = _source(conn, source_id, tenant)
    with conn.transaction():
        schedule = _une(
            conn,
            "INSERT INTO source_schedule (tenant_id, source_id, jumeau_id, intervalle_s, next_run_at, etat) "
            "VALUES (%s, %s, %s, %s, now(), 'paused') "
            "ON CONFLICT (tenant_id, source_id) DO UPDATE SET etat = 'paused', maj_le = now() RETURNING *",
            (tenant, source["id"], source["jumeau_id"], INTERVALLE_DEFAUT),
        )
    return _schedule_publique(schedule)


def resume_source(conn, source_id, tenant) -> dict:
    """Relance la planification ; une source en pause redevient due immédiatement."""
    tenant = _tenant(tenant)
    source = _source(conn, source_id, tenant)
    with conn.transaction():
        schedule = _une(
            conn,
            "INSERT INTO source_schedule (tenant_id, source_id, jumeau_id, intervalle_s, next_run_at, etat) "
            "VALUES (%s, %s, %s, %s, now(), 'active') "
            "ON CONFLICT (tenant_id, source_id) DO UPDATE SET etat = 'active', "
            "next_run_at = least(source_schedule.next_run_at, now()), maj_le = now() RETURNING *",
            (tenant, source["id"], source["jumeau_id"], INTERVALLE_DEFAUT),
        )
    return _schedule_publique(schedule)


async def ingerer_run(conn, db, run, worker_id=None, fencing_token=None, *, veiller=None) -> dict:
    """Exécute un run réclamé : passe du gardien sur la seule source concernée, états et métriques journalisés.

    `gardien.veiller` est importé tardivement (il charge l'agent et le registre, inutiles au planificateur) et
    reste la seule porte d'ingestion : ce module ne réimplémente ni fetch, ni index, ni projection. La passe est
    monolithique ; les jalons INDEXING/EXTRACTING/PROJECTING sont consignés après son retour, dans l'ordre, pour
    que l'API montre la progression sans prétendre instrumenter l'intérieur du gardien.
    """
    if not isinstance(run, Mapping):
        run = _verrou_run(conn, run)
    worker_id = worker_id or run.get("bail_proprietaire")
    fencing_token = fencing_token if fencing_token is not None else run.get("fencing_token")
    if not worker_id or fencing_token is None:
        raise ValueError("run non réclamé : worker_id et fencing_token requis")
    identifiant = run["id"]
    source = None
    try:
        source = _source(conn, run["source_id"], run["tenant_id"])
        marquer_etape(conn, identifiant, worker_id, fencing_token, "FETCHING",
                      tenant_id=run["tenant_id"])
        if veiller is None:
            from jumeau import gardien  # import tardif : le planificateur ne charge pas l'agent
            veiller = gardien.veiller
        journal.info("ingestion run %s : veille de %s (%s)", identifiant, run["jumeau_id"],
                     source.get("nom"))
        await veiller(conn, db, run["jumeau_id"], chemins=[source["emplacement"]])
        source_apres = _source(conn, run["source_id"], run["tenant_id"])
        observed_sha = source_apres.get("curseur")
        for etape in ("INDEXING", "EXTRACTING", "PROJECTING"):
            marquer_etape(conn, identifiant, worker_id, fencing_token, etape,
                          tenant_id=run["tenant_id"])
        run = terminer(
            conn, identifiant, worker_id, fencing_token,
            resultat={"previous_sha": run.get("previous_sha"), "observed_sha": observed_sha,
                      "changement": bool(observed_sha and observed_sha != run.get("previous_sha"))},
            observed_sha=observed_sha, tenant_id=run["tenant_id"])
        return run
    except Exception as erreur:  # noqa: BLE001 - tout échec devient un état durable, jamais un crash worker
        journal.warning("ingestion run %s : échec (%s)", identifiant, type(erreur).__name__)
        try:
            return echouer(conn, identifiant, worker_id, fencing_token, erreur,
                           tenant_id=run["tenant_id"])
        except Exception:  # bail perdu : le fencing empêche déjà l'ancien worker de committer
            journal.warning("ingestion run %s : échec non consigné (bail perdu)", identifiant,
                            exc_info=True)
            return _une(conn, "SELECT * FROM ingestion_run WHERE id = %s", (identifiant,)) or dict(run)


__all__ = [
    "ETATS_RUN", "ETATS_ACTIFS", "ETATS_TERMINAUX", "ETAPES",
    "SourceIntrouvable", "TransitionInvalide",
    "assainir_erreur", "backoff_secondes", "echouer", "enfiler_du", "enfiler_source",
    "ingerer_run", "marquer_etape", "pause_source", "planifier_source", "reclamer_run",
    "renouveler_bail", "reprendre_baux_expires", "resume_source", "run_public",
    "runs_source", "sante_sources", "terminer",
]
