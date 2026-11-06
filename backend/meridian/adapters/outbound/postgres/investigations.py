"""Runs durables des investigations applicatives.

Le store ne lance aucun modele. Il borne la file par tenant, reserve les runs sous
bail/fencing et n'accepte qu'une :class:`ContributionInvestigation` validee. Les
workers peuvent donc tomber puis reprendre sans qu'un ancien proprietaire publie
une contribution apres la perte de son bail.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres.ingestion_runtime import assainir_erreur, backoff_secondes
from meridian.domain.investigation import (
    BudgetInvestigation,
    ContributionInvestigation,
    contribution_depuis_dict,
)

ETATS_ACTIFS = ("QUEUED", "RUNNING", "RETRY_WAIT")
ETATS_TERMINAUX = ("COMPLETED", "COMPLETED_WITH_GAPS", "BUDGET_EXHAUSTED", "FAILED", "CANCELLED")
ETAT_CONTRIBUTION = {
    "completed": "COMPLETED",
    "completed_with_gaps": "COMPLETED_WITH_GAPS",
    "budget_exhausted": "BUDGET_EXHAUSTED",
    "failed": "FAILED",
}
BAIL_DEFAUT = 300
MAX_TENTATIVES_DEFAUT = 3


class InvestigationIntrouvable(LookupError):
    """Run ou jumeau absent du tenant courant."""


class TransitionInvalide(RuntimeError):
    """Transition refusee : etat, bail, proprietaire ou fencing perime."""


class CleIdempotenceReutilisee(ValueError):
    """Une meme cle designe deux demandes differentes."""


def _texte(valeur, nom: str, maximum: int, *, requis=True) -> str:
    texte = " ".join(str(valeur or "").split())
    if requis and not texte:
        raise ValueError(f"{nom} requis")
    if len(texte) > maximum:
        raise ValueError(f"{nom} trop long (maximum {maximum})")
    return texte


def _entier_positif(valeur, nom: str) -> int:
    if isinstance(valeur, bool):
        raise ValueError(f"{nom} doit etre un entier positif")
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        raise ValueError(f"{nom} doit etre un entier positif") from None
    if entier <= 0:
        raise ValueError(f"{nom} doit etre un entier positif")
    return entier


def _limite(valeur, defaut=50, maximum=200) -> int:
    try:
        return max(1, min(int(valeur), maximum))
    except (TypeError, ValueError):
        return defaut


def _budget(valeur) -> dict:
    if valeur is None:
        return BudgetInvestigation().as_dict()
    if isinstance(valeur, BudgetInvestigation):
        return valeur.as_dict()
    if not isinstance(valeur, Mapping):
        raise TypeError("budget doit etre un objet")
    return BudgetInvestigation(**dict(valeur)).as_dict()


def _cur(conn):
    return conn.cursor(row_factory=dict_row)


def _une(conn, sql: str, params: Iterable = ()) -> dict | None:
    with _cur(conn) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _toutes(conn, sql: str, params: Iterable = ()) -> list[dict]:
    with _cur(conn) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _date(valeur):
    return valeur.isoformat() if isinstance(valeur, datetime) else valeur


def _public(run: Mapping | None) -> dict | None:
    if run is None:
        return None
    champs = (
        "id", "tenant_id", "jumeau_id", "question_id", "objectif", "question", "statut",
        "budget", "tentative", "max_tentatives", "next_attempt_at", "erreur", "cree_le",
        "demarre_le", "fini_le", "maj_le",
    )
    return {champ: _date(run.get(champ)) for champ in champs}


def _empreinte(jumeau_id: str, question_id: str, objectif: str, question: str, budget: dict) -> str:
    brut = json.dumps(
        {"jumeau_id": jumeau_id, "question_id": question_id, "objectif": objectif,
         "question": question, "budget": budget},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(brut.encode()).hexdigest()


def creer_run(conn, tenant_id, jumeau_id, question_id, question, *, objectif="",
              cle_idempotence, budget=None, max_tentatives=MAX_TENTATIVES_DEFAUT) -> dict:
    """Cree une investigation QUEUED ou rend le rejeu strictement identique."""
    tenant = _texte(tenant_id, "tenant_id", 160)
    jumeau = _texte(jumeau_id, "jumeau_id", 160)
    qid = _texte(question_id, "question_id", 160)
    question = _texte(question, "question", 4000)
    objectif = _texte(objectif, "objectif", 2000, requis=False)
    cle = _texte(cle_idempotence, "cle_idempotence", 300)
    tentatives = _entier_positif(max_tentatives, "max_tentatives")
    budget_ = _budget(budget)
    empreinte = _empreinte(jumeau, qid, objectif, question, budget_)
    if _une(conn, "SELECT 1 FROM jumeau WHERE id = %s AND tenant_id = %s", (jumeau, tenant)) is None:
        raise InvestigationIntrouvable("jumeau introuvable")
    with conn.transaction():
        run = _une(
            conn,
            "INSERT INTO investigation_run "
            "(id, tenant_id, jumeau_id, question_id, objectif, question, cle_idempotence, "
            "request_fingerprint, budget, max_tentatives) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, cle_idempotence) DO NOTHING RETURNING *",
            (uuid.uuid4().hex, tenant, jumeau, qid, objectif, question, cle, empreinte,
             Jsonb(budget_), tentatives),
        )
        if run is None:
            run = _une(conn, "SELECT * FROM investigation_run WHERE tenant_id = %s AND cle_idempotence = %s "
                       "FOR UPDATE", (tenant, cle))
            if run is None:
                raise InvestigationIntrouvable("investigation introuvable")
            if run["request_fingerprint"] != empreinte:
                raise CleIdempotenceReutilisee("cle d'idempotence reutilisee avec une autre demande")
    return _public(run)


def reclamer_run(conn, worker_id, *, tenant_id=None, bail_secondes=BAIL_DEFAUT) -> dict | None:
    """Reserve atomiquement le prochain run du tenant (ou global pour un role worker dedie)."""
    worker = _texte(worker_id, "worker_id", 200)
    bail = _entier_positif(bail_secondes, "bail_secondes")
    filtre, params = "", [["QUEUED", "RETRY_WAIT"]]
    if tenant_id is not None:
        filtre = " AND tenant_id = %s"
        params.append(_texte(tenant_id, "tenant_id", 160))
    params.extend([worker, bail])
    with conn.transaction():
        return _une(
            conn,
            "WITH candidat AS (SELECT tenant_id, id FROM investigation_run "
            "WHERE statut = ANY(%s) AND (next_attempt_at IS NULL OR next_attempt_at <= now()) "
            "AND (bail_jusqu_a IS NULL OR bail_jusqu_a <= now())" + filtre + " "
            "ORDER BY cree_le, id FOR UPDATE SKIP LOCKED LIMIT 1) "
            "UPDATE investigation_run r SET statut = 'RUNNING', bail_proprietaire = %s, "
            "bail_jusqu_a = now() + (%s * interval '1 second'), fencing_token = r.fencing_token + 1, "
            "tentative = r.tentative + 1, demarre_le = coalesce(r.demarre_le, now()), "
            "next_attempt_at = NULL, maj_le = now() FROM candidat c "
            "WHERE r.tenant_id = c.tenant_id AND r.id = c.id RETURNING r.*",
            tuple(params),
        )


def renouveler_bail(conn, run_id, tenant_id, worker_id, fencing_token,
                    bail_secondes=BAIL_DEFAUT) -> bool:
    bail = _entier_positif(bail_secondes, "bail_secondes")
    with conn.transaction():
        ligne = _une(
            conn,
            "UPDATE investigation_run SET bail_jusqu_a = now() + (%s * interval '1 second'), maj_le = now() "
            "WHERE id = %s AND tenant_id = %s AND statut = 'RUNNING' AND bail_proprietaire = %s "
            "AND fencing_token = %s AND bail_jusqu_a > now() RETURNING id",
            (bail, str(run_id), str(tenant_id), str(worker_id), int(fencing_token)),
        )
    return ligne is not None


def _verrouiller(conn, run_id, tenant_id) -> dict:
    run = _une(conn, "SELECT * FROM investigation_run WHERE id = %s AND tenant_id = %s FOR UPDATE",
               (str(run_id), str(tenant_id)))
    if run is None:
        raise InvestigationIntrouvable("investigation introuvable")
    return run


def _exiger_proprietaire(run, worker_id, fencing_token) -> None:
    if run["statut"] != "RUNNING":
        raise TransitionInvalide("investigation non active")
    if run.get("bail_proprietaire") != str(worker_id):
        raise TransitionInvalide("investigation non possedee par ce worker")
    if int(run.get("fencing_token") or 0) != int(fencing_token):
        raise TransitionInvalide("fencing token perime")
    if run.get("bail_jusqu_a") is None or run["bail_jusqu_a"] <= datetime.now(timezone.utc):
        raise TransitionInvalide("bail expire")


def enregistrer_contribution(conn, run_id, tenant_id, worker_id, fencing_token,
                             contribution: ContributionInvestigation | Mapping) -> dict:
    """Valide puis publie contribution et etat final dans une seule transaction fencee."""
    if isinstance(contribution, Mapping):
        contribution = contribution_depuis_dict(contribution)
    if not isinstance(contribution, ContributionInvestigation):
        raise TypeError("contribution invalide")
    etat = ETAT_CONTRIBUTION.get(contribution.statut)
    if etat is None:
        raise TransitionInvalide("une contribution terminale est requise")
    document = contribution.as_dict()
    with conn.transaction():
        run = _verrouiller(conn, run_id, tenant_id)
        _exiger_proprietaire(run, worker_id, fencing_token)
        if contribution.investigation_id != run["id"] or contribution.question_id != run["question_id"]:
            raise TransitionInvalide("contribution rattachee a une autre investigation ou question")
        if contribution.twin_id != run["jumeau_id"]:
            raise TransitionInvalide("contribution rattachee a un autre jumeau")
        conn.execute(
            "INSERT INTO investigation_contribution (tenant_id, run_id, contribution) VALUES (%s, %s, %s)",
            (run["tenant_id"], run["id"], Jsonb(document)),
        )
        run = _une(
            conn,
            "UPDATE investigation_run SET statut = %s, budget = %s, erreur = NULL, fini_le = now(), "
            "bail_proprietaire = NULL, bail_jusqu_a = NULL, maj_le = now() WHERE id = %s RETURNING *",
            (etat, Jsonb(contribution.budget.as_dict()), run["id"]),
        )
    return _public(run)


def echouer(conn, run_id, tenant_id, worker_id, fencing_token, erreur) -> dict:
    """Programme une reprise avec backoff, puis termine FAILED apres epuisement."""
    message = assainir_erreur(erreur) or "investigation impossible"
    with conn.transaction():
        run = _verrouiller(conn, run_id, tenant_id)
        _exiger_proprietaire(run, worker_id, fencing_token)
        if int(run["tentative"]) < int(run["max_tentatives"]):
            run = _une(
                conn,
                "UPDATE investigation_run SET statut = 'RETRY_WAIT', erreur = %s, "
                "next_attempt_at = now() + (%s * interval '1 second'), bail_proprietaire = NULL, "
                "bail_jusqu_a = NULL, maj_le = now() WHERE id = %s RETURNING *",
                (message, backoff_secondes(run["tentative"]), run["id"]),
            )
        else:
            run = _une(
                conn,
                "UPDATE investigation_run SET statut = 'FAILED', erreur = %s, fini_le = now(), "
                "next_attempt_at = NULL, bail_proprietaire = NULL, bail_jusqu_a = NULL, "
                "maj_le = now() WHERE id = %s RETURNING *",
                (message, run["id"]),
            )
    return _public(run)


def reprendre_baux_expires(conn, limite=50) -> list[dict]:
    """Requeue les RUNNING abandonnes, ou les termine si les tentatives sont epuisees."""
    repris = []
    with conn.transaction():
        runs = _toutes(
            conn,
            "SELECT * FROM investigation_run WHERE statut = 'RUNNING' AND bail_jusqu_a <= now() "
            "ORDER BY bail_jusqu_a FOR UPDATE SKIP LOCKED LIMIT %s",
            (_limite(limite),),
        )
        for run in runs:
            if int(run["tentative"]) >= int(run["max_tentatives"]):
                statut, fini = "FAILED", ", fini_le = now()"
            else:
                statut, fini = "QUEUED", ""
            repris.append(_une(
                conn,
                f"UPDATE investigation_run SET statut = %s, erreur = 'bail expire : reprise', "
                f"next_attempt_at = %s, bail_proprietaire = NULL, bail_jusqu_a = NULL{fini}, "
                "maj_le = now() WHERE id = %s RETURNING *",
                (statut, None if statut == "FAILED" else datetime.now(timezone.utc), run["id"]),
            ))
    return [_public(run) for run in repris]


def lire_run(conn, tenant_id, run_id) -> dict:
    run = _une(conn, "SELECT * FROM investigation_run WHERE tenant_id = %s AND id = %s",
               (str(tenant_id), str(run_id)))
    if run is None:
        raise InvestigationIntrouvable("investigation introuvable")
    return _public(run)


def lister_runs(conn, tenant_id, *, jumeau_id=None, limite=50) -> list[dict]:
    sql = "SELECT * FROM investigation_run WHERE tenant_id = %s"
    params = [str(tenant_id)]
    if jumeau_id is not None:
        sql += " AND jumeau_id = %s"
        params.append(str(jumeau_id))
    sql += " ORDER BY cree_le DESC LIMIT %s"
    params.append(_limite(limite))
    return [_public(run) for run in _toutes(conn, sql, tuple(params))]


def lire_contribution(conn, tenant_id, run_id) -> dict | None:
    ligne = _une(
        conn,
        "SELECT c.contribution FROM investigation_contribution c JOIN investigation_run r ON r.id = c.run_id "
        "AND r.tenant_id = c.tenant_id WHERE c.tenant_id = %s AND c.run_id = %s",
        (str(tenant_id), str(run_id)),
    )
    return dict(ligne["contribution"]) if ligne else None

