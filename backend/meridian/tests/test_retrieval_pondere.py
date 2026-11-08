"""Pondération du retrieval (plan Cognition IA, C1) : taux de succès des learnings
et classement par statut de connaissance."""
import pytest

from meridian.adapters.outbound.postgres import connaissance
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import memoire_durable
from meridian.adapters.outbound.postgres import memoire_prospective
from meridian.adapters.outbound.postgres.retrieval_memoire import recuperer

TENANT = "banque"
DATE = "2026-10-01T08:00:00+00:00"


def _durable(identifiant, contenu, *, scope="twin", scope_id="twin-1",
             confiance=0.7, cree_le=DATE):
    return {
        "id": identifiant,
        "scope": scope,
        "scope_id": scope_id,
        "classe": "contexte",
        "contenu": contenu,
        "provenance": "revue",
        "confiance": confiance,
        "donnees": {},
        "cree_le": cree_le,
    }


def _annotation(identifiant, contenu, *, twins=("twin-1",), confiance=0.7,
                cree_le=DATE):
    return {
        "id": identifiant,
        "titre": contenu,
        "cree_le": cree_le,
        "donnees": {
            "contenu": contenu,
            "genre": "note",
            "source": "revue",
            "twin_ids": list(twins),
            "confiance": confiance,
        },
    }


def _learning(identifiant, enonce, *, twins=("twin-1",), reutilisations=(),
              confiance=0.7, donnees=None, cree_le=DATE):
    charge = {
        "enonce": enonce,
        "twin_ids": list(twins),
        "confiance": confiance,
        "acteur": "revue",
        "reutilisations": list(reutilisations),
    }
    charge.update(donnees or {})
    return {
        "id": identifiant,
        "type": "LEARNING",
        "titre": enonce,
        "cree_le": cree_le,
        "donnees": charge,
    }


def _claim(identifiant, objet, *, statut="ACCEPTED", confiance=0.9):
    return {
        "id": identifiant,
        "sujet": "Système",
        "predicat": "IMPACTE",
        "objet": objet,
        "type": "IMPACT",
        "confiance": confiance,
        # une preuve par claim : la déduplication fusionne les candidats qui
        # partagent la même identité de preuve
        "preuve": f"git://tbt@sha1:src/carte.py#L{identifiant}-L{identifiant}",
        "statut": statut,
        "maturite": "M3",
    }


@pytest.fixture
def sources_factices(monkeypatch):
    """Remplace les cinq lectures par des sources en mémoire, sans base ni réseau."""
    etat = {
        "durables": [], "annotations": [], "learnings": [], "claims": {},
        "intentions": [], "twins": {"twin-1": {"id": "twin-1", "tenant_id": TENANT}},
    }

    monkeypatch.setattr(memoire_durable, "lister",
                        lambda conn, tenant, **options: list(etat["durables"]))
    monkeypatch.setattr(
        entreprise_depot, "lister_objets",
        lambda conn, tenant, type_=None, **options: (
            list(etat["annotations"]) if type_ == "ANNOTATION"
            else list(etat["learnings"]) if type_ == "LEARNING"
            else []))
    monkeypatch.setattr(connaissance, "connaissances",
                        lambda conn, jumeau_id, **options:
                        list(etat["claims"].get(jumeau_id, [])))
    monkeypatch.setattr(memoire_prospective, "echeances",
                        lambda conn, tenant, **options: list(etat["intentions"]))
    monkeypatch.setattr(depot, "jumeau_par_id",
                        lambda conn, jumeau_id: etat["twins"].get(jumeau_id))
    return etat


def test_taux_succes_learning_pondere_le_score(sources_factices):
    """À couverture égale : taux .9 > neutre > taux .1 (facteur 0.5 + taux)."""
    etat = sources_factices
    etat["learnings"] = [
        _learning("l-fort", "Le delai de carte baisse",
                  reutilisations=[{"resultat": "succes"}] * 9
                  + [{"resultat": "echec"}]),
        _learning("l-neutre", "Le delai de carte stagne"),
        _learning("l-faible", "Le delai de carte monte",
                  reutilisations=[{"resultat": "succes"}]
                  + [{"resultat": "echec"}] * 9),
    ]

    resultat = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10)

    scores = {candidat.id: candidat.score for candidat in resultat}
    assert scores["l-fort"] > scores["l-neutre"] > scores["l-faible"]
    # même score de base : les ratios reflètent exactement les facteurs 1.4 et 0.6
    assert scores["l-fort"] == round(scores["l-neutre"] * 1.4, 6)
    assert scores["l-faible"] == round(scores["l-neutre"] * 0.6, 6)
    ids = [candidat.id for candidat in resultat]
    assert ids.index("l-fort") < ids.index("l-neutre") < ids.index("l-faible")
    fort = next(candidat for candidat in resultat if candidat.id == "l-fort")
    assert "taux succès 0.90" in fort.raisons


def test_learning_sans_mesure_reste_neutre(sources_factices):
    """Jamais réutilisé ou seulement des résultats inconnus : facteur 1.0, pas de
    pénalité — le score est le même que celui d'un candidat sans le champ."""
    etat = sources_factices
    etat["learnings"] = [
        _learning("l-vierge", "Le delai de carte baisse"),
        _learning("l-inconnus", "Le delai de carte stagne",
                  reutilisations=[{"resultat": "inconnu"}, {"note": "sans verdict"}]),
        _learning("l-mesure", "Le delai de carte monte",
                  donnees={"taux_succes": 0.9}),
    ]

    resultat = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10)

    scores = {candidat.id: candidat.score for candidat in resultat}
    assert scores["l-vierge"] == scores["l-inconnus"]
    assert scores["l-mesure"] == round(scores["l-vierge"] * 1.4, 6)


def test_claim_accepted_devant_proposed_a_couverture_egale(sources_factices):
    """PROPOSED reste candidat mais score sous ACCEPTED (facteur 0.8)."""
    etat = sources_factices
    etat["claims"]["twin-1"] = [
        _claim(11, "delai carte bleue", statut="ACCEPTED"),
        _claim(12, "delai carte verte", statut="PROPOSED"),
    ]

    resultat = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10)

    scores = {candidat.id: candidat.score for candidat in resultat}
    assert scores["11"] > scores["12"]
    assert scores["12"] == round(scores["11"] * 0.8, 6)
    ids = [candidat.id for candidat in resultat]
    assert ids.index("11") < ids.index("12")


def test_claim_invalide_present_mais_declasse(sources_factices):
    """CONTESTED et INVALIDATED restent candidats, déclassés ; les demander
    explicitement via ``statuts`` lève le déclassement."""
    etat = sources_factices
    etat["claims"]["twin-1"] = [
        _claim(11, "delai carte bleue", statut="ACCEPTED"),
        _claim(12, "delai carte verte", statut="PROPOSED"),
        _claim(13, "delai carte rouge", statut="CONTESTED"),
        _claim(14, "delai carte jaune", statut="INVALIDATED"),
    ]

    resultat = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10)

    ids = [candidat.id for candidat in resultat]
    assert {"11", "12", "13", "14"} <= set(ids)
    assert (ids.index("11") < ids.index("12")
            < ids.index("13") < ids.index("14"))
    invalide = next(candidat for candidat in resultat if candidat.id == "14")
    assert "statut INVALIDATED" in invalide.raisons

    demandes = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10,
                         statuts={"INVALIDATED"})
    assert [candidat.id for candidat in demandes] == ["14"]
    # explicitement demandé : facteur plein, le même que l'ACCEPTED à couverture égale
    scores = {candidat.id: candidat.score for candidat in resultat}
    assert demandes[0].score == scores["11"]


def test_statuts_inconnus_ou_absents_restent_neutres(sources_factices):
    """Un statut hors vocabulaire ou absent ne module rien ; le filtre ``statuts``
    laisse passer les candidats sans statut de connaissance."""
    etat = sources_factices
    etat["durables"] = [_durable("durable", "Le delai de carte baisse")]
    etat["claims"]["twin-1"] = [
        _claim(11, "delai carte bleue", statut="ACCEPTED"),
        _claim(15, "delai carte grise", statut="EN_REVUE_BIZARRE"),
    ]

    resultat = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10)
    scores = {candidat.id: candidat.score for candidat in resultat}
    assert scores["11"] == scores["15"]

    demandes = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], limite=10, statuts=["accepted"])
    ids = [candidat.id for candidat in demandes]
    assert "11" in ids and "15" in ids  # hors vocabulaire : pas un statut filtrable
    assert "durable" in ids             # sans statut : non concerné par le filtre


def test_ordre_existant_preserve_sans_mesure(sources_factices):
    """Régression : sans taux mesuré ni statut déclassé, l'ordre historique est
    strictement inchangé."""
    etat = sources_factices
    etat["durables"] = [_durable("durable", "Le delai de carte baisse")]
    etat["annotations"] = [
        _annotation("annotation-exact", "Le delai de carte baisse"),
        _annotation("annotation-partiel", "Le delai de carte graphique chauffe"),
    ]
    etat["learnings"] = [_learning("learning", "Le delai de carte baisse")]
    etat["claims"]["twin-1"] = [_claim(7, "delai carte", statut="ACCEPTED")]

    resultat = recuperer(object(), TENANT, question="delai carte",
                         twin_ids=["twin-1"], scope="twin", scope_id="twin-1",
                         limite=10)

    assert [candidat.id for candidat in resultat] == [
        "7", "learning", "annotation-exact", "annotation-partiel", "durable"]

    sans_learnings = recuperer(object(), TENANT, question="delai carte",
                               twin_ids=["twin-1"], scope="twin",
                               scope_id="twin-1", limite=10)
    # relance identique : le classement reste déterministe
    assert [candidat.id for candidat in sans_learnings] == [
        candidat.id for candidat in resultat]
