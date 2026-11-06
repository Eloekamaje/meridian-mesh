#!/usr/bin/env python3
"""Indexe une racine legacy et écrit le rapport JSON des sidecars."""
import argparse
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv

from meridian.adapters.outbound.connectors.legacy_index import indexer_legacy

MODES_SQL_LIVE = ("postgres", "oracle")


def _resoudre_sql_live(demande, environnement=None):
    """Résout ``--sql-live`` sans ouvrir de connexion.

    ``None`` (option absente) reste désactivé ; ``auto`` lit ``JUMEAU_SQL_LIVE``.
    Une valeur absente ou vide désactive l'introspection.
    """
    if demande is None:
        return None
    if demande != "auto":
        return demande
    source = os.environ if environnement is None else environnement
    valeur = str(source.get("JUMEAU_SQL_LIVE", "") or "").strip().lower()
    if not valeur:
        return None
    if valeur not in MODES_SQL_LIVE:
        raise ValueError(
            f"JUMEAU_SQL_LIVE invalide : {valeur!r} "
            "(attendu : postgres, oracle ou vide)"
        )
    return valeur


def _valeur_environnement(environnement, nom):
    return str(environnement.get(nom, "") or "").strip()


def _verifier_select(sql: str) -> None:
    texte = str(sql or "").strip()
    if not texte.upper().startswith("SELECT"):
        raise ValueError("seule une instruction SELECT est autorisée")
    if ";" in texte.rstrip().rstrip(";").rstrip():
        raise ValueError("une seule instruction SELECT est autorisée")


def _executeur_postgres(connexion):
    def executer(sql, params=()):
        _verifier_select(sql)
        with connexion.cursor() as curseur:
            curseur.execute(sql, params or ())
            if curseur.description is None:
                return []
            return list(curseur.fetchall())
    return executer


def _ouvrir_postgres(dsn):
    import psycopg
    from psycopg.rows import dict_row
    connexion = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    try:
        connexion.read_only = True
    except (AttributeError, TypeError):
        pass
    return connexion, _executeur_postgres(connexion)


def _driver_oracle():
    try:
        import oracledb
    except ImportError as erreur:
        raise RuntimeError(
            "driver Oracle indisponible : installer python-oracledb (oracledb) "
            "ou utiliser --sql-live postgres"
        ) from erreur
    return oracledb


def _executeur_oracle(connexion):
    def executer(sql, params=()):
        _verifier_select(sql)
        curseur = connexion.cursor()
        try:
            curseur.execute(sql, list(params or ()))
            if curseur.description is None:
                return []
            noms = [str(description[0]).lower() for description in curseur.description]
            return [dict(zip(noms, ligne)) for ligne in curseur.fetchall()]
        finally:
            curseur.close()
    return executer


def _ouvrir_oracle(dsn, module=None):
    module = module or _driver_oracle()
    connexion = module.connect(dsn)
    return connexion, _executeur_oracle(connexion)


def _construire_sql_live(args, parser, mode=None, environnement=None):
    environnement = os.environ if environnement is None else environnement
    mode = mode if mode is not None else args.sql_live
    if mode == "auto":
        try:
            mode = _resoudre_sql_live(mode, environnement)
        except ValueError as erreur:
            parser.error(str(erreur))
    if mode is None:
        return None, None
    if mode not in MODES_SQL_LIVE:
        parser.error("aucun mode SQL live sélectionné")
    module = None
    if mode == "oracle":
        try:
            module = _driver_oracle()
        except RuntimeError as erreur:
            parser.error(str(erreur))
    dsn = str(args.sql_dsn or "").strip() or _valeur_environnement(
        environnement, "JUMEAU_SQL_DSN")
    if not dsn and mode == "postgres":
        dsn = _valeur_environnement(environnement, "JUMEAU_PG_DSN")
    if not dsn:
        if mode == "oracle":
            parser.error(
                "--sql-dsn ou JUMEAU_SQL_DSN requis pour --sql-live oracle")
        parser.error(
            "--sql-dsn, JUMEAU_SQL_DSN ou JUMEAU_PG_DSN requis pour "
            "--sql-live postgres")
    schema = str(args.sql_schema or "").strip() or _valeur_environnement(
        environnement, "JUMEAU_SQL_SCHEMA")
    try:
        if mode == "postgres":
            connexion, executer = _ouvrir_postgres(dsn)
        else:
            connexion, executer = _ouvrir_oracle(dsn, module)
    except Exception as erreur:
        parser.error(f"connexion {mode} impossible : {erreur}")
    from meridian.adapters.outbound.connectors.sql_live import SqlLiveSidecar
    try:
        sidecar = SqlLiveSidecar(mode, executer, schema=schema)
    except Exception:
        connexion.close()
        raise
    return sidecar, connexion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--racine", required=True, type=Path)
    parser.add_argument("--sortie", type=Path)
    parser.add_argument("--fichier", action="append", default=[], help="fichier relatif à indexer (répétable)")
    parser.add_argument("--projet-cbm", help="projet codebase-memory-mcp à fédérer")
    parser.add_argument("--sql-live", choices=(*MODES_SQL_LIVE, "auto"),
                        help="introspection SQL live du catalogue "
                             "(auto : JUMEAU_SQL_LIVE, désactivée si vide)")
    parser.add_argument("--sql-dsn",
                        help="DSN SQL live (défaut : JUMEAU_SQL_DSN, "
                             "puis JUMEAU_PG_DSN pour PostgreSQL)")
    parser.add_argument("--sql-schema",
                        help="schéma SQL live à restreindre (défaut : JUMEAU_SQL_SCHEMA)")
    parser.add_argument("--tenant", default="local", help="tenant de persistance")
    parser.add_argument("--jumeau", help="jumeau de persistance (désactive la sortie seule)")
    parser.add_argument("--commit", help="commit Git des preuves (défaut : HEAD du dépôt)")
    parser.add_argument("--verbose", "--verbeux", action="store_true",
                        help="détaille la résolution SQL live sur stderr")
    args = parser.parse_args()
    load_dotenv(RACINE / "backend" / ".env")
    commit = args.commit
    if not commit and (args.racine / ".git").exists():
        import subprocess
        etat = subprocess.run(
            ["git", "-C", str(args.racine), "status", "--porcelain"],
            capture_output=True, text=True, timeout=20)
        if etat.returncode == 0 and not etat.stdout.strip():
            resultat_git = subprocess.run(
                ["git", "-C", str(args.racine), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10)
            commit = resultat_git.stdout.strip() if resultat_git.returncode == 0 else ""
        else:
            print("arbre de travail modifié : aucun commit automatique, "
                  "les preuves ne seront pas promues (utiliser --commit si le contenu est versionné)",
                  file=sys.stderr)
    sql_live = None
    connexion = None
    mode_sql_live = None
    if args.sql_live:
        try:
            mode_sql_live = _resoudre_sql_live(args.sql_live, os.environ)
        except ValueError as erreur:
            parser.error(str(erreur))
        if args.verbose:
            if mode_sql_live:
                print(f"SQL live : mode {mode_sql_live} sélectionné", file=sys.stderr)
            else:
                print("SQL live : JUMEAU_SQL_LIVE vide, aucune introspection",
                      file=sys.stderr)
    try:
        if mode_sql_live:
            sql_live, connexion = _construire_sql_live(
                args, parser, mode_sql_live, os.environ)
        rapport = indexer_legacy(
            args.racine, args.fichier, args.projet_cbm, commit, sql_live=sql_live)
    finally:
        if connexion is not None:
            connexion.close()
    texte = json.dumps(rapport, ensure_ascii=False, indent=2)
    if args.sortie:
        args.sortie.write_text(texte + "\n", encoding="utf-8")
    if args.jumeau:
        import psycopg
        from meridian.adapters.outbound.postgres import code_index_store, depot
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise SystemExit("JUMEAU_PG_DSN absent : persistance impossible")
        with psycopg.connect(dsn, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            compteurs = code_index_store.remplacer(
                conn, args.tenant, args.jumeau,
                rapport["observations"], rapport["couvertures"], rapport["liens"]["liens"])
        print(f"persisté : {compteurs}")
    if not args.sortie and not args.jumeau:
        print(texte)
    elif args.sortie:
        print(f"{len(rapport['observations'])} observation(s), "
              f"{rapport['liens']['total']} lien(s), "
              f"{rapport['packs']['promouvables']} claim(s) promouvable(s) -> {args.sortie}")


if __name__ == "__main__":
    main()
