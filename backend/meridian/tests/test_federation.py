"""Tests purs de la vue transverse de fédération."""
import copy
import json

import pytest

from meridian.application.federation import FederationRefusee, VueTransverse


def _twins():
    twin_a = {
        "twin_id": "twin-a",
        "tenant_id": "banque",
        "espace": "paiements",
        "nom": "Équipe paiements",
        "ressources": [
            {"id": "res-shared", "nom": "Base partagée", "source": "cmdb"},
            {"id": "res-a", "nom": "Appliance A", "source": "cmdb"},
            {"nom": "Ressource sans identifiant", "source": "cmdb"},
            {"id": "res-cache", "nom": "Ressource cachée", "source": "secret"},
        ],
        "applications": [
            {"application_id": "app-a", "nom": "Application A", "source": "cmdb"},
        ],
        "fournisseurs": [
            {"supplier_id": "sup-a", "nom": "Fournisseur A", "source": "contrat"},
        ],
        "equipes": [
            {"team_id": "equipe-a", "nom": "Équipe A", "source": "annuaire"},
        ],
        "claims": [
            {"id": "c-a1", "sujet": "res-shared", "predicat": "FOURNISSEUR_FOURNIT",
             "objet": "sup-a", "source": "cmdb"},
            {"id": "c-a2", "sujet": "res-cache", "predicat": "FOURNISSEUR_FOURNIT",
             "objet": "sup-a", "source": "secret"},
        ],
        "acl": {
            "sources_visibles": ["cmdb", "contrat", "annuaire"],
            "sources_non_visibles": ["secret"],
        },
    }
    twin_b = {
        "twin_id": "twin-b",
        "tenant_id": "banque",
        "espace": "paiements",
        "nom": "Équipe plateforme",
        "ressources": [
            {"resource_id": "res-shared", "nom": "Base mutualisée", "source": "cmdb"},
            {"resource_id": "res-b", "nom": "Appliance B", "source": "cmdb"},
        ],
        "applications": [],
        "fournisseurs": [
            {"supplier_id": "sup-b", "nom": "Fournisseur B", "source": "cmdb"},
        ],
        "equipes": [],
        "claims": [
            {"claim_id": "c-b1", "sujet": "res-shared", "predicat": "FOURNISSEUR_FOURNIT",
             "objet": "sup-b", "source": "cmdb"},
            {"claim_id": "c-b2", "sujet": "res-shared", "predicat": "RESOURCE_SUPPORTE_APPLICATION",
             "objet": "app-a", "source": "cmdb"},
        ],
        "acl": {"sources_visibles": ["cmdb"]},
    }
    return [twin_a, twin_b]


def _vue(twins=None):
    return VueTransverse(twins if twins is not None else _twins(), tenant_id="banque")


def _par_id(vue, identifiant):
    return [entite for entite in vue["entites"] if entite["id"] == identifiant]


def test_deux_twins_partagent_une_ressource():
    vue = _vue().vue()
    partagees = _par_id(vue, "res-shared")
    assert len(partagees) == 1
    assert partagees[0]["type"] == "RESOURCE"
    assert [p["twin_id"] for p in partagees[0]["provenance"]] == ["twin-a", "twin-b"]
    assert partagees[0]["noms"] == ["Base mutualisée", "Base partagée"]


def test_acl_masque_une_source_sans_la_faire_passer_pour_absente():
    vue = _vue().vue()
    assert {
        "twin_id": "twin-a",
        "source_id": "secret",
        "etat": "non_visible",
    } in vue["sources_non_visibles"]
    assert _par_id(vue, "res-cache") == []
    assert "res-cache" not in json.dumps(vue, ensure_ascii=False)
    assert "Ressource cachée" not in json.dumps(vue, ensure_ascii=False)
    assert all(ref["claim_id"] != "c-a2" for ref in vue["claims_locaux"])


def test_meme_ressource_fusionnee_par_identifiant_et_non_par_nom():
    vue = _vue().vue()
    assert len(_par_id(vue, "res-shared")) == 1
    assert len(_par_id(vue, "res-a")) == 1
    assert len(_par_id(vue, "res-b")) == 1
    assert _par_id(vue, "Base partagée") == []
    assert _par_id(vue, "Base mutualisée") == []


def test_aucun_claim_n_est_copie():
    twins = _twins()
    avant = copy.deepcopy(twins)
    sortie = VueTransverse(twins, tenant_id="banque").vue()
    for reference in sortie["claims_locaux"]:
        assert set(reference) == {"claim_id", "twin_id", "source_id"}
    for entite in sortie["entites"]:
        for reference in entite["claims_locaux"]:
            assert set(reference) == {"claim_id", "twin_id", "source_id"}
    refs = json.dumps(sortie["claims_locaux"], ensure_ascii=False)
    assert "predicat" not in refs
    assert "objet" not in refs
    assert {ref["claim_id"] for ref in sortie["claims_locaux"]} == {"c-a1", "c-b1", "c-b2"}
    assert twins == avant
    sortie["claims_locaux"].clear()
    assert VueTransverse(twins, tenant_id="banque").vue()["claims_locaux"]


def test_conflit_conserve():
    vue = _vue().vue()
    assert len(vue["contradictions"]) == 1
    conflit = vue["contradictions"][0]
    assert conflit["predicat"] == "FOURNISSEUR_FOURNIT"
    assert conflit["sens"] == "sujet_commun"
    assert conflit["ancre"] == "res-shared"
    assert conflit["valeurs"] == ["sup-a", "sup-b"]
    assert {ref["claim_id"] for ref in conflit["claims"]} == {"c-a1", "c-b1"}
    assert len(_par_id(vue, "sup-a")) == 1
    assert len(_par_id(vue, "sup-b")) == 1


def test_tenant_different_refuse():
    twins = _twins()
    twins[1]["tenant_id"] = "autre"
    with pytest.raises(FederationRefusee):
        VueTransverse(twins, tenant_id="banque")
    with pytest.raises(FederationRefusee):
        VueTransverse(_twins(), tenant_id="banque", espace="autre-espace")


def test_json_stable():
    twins = _twins()
    reference = VueTransverse(twins, tenant_id="banque").to_json()
    assert reference == VueTransverse(twins, tenant_id="banque").to_json()
    assert reference == VueTransverse(twins, tenant_id="banque").vers_json()
    assert reference == VueTransverse(list(reversed(twins)), tenant_id="banque").to_json()
    inverse = copy.deepcopy(twins)
    for twin in inverse:
        for cle in ("ressources", "applications", "fournisseurs", "equipes", "claims"):
            twin[cle] = list(reversed(twin.get(cle, [])))
    assert reference == VueTransverse(inverse, tenant_id="banque").to_json()
    assert list(json.loads(reference)) == sorted(json.loads(reference))


def test_inconnues_conservees_sans_inventer_d_identite():
    vue = _vue().vue()
    assert any(
        inconnue["raison"] == "identifiant_canonique_absent"
        and inconnue["nom"] == "Ressource sans identifiant"
        for inconnue in vue["inconnues"]
    )
    twins = _twins()
    twins[0]["claims"].append({
        "id": "c-a3",
        "sujet": "res-shared",
        "predicat": "DEPEND_DE",
        "objet": "app-inconnue",
        "source": "cmdb",
    })
    vue = VueTransverse(twins, tenant_id="banque").vue()
    assert any(
        inconnue["raison"] == "objet_non_resolu" and inconnue["valeur"] == "app-inconnue"
        for inconnue in vue["inconnues"]
    )
