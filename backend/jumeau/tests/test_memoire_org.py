"""Mémoire organisationnelle : persistance tenant-scopée, recherche lexicale et classement pur."""
import pytest

from jumeau import entreprise_depot, memoire_org
from jumeau.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"


def _ligne(identifiant, titre, *, contenu="", twins=(), situations=(),
           cree_le="2026-10-01T08:00:00+00:00"):
    return {
        "id": identifiant,
        "titre": titre,
        "cree_le": cree_le,
        "donnees": {
            "contenu": contenu or titre,
            "genre": "note",
            "source": "test",
            "twin_ids": list(twins),
            "situation_ids": list(situations),
        },
    }


def test_classement_titre_exact_puis_chevauchement_puis_recence():
    lignes = [
        _ligne("recent", "Délai carte récent", twins=["twin-1"],
               cree_le="2026-10-05T08:00:00+00:00"),
        _ligne("exact", "Délai carte", cree_le="2026-10-01T08:00:00+00:00"),
        _ligne("overlap", "Délai carte ancien", twins=["twin-1"],
               cree_le="2026-10-02T08:00:00+00:00"),
        _ligne("hors-sujet", "Autre note", cree_le="2026-10-06T08:00:00+00:00"),
    ]

    resultat = memoire_org.classer_memoires(
        lignes, requete="delai carte", twin_ids=["twin-1"])

    assert [ligne["id"] for ligne in resultat] == ["exact", "recent", "overlap"]
    assert memoire_org.classer_memoires(lignes, requete="absent") == []
    assert [ligne["id"] for ligne in memoire_org.classer_memoires(
        lignes, requete="delai carte", limite=1)] == ["exact"]


def test_classement_par_situation_exacte_puis_twin_et_exclusion():
    lignes = [
        _ligne("twin", "Délai carte", twins=["twin-1"]),
        _ligne("exact", "Délai carte", situations=["sit-1"]),
        _ligne("loin", "Délai carte", situations=["sit-2"], twins=["twin-2"]),
    ]

    resultat = memoire_org.classer_memoires(
        lignes, situation_id="sit-1", twin_ids=["twin-1"], exiger_chevauchement=True)

    assert [ligne["id"] for ligne in resultat] == ["exact", "twin"]


@besoin_pg
def test_memoriser_persiste_et_cherche(conn):
    ligne = memoire_org.memoriser(
        conn, TENANT, "Le délai de carte baisse après automatisation",
        genre="retour_experience", source="revue-cartes",
        twin_ids=["twin-carte"], situation_ids=["sit-1"], confiance=0.8)

    assert (ligne["type"], ligne["famille"], ligne["mode"]) == (
        "ANNOTATION", "interaction_gouvernance", "DECLARED")
    assert ligne["donnees"]["contenu"] == "Le délai de carte baisse après automatisation"
    assert ligne["donnees"]["genre"] == "retour_experience"
    assert ligne["donnees"]["source"] == "revue-cartes"
    assert ligne["donnees"]["twin_ids"] == ["twin-carte"]
    assert ligne["donnees"]["situation_ids"] == ["sit-1"]
    assert ligne["donnees"]["confiance"] == 0.8

    relu = entreprise_depot.lire_objet(conn, TENANT, ligne["id"])
    assert relu["donnees"] == ligne["donnees"]

    assert [resultat["id"] for resultat in memoire_org.chercher(
        conn, TENANT, "delai carte")] == [ligne["id"]]
    assert memoire_org.chercher(conn, AUTRE_TENANT, "delai carte") == []


@besoin_pg
def test_memoriser_exige_contenu_et_provenance(conn):
    with pytest.raises(memoire_org.MemoireInvalide):
        memoire_org.memoriser(conn, TENANT, "", genre="note", source="revue")
    with pytest.raises(memoire_org.MemoireInvalide):
        memoire_org.memoriser(conn, TENANT, "Contenu", genre="note", source=" ")
    with pytest.raises(memoire_org.MemoireInvalide):
        memoire_org.memoriser(
            conn, TENANT, "Contenu", genre="note", source="revue", confiance=1.5)

    assert entreprise_depot.lister_objets(conn, TENANT) == []


@besoin_pg
def test_memoires_isolees_par_tenant_et_rappelees_par_situation(conn):
    exact = memoire_org.memoriser(
        conn, TENANT, "Le délai de carte baisse", genre="note", source="revue",
        twin_ids=["twin-carte"], situation_ids=["sit-1"])
    autre = memoire_org.memoriser(
        conn, TENANT, "Le délai de carte stagne", genre="note", source="revue",
        twin_ids=["twin-autre"], situation_ids=["sit-2"])
    hors = memoire_org.memoriser(
        conn, TENANT, "Le délai de carte est stable", genre="note", source="revue")
    assurance = memoire_org.memoriser(
        conn, AUTRE_TENANT, "Le délai de carte baisse", genre="note", source="revue",
        twin_ids=["twin-carte"], situation_ids=["sit-1"])

    assert [ligne["id"] for ligne in memoire_org.memoriaux_pour_situation(
        conn, TENANT, "sit-1")] == [exact["id"]]
    assert [ligne["id"] for ligne in memoire_org.memoriaux_pour_situation(
        conn, TENANT, "sit-2", twin_ids=["twin-carte"])] == [autre["id"], exact["id"]]
    assert hors["id"] not in [ligne["id"] for ligne in memoire_org.memoriaux_pour_situation(
        conn, TENANT, "sit-1", twin_ids=["twin-carte"])]
    assert entreprise_depot.lire_objet(conn, TENANT, assurance["id"]) is None
    assert assurance["id"] not in [ligne["id"] for ligne in memoire_org.chercher(
        conn, TENANT, "delai carte")]

    trouves = memoire_org.chercher(conn, TENANT, "delai carte", twin_ids=["twin-carte"])
    assert set(ligne["id"] for ligne in trouves) == {exact["id"], autre["id"], hors["id"]}
    assert trouves[0]["id"] == exact["id"]
