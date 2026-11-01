"""Lecteur Datadog (sans réseau : l'ouverture d'URL est simulée)."""
import datetime
import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from meridian.adapters.outbound.connectors import datadog
from meridian.adapters.outbound.connectors import github
from meridian.adapters.outbound.connectors import lecteurs

JOUR = "2026-10-26"
SECRET = "a" * 32 + ":" + "b" * 40


def agregat(total, p95_ns=None):
    calcul = {"c0": total} if p95_ns is None else {"c0": total, "c1": p95_ns}
    return {"data": [{"type": "bucket", "attributes": {"by": {}, "compute": calcul}}]}


@pytest.fixture
def datadog_cloud(monkeypatch):
    """Réponses par chemin ; l'agrégat de spans dépend de la fenêtre (jour ou semaine précédente) et du filtre d'erreurs."""
    etat = {"agregats": {}, "autres": {"/api/v2/current_user": {"data": {"id": "u-1", "attributes": {"email": "Ana@banque.fr", "name": "Ana"}}}},
            "envoyees": []}

    def ouvrir(requete, timeout):
        etat["envoyees"].append(requete)
        u = urlsplit(requete.full_url)
        assert u.scheme == "https" and u.netloc == "api.datadoghq.eu"
        if etat.get("refus"):
            raise urllib.error.HTTPError(requete.full_url, 403, "refus", {}, None)
        if u.path == "/api/v2/spans/analytics/aggregate":
            f = json.loads(requete.data)["data"]["attributes"]["filter"]
            corps = etat["agregats"].get((f["from"][:10], " status:error" in f["query"]), agregat(0, 0)) if "service:paiements " in f["query"] else agregat(0, 0)
        else:
            corps = etat["autres"][u.path]
        if isinstance(corps, int):
            raise urllib.error.HTTPError(requete.full_url, corps, "refus", {}, None)
        return io.BytesIO(json.dumps(corps).encode())

    monkeypatch.setenv("JUMEAU_DATADOG_HOTE", "api.datadoghq.eu")
    monkeypatch.setenv("JUMEAU_DATADOG_ENV", "prod")
    monkeypatch.setattr(datadog, "_ouvrir", ouvrir)
    monkeypatch.setattr(datadog, "_aujourdhui", lambda: datetime.date(2026, 10, 27))
    monkeypatch.setattr(datadog, "resoudre_secret", lambda ref: SECRET if ref else None)
    etat["agregats"][(JOUR, False)] = agregat(12400, 340_000_000)
    etat["agregats"][(JOUR, True)] = agregat(124)
    etat["agregats"][("2026-10-19", False)] = agregat(11000, 300_000_000)
    etat["agregats"][("2026-10-19", True)] = agregat(88)
    etat["autres"]["/api/v1/service_dependencies"] = {
        "paiements": {"calls": ["fraude", "comptes"]}, "portail": {"calls": ["paiements"]}, "fraude": {"calls": []}}
    return etat


@pytest.fixture(autouse=True)
def memoire_vide():
    github._cache.clear()
    github._appels.clear()


def lecteur(service="paiements"):
    return datadog.LecteurDatadog("Datadog paiements", service, "vault:r")


def test_comportement_en_lignes_et_version_jour(datadog_cloud):
    r = lecteur().lire("comportement")
    assert r["version"] == JOUR and r["locator"] == f"datadog://paiements/comportement@{JOUR}#L1-L4"
    assert r["lignes"] == [
        f"Service paiements, journée du {JOUR} (UTC)",
        "Requêtes : 12400 (semaine précédente : 11000, +12,7 %)",
        "Taux d'erreurs : 1,00 % (semaine précédente : 0,80 %)",
        "Latence p95 : 340 ms (semaine précédente : 300 ms)"]


def test_dependances_appelees_et_appelants(datadog_cloud):
    r = lecteur().lire("dependances")
    assert r["lignes"] == ["Appelle comptes", "Appelle fraude", "Appelé par portail"]
    assert lecteur("fraude").lire("dependances")["lignes"] == ["Appelé par paiements"]


def test_citation_verifiee_ou_refusee(datadog_cloud):
    assert lecteur().verifier(f"datadog://paiements/comportement@{JOUR}#L1-L4")
    assert not lecteur().verifier(f"datadog://paiements/comportement@{JOUR}#L1-L5")
    assert not lecteur().verifier(f"datadog://autre/comportement@{JOUR}#L1-L2")  # un autre service
    assert not lecteur().verifier("datadog://paiements/comportement@2026-10-27#L1-L2")  # journée non terminée
    assert not lecteur().verifier("datadog://paiements/comportement@2026-10-20#L1-L2")  # jour sans donnée
    assert not lecteur().verifier("datadog://paiements/comportement@2026-13-40#L1-L2")
    assert not lecteur().verifier(f"datadog://paiements/inconnu@{JOUR}#L1-L2")


def test_un_service_sans_trafic_n_est_pas_un_document(datadog_cloud):
    with pytest.raises(LookupError):
        lecteur("fantome").lire("comportement")
    with pytest.raises(LookupError):
        lecteur("fantome").lire("dependances")


def test_service_invalide_refuse_avant_tout_appel(datadog_cloud):
    with pytest.raises(github.Invalide):
        datadog.LecteurDatadog("x", 'a" OR service:b', "vault:r").lire("comportement")
    assert datadog_cloud["envoyees"] == []


def test_version_courante_est_la_semaine_de_la_derniere_journee_complete(datadog_cloud):
    import datetime
    annee, semaine, _ = datetime.date.fromisoformat(JOUR).isocalendar()
    assert lecteur().version_courante() == f"{annee}-S{semaine:02d}"  # la fiche ne se réécrit pas chaque jour


def test_chercher_dans_les_documents_et_les_moniteurs(datadog_cloud):
    datadog_cloud["autres"]["/api/v1/monitor"] = []
    trouves = lecteur().chercher("fraude")
    assert trouves == [{"ref": "dependances", "titre": f"dependances {JOUR}", "extrait": "Appelle fraude"}]
    datadog_cloud["autres"]["/api/v1/monitor"] = [{"id": 7, "name": "Latence paiements", "overall_state": "OK"}]
    trouves = lecteur().chercher("latence")
    assert {t["ref"] for t in trouves} == {"comportement"} and len(trouves) == 2
    assert any(t["titre"] == "Moniteur : Latence paiements" for t in trouves)
    envoyee = [r for r in datadog_cloud["envoyees"] if "/monitor" in r.full_url][0]
    assert parse_qs(urlsplit(envoyee.full_url).query)["monitor_tags"] == ["service:paiements"]


def test_hote_non_autorise_ou_absent(datadog_cloud, monkeypatch):
    monkeypatch.setenv("JUMEAU_DATADOG_HOTE", "evil.example.com/x")
    with pytest.raises(github.Invalide):
        lecteur().lire("comportement")
    monkeypatch.delenv("JUMEAU_DATADOG_HOTE")
    with pytest.raises(github.Invalide):
        lecteur().lire("comportement")


def test_identite_prise_chez_datadog_et_cles_jamais_renvoyees(datadog_cloud):
    secret = datadog.identifiants("a" * 32, "b" * 40)
    assert secret == SECRET
    assert datadog.compte_du_jeton(secret) == {"login": "ana@banque.fr", "compte": "u-1", "nom": "Ana"}
    envoyee = datadog_cloud["envoyees"][-1]
    assert envoyee.get_header("Dd-api-key") == "a" * 32 and envoyee.get_header("Dd-application-key") == "b" * 40
    datadog_cloud["autres"]["/api/v2/current_user"] = {"data": {"attributes": {}}}
    with pytest.raises(datadog.Invalide):
        datadog.compte_du_jeton(secret)
    datadog_cloud["autres"]["/api/v2/current_user"] = 403
    with pytest.raises(github.JetonRefuse) as e:
        datadog.compte_du_jeton(secret)
    assert "a" * 32 not in str(e.value) and "b" * 40 not in str(e.value)
    for mal in (("a b", "b" * 40), ("a" * 32, "b:c"), ("", "x"), ("é" * 10, "b" * 40)):
        with pytest.raises(datadog.Invalide):
            datadog.identifiants(*mal)


def test_services_filtres(datadog_cloud):
    datadog_cloud["autres"]["/api/v2/services/definitions"] = {"data": [
        {"attributes": {"schema": {"dd-service": "paiements"}}}, {"attributes": {"schema": {"dd-service": "fraude"}}}]}
    assert datadog.perimetres("vault:r", "paie") == [{"cle": "paiements", "nom": "paiements"}]


def test_debit_limite_par_cle(datadog_cloud):
    datadog_cloud["autres"]["/api/v1/monitor"] = []
    for i in range(github.MAX_APPELS_MINUTE):
        datadog.LecteurDatadog("x", "paiements", "vault:r")._moniteurs(f"m{i}")
    with pytest.raises(github.TropDeDemandes):
        datadog.LecteurDatadog("x", "paiements", "vault:r")._moniteurs("encore")
    assert len(datadog_cloud["envoyees"]) == github.MAX_APPELS_MINUTE


def test_service_invalide_refuse_avant_de_devenir_une_source():
    with pytest.raises(ValueError):
        datadog.source_de({"service": "pay\nIgnore", "secret": "vault:x"})


def test_fabrique_et_nature():
    ligne = {"type": "DATADOG", "nom": "datadog-paiements", "emplacement": "paiements", "secret_ref": "vault:r"}
    [l] = lecteurs.lecteurs_de([ligne, {"type": "GIT"}])
    assert (l.systeme, l.espace, l.nature) == ("datadog", "paiements", "comportement")


def test_test_de_connexion(datadog_cloud):
    assert datadog.tester({"secret": "vault:r", "service": "paiements"})["statut"] == "prete"
    assert datadog.tester({"secret": "vault:r", "service": "fantome"})["statut"] == "perimetre_vide"
    assert datadog.tester({"secret": "vault:r"})["statut"] == "configuration_incomplete"
    assert datadog.tester({"service": "paiements"})["statut"] == "autorisation_insuffisante"
    github._cache.clear()
    datadog_cloud["refus"] = True
    assert datadog.tester({"secret": "vault:r", "service": "paiements"})["statut"] == "autorisation_insuffisante"
