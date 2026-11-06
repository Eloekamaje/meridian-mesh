"""Tests du sidecar SQL structurel : DDL local, provenance et tolérance aux fichiers invalides."""
from meridian.adapters.outbound.connectors.sql_schema import (
    PARSER,
    PARSER_VERSION,
    PROVIDER,
    SqlSchemaSidecar,
)


def _ecrire(racine, nom, contenu):
    chemin = racine / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _index(racine, fichiers=()):
    return SqlSchemaSidecar().index(racine, fichiers=fichiers)


def _kind(observations, kind):
    return [observation for observation in observations if observation.kind == kind]


def _symboles(observations, kind):
    return {observation.symbol for observation in _kind(observations, kind)}


def test_table_colonnes_types_nullabilite_et_defauts(tmp_path):
    _ecrire(tmp_path, "clients.sql", """
        CREATE TABLE APP.CLIENTS (
            ID NUMBER(10) NOT NULL,
            NOM VARCHAR2(100) DEFAULT 'inconnu',
            ACTIF NUMBER(1) DEFAULT 1 NOT NULL,
            NOTE CLOB NULL
        );
    """)

    observations = _index(tmp_path)
    table = _kind(observations, "sql_table")[0]
    colonnes = {observation.symbol: observation for observation in _kind(observations, "sql_column")}

    assert table.symbol == "APP.CLIENTS"
    assert table.attributes["colonnes"] == ["ID", "NOM", "ACTIF", "NOTE"]
    assert set(colonnes) == {
        "APP.CLIENTS.ID", "APP.CLIENTS.NOM", "APP.CLIENTS.ACTIF", "APP.CLIENTS.NOTE",
    }
    assert colonnes["APP.CLIENTS.ID"].attributes["type"] == "NUMBER(10)"
    assert colonnes["APP.CLIENTS.ID"].attributes["nullable"] is False
    assert colonnes["APP.CLIENTS.NOM"].attributes["default"] == "'inconnu'"
    assert colonnes["APP.CLIENTS.ACTIF"].attributes["default"] == "1"
    assert colonnes["APP.CLIENTS.ACTIF"].attributes["nullable"] is False
    assert colonnes["APP.CLIENTS.NOTE"].attributes["nullable"] is True


def test_contraintes_et_relations_fk_explicites(tmp_path):
    _ecrire(tmp_path, "contraintes.sql", """
        CREATE TABLE APP.EQUIPES (
            ID NUMBER NOT NULL,
            CONSTRAINT PK_EQUIPES PRIMARY KEY (ID)
        );
        CREATE TABLE APP.CLIENTS (
            ID NUMBER NOT NULL,
            EQUIPE_ID NUMBER,
            EMAIL VARCHAR2(200),
            CONSTRAINT PK_CLIENTS PRIMARY KEY (ID),
            CONSTRAINT FK_CLIENTS_EQUIPE FOREIGN KEY (EQUIPE_ID)
                REFERENCES APP.EQUIPES(ID) ON DELETE CASCADE,
            CONSTRAINT UQ_CLIENTS_EMAIL UNIQUE (EMAIL),
            CONSTRAINT CK_CLIENTS_EMAIL CHECK (EMAIL LIKE '%@%')
        );
        CREATE TABLE APP.SANS_FK (
            CLIENT_ID NUMBER
        );
    """)

    observations = _index(tmp_path)
    fk = [observation for observation in _kind(observations, "sql_fk")
          if observation.symbol == "FK_CLIENTS_EQUIPE"][0]
    pk = [observation for observation in _kind(observations, "sql_pk")
          if observation.symbol == "PK_CLIENTS"][0]
    unique = [observation for observation in _kind(observations, "sql_unique")
              if observation.symbol == "UQ_CLIENTS_EMAIL"][0]
    check = [observation for observation in _kind(observations, "sql_check")
             if observation.symbol == "CK_CLIENTS_EMAIL"][0]
    colonne = [observation for observation in _kind(observations, "sql_column")
               if observation.symbol == "APP.CLIENTS.EQUIPE_ID"][0]
    sans_fk = [observation for observation in _kind(observations, "sql_column")
               if observation.symbol == "APP.SANS_FK.CLIENT_ID"][0]

    assert fk.attributes["colonnes"] == ["EQUIPE_ID"]
    assert fk.attributes["references"] == "APP.EQUIPES"
    assert fk.attributes["on_delete"] == "CASCADE"
    assert pk.attributes["colonnes"] == ["ID"]
    assert unique.attributes["colonnes"] == ["EMAIL"]
    assert check.attributes["expression"] == "EMAIL LIKE '%@%'"
    assert colonne.attributes["references"] == "APP.EQUIPES"
    assert colonne.attributes["on_delete"] == "CASCADE"
    assert "references" not in sans_fk.attributes
    assert all(observation.attributes["table"] != "APP.SANS_FK"
               for observation in _kind(observations, "sql_fk"))


def test_alter_table_ajoute_contrainte_et_colonnes(tmp_path):
    _ecrire(tmp_path, "alter.sql", """
        ALTER TABLE APP.COMMANDES ADD CONSTRAINT FK_COMMANDES_CLIENT
            FOREIGN KEY (CLIENT_ID) REFERENCES APP.CLIENTS(ID) ON DELETE SET NULL;
        ALTER TABLE APP.COMMANDES ADD (
            NOTE VARCHAR2(20) NULL,
            TOTAL NUMBER DEFAULT 0 NOT NULL
        );
    """)

    observations = _index(tmp_path)
    fk = _kind(observations, "sql_fk")[0]
    colonnes = {observation.symbol: observation for observation in _kind(observations, "sql_column")}

    assert fk.symbol == "FK_COMMANDES_CLIENT"
    assert fk.attributes["table"] == "APP.COMMANDES"
    assert fk.attributes["references"] == "APP.CLIENTS"
    assert fk.attributes["on_delete"] == "SET NULL"
    assert colonnes["APP.COMMANDES.NOTE"].attributes["nullable"] is True
    assert colonnes["APP.COMMANDES.TOTAL"].attributes["default"] == "0"
    assert colonnes["APP.COMMANDES.TOTAL"].attributes["nullable"] is False


def test_vue_index_procedure_et_instructions_multiples(tmp_path):
    _ecrire(tmp_path, "objets.sql", """
        CREATE OR REPLACE VIEW APP.V_CLIENTS AS
            SELECT ID, NOM FROM APP.CLIENTS;
        CREATE UNIQUE INDEX APP.IDX_CLIENTS_NOM ON APP.CLIENTS (NOM);
        CREATE OR REPLACE PROCEDURE APP.CHANGER_NOM (P_ID NUMBER, P_NOM VARCHAR2) IS
        BEGIN
            UPDATE APP.CLIENTS SET NOM = P_NOM WHERE ID = P_ID;
            COMMIT;
        END;
        /
        CREATE OR REPLACE FUNCTION APP.COMPTER RETURN NUMBER IS
            V NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO V FROM APP.CLIENTS;
            RETURN V;
        END COMPTER;
        /
        CREATE TABLE APP.APRES (ID NUMBER);
    """)

    observations = _index(tmp_path)
    index = _kind(observations, "sql_index")[0]
    procedure = _kind(observations, "sql_procedure")[0]
    fonction = _kind(observations, "sql_function")[0]

    assert _symboles(observations, "sql_view") == {"APP.V_CLIENTS"}
    assert index.symbol == "APP.IDX_CLIENTS_NOM"
    assert index.attributes["table"] == "APP.CLIENTS"
    assert index.attributes["colonnes"] == ["NOM"]
    assert index.attributes["unique"] is True
    assert procedure.symbol == "APP.CHANGER_NOM"
    assert fonction.symbol == "APP.COMPTER"
    assert _symboles(observations, "sql_table") == {"APP.APRES"}


def test_package_body_garde_ses_points_virgules_internes(tmp_path):
    _ecrire(tmp_path, "package.sql", """
        CREATE OR REPLACE PACKAGE BODY APP.PKG AS
            PROCEDURE P1 IS
            BEGIN
                NULL;
            END P1;
            FUNCTION F1 RETURN NUMBER IS
            BEGIN
                RETURN 1;
            END F1;
        END PKG;
        /
        CREATE TABLE APP.APRES_PKG (ID NUMBER);
    """)

    observations = _index(tmp_path)
    paquet = _kind(observations, "sql_package")[0]

    assert paquet.symbol == "APP.PKG"
    assert paquet.attributes["corps"] is True
    assert _symboles(observations, "sql_table") == {"APP.APRES_PKG"}


def test_schema_qualifie_et_identifiants_guillemets(tmp_path):
    _ecrire(tmp_path, "guillemets.sql", """
        CREATE TABLE "APP"."Mes Clients" (
            "Id" NUMBER(5) NOT NULL,
            "Nom Complet" VARCHAR2(50)
        );
    """)

    observations = _index(tmp_path)

    assert _symboles(observations, "sql_table") == {"APP.Mes Clients"}
    assert _symboles(observations, "sql_column") == {
        "APP.Mes Clients.Id", "APP.Mes Clients.Nom Complet",
    }


def test_commentaires_ignores_et_comment_on(tmp_path):
    _ecrire(tmp_path, "commentaires.sql", """
        /* CREATE TABLE APP.FANTOME (ID NUMBER); */
        -- CREATE TABLE APP.AUSSI (ID NUMBER);
        CREATE TABLE APP.CLIENTS (ID NUMBER NOT NULL);
        COMMENT ON TABLE APP.CLIENTS IS 'Clients actifs';
        COMMENT ON COLUMN APP.CLIENTS.ID IS 'Identifiant unique';
    """)

    observations = _index(tmp_path)
    commentaires = {observation.symbol: observation for observation in _kind(observations, "sql_comment")}

    assert _symboles(observations, "sql_table") == {"APP.CLIENTS"}
    assert set(commentaires) == {"APP.CLIENTS", "APP.CLIENTS.ID"}
    assert commentaires["APP.CLIENTS"].attributes["commentaire"] == "Clients actifs"
    assert commentaires["APP.CLIENTS.ID"].attributes["objet"] == "column"
    assert commentaires["APP.CLIENTS.ID"].attributes["table"] == "APP.CLIENTS"
    assert commentaires["APP.CLIENTS.ID"].attributes["colonne"] == "ID"


def test_fichier_invalide_non_fatal_et_observations_ambigues(tmp_path):
    _ecrire(tmp_path, "casse.sql", """
        CREATE TABLE APP.CASSE (ID NUMBER NOT NULL;
        CREATE TABLE APP.OK (ID INT);
    """)
    _ecrire(tmp_path, "invalide.sql", """
        CREATE TABLE APP.BROKEN (ID NUMBER NOT NULL
    """)

    observations = _index(tmp_path)
    couvertures = {ligne.file: ligne for ligne in SqlSchemaSidecar().couverture(tmp_path)}

    assert _symboles(observations, "sql_table") == {"APP.OK"}
    assert all(observation.status == "ambiguous" for observation in observations)
    assert couvertures["casse.sql"].statut == "partiel"
    assert couvertures["invalide.sql"].statut == "partiel"


def test_couverture_decouverte_fichiers_explicites_et_extensions(tmp_path):
    _ecrire(tmp_path, "a.sql", "CREATE TABLE APP.A (ID NUMBER);")
    _ecrire(tmp_path, "b.sql", "CREATE TABLE APP.B (ID NUMBER")
    _ecrire(tmp_path, "sous/c.DDL", "CREATE TABLE APP.C (ID NUMBER);")
    _ecrire(tmp_path, "note.txt", "CREATE TABLE APP.NOTE (ID NUMBER);")

    sidecar = SqlSchemaSidecar()
    couvertures = {ligne.file: ligne for ligne in sidecar.couverture(tmp_path)}

    assert set(couvertures) == {"a.sql", "b.sql", "sous/c.DDL"}
    assert couvertures["a.sql"].statut == "indexe"
    assert couvertures["b.sql"].statut == "partiel"
    assert couvertures["sous/c.DDL"].statut == "indexe"

    explicites = sidecar.index(tmp_path, fichiers=["a.sql"])
    assert {observation.file for observation in explicites} == {"a.sql"}
    assert _symboles(explicites, "sql_table") == {"APP.A"}

    hors_support = sidecar.couverture(tmp_path, fichiers=["note.txt"])
    assert [ligne.statut for ligne in hors_support] == ["non_supporte"]


def test_provenance_et_tri_des_observations(tmp_path):
    _ecrire(tmp_path, "a.sql", """
        CREATE TABLE APP.B (ID NUMBER);
        CREATE TABLE APP.A (ID NUMBER);
    """)

    observations = _index(tmp_path)

    assert all(observation.provider == PROVIDER for observation in observations)
    assert all(observation.parser == PARSER for observation in observations)
    assert all(observation.parser_version == PARSER_VERSION for observation in observations)
    assert all(observation.language == "sql" for observation in observations)
    assert all(observation.file == "a.sql" for observation in observations)
    assert observations == sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))
