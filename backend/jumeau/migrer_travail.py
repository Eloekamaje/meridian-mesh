"""Compatibilité : backfill Travail Mongo -> Postgres.

    python -m jumeau.migrer_travail --tenant local --dry-run
    python -m jumeau.migrer_travail --tenant local --apply
"""
from meridian.adapters.inbound.worker.travail_worker import main_backfill

main = main_backfill

if __name__ == "__main__":
    raise SystemExit(main())
