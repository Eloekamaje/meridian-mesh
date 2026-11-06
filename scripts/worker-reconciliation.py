#!/usr/bin/env python3
"""Worker de réconciliation globale des liens.

Par défaut : dry-run, une passe toutes les heures. `--apply` persiste les propositions
et cas. Aucun lien n'est confirmé, aucun agent n'est appelé.

    JUMEAU_PG_DSN=... python scripts/worker-reconciliation.py --tenant banque --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

journal = logging.getLogger("meridian.reconciliation_worker")


def _limite(valeur) -> int:
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("limite doit être un entier positif") from exc
    if borne < 1:
        raise argparse.ArgumentTypeError("limite doit être un entier positif")
    return borne


def _executer(conn, tenants, *, appliquer: bool, limite: int | None):
    from meridian.adapters.outbound.postgres import decouverte_naissance

    with conn.transaction():
        rapports = [decouverte_naissance.reconcilier(
            conn, tenant, appliquer=appliquer, limite=limite) for tenant in tenants]
    for tenant, rapport in zip(tenants, rapports):
        mode = "apply" if appliquer else "dry-run"
        journal.info(
            "%s (%s) : %s twin(s), %s proposition(s), %s cas, %s non éligible(s)",
            tenant, mode, rapport["twins"], rapport["propositions"], rapport["cas"],
            len(rapport["non_eligibles"]))
    return rapports


def main(argv=None) -> int:
    from meridian.adapters.inbound.worker.reconciliation_worker import BoucleReconciliation

    analyseur = argparse.ArgumentParser(
        prog="python scripts/worker-reconciliation.py",
        description="Worker de réconciliation globale des liens")
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--tenant", default=None,
                           help="limiter à un tenant (défaut : tous les tenants)")
    analyseur.add_argument("--intervalle", type=float, default=3600,
                           help="secondes entre deux passes (défaut : 3600)")
    analyseur.add_argument("--limite", type=_limite, default=None,
                           help="borner le nombre de manifestes par tenant")
    analyseur.add_argument("--sans-schema", action="store_true",
                           help="ne pas rejouer schema.sql au démarrage")
    analyseur.add_argument("--une-passe", action="store_true",
                           help="exécuter une seule passe puis quitter")
    groupe = analyseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", dest="appliquer", action="store_false")
    groupe.add_argument("--apply", dest="appliquer", action="store_true")
    analyseur.set_defaults(appliquer=False)
    analyseur.add_argument("--log-level", default="INFO")
    args = analyseur.parse_args(argv)

    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    dsn = args.dsn or os.environ.get("JUMEAU_WORKER_PG_DSN") or os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise SystemExit("JUMEAU_PG_DSN (ou --dsn) requis")

    import psycopg

    from meridian.adapters.outbound.postgres import depot as postgres_depot

    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        if not args.sans_schema:
            postgres_depot.appliquer_schema(conn)
        if args.tenant:
            tenants = [args.tenant]
        else:
            tenants = [ligne[0] for ligne in conn.execute(
                "SELECT DISTINCT tenant_id FROM jumeau ORDER BY tenant_id").fetchall()]
        if not tenants:
            journal.warning("aucun tenant à réconcilier")
            return 0

        def passer():
            return _executer(conn, tenants, appliquer=args.appliquer, limite=args.limite)

        if args.une_passe:
            passer()
            return 0

        boucle = BoucleReconciliation(passer, intervalle=args.intervalle)

        def arreter(signum, frame):
            journal.info("arrêt demandé")
            boucle.arreter()

        signal.signal(signal.SIGTERM, arreter)
        signal.signal(signal.SIGINT, arreter)
        journal.info("worker réconciliation démarré (%s, %s s)", ", ".join(tenants),
                     boucle.intervalle)
        boucle.tourner()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
