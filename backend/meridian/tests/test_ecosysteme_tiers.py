"""Socle Claims / responsabilités / autorité de l'écosystème tiers (ADR-0030).

Les tests sont volontairement purs : aucune base, aucun réseau, aucun modèle. Ils vérifient les
types et prédicats de l'ADR, la validation des Claims, la matrice de responsabilités sans
invention, la conservation des inconnues et des contradictions, et la vue transverse qui
référence les Claims sans les copier.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from meridian.application import ecosysteme_tiers as projection
from meridian.domain import ecosysteme_tiers as socle
from meridian.domain.ecosysteme_tiers import (
    AUTORITE_SOURCES,
    PREDICATS,
    SOURCES,
    STATUTS,
    TYPES_TIERS,
    ClaimTiers,
    ClaimTiersInvalide,
    PreuveLocalisee,
    TwinTiers,
    identifiant_canonique,
    valider_claim,
)

MERIDIAN = Path(__file__).resolve().parents[1]


def preuve(localisateur: str = "#L10-L12", emplacement: str = "docs/responsabilites.md", **champs):
    return PreuveLocalisee(emplacement=emplacement, localisateur=localisateur, **champs)


def claim(sujet: str, predicat: str, objet: str, **champs) -> ClaimTiers:
    champs.setdefault("statut", "ETABLI")
    champs.setdefault("preuve", preuve())
    champs.setdefault("autorite", AUTORITE_SOURCES[predicat][0])
    return ClaimTiers(sujet=sujet, predicat=predicat, objet=objet, **champs)


def equipe(claims=(), **champs) -> TwinTiers:
    champs.setdefault("nom", "Équipe cartes")
    return TwinTiers(twin_id="equipe-cartes", type="TEAM", claims=claims, **champs)


def ressource(claims=(), **champs) -> TwinTiers:
    champs.setdefault("nom", "Ressource cartes")
    champs.setdefault("identifiants", {"resource_id": "CI-42"})
    return TwinTiers(twin_id="res-cartes", type="RESOURCE", claims=claims, **champs)


def application(claims=(), **champs) -> TwinTiers:
    champs.setdefault("nom", "Application cartes")
    champs.setdefault("identifiants", {"application_id": "APP-1"})
    return TwinTiers(twin_id="app-cartes", type="APPLICATION", claims=claims, **champs)


def fournisseur(claims=(), **champs) -> TwinTiers:
    champs.setdefault("nom", "Fournisseur cartes")
    champs.setdefault("identifiants", {"supplier_id": "SUP-1"})
    return TwinTiers(twin_id="fournisseur-x", type="SUPPLIER", claims=claims, **champs)


def test_types_predicats_statuts_et_autorites_de_l_adr():
    assert set(TYPES_TIERS) == {"APPLICATION", "TEAM", "RESOURCE", "SUPPLIER", "ECOSYSTEM"}
    assert set(PREDICATS) == {
        "FOURNISSEUR_FOURNIT",
        "EQUIPE_EST_ACCOUNTABLE_DE",
        "EQUIPE_EST_RESPONSABLE_DE",
        "CONTRAT_COUVRE",
        "RESOURCE_SUPPORTE_APPLICATION",
        "APPLICATION_DEPEND_DE_RESSOURCE",
        "RESPONSABILITE_LIMITEE_A",
    }
    assert set(STATUTS) == {"ETABLI", "HISTORIQUE", "SUPPOSE", "CONTESTE", "INCONNU"}
    assert set(AUTORITE_SOURCES) == set(PREDICATS)
    for sources in AUTORITE_SOURCES.values():
        assert sources
        assert set(sources) <= set(SOURCES)
    assert AUTORITE_SOURCES["CONTRAT_COUVRE"] == ("CONTRAT",)
    assert "TEAMS" in AUTORITE_SOURCES["EQUIPE_EST_RESPONSABLE_DE"]
    for statut in ("établi", "historique", "supposé", "contesté", "inconnu"):
        assert socle.normaliser_statut(statut) in STATUTS


def test_claim_valide_avec_preuve_localisee_autorite_et_temporalite():
    valide = ClaimTiers(
        sujet="equipe-cartes",
        predicat="equipe_est_responsable_de",
        objet="res-cartes",
        statut="établi",
        preuve=preuve("INC0012345#journal", "servicenow://incident/INC0012345"),
        autorite="itsm",
        valid_from="2026-01-01",
        valid_to="2026-12-31",
    )

    assert valider_claim(valide) is valide
    assert socle.etat_a_date(valide, "2026-06-01") == "ETABLI"
    assert socle.etat_a_date(valide, "2027-01-01") == "HISTORIQUE"
    assert socle.preuve_est_localisee(valide.preuve) is True
    assert socle.autorite_autorisee("EQUIPE_EST_RESPONSABLE_DE", "ITSM") is True
    assert socle.autorite_autorisee("CONTRAT_COUVRE", "TEAMS") is False

    textuelle = claim(
        "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes",
        preuve="docs/responsabilites.md#L4-L6",
    )
    assert valider_claim(textuelle) is textuelle
    structurelle = claim(
        "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes",
        preuve={"emplacement": "docs/responsabilites.md", "locator": "#L4-L6"},
    )
    assert valider_claim(structurelle) is structurelle


@pytest.mark.parametrize("preuve_invalide", [
    None,
    PreuveLocalisee(emplacement="docs/responsabilites.md", localisateur=""),
    PreuveLocalisee(emplacement="", localisateur="#L1"),
    PreuveLocalisee(emplacement="docs/x.md", localisateur="#L9-L2", ligne_debut=9, ligne_fin=2),
])
def test_claim_sans_preuve_localisee_refuse(preuve_invalide):
    with pytest.raises(ClaimTiersInvalide, match="preuve localisée"):
        valider_claim(claim(
            "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes",
            preuve=preuve_invalide,
        ))


def test_autorite_absente_inconnue_ou_non_admise_refusee():
    with pytest.raises(ClaimTiersInvalide, match="exige une autorité"):
        valider_claim(claim("fournisseur-x", "CONTRAT_COUVRE", "res-cartes", autorite=None))
    with pytest.raises(ClaimTiersInvalide, match="autorité inconnue"):
        valider_claim(claim("fournisseur-x", "CONTRAT_COUVRE", "res-cartes", autorite="WIKI"))
    with pytest.raises(ClaimTiersInvalide, match="non admise"):
        valider_claim(claim("fournisseur-x", "CONTRAT_COUVRE", "res-cartes", autorite="TEAMS"))


def test_temporalite_invalide_refusee():
    with pytest.raises(ClaimTiersInvalide, match="suivre valid_from"):
        valider_claim(claim(
            "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes",
            valid_from="2026-12-31", valid_to="2026-01-01",
        ))
    with pytest.raises(ClaimTiersInvalide, match="date ISO"):
        valider_claim(claim(
            "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes",
            valid_from="pas-une-date",
        ))


def _twins_complets():
    c_responsable = claim(
        "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes", autorite="ITSM")
    c_accountable = claim(
        "equipe-cartes", "EQUIPE_EST_ACCOUNTABLE_DE", "res-cartes", autorite="ITSM")
    c_limite = claim(
        "equipe-cartes", "RESPONSABILITE_LIMITEE_A", "res-cartes", autorite="CONTRAT")
    c_fournit = claim(
        "fournisseur-x", "FOURNISSEUR_FOURNIT", "res-cartes", autorite="CONTRAT")
    c_supporte = claim(
        "res-cartes", "RESOURCE_SUPPORTE_APPLICATION", "app-cartes", autorite="CMDB")
    c_depend = claim(
        "app-cartes", "APPLICATION_DEPEND_DE_RESSOURCE", "res-cartes", autorite="CMDB")
    return {
        "claims": {
            "responsable": c_responsable,
            "accountable": c_accountable,
            "limite": c_limite,
            "fournit": c_fournit,
            "supporte": c_supporte,
            "depend": c_depend,
        },
        "twins": [
            equipe(claims=(c_responsable, c_accountable, c_limite)),
            ressource(claims=(c_supporte,)),
            application(claims=(c_depend,)),
            fournisseur(claims=(c_fournit,)),
        ],
    }


def test_matrice_et_responsabilite_limitee_sans_invention():
    donnees = _twins_complets()
    claims = donnees["claims"]
    resultat = projection.responsabilites(donnees["twins"])

    par_predicat = {relation["predicat"]: relation for relation in resultat["relations"]}
    responsable = par_predicat["EQUIPE_EST_RESPONSABLE_DE"]
    assert responsable["statut"] == "ETABLI"
    assert responsable["claim"] is claims["responsable"]
    assert responsable["limite"] is True
    assert responsable["portee"] == "LIMITEE"
    assert [relation["predicat"] for relation in resultat["matrice"]["compte"]] == [
        "EQUIPE_EST_ACCOUNTABLE_DE"]
    assert resultat["limites"][0]["claim"] is claims["limite"]

    assert {carte["id"] for carte in resultat["matrice"]["equipe"]} == {"equipe-cartes"}
    assert {carte["id"] for carte in resultat["matrice"]["fournisseur"]} == {"fournisseur-x"}
    assert {carte["id"] for carte in resultat["matrice"]["ressource"]} == {"res-cartes"}
    assert {carte["id"] for carte in resultat["matrice"]["application"]} == {"app-cartes"}
    assert resultat["inconnues"] == [] and resultat["contradictions"] == []
    assert len(resultat["claims"]) == 6

    couverture = projection.couverture(resultat)
    assert couverture["etabli"] == 6
    assert couverture["partiel"] is False
    assert couverture["inconnues"] == [] and couverture["contradictions"] == []


def test_inconnue_est_conservee_et_aucune_entite_n_est_inventee():
    inconnu = claim(
        "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-fantome",
        statut="INCONNU", autorite="ITSM",
    )
    resultat = projection.responsabilites([equipe(claims=(inconnu,))])

    relation = next(r for r in resultat["relations"] if r["objet"] == "res-fantome")
    assert relation["statut"] == "INCONNU"
    assert relation["claim"] is inconnu
    assert any(
        entree["type"] == "claim_inconnu" and entree["claim"] is inconnu
        for entree in resultat["inconnues"]
    )
    assert any(
        entree["type"] == "reference_absente" and entree["valeur"] == "res-fantome"
        for entree in resultat["inconnues"]
    )
    assert resultat["matrice"]["ressource"] == []
    assert resultat["matrice"]["compte"] == []

    couverture = projection.couverture(resultat)
    assert couverture["partiel"] is True
    assert couverture["inconnues_total"] >= 2
    assert any(
        entree.get("claim") is inconnu for entree in couverture["inconnues"]
    )


def test_reference_absente_n_est_pas_etablie_dans_la_matrice():
    etabli_sur_absent = claim(
        "equipe-cartes", "EQUIPE_EST_ACCOUNTABLE_DE", "res-fantome")
    resultat = projection.responsabilites([equipe(claims=(etabli_sur_absent,))])

    relation = next(r for r in resultat["relations"] if r["objet"] == "res-fantome")
    assert relation["statut"] == "ETABLI" and relation["resolu"] is False
    assert resultat["matrice"]["compte"] == []
    couverture = projection.couverture(resultat)
    assert couverture["etabli"] == 0
    assert couverture["non_resolues_total"] == 1
    assert couverture["partiel"] is True


def test_contradiction_explicite_et_non_promue():
    etabli = claim("equipe-cartes", "EQUIPE_EST_ACCOUNTABLE_DE", "res-cartes", autorite="ITSM")
    conteste = claim(
        "equipe-cartes", "EQUIPE_EST_ACCOUNTABLE_DE", "res-cartes",
        statut="CONTESTE", autorite="ITSM",
    )
    resultat = projection.responsabilites([equipe(claims=(etabli, conteste)), ressource()])

    relation = next(r for r in resultat["relations"] if r["predicat"] == "EQUIPE_EST_ACCOUNTABLE_DE")
    assert relation["statut"] == "CONTESTE"
    assert relation["contradiction"] is True
    assert resultat["matrice"]["compte"] == []
    assert {entree["type"] for entree in resultat["contradictions"]} >= {
        "claim_conteste", "relation_contradictoire"}

    couverture = projection.couverture(resultat)
    assert couverture["partiel"] is True
    assert couverture["contradictions_total"] >= 2
    assert any(
        entree["type"] == "relation_contradictoire" for entree in couverture["contradictions"]
    )


def test_historique_hors_periode_n_est_pas_etabli():
    ancien = claim(
        "equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes",
        valid_from="2026-01-01", valid_to="2026-02-01",
    )
    resultat = projection.responsabilites(
        [equipe(claims=(ancien,)), ressource()], a_date="2026-03-01")

    relation = next(r for r in resultat["relations"] if r["claim"] is ancien)
    assert relation["statut"] == "HISTORIQUE"
    assert resultat["matrice"]["compte"] == []
    couverture = projection.couverture(resultat)
    assert couverture["etabli"] == 0
    assert any(entree["claim"] is ancien for entree in couverture["historiques"])


def test_application_candidate_sans_application_id_et_jamais_promise():
    candidate = TwinTiers(
        twin_id="app-candidate", type="APPLICATION", nom="Cartes candidates",
        statut_identite="CANDIDAT",
    )
    support = claim(
        "res-cartes", "RESOURCE_SUPPORTE_APPLICATION", "app-candidate", autorite="CMDB")
    resultat = projection.responsabilites([
        ressource(claims=(support,)),
        candidate,
    ])

    assert candidate.application_id is None
    assert identifiant_canonique(candidate) == "app-candidate"
    carte = resultat["matrice"]["application"][0]
    assert carte["id"] == "app-candidate" and carte["candidat"] is True
    assert carte["identifiants"] == {}
    assert resultat["candidats"][0]["statut"] == "CANDIDAT"
    assert resultat["candidats"][0]["twin"] is candidate
    assert projection.couverture(resultat)["candidats"][0]["twin"] is candidate

    sans_id = TwinTiers(twin_id="app-sans-id", type="APPLICATION")
    assert sans_id.application_id is None
    assert sans_id.statut_identite == "CANDIDAT"
    assert socle.est_application_candidate(sans_id)
    assert not socle.est_application_non_resolue(sans_id)


def test_vue_transverse_reference_les_claims_sans_les_copier():
    c1 = claim("equipe-cartes", "EQUIPE_EST_RESPONSABLE_DE", "res-cartes", autorite="ITSM")
    c2 = claim("equipe-cartes", "EQUIPE_EST_ACCOUNTABLE_DE", "res-cartes", autorite="ITSM")
    twins = [equipe(claims=(c1, c2)), ressource()]

    vue = projection.vue_transverse(twins)

    assert vue["type"] == "VUE_TRANSVERSE"
    assert vue["est_twin"] is False
    assert vue["twin_ids"] == ["equipe-cartes", "res-cartes"]
    assert vue["twins"]["equipe-cartes"] is twins[0]
    assert vue["claims"][0] is c1 and vue["claims"][1] is c2
    assert vue["attachements"]["equipe-cartes"][0] is c1
    assert vue["matrice"]["equipe"][0]["claims"][0] is c1
    assert any(relation["claim"] is c1 for relation in vue["relations"])
    assert any(c1 is claim_ref for relation in vue["relations"] for claim_ref in relation["claims"])
    assert vue["couverture"]["partiel"] is False


def test_twin_sans_claim_reste_inconnu_et_la_matrice_n_invente_rien():
    resultat = projection.responsabilites([equipe()])

    assert resultat["matrice"]["equipe"][0]["sans_claim"] is True
    assert resultat["matrice"]["equipe"][0]["claims"] == []
    for role in ("fournisseur", "ressource", "application"):
        assert resultat["matrice"][role] == []
    assert any(entree["type"] == "twin_sans_claim" for entree in resultat["inconnues"])
    assert projection.couverture(resultat)["partiel"] is True


def test_twins_non_applicatifs_et_sources_sans_github():
    equipe_metier = TwinTiers(
        twin_id="equipe-cartes", type="TEAM", nom="Équipe cartes",
        sources=("CONFLUENCE", "SERVICENOW"),
    )
    ecosysteme = TwinTiers(
        twin_id="eco-cartes", type="ECOSYSTEM", nom="Écosystème cartes",
        perimetre="Cartes et paiements", sources=("CONFLUENCE", "SERVICENOW"),
    )

    assert equipe_metier.application_id is None
    assert socle.est_non_applicatif(equipe_metier)
    assert ecosysteme.type == "ECOSYSTEM" and ecosysteme.perimetre == "Cartes et paiements"
    assert ecosysteme.sources == ("CONFLUENCE", "SERVICENOW")
    assert identifiant_canonique(equipe_metier) == "equipe-cartes"
    assert identifiant_canonique(equipe_metier) != equipe_metier.nom

    resultat = projection.responsabilites([equipe_metier, ecosysteme])
    assert resultat["perimetres"][0]["id"] == "eco-cartes"
    assert resultat["perimetres"][0]["twin"] is ecosysteme


def test_modules_sans_acces_db_reseau_ou_llm():
    interdits = {
        "psycopg", "psycopg2", "motor", "pymongo", "neo4j", "redis", "requests",
        "httpx", "openai", "boto3", "botocore", "strands", "fastapi", "starlette",
    }
    fichiers = (
        MERIDIAN / "domain" / "ecosysteme_tiers.py",
        MERIDIAN / "application" / "ecosysteme_tiers.py",
    )
    for fichier in fichiers:
        arbre = ast.parse(fichier.read_text())
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                modules = [alias.name for alias in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                modules = [noeud.module]
            else:
                continue
            for module in modules:
                assert module.split(".")[0] not in interdits, f"{fichier.name} importe {module}"
                assert not module.startswith("meridian.adapters"), (
                    f"{fichier.name} dépend de {module}")
        if fichier.parent.name == "domain":
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.ImportFrom) and noeud.module:
                    assert not noeud.module.startswith("meridian."), (
                        f"le domaine dépend de {noeud.module}")
