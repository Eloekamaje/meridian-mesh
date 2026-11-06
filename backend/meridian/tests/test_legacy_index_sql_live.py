"""Branchement du sidecar SQL live dans l'indexation legacy et le CLI."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from meridian.adapters.outbound.connectors.legacy_index import indexer_legacy
from meridian.domain.code_index import CouvertureFichier, Observation

RACINE_DEPOT = Path(__file__).resolve().parents[3]
SCRIPT = RACINE_DEPOT / "scripts" / "indexer-legacy.py"


def _environnement(**valeurs):
    """Environnement isolé des variables SQL live de la machine de test."""
    noms = {"JUMEAU_SQL_LIVE", "JUMEAU_SQL_DSN", "JUMEAU_SQL_SCHEMA", "JUMEAU_PG_DSN"}
    environnement = {cle: valeur for cle, valeur in os.environ.items() if cle not in noms}
    environnement.update(valeurs)
    return environnement


class FauxSqlLive:
    provider = "sql-live"
    parser = "sql-catalog"
    parser_version = "1.0"
    language = "sql"

    def __init__(self):
        self.appels = []

    def index(self, racine=None, fichiers=()):
        self.appels.append(("index", tuple(fichiers)))
        return [
            Observation(
                provider=self.provider, parser=self.parser,
                parser_version=self.parser_version,
                file="db://postgres/public/clients", language=self.language,
                kind="sql_live_table", symbol="public.clients",
                attributes={"schema": "public", "table": "clients",
                            "colonnes": ["id", "nom"]},
            ),
            Observation(
                provider=self.provider, parser=self.parser,
                parser_version=self.parser_version,
                file="db://postgres/public/clients", language=self.language,
                kind="sql_live_column", symbol="public.clients.id",
                attributes={"schema": "public", "table": "clients", "column": "id",
                            "type": "integer", "nullable": False, "ordinal": 1},
            ),
        ]

    def couverture(self, racine=None, fichiers=()):
        self.appels.append(("couverture", tuple(fichiers)))
        return [CouvertureFichier(
            file="db://postgres/public/clients", language=self.language,
            parser=self.parser, statut="indexe",
        )]


def test_sidecar_sql_live_injecte_sur_racine_vide(tmp_path):
    faux = FauxSqlLive()

    rapport = indexer_legacy(str(tmp_path), sql_live=faux)

    assert "sql-live" in rapport["providers"]
    assert any(observation["provider"] == "sql-live"
               for observation in rapport["observations"])
    assert [ligne["file"] for ligne in rapport["couvertures"]] == [
        "db://postgres/public/clients"
    ]
    assert rapport["compteurs"]["indexe"] == 1
    assert faux.appels
    json.loads(json.dumps(rapport, ensure_ascii=False))


def test_sidecar_sql_live_conserve_les_chemins_db_double_slash(tmp_path):
    (tmp_path / "notes.txt").write_text("hors index\n")

    rapport = indexer_legacy(str(tmp_path), sql_live=FauxSqlLive())

    fichiers = {ligne["file"]: ligne for ligne in rapport["couvertures"]}
    assert fichiers["notes.txt"]["statut"] == "non_supporte"
    assert fichiers["db://postgres/public/clients"]["statut"] == "indexe"
    assert any(observation["file"] == "db://postgres/public/clients"
               for observation in rapport["observations"])
    assert not any(observation["file"].startswith("db:/")
                   and not observation["file"].startswith("db://")
                   for observation in rapport["observations"])


def test_sans_sidecar_sql_live_comportement_inchange(tmp_path):
    (tmp_path / "notes.txt").write_text("hors index\n")

    sans = indexer_legacy(str(tmp_path))
    avec_none = indexer_legacy(str(tmp_path), sql_live=None)

    assert sans == avec_none
    assert sans["providers"] == ["jsp", "java", "java-descriptor", "cobol", "jcl", "sql", "abap", "rpg", "pli", "oracle-forms", "powerbuilder"]
    assert not any(observation["provider"] == "sql-live"
                   for observation in sans["observations"])


def test_indexer_legacy_ne_lit_pas_l_environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("JUMEAU_SQL_LIVE", "postgres")
    monkeypatch.setenv("JUMEAU_SQL_DSN", "postgresql://127.0.0.1:1/absente")
    (tmp_path / "notes.txt").write_text("hors index\n")

    rapport = indexer_legacy(str(tmp_path))

    assert "sql-live" not in rapport["providers"]
    assert not any(observation["provider"] == "sql-live"
                   for observation in rapport["observations"])


def test_resolution_auto_desactive_si_environnement_vide():
    module = _charger_script()

    assert module._resoudre_sql_live("auto", {}) is None
    assert module._resoudre_sql_live("auto", {"JUMEAU_SQL_LIVE": "   "}) is None
    assert module._resoudre_sql_live(None, {"JUMEAU_SQL_LIVE": "postgres"}) is None


def test_resolution_auto_choisit_postgres_ou_oracle():
    module = _charger_script()

    assert module._resoudre_sql_live(
        "auto", {"JUMEAU_SQL_LIVE": "postgres"}) == "postgres"
    assert module._resoudre_sql_live(
        "auto", {"JUMEAU_SQL_LIVE": " ORACLE "}) == "oracle"
    with pytest.raises(ValueError, match="JUMEAU_SQL_LIVE"):
        module._resoudre_sql_live("auto", {"JUMEAU_SQL_LIVE": "mysql"})


def test_cli_prime_sur_les_variables_sql(monkeypatch):
    module = _charger_script()
    capture = {}

    def faux_ouvrir(dsn):
        capture["dsn"] = dsn
        return _FauxConnexion(), lambda sql, params=(): []

    monkeypatch.setattr(module, "_ouvrir_postgres", faux_ouvrir)
    args = argparse.Namespace(
        sql_live="postgres", sql_dsn="postgresql://cli/base", sql_schema="cli_schema")

    sidecar, _ = module._construire_sql_live(
        args, argparse.ArgumentParser(), "postgres",
        {"JUMEAU_SQL_LIVE": "oracle",
         "JUMEAU_SQL_DSN": "postgresql://env/base",
         "JUMEAU_SQL_SCHEMA": "env_schema"},
    )

    assert capture["dsn"] == "postgresql://cli/base"
    assert sidecar.schema == "cli_schema"


def test_variables_sql_prennent_le_relais_des_options(monkeypatch):
    module = _charger_script()
    capture = {}

    def faux_ouvrir(dsn):
        capture["dsn"] = dsn
        return _FauxConnexion(), lambda sql, params=(): []

    monkeypatch.setattr(module, "_ouvrir_postgres", faux_ouvrir)
    args = argparse.Namespace(sql_live="postgres", sql_dsn=None, sql_schema=None)

    sidecar, _ = module._construire_sql_live(
        args, argparse.ArgumentParser(), "postgres",
        {"JUMEAU_SQL_DSN": "postgresql://env/base",
         "JUMEAU_SQL_SCHEMA": "env_schema"},
    )

    assert capture["dsn"] == "postgresql://env/base"
    assert sidecar.schema == "env_schema"


def _charger_script():
    specification = importlib.util.spec_from_file_location(
        "indexer_legacy_cli", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _FauxCurseur:
    description = (("valeur",),)

    def __init__(self):
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.sql = sql

    def fetchall(self):
        return [{"valeur": 1}]

    def close(self):
        pass


class _FauxConnexion:
    def cursor(self):
        return _FauxCurseur()


def test_executeur_postgres_refuse_toute_instruction_non_select():
    module = _charger_script()
    executer = module._executeur_postgres(_FauxConnexion())

    assert executer("SELECT 1") == [{"valeur": 1}]
    with pytest.raises(ValueError):
        executer("DELETE FROM clients")
    with pytest.raises(ValueError):
        executer("SELECT 1; DROP TABLE clients")


def test_cli_oracle_refuse_sans_driver(tmp_path):
    if importlib.util.find_spec("oracledb") is not None:
        pytest.skip("driver oracledb installé")
    (tmp_path / "notes.txt").write_text("hors index\n")

    resultat = subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(tmp_path),
         "--sql-live", "oracle", "--sql-dsn", "127.0.0.1/service"],
        capture_output=True, text=True, timeout=60, env=_environnement(),
    )

    assert resultat.returncode != 0
    assert "oracledb" in resultat.stderr.lower()


def test_cli_auto_oracle_refuse_sans_driver(tmp_path):
    if importlib.util.find_spec("oracledb") is not None:
        pytest.skip("driver oracledb installé")
    (tmp_path / "notes.txt").write_text("hors index\n")
    environnement = _environnement(
        JUMEAU_SQL_LIVE="oracle", JUMEAU_SQL_DSN="127.0.0.1/service")

    resultat = subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(tmp_path),
         "--sql-live", "auto"],
        capture_output=True, text=True, timeout=60, env=environnement,
    )

    assert resultat.returncode != 0
    assert "oracledb" in resultat.stderr.lower()


def test_cli_postgres_refuse_sans_dsn(tmp_path):
    (tmp_path / "notes.txt").write_text("hors index\n")
    environnement = _environnement(JUMEAU_SQL_DSN="", JUMEAU_PG_DSN="")

    resultat = subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(tmp_path),
         "--sql-live", "postgres"],
        capture_output=True, text=True, timeout=60, env=environnement,
    )

    assert resultat.returncode != 0
    assert "JUMEAU_SQL_DSN" in resultat.stderr
    assert "JUMEAU_PG_DSN" in resultat.stderr


def test_cli_auto_postgres_refuse_sans_dsn(tmp_path):
    (tmp_path / "notes.txt").write_text("hors index\n")
    environnement = _environnement(
        JUMEAU_SQL_LIVE="postgres", JUMEAU_SQL_DSN="", JUMEAU_PG_DSN="")

    resultat = subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(tmp_path),
         "--sql-live", "auto"],
        capture_output=True, text=True, timeout=60, env=environnement,
    )

    assert resultat.returncode != 0
    assert "JUMEAU_SQL_DSN" in resultat.stderr


def test_cli_auto_sans_mode_ne_connecte_pas(tmp_path):
    (tmp_path / "notes.txt").write_text("hors index\n")
    environnement = _environnement(
        JUMEAU_SQL_LIVE="",
        JUMEAU_SQL_DSN="postgresql://127.0.0.1:1/absente",
        JUMEAU_PG_DSN="postgresql://127.0.0.1:1/absente",
    )

    resultat = subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(tmp_path),
         "--sql-live", "auto", "--verbose"],
        capture_output=True, text=True, timeout=60, env=environnement,
    )

    assert resultat.returncode == 0, resultat.stderr
    assert "JUMEAU_SQL_LIVE" in resultat.stderr
    rapport = json.loads(resultat.stdout)
    assert "sql-live" not in rapport["providers"]
    assert not any(observation["provider"] == "sql-live"
                   for observation in rapport["observations"])


def test_cli_sans_option_sql_live_ignore_les_variables(tmp_path):
    (tmp_path / "notes.txt").write_text("hors index\n")
    environnement = _environnement(
        JUMEAU_SQL_LIVE="postgres",
        JUMEAU_SQL_DSN="postgresql://127.0.0.1:1/absente",
        JUMEAU_PG_DSN="postgresql://127.0.0.1:1/absente",
    )

    resultat = subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(tmp_path)],
        capture_output=True, text=True, timeout=60, env=environnement,
    )

    assert resultat.returncode == 0, resultat.stderr
    rapport = json.loads(resultat.stdout)
    assert "sql-live" not in rapport["providers"]
