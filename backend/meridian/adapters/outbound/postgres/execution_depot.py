"""Dépôt Postgres du runtime d'exécution.

Pas d'ORM, pas de dépendance FastAPI : les fonctions prennent une connexion psycopg
et restent utilisables par l'API, un worker, un test ou un futur adapter AWS.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.application.execution.modele import (
    ApprobationIntrouvable,
    CommandeExecution,
    ETATS_ACTIFS,
    ETATS_TERMINAUX,
    ConflitApprobation,
    ConflitIdempotence,
    EffetRejete,
    EtatRun,
    QuotaDepasse,
    RunIntrouvable,
    TransitionInvalide,
)

QUOTA_ACTIFS_DEFAUT = 20
QUOTA_ENV = "EXECUTION_MAX_ACTIFS_PAR_TENANT"


def max_actifs_par_tenant(env=None) -> int:
    """Plafond de runs actifs par tenant, lu à chaque création (défaut 20).

    Une valeur absente ou invalide retombe sur le défaut ; une valeur positive est
    respectée telle quelle. Le quota ne s'applique qu'à la création d'un nouveau run.
    """
    source = os.environ if env is None else env
    try:
        valeur = int(str(source.get(QUOTA_ENV) or "").strip())
    except (TypeError, ValueError):
        return QUOTA_ACTIFS_DEFAUT
    return valeur if valeur > 0 else QUOTA_ACTIFS_DEFAUT


def _jsonb(valeur: Mapping[str, Any] | None) -> Jsonb:
    return Jsonb(dict(valeur or {}))


def _json(valeur: Any) -> Jsonb | None:
    return None if valeur is None else Jsonb(valeur)


def empreinte_payload(payload: Mapping[str, Any] | None) -> str:
    canonique = json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), default=str)
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


def _cursor(conn):
    return conn.cursor(row_factory=dict_row)


def _une(conn, sql: str, params: Iterable[Any] = ()) -> dict | None:
    with _cursor(conn) as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchone()


def _toutes(conn, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _cursor(conn) as cur:
        cur.execute(sql, tuple(params))
        return list(cur.fetchall())


def _public_valeur(valeur):
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {k: _public_valeur(v) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_public_valeur(v) for v in valeur]
    return valeur


def run_public(run: Mapping[str, Any] | None) -> dict | None:
    if run is None:
        return None
    champs = (
        "tenant_id", "run_id", "command_id", "type", "etat",
        "priorite", "acteur", "correlation_id", "causation_id", "deadline_at",
        "cancel_requested_at", "tentative", "max_tentatives", "resultat",
        "erreur", "cree_le", "demarre_le", "fini_le", "maj_le",
    )
    return {champ: _public_valeur(run.get(champ)) for champ in champs}


def effet_public(effet: Mapping[str, Any] | None) -> dict | None:
    if effet is None:
        return None
    champs = (
        "tenant_id", "run_id", "etape", "cible", "operation", "outil", "politique",
        "statut", "payload", "resultat", "erreur", "tentatives",
        "cree_le", "maj_le", "execute_le",
    )
    return {champ: _public_valeur(effet.get(champ)) for champ in champs}


def approbation_public(approbation: Mapping[str, Any] | None) -> dict | None:
    if approbation is None:
        return None
    champs = (
        "id", "tenant_id", "run_id", "etape", "outil", "cible", "operation",
        "payload", "statut", "demandeur", "acteur", "motif", "cree_le", "decide_le",
    )
    return {champ: _public_valeur(approbation.get(champ)) for champ in champs}


def approbation_resume(approbation: Mapping[str, Any] | None) -> dict | None:
    """Vue de liste sans payload : aucun secret ni contenu d'effet n'est exposé."""
    if approbation is None:
        return None
    champs = (
        "id", "tenant_id", "run_id", "etape", "outil", "cible", "operation",
        "statut", "demandeur", "acteur", "motif", "cree_le", "decide_le",
    )
    return {champ: _public_valeur(approbation.get(champ)) for champ in champs}


def etape_public(etape: Mapping[str, Any] | None) -> dict | None:
    if etape is None:
        return None
    champs = (
        "tenant_id", "run_id", "seq", "nom", "etat", "entree", "sortie",
        "erreur", "cree_le", "demarre_le", "fini_le", "maj_le",
    )
    return {champ: _public_valeur(etape.get(champ)) for champ in champs}


def evenement_public(evenement: Mapping[str, Any]) -> dict:
    return {
        "id": int(evenement["id"]),
        "run_id": evenement["run_id"],
        "type": evenement["type"],
        "donnees": _public_valeur(evenement.get("donnees") or {}),
        "cree_le": _public_valeur(evenement.get("cree_le")),
    }


def ajouter_evenement(conn, tenant_id: str, run_id: str, type_: str,
                      donnees: Mapping[str, Any] | None = None) -> int:
    with _cursor(conn) as cur:
        cur.execute(
            "INSERT INTO execution_evenement (tenant_id, run_id, type, donnees) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (tenant_id, run_id, type_, _jsonb(donnees)),
        )
        return int(cur.fetchone()["id"])


def ajouter_outbox(conn, tenant_id: str, run_id: str, type_: str,
                   payload: Mapping[str, Any] | None = None) -> int:
    with _cursor(conn) as cur:
        cur.execute(
            "INSERT INTO execution_outbox (tenant_id, run_id, type, payload) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (tenant_id, run_id, type_, _jsonb(payload)),
        )
        return int(cur.fetchone()["id"])


def _emettre(conn, tenant_id: str, run_id: str, type_: str,
             donnees: Mapping[str, Any] | None = None) -> None:
    ajouter_evenement(conn, tenant_id, run_id, type_, donnees)
    ajouter_outbox(conn, tenant_id, run_id, type_, donnees)


def compter_runs_actifs(conn, tenant_id: str) -> int:
    valeur = _une(
        conn,
        "SELECT count(*) AS n FROM execution_run WHERE tenant_id = %s AND etat = ANY(%s)",
        (tenant_id, list(ETATS_ACTIFS)),
    )
    return int(valeur["n"]) if valeur else 0


def creer_run(conn, commande: CommandeExecution, *,
              max_actifs: int | None = None) -> tuple[dict, bool]:
    """Crée un run, ou retourne le run déjà créé pour la même clé d'idempotence.

    Le run et son premier événement sont écrits dans la même transaction. Le booléen
    indique si le run vient d'être créé (`True`) ou s'il existait déjà (`False`).
    La création d'un nouveau run est refusée quand le tenant atteint son quota de runs
    actifs ; un rejeu idempotent reste toujours accepté.
    """
    with conn.transaction():
        # Sérialise les créations d'un même tenant pour que le quota ne soit pas dépassé
        # par deux workers concurrents.
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('execution_quota'), hashtext(%s))",
            (commande.tenant_id,),
        )
        empreinte = empreinte_payload(commande.payload)
        existant = _une(
            conn,
            "SELECT * FROM execution_run WHERE tenant_id = %s AND idempotency_key = %s",
            (commande.tenant_id, commande.idempotency_key),
        )
        if existant is not None:
            if (existant.get("type") != commande.type
                    or existant.get("acteur") != commande.acteur
                    or existant.get("payload_empreinte") != empreinte):
                raise ConflitIdempotence(
                    "idempotency_key déjà utilisée avec un autre type, acteur ou payload")
            return existant, False
        limite = max_actifs_par_tenant() if max_actifs is None else int(max_actifs)
        actifs = compter_runs_actifs(conn, commande.tenant_id)
        if limite > 0 and actifs >= limite:
            raise QuotaDepasse(commande.tenant_id, limite, actifs)
        with _cursor(conn) as cur:
            cur.execute(
                "INSERT INTO execution_run ("
                "tenant_id, run_id, command_id, type, idempotency_key, payload, payload_empreinte, "
                "etat, priorite, acteur, correlation_id, causation_id, deadline_at"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING *",
                (
                    commande.tenant_id, commande.run_id, commande.command_id, commande.type,
                    commande.idempotency_key, _jsonb(commande.payload), empreinte,
                    EtatRun.QUEUED.value, commande.priorite.value, commande.acteur,
                    commande.correlation_id, commande.causation_id, commande.deadline_at,
                ),
            )
            run = cur.fetchone()
        if run is None:  # collision improbable : un autre écrivain a inséré puis supprimé
            raise TransitionInvalide("idempotence : run introuvable après conflit")
        _emettre(conn, commande.tenant_id, commande.run_id, "run.queued", {
            "run_id": commande.run_id,
            "type": commande.type,
            "etat": EtatRun.QUEUED.value,
        })
        return run, True


def obtenir_run(conn, tenant_id: str, run_id: str) -> dict | None:
    return _une(conn, "SELECT * FROM execution_run WHERE tenant_id = %s AND run_id = %s",
                (tenant_id, run_id))


def run_par_idempotence(conn, tenant_id: str, cle: str) -> dict | None:
    return _une(conn, "SELECT * FROM execution_run WHERE tenant_id = %s AND idempotency_key = %s",
                (tenant_id, cle))


def reclamer_run(conn, worker_id: str, bail_secondes: int = 30) -> dict | None:
    """Réserve atomiquement le prochain run en file. Aucun run n'est réservé deux fois."""
    with conn.transaction():
        with _cursor(conn) as cur:
            cur.execute(
                "WITH candidat AS ("
                "  SELECT tenant_id, run_id FROM execution_run"
                "  WHERE etat = %s AND (deadline_at IS NULL OR deadline_at > now())"
                "  ORDER BY CASE priorite WHEN 'interactive' THEN 0 WHEN 'standard' THEN 1 ELSE 2 END, cree_le"
                "  FOR UPDATE SKIP LOCKED LIMIT 1"
                ") "
                "UPDATE execution_run r SET "
                "  etat = %s, bail_proprietaire = %s, "
                "  bail_jusqu_a = now() + (%s * interval '1 second'), "
                "  fencing_token = r.fencing_token + 1, tentative = r.tentative + 1, "
                "  demarre_le = coalesce(r.demarre_le, now()), maj_le = now() "
                "FROM candidat c WHERE r.tenant_id = c.tenant_id AND r.run_id = c.run_id RETURNING r.*",
                (EtatRun.QUEUED.value, EtatRun.RUNNING.value, worker_id, int(bail_secondes)),
            )
            run = cur.fetchone()
        if run:
            _emettre(conn, run["tenant_id"], run["run_id"], "run.started", {
                "run_id": run["run_id"], "etat": EtatRun.RUNNING.value,
                "tentative": run["tentative"], "worker": worker_id,
            })
        return run


def renouveler_bail(conn, tenant_id: str, run_id: str, worker_id: str,
                    fencing_token: int, bail_secondes: int = 30) -> bool:
    with conn.transaction():
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_run SET bail_jusqu_a = now() + (%s * interval '1 second'), maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND etat = %s "
                "AND bail_proprietaire = %s AND fencing_token = %s AND bail_jusqu_a > now() "
                "RETURNING run_id",
                (int(bail_secondes), tenant_id, run_id, EtatRun.RUNNING.value, worker_id, int(fencing_token)),
            )
            return cur.fetchone() is not None


def _verrou(conn, tenant_id: str, run_id: str) -> dict | None:
    return _une(conn, "SELECT * FROM execution_run WHERE tenant_id = %s AND run_id = %s FOR UPDATE",
                (tenant_id, run_id))


def terminer(conn, tenant_id: str, run_id: str, worker_id: str, fencing_token: int,
             etat: EtatRun | str, resultat: Mapping[str, Any] | None = None,
             erreur: str | None = None) -> dict:
    etat = EtatRun(etat) if not isinstance(etat, EtatRun) else etat
    if etat.value not in ETATS_TERMINAUX:
        raise TransitionInvalide(f"état terminal attendu, reçu {etat.value}")
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        if run["etat"] in ETATS_TERMINAUX:
            return run
        if run["etat"] != EtatRun.RUNNING.value or run["bail_proprietaire"] != worker_id:
            raise TransitionInvalide("seul le worker propriétaire d'un run RUNNING peut le terminer")
        if run["fencing_token"] != int(fencing_token):
            raise TransitionInvalide("fencing token périmé")
        if run["bail_jusqu_a"] is None or run["bail_jusqu_a"] <= datetime.now(timezone.utc):
            raise TransitionInvalide("bail expiré")
        if run["cancel_requested_at"] and etat in (EtatRun.SUCCEEDED, EtatRun.FAILED):
            etat = EtatRun.CANCELLED
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_run SET etat = %s, resultat = %s, erreur = %s, fini_le = now(), "
                "bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                (etat.value, _jsonb(resultat), (erreur or "")[:2000] or None, tenant_id, run_id),
            )
            run = cur.fetchone()
        _emettre(conn, tenant_id, run_id, f"run.{etat.value.lower()}", {
            "run_id": run_id, "etat": etat.value, "resultat": dict(resultat or {}),
            **({"erreur": erreur[:2000]} if erreur else {}),
        })
        return run


def obtenir_effet(conn, tenant_id: str, run_id: str, etape: str, cible: str,
                  operation: str) -> dict | None:
    return _une(
        conn,
        "SELECT * FROM execution_effet WHERE tenant_id = %s AND run_id = %s "
        "AND etape = %s AND cible = %s AND operation = %s",
        (tenant_id, run_id, etape, cible, operation),
    )


def obtenir_approbation(conn, tenant_id: str, run_id: str, etape: str, cible: str,
                        operation: str) -> dict | None:
    return _une(
        conn,
        "SELECT * FROM execution_approbation WHERE tenant_id = %s AND run_id = %s "
        "AND etape = %s AND cible = %s AND operation = %s",
        (tenant_id, run_id, etape, cible, operation),
    )


def lister_approbations(conn, tenant_id: str, *, run_id: str | None = None,
                        statut: str = "PROPOSE", limite: int = 50,
                        avant_id: int | None = None) -> list[dict]:
    """Liste bornée des approbations du tenant, sans payload.

    `statut` est restreint au vocabulaire de la table ; `avant_id` permet de paginer
    vers les demandes plus anciennes.
    """
    statut = str(statut or "PROPOSE").upper()
    if statut not in {"PROPOSE", "APPROUVE", "REJETE"}:
        raise ValueError("statut d'approbation inconnu")
    bornes = max(1, min(int(limite), 200))
    filtres = ["tenant_id = %s", "statut = %s"]
    params: list[Any] = [tenant_id, statut]
    if run_id is not None:
        filtres.append("run_id = %s")
        params.append(run_id)
    if avant_id is not None:
        filtres.append("id < %s")
        params.append(int(avant_id))
    params.append(bornes)
    return _toutes(
        conn,
        "SELECT * FROM execution_approbation WHERE " + " AND ".join(filtres)
        + " ORDER BY id DESC LIMIT %s",
        params,
    )


def obtenir_approbation_par_id(conn, tenant_id: str, approbation_id: int) -> dict | None:
    return _une(
        conn,
        "SELECT * FROM execution_approbation WHERE tenant_id = %s AND id = %s",
        (tenant_id, int(approbation_id)),
    )


def etapes_run(conn, tenant_id: str, run_id: str) -> list[dict]:
    return _toutes(
        conn,
        "SELECT * FROM execution_etape WHERE tenant_id = %s AND run_id = %s "
        "ORDER BY seq, nom",
        (tenant_id, run_id),
    )


def obtenir_etape(conn, tenant_id: str, run_id: str, nom: str) -> dict | None:
    return _une(
        conn,
        "SELECT * FROM execution_etape WHERE tenant_id = %s AND run_id = %s AND nom = %s",
        (tenant_id, run_id, nom),
    )


def demarrer_etape(conn, tenant_id: str, run_id: str, nom: str, *, seq: int | None = None,
                   entree: Mapping[str, Any] | None = None,
                   forcer: bool = False) -> tuple[dict, bool]:
    """Journalise le début d'une étape.

    Retourne `(etape, deja_terminee)`. Une étape TERMINE est rendue telle quelle,
    sauf `forcer=True` qui la remet EN_COURS (rejeu explicite sans checkpoint).
    """
    nom = str(nom or "").strip()
    if not nom:
        raise ValueError("nom d'étape requis")
    with conn.transaction():
        run = _une(
            conn, "SELECT run_id FROM execution_run WHERE tenant_id = %s AND run_id = %s",
            (tenant_id, run_id),
        )
        if run is None:
            raise RunIntrouvable(run_id)
        etape = obtenir_etape(conn, tenant_id, run_id, nom)
        if etape is not None and etape["etat"] == "TERMINE" and not forcer:
            return etape, True
        if etape is None:
            position = int(seq) if seq is not None else _prochain_seq(conn, tenant_id, run_id)
            with _cursor(conn) as cur:
                cur.execute(
                    "INSERT INTO execution_etape ("
                    "tenant_id, run_id, seq, nom, etat, entree, demarre_le"
                    ") VALUES (%s, %s, %s, %s, 'EN_COURS', %s, now()) RETURNING *",
                    (tenant_id, run_id, position, nom, _jsonb(entree)),
                )
                etape = cur.fetchone()
        else:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE execution_etape SET etat = 'EN_COURS', entree = %s, erreur = NULL, "
                    "demarre_le = now(), fini_le = NULL, maj_le = now() "
                    "WHERE tenant_id = %s AND run_id = %s AND nom = %s RETURNING *",
                    (_jsonb(entree), tenant_id, run_id, nom),
                )
                etape = cur.fetchone()
        _emettre(conn, tenant_id, run_id, "execution.etape.demarree", {
            "run_id": run_id, "seq": int(etape["seq"]), "nom": nom, "etat": "EN_COURS",
        })
        return etape, False


def _prochain_seq(conn, tenant_id: str, run_id: str) -> int:
    valeur = _une(
        conn,
        "SELECT coalesce(max(seq), -1) + 1 AS seq FROM execution_etape "
        "WHERE tenant_id = %s AND run_id = %s",
        (tenant_id, run_id),
    )
    return int(valeur["seq"]) if valeur else 0


def terminer_etape(conn, tenant_id: str, run_id: str, nom: str,
                   sortie: Any = None) -> dict:
    """Clôt une étape TERMINE et persiste son checkpoint (`sortie`). Idempotent."""
    with conn.transaction():
        etape = _une(
            conn,
            "SELECT * FROM execution_etape WHERE tenant_id = %s AND run_id = %s AND nom = %s "
            "FOR UPDATE",
            (tenant_id, run_id, nom),
        )
        if etape is None:
            raise TransitionInvalide(f"étape {nom!r} introuvable")
        if etape["etat"] == "TERMINE":
            return etape
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_etape SET etat = 'TERMINE', sortie = %s, erreur = NULL, "
                "fini_le = now(), maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND nom = %s RETURNING *",
                (_json(sortie), tenant_id, run_id, nom),
            )
            etape = cur.fetchone()
        _emettre(conn, tenant_id, run_id, "execution.etape.terminee", {
            "run_id": run_id, "seq": int(etape["seq"]), "nom": nom, "etat": "TERMINE",
        })
        return etape


def clore_etape(conn, tenant_id: str, run_id: str, nom: str, etat: str,
                erreur: str | None = None) -> dict:
    """Clôt une étape non terminée en ECHEC, ANNULE ou SUSPENDU."""
    etat = str(etat or "").upper()
    if etat not in {"ECHEC", "ANNULE", "SUSPENDU"}:
        raise ValueError("état de clôture d'étape inconnu")
    with conn.transaction():
        etape = _une(
            conn,
            "SELECT * FROM execution_etape WHERE tenant_id = %s AND run_id = %s AND nom = %s "
            "FOR UPDATE",
            (tenant_id, run_id, nom),
        )
        if etape is None:
            raise TransitionInvalide(f"étape {nom!r} introuvable")
        if etape["etat"] == "TERMINE":
            return etape
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_etape SET etat = %s, erreur = %s, fini_le = now(), maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND nom = %s RETURNING *",
                (etat, (erreur or "")[:2000] or None, tenant_id, run_id, nom),
            )
            etape = cur.fetchone()
        _emettre(conn, tenant_id, run_id, f"execution.etape.{etat.lower()}", {
            "run_id": run_id, "seq": int(etape["seq"]), "nom": nom, "etat": etat,
            **({"erreur": (erreur or "")[:2000]} if erreur else {}),
        })
        return etape


def journaliser_etape(conn, tenant_id: str, run_id: str, nom: str, *,
                      etat: str = "EN_COURS", seq: int | None = None,
                      entree: Mapping[str, Any] | None = None,
                      sortie: Any = None, erreur: str | None = None) -> dict:
    """Contrat en un appel : journalise EN_COURS, TERMINE ou une clôture non terminale."""
    etat = str(etat or "").upper()
    if etat == "EN_COURS":
        return demarrer_etape(
            conn, tenant_id, run_id, nom, seq=seq, entree=entree, forcer=True)[0]
    if etat == "TERMINE":
        if obtenir_etape(conn, tenant_id, run_id, nom) is None:
            demarrer_etape(conn, tenant_id, run_id, nom, seq=seq, entree=entree)
        return terminer_etape(conn, tenant_id, run_id, nom, sortie)
    if etat in {"ECHEC", "ANNULE", "SUSPENDU"}:
        if obtenir_etape(conn, tenant_id, run_id, nom) is None:
            demarrer_etape(conn, tenant_id, run_id, nom, seq=seq, entree=entree)
        return clore_etape(conn, tenant_id, run_id, nom, etat, erreur)
    raise ValueError("état d'étape inconnu")


def reprendre_run(conn, tenant_id: str, run_id: str) -> dict:
    """Remet en file un run RUNNING dont le bail a expiré (reprise après crash).

    Un bail encore valide est refusé pour ne pas dupliquer un travail vivant. Les
    étapes EN_COURS restent en place : le prochain ProcessManager les rejoue, les
    étapes TERMINE sont conservées comme checkpoints.
    """
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        if run["etat"] in ETATS_TERMINAUX:
            return run
        if run["etat"] == EtatRun.QUEUED.value:
            return run
        if run["etat"] != EtatRun.RUNNING.value:
            raise TransitionInvalide("seul un run RUNNING au bail expiré peut être repris")
        if run["bail_jusqu_a"] is not None and run["bail_jusqu_a"] > datetime.now(timezone.utc):
            raise TransitionInvalide("le bail du run est encore valide")
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_etape SET etat = 'EN_ATTENTE', maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND etat = 'EN_COURS'",
                (tenant_id, run_id),
            )
            cur.execute(
                "UPDATE execution_run SET etat = %s, bail_proprietaire = NULL, "
                "bail_jusqu_a = NULL, maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                (EtatRun.QUEUED.value, tenant_id, run_id),
            )
            run = cur.fetchone()
        _emettre(conn, tenant_id, run_id, "run.requeued", {
            "run_id": run_id, "etat": EtatRun.QUEUED.value, "motif": "bail expiré",
        })
        return run


def proposer_effet(conn, tenant_id: str, run_id: str, *, etape: str, cible: str,
                   operation: str, outil: str, acteur: str,
                   payload: Mapping[str, Any] | None = None,
                   worker_id: str | None = None,
                   fencing_token: int | None = None) -> tuple[dict, bool]:
    """Enregistre un effet d'écriture proposé et met le run en attente d'approbation."""
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        effet = _une(
            conn,
            "SELECT * FROM execution_effet WHERE tenant_id = %s AND run_id = %s "
            "AND etape = %s AND cible = %s AND operation = %s FOR UPDATE",
            (tenant_id, run_id, etape, cible, operation),
        )
        if effet is not None:
            if effet["outil"] != outil or dict(effet["payload"] or {}) != dict(payload or {}):
                raise ConflitIdempotence(
                    "clé d'effet déjà utilisée avec un autre outil ou payload")
            return effet, False
        if run["etat"] != EtatRun.RUNNING.value:
            raise TransitionInvalide("un effet ne peut être proposé que depuis RUNNING")
        if worker_id is not None and run["bail_proprietaire"] != worker_id:
            raise TransitionInvalide("worker non propriétaire du run")
        if fencing_token is not None and int(run["fencing_token"]) != int(fencing_token):
            raise TransitionInvalide("fencing token périmé")
        with _cursor(conn) as cur:
            cur.execute(
                "INSERT INTO execution_effet ("
                "tenant_id, run_id, etape, cible, operation, outil, politique, statut, payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, 'ecriture', 'PROPOSE', %s) RETURNING *",
                (tenant_id, run_id, etape, cible, operation, outil, _jsonb(payload)),
            )
            effet = cur.fetchone()
            cur.execute(
                "INSERT INTO execution_approbation ("
                "tenant_id, run_id, etape, outil, cible, operation, payload, statut, demandeur"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, 'PROPOSE', %s) RETURNING *",
                (tenant_id, run_id, etape, outil, cible, operation, _jsonb(payload), acteur),
            )
            cur.execute(
                "UPDATE execution_run SET etat = %s, bail_proprietaire = NULL, "
                "bail_jusqu_a = NULL, maj_le = now() WHERE tenant_id = %s AND run_id = %s",
                (EtatRun.WAITING_APPROVAL.value, tenant_id, run_id),
            )
        donnees = {
            "run_id": run_id, "etape": etape, "outil": outil, "cible": cible,
            "operation": operation, "statut": "PROPOSE", "acteur": acteur,
        }
        _emettre(conn, tenant_id, run_id, "execution.effet.propose", donnees)
        _emettre(conn, tenant_id, run_id, "run.waiting_approval", {
            **donnees, "etat": EtatRun.WAITING_APPROVAL.value,
        })
        return effet, True


def enregistrer_effet_lecture(conn, tenant_id: str, run_id: str, *, etape: str, cible: str,
                              operation: str, outil: str,
                              payload: Mapping[str, Any] | None,
                              resultat: Any) -> tuple[dict, bool]:
    """Enregistre un effet de lecture déjà exécuté ; la clé composite le rend idempotent."""
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        effet = _une(
            conn,
            "SELECT * FROM execution_effet WHERE tenant_id = %s AND run_id = %s "
            "AND etape = %s AND cible = %s AND operation = %s FOR UPDATE",
            (tenant_id, run_id, etape, cible, operation),
        )
        if effet is not None:
            if effet["outil"] != outil or dict(effet["payload"] or {}) != dict(payload or {}):
                raise ConflitIdempotence(
                    "clé d'effet déjà utilisée avec un autre outil ou payload")
            return effet, False
        if run["etat"] != EtatRun.RUNNING.value:
            raise TransitionInvalide("un effet ne peut être exécuté que depuis RUNNING")
        with _cursor(conn) as cur:
            cur.execute(
                "INSERT INTO execution_effet ("
                "tenant_id, run_id, etape, cible, operation, outil, politique, statut, "
                "payload, resultat, tentatives, execute_le"
                ") VALUES (%s, %s, %s, %s, %s, %s, 'lecture', 'EXECUTE', %s, %s, 1, now()) "
                "RETURNING *",
                (tenant_id, run_id, etape, cible, operation, outil, _jsonb(payload),
                 _json(resultat)),
            )
            effet = cur.fetchone()
        _emettre(conn, tenant_id, run_id, "execution.effet.execute", {
            "run_id": run_id, "etape": etape, "outil": outil, "cible": cible,
            "operation": operation, "statut": "EXECUTE", "politique": "lecture",
        })
        return effet, True


def marquer_effet_execute(conn, tenant_id: str, run_id: str, *, etape: str, cible: str,
                          operation: str, resultat: Any) -> tuple[dict, bool]:
    """Passe un effet approuvé à EXECUTE ; une seconde exécution retourne le résultat existant."""
    with conn.transaction():
        effet = _une(
            conn,
            "SELECT * FROM execution_effet WHERE tenant_id = %s AND run_id = %s "
            "AND etape = %s AND cible = %s AND operation = %s FOR UPDATE",
            (tenant_id, run_id, etape, cible, operation),
        )
        if effet is None:
            raise TransitionInvalide("effet introuvable")
        if effet["statut"] == "EXECUTE":
            return effet, False
        if effet["statut"] == "REJETE":
            raise EffetRejete(f"effet rejeté : {etape}/{cible}/{operation}")
        if effet["statut"] != "APPROUVE":
            raise TransitionInvalide("seul un effet approuvé peut être exécuté")
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_effet SET statut = 'EXECUTE', resultat = %s, erreur = NULL, "
                "execute_le = now(), tentatives = tentatives + 1, maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND etape = %s AND cible = %s "
                "AND operation = %s RETURNING *",
                (_json(resultat), tenant_id, run_id, etape, cible, operation),
            )
            effet = cur.fetchone()
        _emettre(conn, tenant_id, run_id, "execution.effet.execute", {
            "run_id": run_id, "etape": etape, "cible": cible, "operation": operation,
            "outil": effet["outil"], "statut": "EXECUTE",
        })
        return effet, True


def marquer_effet_echec(conn, tenant_id: str, run_id: str, *, etape: str, cible: str,
                        operation: str, erreur: str) -> dict | None:
    """Conserve l'approbation et trace l'échec : la prochaine tentative reste possible."""
    with conn.transaction():
        effet = _une(
            conn,
            "SELECT * FROM execution_effet WHERE tenant_id = %s AND run_id = %s "
            "AND etape = %s AND cible = %s AND operation = %s FOR UPDATE",
            (tenant_id, run_id, etape, cible, operation),
        )
        if effet is None or effet["statut"] != "APPROUVE":
            return effet
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_effet SET erreur = %s, tentatives = tentatives + 1, maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND etape = %s AND cible = %s "
                "AND operation = %s RETURNING *",
                ((erreur or "")[:2000] or None, tenant_id, run_id, etape, cible, operation),
            )
            effet = cur.fetchone()
        _emettre(conn, tenant_id, run_id, "execution.effet.echec", {
            "run_id": run_id, "etape": etape, "cible": cible, "operation": operation,
            "erreur": (erreur or "")[:2000],
        })
        return effet


def _rejeter_approbations_en_attente(conn, tenant_id: str, run_id: str, motif: str) -> int:
    approbations = _toutes(
        conn,
        "SELECT * FROM execution_approbation WHERE tenant_id = %s AND run_id = %s "
        "AND statut = 'PROPOSE' ORDER BY id FOR UPDATE",
        (tenant_id, run_id),
    )
    for approbation in approbations:
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_approbation SET statut = 'REJETE', acteur = 'systeme', "
                "motif = %s, decide_le = now() WHERE id = %s RETURNING *",
                (motif, approbation["id"]),
            )
            approbation = cur.fetchone()
            cur.execute(
                "UPDATE execution_effet SET statut = 'REJETE', maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND etape = %s AND cible = %s "
                "AND operation = %s AND statut = 'PROPOSE' RETURNING *",
                (tenant_id, run_id, approbation["etape"], approbation["cible"],
                 approbation["operation"]),
            )
        _emettre(conn, tenant_id, run_id, "execution.effet.rejete", {
            "run_id": run_id, "etape": approbation["etape"], "outil": approbation["outil"],
            "cible": approbation["cible"], "operation": approbation["operation"],
            "statut": "REJETE", "motif": motif,
        })
    return len(approbations)


def _decision_coherente(approbation: Mapping[str, Any], approuve: bool) -> bool:
    return approbation["statut"] == ("APPROUVE" if approuve else "REJETE")


def decider_approbation(conn, tenant_id: str, run_id: str, *, approuve: bool, acteur: str,
                        motif: str | None = None, etape: str | None = None,
                        cible: str | None = None, operation: str | None = None,
                        outil: str | None = None) -> dict:
    """Approuve ou rejette un effet ; l'approbation reprend le run, le rejet l'annule."""
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        filtres = ["tenant_id = %s", "run_id = %s"]
        params: list[Any] = [tenant_id, run_id]
        for nom, valeur in (("etape", etape), ("cible", cible),
                            ("operation", operation), ("outil", outil)):
            if valeur is not None:
                filtres.append(f"{nom} = %s")
                params.append(valeur)
        approbations = _toutes(
            conn,
            "SELECT * FROM execution_approbation WHERE " + " AND ".join(filtres)
            + " ORDER BY id FOR UPDATE",
            params,
        )
        if not approbations:
            raise ApprobationIntrouvable(
                f"aucune approbation pour le run {run_id} et la clé demandée")
        en_attente = [a for a in approbations if a["statut"] == "PROPOSE"]
        if not en_attente:
            if len(approbations) == 1 and _decision_coherente(approbations[0], approuve):
                effet = obtenir_effet(
                    conn, tenant_id, run_id, approbations[0]["etape"],
                    approbations[0]["cible"], approbations[0]["operation"],
                )
                return {"run": run, "effet": effet, "approbation": approbations[0]}
            raise ConflitApprobation("approbation déjà décidée autrement")
        if len(en_attente) > 1:
            raise TransitionInvalide("plusieurs approbations en attente : précisez l'effet")
        approbation = en_attente[0]
        if run["etat"] != EtatRun.WAITING_APPROVAL.value:
            raise TransitionInvalide("le run n'est pas en attente d'approbation")
        statut_effet = "APPROUVE" if approuve else "REJETE"
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_approbation SET statut = %s, acteur = %s, motif = %s, "
                "decide_le = now() WHERE id = %s RETURNING *",
                (statut_effet, acteur, (motif or "")[:2000] or None, approbation["id"]),
            )
            approbation = cur.fetchone()
            cur.execute(
                "UPDATE execution_effet SET statut = %s, maj_le = now() "
                "WHERE tenant_id = %s AND run_id = %s AND etape = %s AND cible = %s "
                "AND operation = %s RETURNING *",
                (statut_effet, tenant_id, run_id, approbation["etape"],
                 approbation["cible"], approbation["operation"]),
            )
            effet = cur.fetchone()
            if approuve:
                cur.execute(
                    "UPDATE execution_run SET etat = %s, erreur = NULL, fini_le = NULL, "
                    "bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                    "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                    (EtatRun.QUEUED.value, tenant_id, run_id),
                )
            else:
                cur.execute(
                    "UPDATE execution_run SET etat = %s, erreur = %s, fini_le = now(), "
                    "bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() "
                    "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                    (EtatRun.CANCELLED.value,
                     ((motif or "approbation rejetée")[:2000]), tenant_id, run_id),
                )
            run = cur.fetchone()
        _emettre(conn, tenant_id, run_id, f"execution.effet.{statut_effet.lower()}", {
            "run_id": run_id, "etape": approbation["etape"], "outil": approbation["outil"],
            "cible": approbation["cible"], "operation": approbation["operation"],
            "statut": statut_effet, "acteur": acteur,
            **({"motif": motif[:2000]} if motif else {}),
        })
        if approuve:
            _emettre(conn, tenant_id, run_id, "run.queued", {
                "run_id": run_id, "etat": EtatRun.QUEUED.value, "motif": "approbation approuvée",
            })
        else:
            _emettre(conn, tenant_id, run_id, "run.cancelled", {
                "run_id": run_id, "etat": EtatRun.CANCELLED.value,
                "motif": (motif or "approbation rejetée")[:2000],
            })
        return {"run": run, "effet": effet, "approbation": approbation}


def demander_annulation(conn, tenant_id: str, run_id: str) -> dict:
    """Demande l'annulation. Un run en file est annulé immédiatement ; un run RUNNING
    reçoit un drapeau et le worker décide à sa prochaine frontière coopérative."""
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        if run["etat"] in ETATS_TERMINAUX:
            return run
        deja_demande = run["cancel_requested_at"] is not None
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_run SET cancel_requested_at = coalesce(cancel_requested_at, now()), "
                "maj_le = now() WHERE tenant_id = %s AND run_id = %s RETURNING *",
                (tenant_id, run_id),
            )
            run = cur.fetchone()
        if not deja_demande and run["etat"] not in ETATS_TERMINAUX:
            _emettre(conn, tenant_id, run_id, "run.cancel_requested", {
                "run_id": run_id, "etat": run["etat"],
            })
        if run["etat"] in (EtatRun.QUEUED.value, EtatRun.WAITING_RETRY.value,
                           EtatRun.WAITING_APPROVAL.value):
            if run["etat"] == EtatRun.WAITING_APPROVAL.value:
                _rejeter_approbations_en_attente(conn, tenant_id, run_id, "run annulé")
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE execution_run SET etat = %s, fini_le = now(), maj_le = now() "
                    "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                    (EtatRun.CANCELLED.value, tenant_id, run_id),
                )
                run = cur.fetchone()
            _emettre(conn, tenant_id, run_id, "run.cancelled", {
                "run_id": run_id, "etat": EtatRun.CANCELLED.value,
            })
        return run


def planifier_retry(conn, tenant_id: str, run_id: str, worker_id: str, fencing_token: int,
                    erreur: str, due_at: datetime | None = None) -> dict:
    due_at = due_at or (datetime.now(timezone.utc) + timedelta(seconds=5))
    with conn.transaction():
        run = _verrou(conn, tenant_id, run_id)
        if run is None:
            raise RunIntrouvable(run_id)
        if run["etat"] != EtatRun.RUNNING.value or run["bail_proprietaire"] != worker_id:
            raise TransitionInvalide("retry refusé : run non possédé")
        if run["fencing_token"] != int(fencing_token):
            raise TransitionInvalide("fencing token périmé")
        if run["cancel_requested_at"]:
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE execution_run SET etat = %s, bail_proprietaire = NULL, bail_jusqu_a = NULL, "
                    "erreur = %s, fini_le = now(), maj_le = now() "
                    "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                    (EtatRun.CANCELLED.value, (erreur or "")[:2000] or None, tenant_id, run_id),
                )
                run = cur.fetchone()
            _emettre(conn, tenant_id, run_id, "run.cancelled", {
                "run_id": run_id, "etat": EtatRun.CANCELLED.value,
                "motif": "annulation demandée pendant l'exécution",
            })
            return run
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE execution_run SET etat = %s, bail_proprietaire = NULL, bail_jusqu_a = NULL, "
                "erreur = %s, maj_le = now() WHERE tenant_id = %s AND run_id = %s RETURNING *",
                (EtatRun.WAITING_RETRY.value, (erreur or "")[:2000] or None, tenant_id, run_id),
            )
            run = cur.fetchone()
            cur.execute(
                "INSERT INTO execution_timer (tenant_id, run_id, type, due_at, payload) "
                "VALUES (%s, %s, %s, %s, %s)",
                (tenant_id, run_id, "run.retry", due_at, _jsonb({"erreur": erreur[:2000]})),
            )
        _emettre(conn, tenant_id, run_id, "run.waiting_retry", {
            "run_id": run_id, "etat": EtatRun.WAITING_RETRY.value, "due_at": due_at.isoformat(),
            "erreur": (erreur or "")[:2000],
        })
        return run


def reprendre_baux_expires(conn, limite: int = 50) -> list[dict]:
    """Requeue les RUNNING dont le bail est expiré ; un run annulé devient CANCELLED.

    Le fencing token n'est pas incrémenté ici : le prochain claim l'incrémente, et
    l'ancien worker ne peut plus committer avec son token périmé.
    """
    with conn.transaction():
        runs = _toutes(
            conn,
            "SELECT * FROM execution_run WHERE etat = %s AND bail_jusqu_a IS NOT NULL "
            "AND bail_jusqu_a <= now() ORDER BY bail_jusqu_a FOR UPDATE SKIP LOCKED LIMIT %s",
            (EtatRun.RUNNING.value, int(limite)),
        )
        for run in runs:
            if run["cancel_requested_at"]:
                etat = EtatRun.CANCELLED.value
                type_ = "run.cancelled"
            elif run["deadline_at"] is not None and run["deadline_at"] <= datetime.now(timezone.utc):
                etat = EtatRun.EXPIRED.value
                type_ = "run.expired"
            elif int(run["tentative"]) >= int(run["max_tentatives"]):
                etat = EtatRun.FAILED.value
                type_ = "run.failed"
            else:
                etat = EtatRun.QUEUED.value
                type_ = "run.requeued"
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE execution_run SET etat = %s, bail_proprietaire = NULL, bail_jusqu_a = NULL, "
                    "fini_le = CASE WHEN %s IN ('CANCELLED', 'EXPIRED') THEN now() ELSE fini_le END, "
                    "maj_le = now() WHERE tenant_id = %s AND run_id = %s RETURNING *",
                    (etat, etat, run["tenant_id"], run["run_id"]),
                )
                run = cur.fetchone()
            _emettre(conn, run["tenant_id"], run["run_id"], type_, {
                "run_id": run["run_id"], "etat": etat, "motif": "bail expiré",
            })
        return runs


def expirer_file(conn, limite: int = 50) -> list[dict]:
    """Marque EXPIRED les runs en file dont la deadline est dépassée."""
    with conn.transaction():
        runs = _toutes(
            conn,
            "SELECT * FROM execution_run WHERE etat IN (%s, %s, %s) "
            "AND deadline_at IS NOT NULL AND deadline_at <= now() "
            "ORDER BY deadline_at FOR UPDATE SKIP LOCKED LIMIT %s",
            (EtatRun.QUEUED.value, EtatRun.WAITING_RETRY.value,
             EtatRun.WAITING_APPROVAL.value, int(limite)),
        )
        for run in runs:
            if run["etat"] == EtatRun.WAITING_APPROVAL.value:
                _rejeter_approbations_en_attente(conn, run["tenant_id"], run["run_id"],
                                                 "deadline dépassée")
            with _cursor(conn) as cur:
                cur.execute(
                    "UPDATE execution_run SET etat = %s, fini_le = now(), bail_proprietaire = NULL, "
                    "bail_jusqu_a = NULL, maj_le = now() WHERE tenant_id = %s AND run_id = %s RETURNING *",
                    (EtatRun.EXPIRED.value, run["tenant_id"], run["run_id"]),
                )
                run = cur.fetchone()
            _emettre(conn, run["tenant_id"], run["run_id"], "run.expired", {
                "run_id": run["run_id"], "etat": EtatRun.EXPIRED.value,
            })
        return runs


def rearmer_timers(conn, limite: int = 50) -> list[dict]:
    """Remet en file les runs WAITING_RETRY dont le timer est dû."""
    with conn.transaction():
        timers = _toutes(
            conn,
            "SELECT * FROM execution_timer WHERE traite_le IS NULL AND due_at <= now() "
            "ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT %s",
            (int(limite),),
        )
        for timer in timers:
            run = _verrou(conn, timer["tenant_id"], timer["run_id"])
            if run and run["etat"] == EtatRun.WAITING_RETRY.value and run["cancel_requested_at"]:
                with _cursor(conn) as cur:
                    cur.execute(
                        "UPDATE execution_run SET etat = %s, fini_le = now(), maj_le = now() "
                        "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                        (EtatRun.CANCELLED.value, run["tenant_id"], run["run_id"]),
                    )
                    run = cur.fetchone()
                _emettre(conn, run["tenant_id"], run["run_id"], "run.cancelled", {
                    "run_id": run["run_id"], "etat": EtatRun.CANCELLED.value,
                    "motif": "annulation demandée avant le retry",
                })
            elif run and run["etat"] == EtatRun.WAITING_RETRY.value:
                with _cursor(conn) as cur:
                    cur.execute(
                        "UPDATE execution_run SET etat = %s, maj_le = now() "
                        "WHERE tenant_id = %s AND run_id = %s RETURNING *",
                        (EtatRun.QUEUED.value, run["tenant_id"], run["run_id"]),
                    )
                    run = cur.fetchone()
                _emettre(conn, run["tenant_id"], run["run_id"], "run.requeued", {
                    "run_id": run["run_id"], "etat": EtatRun.QUEUED.value,
                })
            with _cursor(conn) as cur:
                cur.execute("UPDATE execution_timer SET traite_le = now() WHERE id = %s", (timer["id"],))
        return timers


def evenements(conn, tenant_id: str, run_id: str, apres_id: int = 0) -> list[dict]:
    return _toutes(
        conn,
        "SELECT * FROM execution_evenement WHERE tenant_id = %s AND run_id = %s AND id > %s "
        "ORDER BY id LIMIT 500",
        (tenant_id, run_id, int(apres_id)),
    )


def publier_outbox(conn, publieur, limite: int = 100) -> int:
    """Publie atomiquement les lignes dues : sélection, appel, marquage dans la même transaction.

    `publieur` doit être idempotent : la transaction peut être rejouée après un crash.
    """
    with conn.transaction():
        lignes = _toutes(
            conn,
            "SELECT * FROM execution_outbox WHERE publie_le IS NULL ORDER BY id "
            "FOR UPDATE SKIP LOCKED LIMIT %s",
            (int(limite),),
        )
        for ligne in lignes:
            publieur(ligne)
            conn.execute(
                "UPDATE execution_outbox SET publie_le = now(), tentatives = tentatives + 1 WHERE id = %s",
                (ligne["id"],),
            )
        return len(lignes)
