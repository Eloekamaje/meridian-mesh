"""Magasin de l'index legacy fédéré : normalisation, SQL, isolation tenant/jumeau."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from meridian.adapters.outbound.postgres import code_index_store
from meridian.application.code_links import Link
from meridian.domain.code_index import CouvertureFichier, Observation
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
JUMEAU = "tbt"


class FauxConn:
    """Connexion enregistreuse : elle rend les lignes configurées, sans Postgres."""

    def __init__(self, files=()):
        self.executions = []
        self._files = list(files)
        self._derniere = []
        self.transactions = 0
        self.ferme = False
        self.row_factory = None

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def cursor(self, row_factory=None):
        self.row_factory = row_factory
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.executions.append((sql, params))
        self._derniere = self._files.pop(0) if self._files else []
        return self

    def executemany(self, sql, lignes):
        self.executions.append((sql, list(lignes)))
        return self

    def fetchall(self):
        return list(self._derniere)

    def fetchone(self):
        return self._derniere[0] if self._derniere else None

    def close(self):
        self.ferme = True


def _observation(**champs):
    valeurs = {
        "provider": "java", "parser": "javaparser", "parser_version": "1",
        "file": "src/A.java", "language": "java", "kind": "java_type", "symbol": "A",
        "start": 3, "end": 9, "commit": "abc", "attributes": {"lignes": 7},
        "confidence": 0.8, "status": "extracted",
    }
    valeurs.update(champs)
    return Observation(**valeurs)


def _lien(**champs):
    valeurs = {
        "kind": "java_to_jpa_entity", "source_file": "src/A.java", "source_symbol": "A",
        "target_file": "src/A.java", "target_symbol": "A.entity",
        "attributes": {"via": ["import"]}, "confidence": 0.7,
        "status": "inferred", "evidence": {"source": {"file": "src/A.java"}},
    }
    valeurs.update(champs)
    return Link(**valeurs)


def _suppressions(conn):
    return [(sql, params) for sql, params in conn.executions
            if sql.lstrip().upper().startswith("DELETE")]


def test_remplacer_normalise_les_objets_et_les_dicts():
    conn = FauxConn()
    compteurs = code_index_store.remplacer(
        conn, TENANT, JUMEAU,
        observations=[
            {"provider": " java ", "parser": "javaparser", "parser_version": "1",
             "file": " src/A.java\n", "language": "java", "kind": "java_type",
             "symbol": " A ", "start_line": "3", "end_line": "9", "commit_sha": "abc",
             "attributes": {"lignes": 7}, "confidence": "0.8", "status": "extracted"},
            _observation(provider="cobol", file="src/B.cbl", language="cobol",
                         kind="cobol_program", symbol="B", start=1, end=2),
        ],
        couvertures=[
            CouvertureFichier(file="src/A.java", language="java", parser="javaparser",
                              statut="indexe"),
            {"file": "src/C.jsp", "language": "jsp", "parser": "jsp",
             "status": "non_supporte", "reason": "aucun parser"},
        ],
        liens=[
            _lien(),
            {"kind": "sql_fk_to_table", "source_file": "a.sql", "source_symbol": "FK",
             "target_file": "b.sql", "target_symbol": "B", "attributes": {},
             "confidence": 1, "status": "linked", "evidence": {}},
        ],
    )

    assert compteurs == {"observations": 2, "couvertures": 2, "liens": 2}
    assert conn.transactions == 1

    insertions = [(sql, params) for sql, params in conn.executions if "INSERT INTO" in sql]
    assert [sql.split()[2] for sql, _ in insertions] == [
        "code_observation", "code_coverage", "code_link"]

    _, observations = insertions[0]
    assert len(observations) == 2
    premiere = observations[0]
    assert premiere[0:2] == (TENANT, JUMEAU)
    assert premiere[2:6] == ("java", "javaparser", "1", "src/A.java")
    assert premiere[6:9] == ("java", "java_type", "A")
    assert premiere[9:12] == (3, 9, "abc")
    assert premiere[12].obj == {"lignes": 7}
    assert premiere[13] == pytest.approx(0.8)
    assert premiere[14] == "extracted"
    assert len(premiere[15]) == 64 and int(premiere[15], 16) >= 0

    _, couvertures = insertions[1]
    assert couvertures[0] == (TENANT, JUMEAU, "src/A.java", "java", "javaparser", "indexe", "")
    assert couvertures[1] == (TENANT, JUMEAU, "src/C.jsp", "jsp", "jsp", "non_supporte",
                              "aucun parser")

    _, liens = insertions[2]
    assert liens[0][2:7] == ("java_to_jpa_entity", "src/A.java", "A", "src/A.java", "A.entity")
    assert liens[0][7].obj == {"via": ["import"]}
    assert liens[0][8] == pytest.approx(0.7)
    assert liens[0][9] == "inferred"
    assert liens[0][10].obj == {"source": {"file": "src/A.java"}}
    assert len(liens[0][11]) == 64


def test_remplacer_deduplique_les_cles_et_ne_touche_que_le_couple():
    conn = FauxConn()
    premiere = {"provider": "java", "parser": "p", "parser_version": "1",
                "file": "src/A.java", "language": "java", "kind": "java_type",
                "symbol": "A", "start_line": 1, "end_line": 2, "commit_sha": "abc",
                "attributes": {}, "confidence": 0.5, "status": "extracted"}
    compteurs = code_index_store.remplacer(
        conn, TENANT, JUMEAU,
        observations=[premiere, {**premiere, "status": "inferred"}],
        couvertures=[{"file": "src/A.java", "statut": "indexe"},
                     {"file": "src/A.java", "statut": "partiel"}],
        liens=[_lien(), _lien(status="linked")],
    )

    assert compteurs == {"observations": 1, "couvertures": 1, "liens": 1}
    insertions = [(sql, params) for sql, params in conn.executions if "INSERT INTO" in sql]
    assert insertions[0][1][0][14] == "inferred"
    assert insertions[1][1][0][5] == "partiel"
    assert insertions[2][1][0][9] == "linked"

    suppressions = _suppressions(conn)
    assert len(suppressions) == 3
    assert all(params == (TENANT, JUMEAU) for _, params in suppressions)
    assert all("tenant_id = %s AND jumeau_id = %s" in sql for sql, _ in suppressions)
    assert all("claim" not in sql.casefold() for sql, _ in conn.executions)


def test_remplacer_source_namespace_les_chemins_et_ne_supprime_que_ce_depot():
    conn = FauxConn()
    compteurs = code_index_store.remplacer_source(
        conn, TENANT, JUMEAU, "api",
        observations=[_observation(file="src/A.java")],
        couvertures=[CouvertureFichier(file="src/A.java", statut="indexe")],
        liens=[_lien(evidence={"source": {"file": "src/A.java"}})],
    )

    assert compteurs == {"observations": 1, "couvertures": 1, "liens": 1}
    suppressions = _suppressions(conn)
    assert len(suppressions) == 3
    assert suppressions[0][1] == (TENANT, JUMEAU, "api/", "api/", "api/", "api/")
    assert suppressions[1][1] == (TENANT, JUMEAU, "api/", "api/")
    assert suppressions[2][1] == (TENANT, JUMEAU, "api/", "api/")
    assert all(" LIKE " not in sql for sql, _ in suppressions)

    insertions = [(sql, params) for sql, params in conn.executions if "INSERT INTO" in sql]
    assert insertions[0][1][0][5] == "api/src/A.java"
    assert insertions[1][1][0][2] == "api/src/A.java"
    lien = insertions[2][1][0]
    assert lien[3] == lien[5] == "api/src/A.java"
    assert lien[10].obj == {"source": {"file": "api/src/A.java"}}


@pytest.mark.parametrize("source", ["", "..", "api/front", "api%"])
def test_remplacer_source_refuse_une_portee_ambigue(source):
    conn = FauxConn()
    with pytest.raises(ValueError):
        code_index_store.remplacer_source(conn, TENANT, JUMEAU, source)
    assert conn.executions == []


def test_remplacer_source_traite_un_underscore_comme_un_caractere_litteral():
    conn = FauxConn()
    code_index_store.remplacer_source(conn, TENANT, JUMEAU, "api_v1")
    suppressions = _suppressions(conn)
    assert suppressions[1][1] == (TENANT, JUMEAU, "api_v1/", "api_v1/")
    assert "left(file, length(%s)) = %s" in suppressions[1][0]


def test_les_empreintes_sont_stables_et_discriminent_la_provenance():
    def empreinte(observation):
        conn = FauxConn()
        code_index_store.remplacer(conn, TENANT, JUMEAU, [observation])
        insertion = next(params for sql, params in conn.executions if "INSERT INTO" in sql)
        return insertion[0][15]

    reference = _observation()
    assert empreinte(reference) == empreinte(_observation())
    assert empreinte(reference) != empreinte(_observation(provider="cobol"))
    assert empreinte(reference) != empreinte(_observation(start=4))

    conn = FauxConn()
    code_index_store.remplacer(conn, TENANT, JUMEAU, liens=[_lien()])
    insertion = next(params for sql, params in conn.executions if "INSERT INTO" in sql)
    assert len(insertion[0][11]) == 64


def test_lire_observations_filtre_tenant_jumeau_kind_fichier_et_borne():
    conn = FauxConn([[
        {"provider": "java", "confidence": Decimal("0.80"),
         "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    ]])

    lignes = code_index_store.lire_observations(
        conn, TENANT, JUMEAU, kind="java_type", fichier="src/A.java", limite=25)

    sql, params = conn.executions[-1]
    assert "WHERE tenant_id = %s AND jumeau_id = %s" in sql
    assert "AND kind = %s" in sql and "AND file = %s" in sql
    assert "ORDER BY file, start_line, kind, symbol" in sql
    assert params == (TENANT, JUMEAU, "java_type", "src/A.java", 25)
    assert lignes[0]["confidence"] == 0.8
    assert lignes[0]["updated_at"].startswith("2026-01-01")


def test_lire_couverture_filtre_le_statut_et_borne():
    conn = FauxConn([[{"file": "src/A.java", "status": "indexe",
                       "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc)}]])

    lignes = code_index_store.lire_couverture(conn, TENANT, JUMEAU,
                                              statut="indexe", limite=10)

    sql, params = conn.executions[-1]
    assert "WHERE tenant_id = %s AND jumeau_id = %s" in sql
    assert "AND status = %s" in sql
    assert "ORDER BY file LIMIT %s" in sql
    assert params == (TENANT, JUMEAU, "indexe", 10)
    assert lignes[0]["file"] == "src/A.java"


def test_lire_liens_filtre_la_famille_et_borne():
    conn = FauxConn([[{"kind": "java_to_jpa_entity", "confidence": Decimal("0.70"),
                       "updated_at": datetime(2026, 1, 3, tzinfo=timezone.utc)}]])

    lignes = code_index_store.lire_liens(conn, TENANT, JUMEAU,
                                         kind="java_to_jpa_entity", limite=5)

    sql, params = conn.executions[-1]
    assert "WHERE tenant_id = %s AND jumeau_id = %s" in sql
    assert "AND kind = %s" in sql
    assert "ORDER BY kind, source_file, source_symbol, target_file, target_symbol" in sql
    assert params == (TENANT, JUMEAU, "java_to_jpa_entity", 5)
    assert lignes[0]["confidence"] == 0.7


@pytest.mark.parametrize("limite", [0, -1, 1001, "abc", True])
def test_une_limite_invalide_est_refusee_avant_toute_lecture(limite):
    conn = FauxConn()
    with pytest.raises(ValueError):
        code_index_store.lire_liens(conn, TENANT, JUMEAU, limite=limite)
    assert conn.executions == []


def test_resume_compte_par_statut_provider_kind_et_fichiers():
    conn = FauxConn([
        [{"cle": "extracted", "nombre": 3}, {"cle": "inferred", "nombre": 1}],
        [{"cle": "java", "nombre": 3}, {"cle": "cobol", "nombre": 1}],
        [{"cle": "indexe", "nombre": 2}, {"cle": "partiel", "nombre": 1}],
        [{"nombre": 3}],
        [{"cle": "java_to_jpa_entity", "nombre": 2}],
        [{"cle": "linked", "nombre": 1}, {"cle": "inferred", "nombre": 1}],
    ])

    resultat = code_index_store.resume(conn, TENANT, JUMEAU)

    assert resultat["observations"]["total"] == 4
    assert resultat["observations"]["par_statut"] == {
        "ambiguous": 0, "conflict": 0, "extracted": 3, "inferred": 1}
    assert resultat["observations"]["par_provider"] == {"cobol": 1, "java": 3}
    assert resultat["couverture"]["total"] == 3
    assert resultat["couverture"]["fichiers_couverts"] == 3
    assert resultat["couverture"]["fichiers_indexes"] == 2
    assert resultat["couverture"]["par_statut"] == {
        "conflit": 0, "ignore": 0, "indexe": 2, "non_supporte": 0,
        "partiel": 1, "tronque": 0}
    assert resultat["liens"]["total"] == 2
    assert resultat["liens"]["par_kind"] == {"java_to_jpa_entity": 2}
    assert resultat["liens"]["par_statut"] == {
        "ambiguous": 0, "inferred": 1, "linked": 1}
    assert all("tenant_id = %s AND jumeau_id = %s" in sql
               for sql, _ in conn.executions)


@besoin_pg
def test_le_magasin_persiste_relit_et_isole_les_couples(conn):
    observation = _observation()
    couverture = CouvertureFichier(file="src/A.java", language="java",
                                   parser="javaparser", statut="indexe")
    lien = _lien()

    compteurs = code_index_store.remplacer(
        conn, TENANT, JUMEAU, [observation], [couverture], [lien])
    assert compteurs == {"observations": 1, "couvertures": 1, "liens": 1}

    lues = code_index_store.lire_observations(conn, TENANT, JUMEAU)
    assert len(lues) == 1
    assert lues[0]["provider"] == "java" and lues[0]["start_line"] == 3
    assert lues[0]["attributes"] == {"lignes": 7}
    assert lues[0]["confidence"] == pytest.approx(0.8)

    assert code_index_store.lire_couverture(conn, TENANT, JUMEAU)[0]["status"] == "indexe"
    liens_lus = code_index_store.lire_liens(conn, TENANT, JUMEAU)
    assert liens_lus[0]["kind"] == "java_to_jpa_entity"
    assert liens_lus[0]["evidence"] == {"source": {"file": "src/A.java"}}

    resume = code_index_store.resume(conn, TENANT, JUMEAU)
    assert resume["observations"]["total"] == 1
    assert resume["couverture"]["fichiers_indexes"] == 1
    assert resume["liens"]["par_kind"] == {"java_to_jpa_entity": 1}

    autre = _observation(provider="cobol", file="src/Z.cbl", language="cobol",
                         kind="cobol_program", symbol="Z")
    code_index_store.remplacer(conn, "assurance", "autre", [autre], [], [])
    code_index_store.remplacer(conn, TENANT, JUMEAU, [], [], [])

    assert code_index_store.lire_observations(conn, TENANT, JUMEAU) == []
    assert code_index_store.lire_couverture(conn, TENANT, JUMEAU) == []
    assert code_index_store.lire_liens(conn, TENANT, JUMEAU) == []
    assert len(code_index_store.lire_observations(conn, "assurance", "autre")) == 1


@besoin_pg
def test_un_remplacement_retire_les_lignes_absentes_du_nouveau_lot(conn):
    code_index_store.remplacer(
        conn, TENANT, JUMEAU,
        [_observation(symbol="A"), _observation(symbol="B")],
        [CouvertureFichier(file="src/A.java", statut="indexe"),
         CouvertureFichier(file="src/B.java", statut="partiel")],
        [_lien(source_symbol="A"), _lien(source_symbol="B")])

    code_index_store.remplacer(
        conn, TENANT, JUMEAU, [_observation(symbol="B")],
        [CouvertureFichier(file="src/B.java", statut="indexe")], [])

    assert [ligne["symbol"] for ligne in
            code_index_store.lire_observations(conn, TENANT, JUMEAU)] == ["B"]
    assert [ligne["file"] for ligne in
            code_index_store.lire_couverture(conn, TENANT, JUMEAU)] == ["src/B.java"]
    assert code_index_store.lire_liens(conn, TENANT, JUMEAU) == []
