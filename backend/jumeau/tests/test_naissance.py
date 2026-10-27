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
    monkeypatch.setenv("MERIDIAN_JETON_TEST", "abc")
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    assert naissance.resoudre_secret("env:MERIDIAN_JETON_TEST") == "abc"
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


@pytest.mark.parametrize("url", ["https://github.com@evil.example/x.git", "https://evil.example/github.com/x.git",
                                 "https://github.com:8443/x.git", "http://github.com/x.git",
                                 "https://user:pw@github.com/x.git", "https://github.com.evil/x.git"])
def test_url_analysee_et_non_comparee_par_prefixe(monkeypatch, url):
    monkeypatch.delenv("JUMEAU_DEPOTS_LOCAUX")
    with pytest.raises(ValueError):
        naissance.url_depot({"url": url})


def test_organisation_en_points_refusee():
    for nom in (".", ".."):
        with pytest.raises(ValueError):
            naissance.url_depot({"organisation": nom, "depots": "x"})


def test_git_recoit_un_environnement_minimal_sans_redirection_ni_hooks(monkeypatch):
    monkeypatch.setenv("VAULT_TOKEN", "jeton-vault")
    monkeypatch.setenv("GIT_SSH_COMMAND", "evil")
    env = naissance.env_git("s3cr3t")
    assert "VAULT_TOKEN" not in env and "GIT_SSH_COMMAND" not in env and "PATH" in env
    config = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert config["http.followRedirects"] == "false" and config["core.hooksPath"] == "/dev/null"
    assert config["protocol.allow"] == "never" and config["protocol.https.allow"] == "always"


def test_references_de_secret_bornees(monkeypatch):
    monkeypatch.setenv("VAULT_TOKEN", "x")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.intra")
    for ref in ("env:VAULT_TOKEN", "env:JUMEAU_PG_DSN", "vault:autre/secret#jeton", "vault:meridian/../autre#jeton"):
        with pytest.raises(RuntimeError):
            naissance.resoudre_secret(ref)
    monkeypatch.setenv("MERIDIAN_JETON_GITHUB", "abc")
    assert naissance.resoudre_secret("env:MERIDIAN_JETON_GITHUB") == "abc"


def test_delai_depasse_donne_un_echec_propre(monkeypatch, depot_distant):
    def trop_long(*_, **__):
        raise subprocess.TimeoutExpired("git", 30)
    monkeypatch.setattr(naissance.subprocess, "run", trop_long)
    assert naissance.tester_git({"url": f"file://{depot_distant}", "branches": "main"})["statut"] == "erreur_connexion"


def test_plusieurs_depots_chacun_sur_sa_branche():
    config = {"organisation": "banque", "depots": "tbt-api@main, tbt-front@develop, tbt-infra", "branches": "release"}
    assert naissance.depots_de(config) == [("tbt-api", "main"), ("tbt-front", "develop"), ("tbt-infra", "release")]
    assert naissance.depots_de({"organisation": "o", "depots": "seul"}) == [("seul", "main")]
    with pytest.raises(ValueError):
        naissance.depots_de({"organisation": "o", "depots": "x@-oups"})


def depot_nu(tmp_path, nom, branche, fichiers):
    """Dépôt distant (nu) avec une branche donnée ; renvoie (chemin du dépôt nu, chemin de travail)."""
    travail, nu = tmp_path / f"{nom}-travail", tmp_path / f"{nom}.git"
    subprocess.run(["git", "init", "-q", "-b", branche, str(travail)], check=True)
    for f, contenu in fichiers.items():
        (travail / f).write_text(contenu)
    subprocess.run(["git", "-C", str(travail), "add", "."], check=True)
    subprocess.run(["git", "-C", str(travail), "-c", "user.name=A", "-c", "user.email=a@a", "commit", "-qm", "init"],
                   check=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(travail), str(nu)], check=True)
    subprocess.run(["git", "-C", str(travail), "remote", "add", "origin", str(nu)], check=True)
    return nu, travail


@besoin_pg
@pytest.mark.skipif(not os.environ.get("MONGO_URL") or not os.environ.get("CBM_BIN"), reason="Mongo et cbm requis")
def test_naissance_puis_veille_avec_deux_depots_sur_deux_branches(conn, tmp_path, monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    from jumeau import cbm, gardien, ingerer
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    monkeypatch.setattr(naissance, "DEPOTS", tmp_path / "depots")
    api_nu, _ = depot_nu(tmp_path, "tbt-api", "main", {"requirements.txt": "fastapi==0.1\n"})
    front_nu, front_travail = depot_nu(tmp_path, "tbt-front", "develop",
                                       {"package.json": '{"dependencies": {"axios": "^1"}}\n'})
    commande = {"id": "cmd-2", "jumeau": {"nom": "TBT", "proprietaire": "Équipe TBT"},
                "sources": [{"id": "a", "connecteur": "github", "statut": "prete",
                             "config": {"url": f"file://{api_nu}", "branches": "main"}},
                            {"id": "f", "connecteur": "github", "statut": "prete",
                             "config": {"url": f"file://{front_nu}", "branches": "develop"}}]}

    async def rediger_factice(ctx, dsn, sigs, commits):
        return f"Fiche ({len(ctx['sources'])} dépôts)", None

    async def scenario():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        nom_db = f"test_multi_{uuid.uuid4().hex[:8]}"
        db = client[nom_db]
        try:
            await db.commandes.insert_one(dict(commande))
            await naissance.naitre(conn, db, commande, "tbt", rediger=rediger_factice)
            etat = (await db.commandes.find_one({"id": "cmd-2"}))["naissance"]
            # Un nouveau commit sur le seul front (branche develop), poussé sur le dépôt distant.
            (front_travail / "package.json").write_text('{"dependencies": {"axios": "^1", "react": "^18"}}\n')
            subprocess.run(["git", "-C", str(front_travail), "-c", "user.name=A", "-c", "user.email=a@a", "commit",
                            "-qam", "Ajoute React"], check=True)
            subprocess.run(["git", "-C", str(front_travail), "push", "-q", "origin", "develop"], check=True)
            veille = await gardien.veiller(conn, db, "tbt", rediger=rediger_factice)
            return etat, veille
        finally:
            await client.drop_database(nom_db)
            client.close()

    try:
        etat, veille = asyncio.run(scenario())
    finally:
        for s in depot.sources_du_jumeau(conn, "tbt"):
            cbm.texte("delete_project", "--project", s["index_code"])
    assert etat["etat"] == "ne" and sorted(etat["depots"]) == ["tbt-api", "tbt-front"]
    assert [(s["nom"], s["branche"]) for s in depot.sources_du_jumeau(conn, "tbt")] == \
        [("tbt-api", "main"), ("tbt-front", "develop")]
    assert veille["depots"] == ["tbt-front"] and veille["signaux"] == 1  # react : nouvelle dépendance
    assert {c["objet"] for c in depot.lister_claims(conn, "tbt")} >= {"fastapi", "axios", "react"}  # rien de fermé
    assert gardien.fiche_courante(conn, "tbt")["contenu"] == "Fiche (2 dépôts)"


def test_deux_depots_homonymes_refuses():
    commande = {"sources": [
        {"connecteur": "github", "statut": "prete", "config": {"organisation": "a", "depots": "api"}},
        {"connecteur": "github", "statut": "prete", "config": {"organisation": "b", "depots": "api@develop"}}]}
    with pytest.raises(ValueError, match="même nom"):
        naissance.sources_de_code(commande)


@pytest.mark.skipif(not os.environ.get("VAULT_TOKEN"), reason="Vault local requis")
def test_jeton_colle_depose_dans_vault_et_remplace_par_sa_reference():
    config = {"organisation": "o", "depots": "d", "secret": "ghp_jeton_de_test"}
    proteges = naissance.proteger_secrets(config, ["secret"], "cmd-test/src-1")
    assert proteges["secret"] == "vault:meridian/commandes/cmd-test/src-1#jeton"
    assert naissance.resoudre_secret(proteges["secret"]) == "ghp_jeton_de_test"
    # Une référence déjà posée n'est pas réécrite ; une valeur vide reste vide.
    assert naissance.proteger_secrets(proteges, ["secret"], "cmd-test/src-1") == proteges
    assert naissance.proteger_secrets({"secret": ""}, ["secret"], "x/y") == {"secret": ""}


def test_couples_depot_branche_choisis_dans_l_interface():
    config = {"secret": "vault:meridian/x#jeton", "selection": [
        {"depot": "banque/paie-api", "branche": "main"}, {"depot": "banque/paie-front", "branche": "release/2026-11"},
        {"depot": "", "branche": ""}]}  # ligne ajoutée mais pas encore remplie : ignorée
    configs = naissance.configs_depots(config)
    assert [(naissance.url_depot(c), naissance.branche(c)) for c in configs] == [
        ("https://github.com/banque/paie-api.git", "main"),
        ("https://github.com/banque/paie-front.git", "release/2026-11")]
    assert all(c["secret"] == "vault:meridian/x#jeton" for c in configs)
    with pytest.raises(ValueError):
        naissance.configs_depots({"selection": [{"depot": "sans-proprietaire", "branche": "main"}]})
