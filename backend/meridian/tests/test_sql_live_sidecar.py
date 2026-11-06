"""Tests du sidecar SQL vivant : faux exécuteur, catalogues simulés, aucune base requise."""
import pytest

from meridian.adapters.outbound.connectors.sql_live import (
    LANGAGE,
    PARSER,
    PARSER_VERSION,
    PROVIDER,
    SqlLiveSidecar,
)

REPONSES_POSTGRES = [
    ("information_schema.tables", [
        {"table_schema": "public", "table_name": "clients", "table_type": "BASE TABLE"},
        {"table_schema": "public", "table_name": "equipes", "table_type": "BASE TABLE"},
        {"table_schema": "public", "table_name": "v_clients", "table_type": "VIEW"},
    ]),
    ("information_schema.columns", [
        {"table_schema": "public", "table_name": "clients", "column_name": "nom",
         "data_type": "text", "is_nullable": "YES", "ordinal_position": 3},
        {"table_schema": "public", "table_name": "clients", "column_name": "equipe_id",
         "data_type": "integer", "is_nullable": "YES", "ordinal_position": 2},
        {"table_schema": "public", "table_name": "clients", "column_name": "id",
         "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
        {"table_schema": "public", "table_name": "equipes", "column_name": "id",
         "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
        {"table_schema": "public", "table_name": "v_clients", "column_name": "id",
         "data_type": "integer", "is_nullable": "YES", "ordinal_position": 1},
    ]),
    ("information_schema.table_constraints", [
        {"table_schema": "public", "table_name": "clients", "constraint_name": "clients_pkey",
         "constraint_type": "PRIMARY KEY", "column_name": "id", "ordinal_position": 1},
        {"table_schema": "public", "table_name": "clients", "constraint_name": "clients_equipe_fk",
         "constraint_type": "FOREIGN KEY", "column_name": "equipe_id", "ordinal_position": 1,
         "ref_schema": "public", "ref_table": "equipes", "ref_column": "id",
         "on_delete": "CASCADE"},
        {"table_schema": "public", "table_name": "clients", "constraint_name": "clients_nom_key",
         "constraint_type": "UNIQUE", "column_name": "nom", "ordinal_position": 1},
    ]),
    ("pg_indexes", [
        {"schemaname": "public", "tablename": "clients", "indexname": "clients_nom_idx",
         "indexdef": "CREATE UNIQUE INDEX clients_nom_idx ON public.clients USING btree (nom)"},
    ]),
]

REPONSES_ORACLE = [
    ("ALL_TABLES", [
        {"owner": "APP", "table_name": "CLIENTS"},
    ]),
    ("ALL_TAB_COLUMNS", [
        {"owner": "APP", "table_name": "CLIENTS", "column_name": "ID",
         "data_type": "NUMBER", "nullable": "N", "column_id": 1},
        {"owner": "APP", "table_name": "CLIENTS", "column_name": "NOM",
         "data_type": "VARCHAR2", "nullable": "Y", "column_id": 2},
    ]),
    ("ALL_CONSTRAINTS", [
        {"owner": "APP", "table_name": "CLIENTS", "constraint_name": "PK_CLIENTS",
         "constraint_type": "P", "column_name": "ID", "position": 1},
        {"owner": "APP", "table_name": "CLIENTS", "constraint_name": "FK_CLIENTS_EQUIPE",
         "constraint_type": "R", "column_name": "EQUIPE_ID", "position": 1,
         "ref_schema": "APP", "ref_table": "EQUIPES", "on_delete": "CASCADE"},
    ]),
    ("ALL_INDEXES", [
        {"owner": "APP", "table_name": "CLIENTS", "index_name": "IDX_CLIENTS_NOM",
         "uniqueness": "UNIQUE", "column_name": "NOM"},
    ]),
    ("ALL_VIEWS", [
        {"owner": "APP", "view_name": "V_CLIENTS"},
    ]),
    ("ALL_PROCEDURES", [
        {"owner": "APP", "object_name": "CHANGER_NOM", "procedure_name": "CHANGER_NOM",
         "object_type": "PROCEDURE"},
    ]),
]


class FauxExecuteur:
    """Répond selon un fragment SQL et enregistre les requêtes réellement émises."""

    def __init__(self, reponses=(), pannes=()):
        self.reponses = list(reponses)
        self.pannes = tuple(pannes)
        self.requetes = []

    def __call__(self, sql, params=()):
        self.requetes.append((sql, params))
        assert sql.lstrip().upper().startswith("SELECT")
        for fragment in self.pannes:
            if fragment in sql:
                raise RuntimeError(f"panne simulée sur {fragment}")
        for fragment, lignes in self.reponses:
            if fragment in sql:
                return lignes
        return []


def _par_kind(observations, kind):
    return [observation for observation in observations if observation.kind == kind]


def _par_symbole(observations, kind, symbole):
    return next(observation for observation in observations
                if observation.kind == kind and observation.symbol == symbole)


def test_postgres_tables_colonnes_pk_fk_unique_et_index():
    executeur = FauxExecuteur(REPONSES_POSTGRES)
    sidecar = SqlLiveSidecar("postgres", executeur)

    observations = sidecar.index()

    assert sidecar.provider == PROVIDER
    assert sidecar.parser == PARSER
    assert sidecar.parser_version == PARSER_VERSION
    assert sidecar.language == LANGAGE
    assert all(observation.provider == PROVIDER for observation in observations)
    assert all(observation.parser == PARSER for observation in observations)
    assert all(observation.language == LANGAGE for observation in observations)

    table = _par_symbole(observations, "sql_live_table", "public.clients")
    assert table.file == "db://postgres/public/clients"
    assert table.attributes["schema"] == "public"
    assert table.attributes["table"] == "clients"
    assert table.attributes["colonnes"] == ["id", "equipe_id", "nom"]

    colonne = _par_symbole(observations, "sql_live_column", "public.clients.equipe_id")
    assert colonne.file == "db://postgres/public/clients"
    assert colonne.attributes["column"] == "equipe_id"
    assert colonne.attributes["type"] == "integer"
    assert colonne.attributes["nullable"] is True
    assert colonne.attributes["ordinal"] == 2
    assert colonne.attributes["references"] == "public.equipes"
    assert colonne.attributes["on_delete"] == "CASCADE"

    identifiant = _par_symbole(observations, "sql_live_column", "public.clients.id")
    assert identifiant.attributes["nullable"] is False

    pk = _par_symbole(observations, "sql_live_pk", "clients_pkey")
    assert pk.attributes["table"] == "clients"
    assert pk.attributes["colonnes"] == ["id"]

    fk = _par_symbole(observations, "sql_live_fk", "clients_equipe_fk")
    assert fk.attributes["colonnes"] == ["equipe_id"]
    assert fk.attributes["references"] == "public.equipes"
    assert fk.attributes["on_delete"] == "CASCADE"

    unique = _par_symbole(observations, "sql_live_unique", "clients_nom_key")
    assert unique.attributes["colonnes"] == ["nom"]

    index = _par_symbole(observations, "sql_live_index", "clients_nom_idx")
    assert index.attributes["colonnes"] == ["nom"]
    assert index.attributes["unique"] is True

    vue = _par_symbole(observations, "sql_live_view", "public.v_clients")
    assert vue.file == "db://postgres/public/v_clients"

    couvertures = sidecar.couverture()
    assert {ligne.file for ligne in couvertures} == {
        "db://postgres/public/clients",
        "db://postgres/public/equipes",
        "db://postgres/public/v_clients",
    }
    assert all(ligne.statut == "indexe" for ligne in couvertures)


def test_oracle_table_vue_contraintes_index_et_procedure():
    executeur = FauxExecuteur(REPONSES_ORACLE)
    sidecar = SqlLiveSidecar("oracle", executeur)
    observations = sidecar.index()

    table = _par_symbole(observations, "sql_live_table", "APP.CLIENTS")
    assert table.file == "db://oracle/APP/CLIENTS"
    assert table.attributes["colonnes"] == ["ID", "NOM"]

    colonne = _par_symbole(observations, "sql_live_column", "APP.CLIENTS.ID")
    assert colonne.attributes["type"] == "NUMBER"
    assert colonne.attributes["nullable"] is False
    assert colonne.attributes["ordinal"] == 1

    fk = _par_symbole(observations, "sql_live_fk", "FK_CLIENTS_EQUIPE")
    assert fk.attributes["references"] == "APP.EQUIPES"
    assert fk.attributes["on_delete"] == "CASCADE"

    index = _par_symbole(observations, "sql_live_index", "IDX_CLIENTS_NOM")
    assert index.attributes["unique"] is True

    vue = _par_symbole(observations, "sql_live_view", "APP.V_CLIENTS")
    assert vue.file == "db://oracle/APP/V_CLIENTS"

    procedure = _par_symbole(observations, "sql_live_procedure", "APP.CHANGER_NOM")
    assert procedure.file == "db://oracle/APP/CHANGER_NOM"

    couvertures = {ligne.file: ligne for ligne in sidecar.couverture()}
    assert set(couvertures) == {"db://oracle/APP/CLIENTS", "db://oracle/APP/V_CLIENTS"}
    assert all(ligne.statut == "indexe" for ligne in couvertures.values())


def test_panne_couverture_partielle_sans_lever():
    executeur = FauxExecuteur(REPONSES_POSTGRES, pannes=("information_schema.columns",))
    sidecar = SqlLiveSidecar("postgres", executeur)

    observations = sidecar.index()
    couvertures = sidecar.couverture()

    assert couvertures
    assert all(ligne.statut == "partiel" for ligne in couvertures)
    assert all("panne simulée" in ligne.raison for ligne in couvertures)
    assert _par_kind(observations, "sql_live_table")
    assert not _par_kind(observations, "sql_live_column")


def test_panne_totale_couverture_partielle_et_index_vide():
    executeur = FauxExecuteur(REPONSES_POSTGRES, pannes=("SELECT",))
    sidecar = SqlLiveSidecar("postgres", executeur)

    assert sidecar.index() == []
    couvertures = sidecar.couverture()

    assert len(couvertures) == 1
    assert couvertures[0].statut == "partiel"
    assert "panne simulée" in couvertures[0].raison


def test_dialecte_inconnu_leve_value_error():
    with pytest.raises(ValueError):
        SqlLiveSidecar("mysql", lambda sql, params=(): [])
    with pytest.raises(ValueError):
        SqlLiveSidecar("", lambda sql, params=(): [])


def test_parametres_lies_et_aucune_valeur_concaténee():
    executeur = FauxExecuteur(REPONSES_POSTGRES)
    sidecar = SqlLiveSidecar("postgres", executeur, schema="public")

    sidecar.index()

    assert executeur.requetes
    assert all("public" not in sql for sql, _ in executeur.requetes)
    assert all(params == ("public",) for _, params in executeur.requetes)

    executeur_oracle = FauxExecuteur(REPONSES_ORACLE)
    sidecar_oracle = SqlLiveSidecar("oracle", executeur_oracle, schema="APP")

    sidecar_oracle.index()

    assert executeur_oracle.requetes
    assert all("APP" not in sql for sql, _ in executeur_oracle.requetes)
    assert all(params == ("APP",) for _, params in executeur_oracle.requetes)


def test_ordre_stable_et_deduplication():
    lignes_desordonnees = [
        {"table_schema": "public", "table_name": "clients", "table_type": "BASE TABLE"},
        {"table_schema": "public", "table_name": "equipes", "table_type": "BASE TABLE"},
        {"table_schema": "public", "table_name": "clients", "table_type": "BASE TABLE"},
    ]
    colonnes_desordonnees = [
        {"table_schema": "public", "table_name": "clients", "column_name": "nom",
         "data_type": "text", "is_nullable": "YES", "ordinal_position": 2},
        {"table_schema": "public", "table_name": "clients", "column_name": "id",
         "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
        {"table_schema": "public", "table_name": "clients", "column_name": "id",
         "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
    ]
    executeur = FauxExecuteur([
        ("information_schema.columns", colonnes_desordonnees),
        ("information_schema.tables", lignes_desordonnees),
    ])
    sidecar = SqlLiveSidecar("postgres", executeur)

    premier = sidecar.index()
    second = sidecar.index()

    assert premier == second
    assert premier == sorted(premier, key=lambda o: (o.file, o.start, o.kind, o.symbol))
    assert len({observation.fingerprint for observation in premier}) == len(premier)
    assert len(_par_kind(premier, "sql_live_table")) == 2
    assert len(_par_kind(premier, "sql_live_column")) == 2

    couvertures = sidecar.couverture()
    assert [ligne.file for ligne in couvertures] == sorted(
        ligne.file for ligne in couvertures)
