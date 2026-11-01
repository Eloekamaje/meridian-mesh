"""Lecteur ServiceNow (sans réseau : l'ouverture d'URL est simulée)."""
import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from meridian.adapters.outbound.connectors import github
from meridian.adapters.outbound.connectors import lecteurs
from meridian.adapters.outbound.connectors import servicenow

INCIDENT = {
    "number": "INC0012345", "short_description": "Paiements : file saturée", "priority": "1 - Critique", "state": "Résolu",
    "opened_at": "2026-10-01 08:00:00", "resolved_at": "2026-10-01 09:30:00", "assignment_group": "PAY-APP",
    "cmdb_ci": "Paiements", "close_notes": "Purge de la file\net redémarrage", "sys_mod_count": "7",
    "sys_updated_on": "2026-10-01 09:31:00",
    "caller_id": "Jean Dupont", "assigned_to": "Ana Martin", "opened_by": "jean.dupont@banque.fr",  # jamais restitués
}
LIGNES = ["Paiements : file saturée", "Numéro : INC0012345", "Type : incident", "Priorité : 1 - Critique", "État : Résolu",
          "Ouvert le : 2026-10-01 08:00:00", "Résolu le : 2026-10-01 09:30:00", "Groupe d'affectation : PAY-APP",
          "Notes de clôture : Purge de la file", "Notes de clôture : et redémarrage"]


@pytest.fixture
def snow(monkeypatch):
    reponses, envoyees = {}, []

    def ouvrir(requete, timeout):
        envoyees.append(requete)
        u = urlsplit(requete.full_url)
        assert u.scheme == "https" and u.netloc == "banque.service-now.com"
        corps = reponses[u.path]
        if isinstance(corps, int):
            raise urllib.error.HTTPError(requete.full_url, corps, "refus", {}, None)
        return io.BytesIO(json.dumps({"result": corps}).encode())

    monkeypatch.setenv("JUMEAU_SERVICENOW_HOTE", "banque.service-now.com")
    monkeypatch.setattr(servicenow, "_ouvrir", ouvrir)
    monkeypatch.setattr(servicenow, "resoudre_secret", lambda ref: "svc-lecture:mdp" if ref else None)
    return reponses, envoyees


@pytest.fixture(autouse=True)
def memoire_vide():
    github._cache.clear()
    github._appels.clear()


def lecteur(ci="Paiements"):
    return servicenow.LecteurServiceNow("ServiceNow Paiements", ci, "vault:r")


def requete(envoyees, i=-1):
    return parse_qs(urlsplit(envoyees[i].full_url).query)["sysparm_query"][0]


def test_lecture_en_lignes_sans_donnees_personnelles_avec_version_et_citation(snow):
    reponses, envoyees = snow
    reponses["/api/now/table/incident"] = [INCIDENT]
    r = lecteur().lire("INC0012345")
    assert r["lignes"] == LIGNES and r["version"] == "7"
    assert r["titre"] == "INC0012345 Paiements : file saturée"
    assert r["locator"] == "servicenow://Paiements/INC0012345@7#L1-L10"
    tout = " ".join(r["lignes"]) + " ".join(u.full_url for u in envoyees)
    assert "Dupont" not in tout and "Ana" not in tout and "caller_id" not in tout and "assigned_to" not in tout
    assert requete(envoyees) == "number=INC0012345^cmdb_ci.name=Paiements"


def test_probleme_avec_sa_cause(snow):
    reponses, _ = snow
    reponses["/api/now/table/problem"] = [{"number": "PRB0001234", "short_description": "Fuite mémoire", "cmdb_ci": "Paiements",
                                           "cause_notes": "Cache sans borne", "sys_mod_count": "2"}]
    assert "Cause : Cache sans borne" in lecteur().lire("PRB0001234")["lignes"]


def test_verifier_une_citation(snow):
    reponses, _ = snow
    reponses["/api/now/table/incident"] = [INCIDENT]
    assert lecteur().verifier("servicenow://Paiements/INC0012345@7#L1-L10")
    assert not lecteur().verifier("servicenow://Paiements/INC0012345@7#L1-L11")
    assert not lecteur().verifier("servicenow://Paiements/INC0012345@6#L1-L2")  # modifié depuis
    assert not lecteur().verifier("servicenow://Autre/INC0012345@7#L1-L2")
    assert not lecteur().verifier("jira://Paiements/INC0012345@7#L1-L2")


def test_un_enregistrement_d_un_autre_ci_n_est_jamais_une_preuve(snow):
    reponses, envoyees = snow
    reponses["/api/now/table/incident"] = [{**INCIDENT, "cmdb_ci": "Comptes"}]  # même si le filtre côté ServiceNow échouait
    with pytest.raises(LookupError):
        lecteur().lire("INC0012345")
    reponses["/api/now/table/incident"] = []
    envoyees.clear()
    for ref in ("../../x", "INC1; DROP", "inc0012345", "XYZ0012345", "INC0012345^OR"):
        with pytest.raises(LookupError):
            lecteur().lire(ref)
    assert envoyees == []  # refusé avant tout appel


def test_recherche_nettoyee_et_bornee_au_ci(snow):
    reponses, envoyees = snow
    reponses["/api/now/table/incident"] = [{"number": "INC0012345", "short_description": "file saturée"}]
    reponses["/api/now/table/problem"] = []
    reponses["/api/now/table/change_request"] = [{"number": "CHG0000123", "short_description": "Montée de version"}]
    trouves = lecteur().chercher("file^ORcmdb_ci.name=Comptes")
    assert [t["ref"] for t in trouves] == ["INC0012345", "CHG0000123"]
    q = requete(envoyees, 0)
    assert q == "cmdb_ci.name=Paiements^short_descriptionLIKEfile ORcmdb_ci.name Comptes^ORDERBYDESCopened_at"
    assert q.count("^") == 2 and "=" not in q.split("^")[1]
    n = len(envoyees)
    assert lecteur().chercher('^=:"\\') == [] and len(envoyees) == n


def test_ci_invalide_refuse_avant_tout_appel(snow):
    _, envoyees = snow
    for ci in ("Paiements^ORactive=true", "a=b", "javascript:x", ""):
        with pytest.raises(github.Invalide):
            servicenow.LecteurServiceNow("x", ci, "vault:r").chercher("a")
    assert envoyees == []


def test_version_courante(snow):
    reponses, _ = snow
    reponses["/api/now/table/incident"] = [INCIDENT]
    reponses["/api/now/table/problem"] = []
    reponses["/api/now/table/change_request"] = [{"number": "CHG0000123", "sys_updated_on": "2026-10-02 10:00:00"}]
    assert lecteur().version_courante() == "INC0012345@20261001093100,CHG0000123@20261002100000"


def test_hote_non_autorise_ou_absent(snow, monkeypatch):
    monkeypatch.setenv("JUMEAU_SERVICENOW_HOTE", "evil.example.com/x")
    with pytest.raises(github.Invalide):
        lecteur().chercher("a")
    monkeypatch.delenv("JUMEAU_SERVICENOW_HOTE")
    with pytest.raises(github.Invalide):
        lecteur().chercher("a")


def test_identifiants_et_identite_prise_chez_servicenow(snow):
    reponses, envoyees = snow
    assert servicenow.identifiants(" svc-lecture ", " mdp:avec:deux-points ") == "svc-lecture:mdp:avec:deux-points"
    for mauvais in ("a:b", "a^b", "a b", ""):
        with pytest.raises(github.Invalide):
            servicenow.identifiants(mauvais, "x")
    reponses["/api/now/table/sys_user"] = [{"sys_id": "6816f79c", "user_name": "Svc-Lecture", "name": "Jean Dupont"}]
    assert servicenow.compte_du_jeton("svc-lecture:mdp") == {"login": "svc-lecture", "compte": "6816f79c", "nom": "svc-lecture"}
    assert requete(envoyees) == "user_name=svc-lecture"
    reponses["/api/now/table/sys_user"] = [{"sys_id": "1", "user_name": "autre"}]
    with pytest.raises(github.Invalide):
        servicenow.compte_du_jeton("svc-lecture:mdp")
    reponses["/api/now/table/sys_user"] = []
    with pytest.raises(github.Invalide):
        servicenow.compte_du_jeton("svc-lecture:mdp")
    reponses["/api/now/table/sys_user"] = 401
    with pytest.raises(github.JetonRefuse) as e:
        servicenow.compte_du_jeton("svc-lecture:mot-de-passe-secret")
    assert "mot-de-passe-secret" not in str(e.value)


def test_perimetres_filtres(snow):
    reponses, _ = snow
    reponses["/api/now/table/cmdb_ci_appl"] = [{"name": "Paiements", "short_description": "Moteur de paiement"}, {"name": "RH", "short_description": ""},
                                               {"name": "x^y", "short_description": ""}]
    assert servicenow.perimetres("vault:r", "paie") == [{"cle": "Paiements", "nom": "Moteur de paiement"}]
    assert [p["cle"] for p in servicenow.perimetres("vault:r")] == ["Paiements", "RH"]


def test_debit_limite_par_compte(snow):
    reponses, envoyees = snow
    reponses["/api/now/table/incident"] = []
    for _ in range(github.MAX_APPELS_MINUTE):
        servicenow._table("vault:r", "incident", "number=INC0000001", "number", 1)
    with pytest.raises(github.TropDeDemandes):
        servicenow._table("vault:r", "incident", "number=INC0000001", "number", 1)
    assert len(envoyees) == github.MAX_APPELS_MINUTE


def test_ci_invalide_refuse_avant_de_devenir_une_source():
    with pytest.raises(ValueError):
        servicenow.source_de({"ci": "Paiements^ORactive=true", "secret": "vault:x"})


def test_source_prete(monkeypatch):
    monkeypatch.setenv("JUMEAU_SERVICENOW_HOTE", "banque.service-now.com")
    s = servicenow.source_de({"ci": "Paiements", "secret": "vault:x"})
    assert (s["type"], s["emplacement"], s["secret_ref"]) == ("SERVICENOW", "Paiements", "vault:x")


def test_fabrique_et_nature():
    ligne = {"type": "SERVICENOW", "nom": "servicenow-Paiements", "emplacement": "Paiements", "secret_ref": "vault:r"}
    [l] = lecteurs.lecteurs_de([ligne, {"type": "GIT"}])
    assert (l.systeme, l.espace, l.nature) == ("servicenow", "Paiements", "exploitation")


def test_test_de_connexion(snow):
    reponses, _ = snow
    reponses["/api/now/table/cmdb_ci_appl"] = [{"name": "Paiements"}]
    reponses["/api/now/table/incident"] = []
    assert servicenow.tester({"secret": "vault:r", "ci": "Paiements"})["statut"] == "prete"
    reponses["/api/now/table/cmdb_ci_appl"] = []
    assert servicenow.tester({"secret": "vault:r", "ci": "Paiements"})["statut"] == "perimetre_vide"
    assert servicenow.tester({"secret": "vault:r"})["statut"] == "configuration_incomplete"
    assert servicenow.tester({"ci": "Paiements"})["statut"] == "autorisation_insuffisante"
    reponses["/api/now/table/cmdb_ci_appl"] = 403
    assert servicenow.tester({"secret": "vault:r", "ci": "Paiements"})["statut"] == "autorisation_insuffisante"
