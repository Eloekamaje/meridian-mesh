"""Naissance d'un jumeau depuis la commande : source GitHub réelle, clone, ingestion, fiche, registre."""
import asyncio
import io
import os
import subprocess
import urllib.error
import uuid

import pytest

from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.connectors import naissance
from meridian.tests.conftest import besoin_pg


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


def test_secret_absent_du_coffre_est_signale(monkeypatch):
    monkeypatch.setenv("VAULT_TOKEN", "jeton-vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.intra")

    def absent(*args, **kwargs):
        raise urllib.error.HTTPError("https://vault.intra", 404, "absent", {}, None)

    monkeypatch.setattr(naissance.urllib.request, "urlopen", absent)
    with pytest.raises(naissance.SecretAbsent, match="redéclarez"):
        naissance.resoudre_secret("vault:meridian/github/gh-x#jeton")


def test_secret_incomplet_demande_redeclaration(monkeypatch):
    monkeypatch.setenv("VAULT_TOKEN", "jeton-vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.intra")
    monkeypatch.setattr(naissance.urllib.request, "urlopen",
                        lambda *a, **k: io.BytesIO(b'{"data": {"data": {}}}'))
    with pytest.raises(naissance.SecretAbsent, match="redéclarez"):
        naissance.resoudre_secret("vault:meridian/github/gh-x#jeton")


def test_ecriture_vault_404_n_est_pas_un_secret_absent(monkeypatch):
    monkeypatch.setenv("VAULT_TOKEN", "jeton-vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.intra")

    def absent(*args, **kwargs):
        raise urllib.error.HTTPError("https://vault.intra", 404, "absent", {}, None)

    monkeypatch.setattr(naissance.urllib.request, "urlopen", absent)
    with pytest.raises(naissance.CoffreIndisponible):
        naissance.deposer_jeton("connexions/github/gh-x", "ghp_x")


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
def test_naissance_complete_depuis_une_commande(conn, depot_distant, tmp_path, monkeypatch, index_jetables):
    from motor.motor_asyncio import AsyncIOMotorClient
    from meridian.adapters.outbound.connectors import cbm
    from meridian.adapters.outbound.connectors import ingerer
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
def test_naissance_puis_veille_avec_deux_depots_sur_deux_branches(conn, tmp_path, monkeypatch, index_jetables):
    from motor.motor_asyncio import AsyncIOMotorClient
    from meridian.adapters.outbound.connectors import cbm
    from meridian.adapters.outbound.llm import gardien
    from meridian.adapters.outbound.connectors import ingerer
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
def test_jeton_depose_dans_vault_et_designe_par_sa_reference():
    reference = naissance.deposer_jeton("connexions/github/gh-test", "ghp_jeton_de_test")
    assert reference == "vault:meridian/connexions/github/gh-test#jeton"
    assert naissance.resoudre_secret(reference) == "ghp_jeton_de_test"
    with pytest.raises(RuntimeError):
        naissance.deposer_jeton("../ailleurs", "x")


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


# --- naissance sans code (Sources v1 §8) : un progiciel dont la banque n'a pas le code ---

def _pretes(*connecteurs):
    return {"jumeau": {"nom": "Progiciel", "proprietaire": "Équipe"}, "sources": [
        {"id": c, "connecteur": c, "statut": "prete", "config": {"ci": "CI-1", "service": "svc", "espace": "ESP",
                                                                 "secret": "env:MERIDIAN_X"}}
        for c in connecteurs]}


def test_ancre_servicenow_et_substance_datadog_preferee_a_confluence():
    ancre, substance = naissance.substance_sans_code(_pretes("confluence", "datadog", "servicenow"))
    assert (ancre["connecteur"], substance["connecteur"]) == ("servicenow", "datadog")
    assert naissance.substance_sans_code(_pretes("servicenow", "confluence"))[1]["connecteur"] == "confluence"


def test_cmdb_est_l_alias_servicenow_pour_l_ancrage():
    ancre, substance = naissance.substance_sans_code(_pretes("cmdb", "datadog"))
    assert (ancre["connecteur"], substance["connecteur"]) == ("cmdb", "datadog")


def test_sans_servicenow_ou_sans_substance_la_naissance_dit_ce_qui_manque():
    with pytest.raises(ValueError, match="ServiceNow"):
        naissance.substance_sans_code(_pretes("datadog"))
    with pytest.raises(ValueError, match="Datadog.*Confluence"):
        naissance.substance_sans_code(_pretes("servicenow", "jira"))
    commande = _pretes("servicenow", "datadog")
    commande["sources"][0]["statut"] = "configuration_incomplete"  # ServiceNow pas prête
    with pytest.raises(ValueError):
        naissance.substance_sans_code(commande)


class _Collection:
    def __init__(self):
        self.maj = []

    async def update_one(self, filtre, op):
        self.maj.append(op["$set"])


class _Db:
    def __init__(self):
        self.commandes = _Collection()


def _etat(db):
    return {k.removeprefix("naissance."): v for m in db.commandes.maj for k, v in m.items()}


def test_etat_de_naissance_est_projete_sur_le_twin():
    class Commandes(_Collection):
        async def find_one(self, filtre, projection=None):
            return {"jumeau_id": "progiciel"}

    class Jumeaux:
        def __init__(self):
            self.maj = []

        async def update_one(self, filtre, op):
            self.maj.append((filtre, op["$set"]))

    db = _Db()
    db.commandes = Commandes()
    db.jumeaux = Jumeaux()
    asyncio.run(naissance._etat(db, "c1", etat="ne"))
    assert db.jumeaux.maj == [({"id": "progiciel"}, {"naissance_etat": "ne"})]


def test_naissance_sans_code_cree_declare_projette_et_redige(monkeypatch):
    monkeypatch.setenv("JUMEAU_DATADOG_HOTE", "api.datadoghq.eu")
    monkeypatch.setenv("JUMEAU_SERVICENOW_HOTE", "banque.service-now.com")
    appels = []
    monkeypatch.setattr(naissance, "_verifier_sources", lambda commande: None)  # sans réseau
    monkeypatch.setattr(depot, "creer_jumeau", lambda conn, j: appels.append(("jumeau", j["id"])))
    monkeypatch.setattr(depot, "declarer_source", lambda conn, j, s: appels.append(("source", s["type"])))

    async def projeter(db, conn):
        appels.append(("registre",))

    async def veiller(conn, db, jid, **kw):
        appels.append(("veiller", jid))
    monkeypatch.setattr(naissance.registre, "projeter", projeter)
    monkeypatch.setattr(naissance.gardien, "veiller", veiller)
    db = _Db()
    asyncio.run(naissance.naitre(None, db, {"id": "c1", **_pretes("servicenow", "datadog")}, "progiciel"))
    assert _etat(db)["etat"] == "ne"
    assert appels == [("jumeau", "progiciel"), ("source", "SERVICENOW"), ("source", "DATADOG"), ("registre",),
                      ("veiller", "progiciel")]


def test_naissance_sans_substance_n_ecrit_rien(monkeypatch):
    monkeypatch.setattr(depot, "creer_jumeau", lambda *a: pytest.fail("jumeau créé sans substance"))
    db = _Db()
    asyncio.run(naissance.naitre(None, db, {"id": "c1", **_pretes("servicenow")}, "progiciel"))
    etat = _etat(db)
    assert etat["etat"] == "sans_substance" and "Datadog" in etat["message"]


def test_naissance_sans_code_reportee_si_une_source_ne_repond_pas(monkeypatch):
    # Rien n'est écrit (ni jumeau, ni source, ni registre) : pas de jumeau à moitié né.
    monkeypatch.setenv("JUMEAU_DATADOG_HOTE", "api.datadoghq.eu")
    monkeypatch.setenv("JUMEAU_SERVICENOW_HOTE", "banque.service-now.com")
    monkeypatch.setattr(depot, "creer_jumeau", lambda *a: pytest.fail("jumeau créé malgré une source muette"))

    def muette(commande):
        raise RuntimeError("la source datadog-paiements ne répond pas : naissance reportée")
    monkeypatch.setattr(naissance, "_verifier_sources", muette)
    db = _Db()
    asyncio.run(naissance.naitre(None, db, {"id": "c1", **_pretes("servicenow", "datadog")}, "progiciel"))
    etat = _etat(db)
    assert etat["etat"] == "echec" and "ne répond pas" in etat["message"]


# --- naissance typée (ADR-0030) : le type du Twin décide des sources qui le font naître ---

def _commande_type(type_, *connecteurs, nom="Twin"):
    hotes = {"confluence": "banque.atlassian.net", "servicenow": "banque.service-now.com",
             "datadog": "api.datadoghq.eu", "jira": "banque.atlassian.net"}
    return {"id": f"cmd-{type_.lower()}",
            "jumeau": {"nom": nom, "proprietaire": "Équipe", "type": type_},
            "sources": [{"id": c, "connecteur": c, "statut": "prete",
                         "config": {"ci": "CI-1", "service": "svc", "espace": "ESP",
                                    "hote": hotes.get(c, "exemple.invalid"),
                                    "secret": "env:MERIDIAN_X"}}
                        for c in connecteurs]}


def _espionner_naissance(monkeypatch):
    appels = []
    monkeypatch.setattr(naissance, "_verifier_sources", lambda commande: None)
    monkeypatch.setattr(depot, "creer_jumeau", lambda conn, j: appels.append(("jumeau", j)))
    monkeypatch.setattr(depot, "declarer_source", lambda conn, j, s: appels.append(("source", s["type"])))

    async def projeter(db, conn):
        appels.append(("registre",))

    async def veiller(conn, db, jid, **kw):
        appels.append(("veiller", jid))
    monkeypatch.setattr(naissance.registre, "projeter", projeter)
    monkeypatch.setattr(naissance.gardien, "veiller", veiller)
    return appels


def test_twin_team_sans_application_id_nait_avec_confluence(monkeypatch):
    appels = _espionner_naissance(monkeypatch)
    commande = _commande_type("TEAM", "confluence", nom="Équipe Paiements")
    assert "application_id" not in commande["jumeau"]
    db = _Db()
    asyncio.run(naissance.naitre(None, db, commande, "equipe-paiements"))
    etat = _etat(db)
    assert etat["etat"] == "ne" and etat["depots"] == []
    jumeau = next(valeur for nature, valeur in appels if nature == "jumeau")
    assert jumeau["id"] == "equipe-paiements" and jumeau["type"] == "TEAM"
    assert ("source", "CONFLUENCE") in appels


def test_twin_ecosysteme_sans_code_nait_avec_confluence_et_servicenow(monkeypatch):
    appels = _espionner_naissance(monkeypatch)
    commande = _commande_type("ECOSYSTEM", "confluence", "servicenow")
    assert all(s["connecteur"] != "github" for s in commande["sources"])
    db = _Db()
    asyncio.run(naissance.naitre(None, db, commande, "ecosysteme-paiements"))
    assert _etat(db)["etat"] == "ne"
    jumeau = next(valeur for nature, valeur in appels if nature == "jumeau")
    assert jumeau["type"] == "ECOSYSTEM"
    assert {appel[1] for appel in appels if appel[0] == "source"} == {"CONFLUENCE", "SERVICENOW"}


def test_twin_resource_nait_depuis_servicenow_sans_substance(monkeypatch):
    appels = _espionner_naissance(monkeypatch)
    commande = _commande_type("RESOURCE", "servicenow")
    db = _Db()
    asyncio.run(naissance.naitre(None, db, commande, "crm-saas"))
    assert _etat(db)["etat"] == "ne"
    jumeau = next(valeur for nature, valeur in appels if nature == "jumeau")
    assert jumeau["type"] == "RESOURCE"
    assert ("source", "SERVICENOW") in appels


@pytest.mark.parametrize("type_, connecteur", [
    ("RESOURCE", "cmdb"), ("RESOURCE", "contrat"), ("SUPPLIER", "export_fournisseur"),
    ("TEAM", "sharepoint"), ("ECOSYSTEM", "teams")])
def test_sources_acceptees_selon_le_type(type_, connecteur):
    rendu, sources = naissance.regle_naissance(_commande_type(type_, connecteur))
    assert rendu == type_ and [s["connecteur"] for s in sources] == [connecteur]


@besoin_pg
def test_twin_ne_avec_un_perimetre_a_perimetre_id_persiste(conn, monkeypatch):
    monkeypatch.setattr(naissance, "_verifier_sources", lambda commande: None)

    async def projeter(db, conn):
        return None

    async def veiller(conn, db, jid, **kw):
        return None

    monkeypatch.setattr(naissance.registre, "projeter", projeter)
    monkeypatch.setattr(naissance.gardien, "veiller", veiller)
    commande = _commande_type("TEAM", "confluence", nom="Équipe Paiements")
    commande["jumeau"]["perimetre"] = "Périmètre Paiements Europe"
    db = _Db()
    asyncio.run(naissance.naitre(conn, db, commande, "equipe-paiements"))
    assert _etat(db)["etat"] == "ne"
    ligne = conn.execute(
        "SELECT perimetre, perimetre_id FROM jumeau WHERE id = %s", ("equipe-paiements",)).fetchone()
    assert ligne == ("Périmètre Paiements Europe", "perimetre-paiements-europe")


def test_application_sans_type_garde_les_regles_actuelles(monkeypatch):
    assert naissance.type_jumeau({"jumeau": {}}) == "APPLICATION"
    monkeypatch.setattr(depot, "creer_jumeau", lambda *a: pytest.fail("application créée sans substance"))
    commande = _commande_type("APPLICATION", "confluence")
    commande["jumeau"].pop("type")  # commande historique : aucun type déclaré
    db = _Db()
    asyncio.run(naissance.naitre(None, db, commande, "paie"))
    etat = _etat(db)
    assert etat["etat"] == "sans_substance" and "ServiceNow" in etat["message"]


def test_application_explicite_suit_les_memes_regles(monkeypatch):
    appels = _espionner_naissance(monkeypatch)
    db = _Db()
    asyncio.run(naissance.naitre(None, db, _commande_type("APPLICATION", "servicenow", "datadog"), "paie"))
    assert _etat(db)["etat"] == "ne"
    assert ("source", "SERVICENOW") in appels and ("source", "DATADOG") in appels


@pytest.mark.parametrize("type_", ["APPLICATION", "TEAM", "ECOSYSTEM", "RESOURCE", "SUPPLIER"])
def test_sans_source_aucun_twin_ne_nait(type_):
    with pytest.raises(ValueError, match="source"):
        naissance.regle_naissance({"jumeau": {"nom": "Orphelin", "type": type_}, "sources": []})


def test_naissance_non_applicative_sans_source_ne_cree_rien(monkeypatch):
    monkeypatch.setattr(depot, "creer_jumeau", lambda *a: pytest.fail("Twin créé sans source"))
    db = _Db()
    asyncio.run(naissance.naitre(None, db, {"id": "c1", "jumeau": {"nom": "Orphelin", "type": "TEAM"},
                                          "sources": []}, "orphelin"))
    etat = _etat(db)
    assert etat["etat"] == "echec" and "TEAM" in etat["message"] and "source" in etat["message"]


def test_type_de_twin_inconnu_est_refuse():
    with pytest.raises(ValueError, match="inconnu"):
        naissance.type_jumeau({"jumeau": {"nom": "X", "type": "PROCESS"}})
