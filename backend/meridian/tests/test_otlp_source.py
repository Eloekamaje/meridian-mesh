"""Source OTLP de bout en bout : catalogue, test simulé, persistance et naissance.

L'OTLP est une source runtime : l'URL, la référence de secret et les deux selects sont validés sans réseau, puis la
configuration (jamais le secret brut) est rangée en jsonb. Elle reste hors du code (GIT) tout en restant lisible par
`toutes_les_sources`.
"""
import asyncio

import pytest

from meridian.adapters.outbound.connectors import connecteurs
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.connectors import naissance
from meridian.tests.conftest import JUMEAU, besoin_pg
from seed_data import CONNECTEURS

URL = "https://collecteur.exemple.fr/v1/traces"
HOTE = "collecteur.exemple.fr"
SECRET = "env:MERIDIAN_OTLP_TOKEN"


def source_otlp(**config):
    complet = {"url": URL, "secret_ref": SECRET, "environnement": "production", "frequence": "horaire"}
    complet.update(config)
    return {"id": "src-otlp", "connecteur": "otlp", "nom": "APM production", "statut": "prete",
            "config": complet}


def test_catalogue_otlp_complet_et_branche():
    connecteur = next(c for c in CONNECTEURS if c["id"] == "otlp")
    assert (connecteur["nom"], connecteur["categorie"]) == ("APM / Gateway OTLP", "Observabilité")
    assert connecteur["capacites"] == "traces observées, appels consommés/exposés"
    champs = {ch["cle"]: ch for ch in connecteur["champs"]}
    assert set(champs) == {"url", "secret_ref", "environnement", "frequence"}
    assert champs["url"]["requis"] is True and champs["secret_ref"]["requis"] is True
    assert champs["url"]["type"] == champs["secret_ref"]["type"] == "texte"
    assert "perimetre" not in champs
    assert champs["environnement"]["options"] == ["production", "préproduction", "recette", "développement"]
    assert champs["frequence"]["options"] == ["horaire", "quotidienne", "hebdomadaire"]
    assert connecteurs.connecteur_branche("otlp") == "otlp"


def test_otlp_prete_sans_perimetre_des_que_url_secret_et_hote_sont_valides(monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    resultat = connecteurs.test_simule(source_otlp(), CONNECTEURS)
    assert resultat["statut"] == "prete" and resultat["erreur"] is None
    assert resultat["dernier_test"]["resultat"] == "ok"


@pytest.mark.parametrize("url", [
    "http://collecteur.exemple.fr/v1/traces",
    "https://user:motdepasse@collecteur.exemple.fr/v1/traces",
    "https://127.0.0.1/v1/traces",
    "https://localhost/v1/traces",
    "https://collecteur.exemple.fr:8443/v1/traces",
])
def test_url_invalide_ne_rend_jamais_prete(monkeypatch, url):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    resultat = connecteurs.test_simule(source_otlp(url=url), CONNECTEURS)
    assert resultat["statut"] == "configuration_incomplete"
    assert resultat["dernier_test"]["resultat"] == "echec"
    assert resultat["erreur"]["action"]


@pytest.mark.parametrize("secret_ref", ["coffre/otlp", "env:", "vault:", "vault:meridian/../autre#jeton",
                                        "env:JETON\nInjection"])
def test_reference_de_secret_invalide_refusee(monkeypatch, secret_ref):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    resultat = connecteurs.test_simule(source_otlp(secret_ref=secret_ref), CONNECTEURS)
    assert resultat["statut"] == "configuration_incomplete"
    assert "secret" in resultat["erreur"]["detail"].lower()


def test_hote_non_autorise_refuse_avant_tout_reseau(monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", "autre.exemple.fr")
    resultat = connecteurs.test_simule(source_otlp(), CONNECTEURS)
    assert resultat["statut"] == "configuration_incomplete"
    assert "autoris" in resultat["erreur"]["detail"].lower()


def test_hote_autorise_manquant_refuse(monkeypatch):
    monkeypatch.delenv("JUMEAU_OTLP_HOTES", raising=False)
    resultat = connecteurs.test_simule(source_otlp(), CONNECTEURS)
    assert resultat["statut"] == "configuration_incomplete"
    assert "JUMEAU_OTLP_HOTES" in resultat["erreur"]["detail"]


def test_environnement_ou_frequence_hors_catalogue_refuses(monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    assert connecteurs.test_simule(source_otlp(environnement="dev"),
                                   CONNECTEURS)["statut"] == "configuration_incomplete"
    assert connecteurs.test_simule(source_otlp(frequence="temps réel"),
                                   CONNECTEURS)["statut"] == "configuration_incomplete"


def test_source_de_otlp_ne_recopie_jamais_un_secret_brut():
    source = connecteurs.source_de_otlp(source_otlp(secret="jeton-brut-interdit"))
    assert set(source["configuration"]) == {"url", "secret_ref", "environnement", "frequence"}
    assert "jeton-brut-interdit" not in str(source)


@besoin_pg
def test_declarer_source_otlp_persiste_la_configuration_sans_secret_brut(conn):
    depot.creer_jumeau(conn, JUMEAU)
    source = connecteurs.source_de_otlp(source_otlp())
    depot.declarer_source(conn, JUMEAU, source)
    depot.declarer_source(conn, JUMEAU, source)  # idempotent : une seule ligne

    [ligne] = depot.toutes_les_sources(conn, "tbt")
    assert (ligne["type"], ligne["nom"], ligne["emplacement"]) == ("OTLP", "APM production", URL)
    assert (ligne["url"], ligne["secret_ref"]) == (URL, SECRET)
    assert ligne["configuration"] == {"url": URL, "secret_ref": SECRET, "environnement": "production",
                                      "frequence": "horaire"}
    assert set(ligne["configuration"]) == {"url", "secret_ref", "environnement", "frequence"}
    assert depot.sources_du_jumeau(conn, "tbt") == []
    [runtime] = depot.sources_runtime(conn, "tbt")
    assert runtime["id"] == ligne["id"] and runtime["configuration"] == ligne["configuration"]


@besoin_pg
def test_declarer_source_upsert_la_configuration_et_accepte_une_ligne_sans_url(conn):
    depot.creer_jumeau(conn, JUMEAU)
    depot.declarer_source(conn, JUMEAU, {"type": "OTLP", "nom": "otlp",
                                         "configuration": {"url": URL, "secret_ref": SECRET,
                                                           "environnement": "recette",
                                                           "frequence": "hebdomadaire"}})
    [ligne] = depot.sources_runtime(conn, "tbt")
    assert (ligne["emplacement"], ligne["url"], ligne["secret_ref"]) == (URL, URL, SECRET)
    assert ligne["configuration"]["environnement"] == "recette"

    depot.declarer_source(conn, JUMEAU, {"type": "OTLP", "nom": "otlp",
                                         "configuration": {"url": URL, "secret_ref": SECRET,
                                                           "environnement": "production",
                                                           "frequence": "quotidienne"}})
    [ligne] = depot.sources_runtime(conn, "tbt")
    assert ligne["configuration"]["environnement"] == "production"
    assert ligne["configuration"]["frequence"] == "quotidienne"


def _commande(*sources):
    return {"jumeau": {"nom": "Progiciel", "proprietaire": "Équipe"}, "sources": list(sources)}


def test_otlp_est_une_substance_sans_code_avec_servicenow():
    commande = _commande(
        {"id": "sn", "connecteur": "servicenow", "statut": "prete",
         "config": {"ci": "CI-1", "secret": "env:MERIDIAN_SN"}},
        source_otlp())
    ancre, substance = naissance.substance_sans_code(commande)
    assert ancre["connecteur"] == "servicenow"
    assert substance["connecteur"] == "otlp"


def test_naissance_declare_otlp_avec_ou_sans_github(monkeypatch):
    declarees = []
    monkeypatch.setattr(depot, "declarer_source", lambda conn, j, s: declarees.append(s))
    github = {"id": "gh", "connecteur": "github", "statut": "prete",
              "config": {"url": "https://github.com/banque/api.git", "branches": "main"}}
    naissance._declarer_sources(None, JUMEAU, _commande(github, source_otlp()))
    assert [s["type"] for s in declarees] == ["OTLP"]
    assert declarees[0]["configuration"]["url"] == URL


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


def test_naissance_sans_code_avec_servicenow_et_otlp(monkeypatch):
    monkeypatch.setenv("JUMEAU_SERVICENOW_HOTE", "banque.service-now.com")
    appels = []
    monkeypatch.setattr(naissance, "_verifier_sources", lambda commande: None)  # aucun réseau
    monkeypatch.setattr(depot, "creer_jumeau", lambda conn, j: appels.append(("jumeau", j["id"])))
    monkeypatch.setattr(depot, "declarer_source", lambda conn, j, s: appels.append(("source", s["type"])))

    async def projeter(db, conn):
        appels.append(("registre",))

    async def veiller(conn, db, jid, **kw):
        appels.append(("veiller", jid))

    monkeypatch.setattr(naissance.registre, "projeter", projeter)
    monkeypatch.setattr(naissance.gardien, "veiller", veiller)
    commande = {"id": "c1", **_commande(
        {"id": "sn", "connecteur": "servicenow", "statut": "prete",
         "config": {"ci": "CI-1", "secret": "env:MERIDIAN_SN"}},
        source_otlp())}
    db = _Db()
    asyncio.run(naissance.naitre(None, db, commande, "progiciel"))
    assert _etat(db)["etat"] == "ne"
    assert appels == [("jumeau", "progiciel"), ("source", "SERVICENOW"), ("source", "OTLP"),
                      ("registre",), ("veiller", "progiciel")]
