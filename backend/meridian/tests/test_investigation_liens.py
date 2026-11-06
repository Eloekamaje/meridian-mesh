"""Enquête bornée sur un cas, avec les bindings et manifestes persistés."""
from __future__ import annotations

import os

import pytest

from meridian.adapters.outbound.postgres import decouverte_liens as depot_liens
from meridian.adapters.outbound.postgres import investigation_liens
from meridian.adapters.outbound.postgres import relations_naissance as depot_relations
from meridian.domain.decouverte_liens import Binding, ResolutionCase
from meridian.domain.naissance_relationnelle import Exposition, ManifesteNaissance

pytestmark = pytest.mark.skipif(
    not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")


def _cas():
    return ResolutionCase(
        tenant_id="banque", twin_id="app-a", reference="${comptes.base-url}",
        environment="prod", missing_evidence="propriété de configuration absente",
        next_check="chercher la propriété dans le déploiement", owner="Équipe app-a")


def _manifestes():
    return [
        ManifesteNaissance(
            tenant_id="banque", twin_id="app-a", birth_run_id="run-a",
            application_id="app-a", status="CONFIRMED", owner="Équipe app-a"),
        ManifesteNaissance(
            tenant_id="banque", twin_id="app-b", birth_run_id="run-b",
            application_id="app-b", status="CONFIRMED", owner="Équipe app-b",
            exposures=(Exposition(
                kind="HTTP", operation="GET /accounts/{id}", environment="prod",
                portee="SERVICE", evidence_ids=("code:controller",)),)),
    ]


def _bindings():
    return [
        Binding(kind="PROPERTY", nom="comptes.base-url",
                valeur="http://gateway.internal/accounts", environment="prod",
                source="application.yml"),
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod", source="ingress.yaml"),
        Binding(kind="SERVICE", nom="comptes-api", valeur="app-b",
                environment="prod", source="service.yaml"),
    ]


def test_enqueter_un_cas_resout_par_les_bindings_sans_ecrire_de_lien(conn):
    for manifeste in _manifestes():
        depot_relations.enregistrer_manifeste(conn, manifeste)
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)
    cas = _cas()
    depot_liens.enregistrer_resolution_case(conn, cas)

    resultat = investigation_liens.enqueter_case(conn, "banque", cas.id)

    assert resultat["investigation"]["arret"] == "candidat trouvé"
    assert len(resultat["investigation"]["candidats"]) == 1
    assert resultat["investigation"]["candidats"][0]["twin_id"] == "app-b"
    assert resultat["case"]["attempts"] == 1
    assert resultat["case"]["candidates"][0]["twin_id"] == "app-b"
    assert resultat["case"]["next_check"] == "revue des candidats"
    # L'enquête propose ; elle ne crée aucune relation.
    assert depot_relations.lister_propositions(conn, "banque") == []


def test_enqueter_sans_binding_laisse_le_cas_ouvert(conn):
    cas = _cas()
    depot_liens.enregistrer_resolution_case(conn, cas)

    resultat = investigation_liens.enqueter_case(conn, "banque", cas.id)

    assert resultat["case"]["status"] == "open"
    assert resultat["case"]["candidates"] == []
    assert resultat["investigation"]["budget_atteint"] is True
    assert depot_relations.lister_propositions(conn, "banque") == []


def test_le_registre_des_twins_sert_de_cmdb(conn):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s)",
        ("comptes", "banque", "comptes", "Équipe comptes"))
    cas = ResolutionCase(
        tenant_id="banque", twin_id="app-a", reference="comptes",
        environment="prod", missing_evidence="propriétaire inconnu",
        next_check="chercher dans l'annuaire")

    from meridian.adapters.outbound.postgres.sources_investigation import lister_cmdb
    cmdb = lister_cmdb(conn, "banque")
    assert cmdb[0]["twin_id"] == "comptes"

    depot_liens.enregistrer_resolution_case(conn, cas)
    resultat = investigation_liens.enqueter_case(conn, "banque", cas.id)

    assert resultat["investigation"]["arret"] == "candidat trouvé"
    assert resultat["investigation"]["candidats"][0]["twin_id"] == "comptes"
    assert any("jumeau:comptes" in (preuve or "")
               for preuve in resultat["investigation"]["evidence_ids"])


def test_la_copie_git_locale_alimente_l_outil_code(conn, tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text(
        "class App { String url = \"${comptes.base-url}\"; }", encoding="utf-8")
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s)",
        ("app-a", "banque", "app-a", "Équipe app-a"))
    conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) "
        "VALUES (%s, %s, %s, %s, %s)",
        ("banque", "app-a", "GIT", "app-a-src", str(tmp_path)))
    monkeypatch.setenv("JUMEAU_ENQUETE_CODE", "1")
    monkeypatch.delenv("JUMEAU_ENQUETE_CODE_ROOT", raising=False)

    from meridian.adapters.outbound.postgres.sources_investigation import lire_code_jumeau
    fichiers, diagnostics = lire_code_jumeau(conn, "banque", "app-a")

    assert "src/App.java" in fichiers
    assert "${comptes.base-url}" in fichiers["src/App.java"]
    assert diagnostics == []


def test_la_lecture_code_reutilise_les_preuves_au_sha(conn, tmp_path, monkeypatch):
    import subprocess

    from meridian.adapters.outbound.postgres import depot as depot_pg
    from meridian.adapters.outbound.postgres.sources_investigation import lire_code_preuves

    depot_git = tmp_path / "repo"
    (depot_git / "src").mkdir(parents=True)
    (depot_git / "src" / "App.java").write_text(
        "class App { String url = \"${comptes.base-url}\"; }", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(depot_git)], check=True)
    subprocess.run(["git", "-C", str(depot_git), "config", "user.email", "test@example.com"],
                   check=True)
    subprocess.run(["git", "-C", str(depot_git), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(depot_git), "add", "."], check=True)
    subprocess.run(["git", "-C", str(depot_git), "commit", "-q", "-m", "init"], check=True)
    sha = subprocess.check_output(
        ["git", "-C", str(depot_git), "rev-parse", "HEAD"], text=True).strip()

    jumeau = {"id": "app-a", "tenant_id": "banque", "nom": "App A",
              "type": "APPLICATION", "application_id": "app-a",
              "equipe": "Équipe app-a", "proprietaire": "Équipe app-a",
              "statut": "actif", "perimetre_id": "paiements"}
    claims = [{
        "sujet": "app-a", "predicat": "EXPOSE", "objet": "GET /accounts/{id}",
        "type": "API_USAGE", "confiance": 0.9,
        "preuves": [{
            "locator": f"git://repo@{sha}:src/App.java#L1-L1",
            "chemin": "src/App.java", "sha": sha, "ligne_debut": 1, "ligne_fin": 1,
            "citation": "class App", "hash": "h",
        }],
    }]
    depot_pg.enregistrer(
        conn, jumeau,
        {"nom": "repo", "type": "GIT", "emplacement": str(depot_git), "curseur": sha},
        claims, {"extracteur": "test", "version": "1"})
    monkeypatch.setenv("JUMEAU_ENQUETE_CODE", "1")

    fichiers, diagnostics = lire_code_preuves(conn, "banque", "app-a")

    assert "repo/src/App.java" in fichiers
    assert "${comptes.base-url}" in fichiers["repo/src/App.java"]
    assert diagnostics == []


def test_l_enquete_utilise_le_lecteur_servicenow(conn):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s)",
        ("comptes", "banque", "comptes-api", "Équipe comptes"))
    cas = ResolutionCase(
        tenant_id="banque", twin_id="app-a", reference="comptes",
        environment="prod", missing_evidence="propriétaire inconnu",
        next_check="chercher dans la CMDB")
    depot_liens.enregistrer_resolution_case(conn, cas)

    resultat = investigation_liens.enqueter_case(
        conn, "banque", cas.id,
        servicenow_fn=lambda recherche: [{"cle": "comptes-api", "nom": "Comptes API"}])

    assert resultat["investigation"]["arret"] == "candidat trouvé"
    assert resultat["investigation"]["candidats"][0]["twin_id"] == "comptes"
    assert "servicenow:ci:comptes-api" in resultat["investigation"]["evidence_ids"]


def test_la_lecture_code_utilise_github_au_sha(conn, monkeypatch):
    from meridian.adapters.outbound.connectors import github
    from meridian.adapters.outbound.postgres import depot as depot_pg
    from meridian.adapters.outbound.postgres.sources_investigation import lire_code_preuves

    jumeau = {"id": "app-a", "tenant_id": "banque", "nom": "App A",
              "type": "APPLICATION", "application_id": "app-a",
              "equipe": "Équipe app-a", "proprietaire": "Équipe app-a",
              "statut": "actif", "perimetre_id": "paiements"}
    claims = [{
        "sujet": "app-a", "predicat": "EXPOSE", "objet": "GET /accounts/{id}",
        "type": "API_USAGE", "confiance": 0.9,
        "preuves": [{
            "locator": "git://github.com/banque/paie@abc:src/App.java#L1-L1",
            "chemin": "src/App.java", "sha": "abc", "ligne_debut": 1, "ligne_fin": 1,
            "citation": "class App", "hash": "h",
        }],
    }]
    depot_pg.enregistrer(
        conn, jumeau,
        {"nom": "repo", "type": "GIT", "emplacement": "banque/paie", "curseur": "abc",
         "url": "https://github.com/banque/paie", "secret_ref": "vault:r"},
        claims, {"extracteur": "test", "version": "1"})
    monkeypatch.setenv("JUMEAU_ENQUETE_CODE", "1")
    monkeypatch.setattr(github, "lire_fichier",
                        lambda reference, depot, chemin, ref="": "class App { }")

    fichiers, diagnostics = lire_code_preuves(conn, "banque", "app-a")

    assert fichiers == {"repo/src/App.java": "class App { }"}
    assert diagnostics == []
