"""Naissance d'un jumeau depuis la commande : source GitHub réelle, clone, ingestion, fiche, registre."""
import asyncio
import os
import subprocess
import uuid

import pytest

from jumeau import depot, naissance
from jumeau.tests.conftest import besoin_pg


@pytest.fixture(autouse=True)
def depots_locaux_autorises(monkeypatch):
    monkeypatch.setenv("JUMEAU_DEPOTS_LOCAUX", "1")
    monkeypatch.delenv("JUMEAU_GIT_HOTE", raising=False)


@pytest.fixture
def depot_distant(tmp_path):
    """Un dépôt « distant » (nu) avec une branche main contenant une petite API FastAPI."""
    travail, nu = tmp_path / "travail", tmp_path / "distant.git"
    subprocess.run(["git", "init", "-q", "-b", "main", str(travail)], check=True)
    (travail / "requirements.txt").write_text("fastapi==0.1\n")
    (travail / "api.py").write_text('from fastapi import FastAPI\napp = FastAPI()\n\n\n@app.get("/remboursements")\n'
                                    'def remboursements():\n    return []\n')
    subprocess.run(["git", "-C", str(travail), "add", "."], check=True)
    subprocess.run(["git", "-C", str(travail), "-c", "user.name=A", "-c", "user.email=a@a", "commit", "-qm", "init"],
                   check=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(travail), str(nu)], check=True)
    return nu


def test_url_du_depot_github_ou_explicite(monkeypatch):
    monkeypatch.delenv("JUMEAU_GIT_HOTE", raising=False)
    assert naissance.url_depot({"organisation": "banque", "depots": "pay-remboursements, autre"}) == \
        "https://github.com/banque/pay-remboursements.git"
    monkeypatch.setenv("JUMEAU_GIT_HOTE", "git.banque.intra")
    assert naissance.url_depot({"organisation": "banque", "depots": "x"}) == "https://git.banque.intra/banque/x.git"
    assert naissance.url_depot({"url": "file:///depots/x.git"}) == "file:///depots/x.git"
    with pytest.raises(ValueError):
        naissance.url_depot({"organisation": "banque; rm", "depots": "x"})


def test_ni_hote_arbitraire_ni_chemin_local_hors_developpement(monkeypatch):
    monkeypatch.delenv("JUMEAU_DEPOTS_LOCAUX")
    for url in ("file:///etc/depot.git", "https://interne.evil/x.git", "https://github.com.evil/x.git"):
        with pytest.raises(ValueError):
            naissance.url_depot({"url": url})
    assert naissance.url_depot({"url": "https://github.com/o/d.git"}) == "https://github.com/o/d.git"


def test_resolution_du_secret(monkeypatch):
    monkeypatch.setenv("JETON_TEST", "abc")
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    assert naissance.resoudre_secret("env:JETON_TEST") == "abc"
    assert naissance.resoudre_secret("") is None
    with pytest.raises(RuntimeError):
        naissance.resoudre_secret("vault:meridian/github/banque#jeton")  # Vault non configuré


def test_le_jeton_ne_passe_ni_par_l_url_ni_par_la_ligne_de_commande():
    env = naissance.env_git("s3cr3t")
    assert "s3cr3t" not in " ".join(naissance.commande_git(["ls-remote", "https://h/o/d.git"]))
    assert any("s3cr3t" not in v and "Authorization" in v for k, v in env.items() if k.startswith("GIT_CONFIG_VALUE"))


def test_tester_une_source_reelle(depot_distant):
    ok = naissance.tester_git({"url": f"file://{depot_distant}", "branches": "main"})
    assert ok["statut"] == "prete" and ok["dernier_test"]["resultat"] == "ok"
    absente = naissance.tester_git({"url": f"file://{depot_distant}", "branches": "inexistante"})
    assert absente["statut"] == "perimetre_vide"
    injoignable = naissance.tester_git({"url": "file:///nulle/part.git", "branches": "main"})
    assert injoignable["statut"] == "erreur_connexion" and injoignable["erreur"]["titre"]


def test_cloner_puis_mettre_a_jour(depot_distant, tmp_path):
    cible = tmp_path / "clone"
    naissance.cloner({"url": f"file://{depot_distant}", "branches": "main"}, cible)
    assert (cible / "api.py").exists()
    naissance.cloner({"url": f"file://{depot_distant}", "branches": "main"}, cible)  # deuxième fois : mise à jour


@besoin_pg
@pytest.mark.skipif(not os.environ.get("MONGO_URL") or not os.environ.get("CBM_BIN"), reason="Mongo et cbm requis")
def test_naissance_complete_depuis_une_commande(conn, depot_distant, tmp_path, monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    from jumeau import cbm, ingerer
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    monkeypatch.setattr(naissance, "DEPOTS", tmp_path / "depots")
    commande = {"id": "cmd-1", "jumeau": {"nom": "Remboursements", "domaine": "Paiement",
                                          "mission": "Traite les remboursements", "proprietaire": "Équipe Paiements"},
                "sources": [{"id": "src-gh", "connecteur": "github", "statut": "prete",
                             "config": {"url": f"file://{depot_distant}", "branches": "main"}}]}

    async def rediger_factice(ctx, dsn, sigs, commits):
        return "Fiche de Remboursements", None

    async def scenario():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        nom_db = f"test_naissance_{uuid.uuid4().hex[:8]}"
        db = client[nom_db]
        try:
            await db.commandes.insert_one(dict(commande))
            await db.jumeaux.insert_one({"id": "remboursements", "nom": "Remboursements", "statut": "observation"})
            await naissance.naitre(conn, db, commande, "remboursements", rediger=rediger_factice)
            return (await db.commandes.find_one({"id": "cmd-1"}), await db.jumeaux.find_one({"id": "remboursements"}))
        finally:
            await client.drop_database(nom_db)
            client.close()

    try:
        cmd, registre = asyncio.run(scenario())
    finally:
        source = depot.source_du_jumeau(conn, "remboursements")
        if source:
            cbm.texte("delete_project", "--project", source["index_code"])
    assert cmd["naissance"]["etat"] == "ne" and [e["etape"] for e in cmd["naissance"]["etapes"]] == \
        ["clone", "ingestion", "fiche"]
    assert registre["reel"] is True and registre["statut"] == "observation"  # l'admission reste humaine
    assert {c["objet"] for c in depot.lister_claims(conn, "remboursements")} >= {"GET /remboursements", "fastapi"}
