"""Attention déterministe : priorités, récence, confiance, déduplication, filtres et absence de mutation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from jumeau import attention

MAINTENANT = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def objet(identifiant, **champs):
    base = {
        "id": identifiant,
        "type": "SITUATION",
        "titre": f"Situation {identifiant}",
        "resume": "Un résumé métier",
        "priorite": "MOYENNE",
        "confiance": 0.5,
        "observe_le": MAINTENANT.isoformat(),
        "twin_ids": ["twin-1"],
    }
    base.update(champs)
    return base


def _score(objet_, **champs):
    return attention.score(objet_, maintenant=MAINTENANT, **champs)["score"]


def test_priorite_recence_et_confiance_ordonnent_le_score():
    hautes = _score(objet("h", priorite="HAUTE"))
    moyennes = _score(objet("m", priorite="MOYENNE"))
    basses = _score(objet("b", priorite="BASSE"))
    assert hautes > moyennes > basses

    confiante = _score(objet("c1", confiance=0.95))
    douteuse = _score(objet("c2", confiance=0.05))
    assert confiante > douteuse

    recente = _score(objet("r1", observe_le=MAINTENANT.isoformat()))
    ancienne = _score(objet("r2", observe_le=(MAINTENANT - timedelta(days=120)).isoformat()))
    assert recente > ancienne
    assert 0 <= ancienne <= recente <= 100


def test_classement_deterministe_egalite_par_identifiant():
    objets = [objet("b", titre="B"), objet("a", titre="A")]
    premier = attention.classer(objets, maintenant=MAINTENANT)
    inverse = attention.classer(list(reversed(objets)), maintenant=MAINTENANT)

    assert [item["id"] for item in premier] == ["a", "b"]
    assert [item["score"] for item in premier] == [item["score"] for item in inverse]
    assert [item["id"] for item in inverse] == ["a", "b"]


def test_deduplication_par_signature_et_choix_du_meilleur_score():
    basse = objet("bas", priorite="BASSE", titre="Délai  API", resume="Même résumé",
                  twin_ids=["t2", "t1"])
    haute = objet("haute", priorite="HAUTE", titre="delai api", resume="meme resume",
                  twin_ids=["t1", "t2"])
    assert attention.signature(basse) == attention.signature(haute)

    resultat = attention.classer([basse, haute], maintenant=MAINTENANT)
    assert len(resultat) == 1
    assert resultat[0]["id"] == "haute"
    assert resultat[0]["original_id"] == "haute"
    assert resultat[0]["score"] == _score(haute)
    assert resultat[0]["raisons"]


def test_signature_ne_recopie_ni_secret_ni_titre_en_clair():
    secret = "tok_live_9f3c2b7a"
    empreinte = attention.signature(objet("s", titre=f"Jeton {secret}", resume="Texte"))
    assert secret not in empreinte
    assert "Jeton" not in empreinte
    assert empreinte.startswith("SITUATION:")


def test_limite_et_filtres_persona_domaine():
    objets = [
        objet("a", persona="Architecte", domaine="Paiement"),
        objet("b", persona="exploitant", domaine="paiement"),
        objet("c", persona="architecte", domaine="risque"),
        objet("d"),
    ]
    retenus = attention.selectionner(
        objets, persona="architecte", domaine="paiement", limite=10, maintenant=MAINTENANT)
    assert {item["id"] for item in retenus} == {"a", "d"}

    assert len(attention.classer(objets, limite=2, maintenant=MAINTENANT)) == 2
    assert attention.classer(objets, limite=0, maintenant=MAINTENANT) == []
    assert len(attention.selectionner(objets, limite=1, maintenant=MAINTENANT)) == 1


def test_date_invalide_est_conservatrice_sans_crash():
    casse = objet("casse", observe_le="pas une date")
    evaluation = attention.score(casse, maintenant=MAINTENANT)

    assert evaluation["composantes"]["recence"] == 0
    assert 0 <= evaluation["score"] <= 100
    assert [item["id"] for item in attention.classer([casse], maintenant=MAINTENANT)] == ["casse"]


def test_impact_contradictions_nouveaute_et_decisions_non_tranchees():
    base = objet("base")
    enrichi = objet("enrichi", impacts=["un", "deux", "trois"], contradiction_ids=["c1"],
                    nouveaute=True)
    assert _score(enrichi) > _score(base)
    assert attention.score(enrichi, maintenant=MAINTENANT)["composantes"]["impact"] > 0
    assert attention.score(enrichi, maintenant=MAINTENANT)["composantes"]["contradictions"] > 0
    assert attention.score(enrichi, maintenant=MAINTENANT)["composantes"]["nouveaute"] > 0

    proposee = objet("dec-1", type="DECISION", statut="PROPOSED")
    tranchee = objet("dec-2", type="DECISION", statut="DECIDED")
    assert attention.score(proposee, maintenant=MAINTENANT)["composantes"][
        "decisions_non_tranchees"] > 0
    assert attention.score(tranchee, maintenant=MAINTENANT)["composantes"][
        "decisions_non_tranchees"] == 0


def test_resume_attention_compte_par_priorite_et_type():
    objets = [
        objet("h1", priorite="HAUTE", titre="H1"),
        objet("h2", priorite="HAUTE", titre="H2"),
        objet("m", priorite="MOYENNE", titre="M"),
    ]
    resume = attention.resume_attention(objets, maintenant=MAINTENANT)

    assert resume["total"] == 3 and resume["total_brut"] == 3
    assert resume["dedoublonnes"] == 0
    assert resume["par_priorite"] == {"HAUTE": 2, "MOYENNE": 1}
    assert resume["par_type"] == {"SITUATION": 3}


def test_aucune_mutation_des_objets_recus():
    objets = [
        objet("a", persona="architecte", domaine="paiement", impacts=["x"]),
        objet("b", priorite="HAUTE", titre="B"),
    ]
    avant = deepcopy(objets)

    attention.signature(objets[0])
    attention.score(objets[0], maintenant=MAINTENANT)
    attention.classer(objets, maintenant=MAINTENANT)
    attention.selectionner(objets, persona="architecte", maintenant=MAINTENANT)
    attention.resume_attention(objets, maintenant=MAINTENANT)

    assert objets == avant
