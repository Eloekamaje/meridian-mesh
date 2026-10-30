"""Audit persistant du harness : schéma, expurgation, idempotence, append-only et panne silencieuse."""
import ast
import asyncio
from pathlib import Path
import re

import pytest

from jumeau import audit_harness, depot
from jumeau.audit_harness import AuditPostgres
from jumeau.capacites import ManifesteOutil, RegistreCapacites
from jumeau.harness import Harness
from jumeau.tests.conftest import besoin_pg

SCHEMA_ENTREE = {
    "type": "object",
    "properties": {"application": {"type": "string"}},
    "required": ["application"],
    "additionalProperties": False,
}
SCHEMA_SORTIE = {
    "type": "object",
    "properties": {"traces": {"type": "array", "items": {"type": "object"}}},
    "required": ["traces"],
    "additionalProperties": False,
}


class _ConnexionCourte:
    def __init__(self, conn):
        self.conn = conn
        self.fermee = False

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        self.fermee = True
        return False


def manifeste():
    return ManifesteOutil(
        nom="lire_traces",
        version="1.0.0",
        description="Lit les traces d'observabilité d'une application",
        capacite="observer",
        types_objets_lus=("Trace",),
        schema_entree=SCHEMA_ENTREE,
        schema_sortie=SCHEMA_SORTIE,
        timeout_ms=2000,
        mode_preuve="OBSERVED",
        source="manifeste",
    )


@besoin_pg
def test_le_schema_outil_audit_expose_les_colonnes_et_index(conn):
    depot.appliquer_schema(conn)
    depot.appliquer_schema(conn)

    colonnes = {
        ligne[0] for ligne in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'outil_audit'")
    }
    assert {"id", "tenant_id", "outil", "capacite", "acteur", "arguments", "duree_ms",
            "statut", "erreur", "quand"} <= colonnes

    index = {
        ligne[0] for ligne in conn.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = current_schema() AND tablename = 'outil_audit'")
    }
    assert {"outil_audit_tenant_quand", "outil_audit_tenant_outil_quand",
            "outil_audit_idempotence"} <= index


@besoin_pg
def test_enregistrer_expurge_les_secrets_et_ne_change_pas_de_tenant(conn):
    audit = AuditPostgres(conn, "banque", "flore")

    statut = audit.enregistrer({
        "nom": "lire_traces",
        "capacite": "observer",
        "tenant_id": "assurance",
        "acteur": "pirate",
        "arguments": {
            "application": "alpha",
            "api_key": "sk-secret-123456",
            "nested": {"access_token": "abcdef123456"},
            "note": "Bearer abcdefghijklmnop",
        },
        "duree_ms": 2.5,
        "statut": "ok",
        "erreur": "password=hunter2",
    })

    assert statut["statut"] == "ok" and statut["insere"] is True
    assert isinstance(statut["id"], int)
    lignes = audit.derniers("banque", 10)
    assert len(lignes) == 1
    ligne = lignes[0]
    assert (ligne["tenant_id"], ligne["acteur"], ligne["outil"]) == ("banque", "flore", "lire_traces")
    assert ligne["capacite"] == "observer" and ligne["duree_ms"] == 2.5
    assert ligne["arguments"]["api_key"] == "***"
    assert ligne["arguments"]["nested"]["access_token"] == "***"
    assert ligne["arguments"]["note"] == "***"
    assert ligne["erreur"] == "***"
    encode = str(lignes)
    assert "sk-secret-123456" not in encode
    assert "abcdef123456" not in encode
    assert "hunter2" not in encode
    assert audit.derniers("assurance", 10) == []


@besoin_pg
def test_enregistrer_est_idempotent_et_append_only(conn):
    audit = AuditPostgres(conn, "banque", "flore")
    ligne = {
        "outil": "lire_traces",
        "capacite": "observer",
        "arguments": {"application": "alpha"},
        "duree_ms": 1.0,
        "statut": "ok",
        "quand": "2026-10-30T10:00:00Z",
    }

    premier = audit.enregistrer(ligne)
    second = audit.enregistrer(dict(ligne))

    assert premier["statut"] == "ok" and premier["insere"] is True
    assert second["statut"] == "ok" and second["insere"] is False
    assert len(audit.derniers("banque", 10)) == 1

    autre = audit.enregistrer({**ligne, "outil": "creer_travail"})
    assert autre["insere"] is True
    assert len(audit.derniers("banque", 10)) == 2

    with pytest.raises(Exception):
        conn.execute("UPDATE outil_audit SET statut = 'falsifie'")
    with pytest.raises(Exception):
        conn.execute("DELETE FROM outil_audit")
    with pytest.raises(Exception):
        conn.execute("TRUNCATE outil_audit")
    assert len(audit.derniers("banque", 10)) == 2


@besoin_pg
def test_enregistrer_la_meme_ligne_sans_horodatage_ne_duplique_pas(conn):
    audit = AuditPostgres(conn, "banque", "flore")
    ligne = {"outil": "lire_traces", "statut": "ok", "arguments": {"application": "alpha"}}

    assert audit.enregistrer(ligne)["insere"] is True
    assert audit.enregistrer(ligne)["insere"] is False
    assert len(audit.derniers("banque", 10)) == 1


def test_une_base_indisponible_rend_un_statut_sans_lever():
    audit = AuditPostgres(None, "banque", "flore")
    statut = audit.enregistrer({"outil": "lire_traces", "statut": "ok"})
    assert statut["statut"] == "erreur"
    assert statut["insere"] is False


@besoin_pg
def test_enregistrer_lignes_ecrit_un_lot_expurge_dans_une_connexion_courte(conn, monkeypatch):
    connexion = _ConnexionCourte(conn)
    monkeypatch.setattr(audit_harness.psycopg, "connect", lambda *_, **__: connexion)

    resultat = audit_harness.enregistrer_lignes("postgresql://test/test", "banque", "flore", [
        {"outil": "lire_traces", "capacite": "observer",
         "arguments": {"application": "alpha", "api_key": "sk-secret-123456"}, "statut": "ok"},
        {"nom": "creer_travail", "capacite": "agir",
         "arguments": {"note": "Bearer abcdefghijklmnop"}, "duree_ms": 2, "statut": "ok"},
    ])

    assert resultat == {"ecrits": 2, "erreurs": 0}
    assert connexion.fermee is True
    lignes = audit_harness.derniers(conn, "banque", 10)
    assert len(lignes) == 2
    assert {(ligne["tenant_id"], ligne["acteur"]) for ligne in lignes} == {("banque", "flore")}
    encode = str(lignes)
    assert "sk-secret-123456" not in encode
    assert "abcdefghijklmnop" not in encode
    assert "postgresql://test/test" not in encode


@besoin_pg
def test_enregistrer_lignes_compte_les_refus_sans_interrompre_le_lot(conn, monkeypatch):
    monkeypatch.setattr(audit_harness.psycopg, "connect", lambda *_, **__: _ConnexionCourte(conn))

    resultat = audit_harness.enregistrer_lignes("postgresql://test/test", "banque", "flore", [
        {"outil": "lire_traces", "statut": "ok"},
        {"arguments": "pas un objet"},
        "pas une ligne",
    ])

    assert resultat == {"ecrits": 1, "erreurs": 2}
    assert len(audit_harness.derniers(conn, "banque", 10)) == 1


def test_enregistrer_lignes_ne_leve_jamais_et_ne_revele_ni_dsn_ni_erreur(monkeypatch):
    def casse(*_, **__):
        raise RuntimeError("secret=postgresql://interdit")

    monkeypatch.setattr(audit_harness.psycopg, "connect", casse)
    resultat = audit_harness.enregistrer_lignes(
        "postgresql://interdit", "banque", "flore", [{"outil": "lire_traces"}, {"outil": "autre"}])

    assert resultat == {"ecrits": 0, "erreurs": 2}
    assert "postgresql" not in str(resultat)
    assert "interdit" not in str(resultat)


def test_enregistrer_lignes_sans_dsn_compte_les_erreurs_sans_se_connecter(monkeypatch):
    def interdit(*_, **__):
        raise AssertionError("aucune connexion sans DSN")

    monkeypatch.setattr(audit_harness.psycopg, "connect", interdit)
    assert audit_harness.enregistrer_lignes(None, "banque", "flore", [{"outil": "lire_traces"}]) == {
        "ecrits": 0, "erreurs": 1}
    assert audit_harness.enregistrer_lignes("postgresql://test", "banque", "flore", []) == {
        "ecrits": 0, "erreurs": 0}


@besoin_pg
def test_le_harness_ecrit_chaque_appel_dans_postgres(conn):
    audit = AuditPostgres(conn, "banque", "flore")
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application: {"traces": [application]}},
        tenant="banque",
        audit_sink=audit,
    )

    assert asyncio.run(harnais.appeler("lire_traces", {"application": "alpha"})) == {
        "traces": ["alpha"]}
    lignes = audit.derniers("banque", 10)
    assert len(lignes) == 1
    assert (lignes[0]["outil"], lignes[0]["capacite"], lignes[0]["statut"]) == (
        "lire_traces", "observer", "ok")
    assert lignes[0]["arguments"] == {"application": "alpha"}
    assert harnais.auditer()[-1]["statut"] == "ok"


@besoin_pg
def test_un_outil_en_erreur_est_audite_puis_propage_l_erreur(conn):
    def casse(application):
        raise ValueError("indisponible")

    audit = AuditPostgres(conn, "banque", "flore")
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": casse},
        tenant="banque",
        audit_sink=audit,
    )

    with pytest.raises(ValueError):
        asyncio.run(harnais.appeler("lire_traces", {"application": "alpha"}))
    lignes = audit.derniers("banque", 10)
    assert len(lignes) == 1
    assert (lignes[0]["statut"], lignes[0]["erreur"]) == ("erreur", "ValueError")


def test_l_audit_est_sans_execution_dynamique_ni_reseau():
    source = Path(audit_harness.__file__).read_text(encoding="utf-8")
    interdits = (
        r"\beval\s*\(", r"\bexec\s*\(", r"__import__\s*\(", r"\bcompile\s*\(",
        r"\bimportlib\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b",
        r"\bhttpx\b", r"\bsubprocess\b", r"\bos\.system\b", r"\bopen\s*\(",
    )
    for motif in interdits:
        assert re.search(motif, source) is None, motif
    arbre = ast.parse(source)
    autorises = {"__future__", "collections", "datetime", "json", "math", "typing",
                 "psycopg", "jumeau"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert all(alias.name.split(".")[0] in autorises for alias in noeud.names)
        if isinstance(noeud, ast.ImportFrom):
            assert (noeud.module or "").split(".")[0] in autorises
