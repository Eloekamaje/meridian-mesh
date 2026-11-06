"""Contrat strict des contributions d'investigation, sans modèle ni persistance."""
from datetime import datetime, timezone

import pytest

from meridian.domain.investigation import (
    BudgetInvestigation,
    ClaimInvestigation,
    ContributionInvestigation,
    CouvertureInvestigation,
    InconnueInvestigation,
    PorteeInvestigation,
    PreuveInvestigation,
    SuiviInvestigation,
    contribution_depuis_dict,
    valider_perimetre,
)


MAINTENANT = datetime.now(timezone.utc).isoformat()


def preuve(source="git-api", locator="git://api@abc:service.py#L10-L14"):
    return PreuveInvestigation(
        source_id=source, locator=locator, version="abc123", type="code",
        observee_le=MAINTENANT, repository="api", commit="abc123",
        fichier="service.py", symbole="soumettre", lignes=(10, 14),
    )


def claim(**surcharges):
    valeurs = {
        "id": "claim-1", "affirmation": "La soumission contrôle les permissions.",
        "mode": "observed", "preuves": (preuve(),), "confiance": 0.9,
        "portee": PorteeInvestigation(
            repositories=("api",), points_entree=("POST /soumissions",),
            parcours=("route → service → autorisation",),
        ),
    }
    valeurs.update(surcharges)
    return ClaimInvestigation(**valeurs)


def contribution(**surcharges):
    valeurs = {
        "investigation_id": "inv-1", "question_id": "q-1", "twin_id": "paiements",
        "horodatage": MAINTENANT, "statut": "completed", "claims": (claim(),),
        "couverture": CouvertureInvestigation(examinees=("git-api",)),
        "budget": BudgetInvestigation(appels_max=8, appels_utilises=3),
    }
    valeurs.update(surcharges)
    return ContributionInvestigation(**valeurs)


def test_une_contribution_complete_est_serialisable_et_autorisee():
    resultat = contribution()
    assert valider_perimetre(resultat, {"git-api"}, twin_id="paiements") is resultat
    document = resultat.as_dict()
    assert document["claims"][0]["mode"] == "observed"
    assert document["claims"][0]["preuves"][0]["lignes"] == [10, 14]
    assert document["couverture"]["examinees"] == ["git-api"]


@pytest.mark.parametrize("mode", ["observed", "inferred"])
def test_un_claim_tenu_exige_une_preuve(mode):
    with pytest.raises(ValueError, match="exige au moins une preuve"):
        claim(mode=mode, preuves=())


def test_un_inconnu_peut_rester_sans_preuve():
    inconnu = claim(mode="unknown", preuves=(), confiance=0.0)
    assert inconnu.mode == "unknown" and inconnu.preuves == ()


def test_un_claim_inconnu_impose_un_statut_avec_lacunes():
    inconnu = claim(mode="unknown", preuves=(), confiance=0.0)
    with pytest.raises(ValueError, match="completed_with_gaps"):
        contribution(claims=(inconnu,))
    resultat = contribution(statut="completed_with_gaps", claims=(inconnu,))
    assert resultat.statut == "completed_with_gaps"


def test_modes_confiance_dates_et_lignes_sont_stricts():
    with pytest.raises(ValueError, match="mode inconnu"):
        claim(mode="certain")
    with pytest.raises(ValueError, match="confiance hors bornes"):
        claim(confiance=1.1)


def test_preuve_refuse_date_et_lignes_invalides():
    with pytest.raises(ValueError, match="fuseau"):
        PreuveInvestigation("s", "git://x", "v1", "code", "2026-11-04T12:00:00")
    with pytest.raises(ValueError, match="hors bornes"):
        PreuveInvestigation("s", "git://x", "v1", "code", MAINTENANT, lignes=(4, 2))


def test_une_preuve_ne_peut_etre_dupliquee_comme_soutien_et_contre_preuve():
    p = preuve()
    with pytest.raises(ValueError, match="dupliquée"):
        claim(preuves=(p,), contre_preuves=(p,))


def test_le_perimetre_effectif_est_impose_par_le_runtime():
    resultat = contribution()
    with pytest.raises(PermissionError, match="git-api"):
        valider_perimetre(resultat, {"confluence"})
    with pytest.raises(PermissionError, match="jumeau"):
        valider_perimetre(resultat, {"git-api"}, twin_id="fraude")


def test_les_contre_preuves_et_la_couverture_sont_egalement_bornees():
    contredit = claim(contre_preuves=(preuve("runtime", "otlp://trace/1"),))
    resultat = contribution(
        claims=(contredit,), statut="completed_with_gaps",
        couverture=CouvertureInvestigation(examinees=("git-api",), inaccessibles=("jira",)),
    )
    with pytest.raises(PermissionError, match="jira, runtime"):
        valider_perimetre(resultat, {"git-api"})


def test_une_source_ne_peut_avoir_deux_etats_de_couverture():
    with pytest.raises(ValueError, match="deux états"):
        CouvertureInvestigation(examinees=("git-api",), inaccessibles=("git-api",))


def test_completed_exige_l_absence_de_lacunes():
    inconnue = InconnueInvestigation(
        question="Qui consomme cet événement ?", consequence="Décommissionnement incertain",
        source_necessaire="Observabilité de production",
    )
    with pytest.raises(ValueError, match="completed_with_gaps"):
        contribution(inconnues=(inconnue,))
    partiel = contribution(statut="completed_with_gaps", inconnues=(inconnue,))
    assert partiel.statut == "completed_with_gaps"


def test_un_budget_epuise_est_coherent_avec_le_statut():
    with pytest.raises(ValueError, match="budget épuisé"):
        contribution(statut="budget_exhausted")
    resultat = contribution(
        statut="budget_exhausted",
        budget=BudgetInvestigation(appels_max=3, appels_utilises=3),
    )
    assert resultat.budget.epuise


def test_les_doublons_de_claim_inconnue_et_suivi_sont_refuses():
    c = claim()
    with pytest.raises(ValueError, match="claim dupliqué"):
        contribution(claims=(c, c))
    i = InconnueInvestigation("Question ?", "Conséquence", "Source")
    with pytest.raises(ValueError, match="inconnue dupliquée"):
        contribution(statut="completed_with_gaps", inconnues=(i, i))
    s = SuiviInvestigation("fraude", "Confirmez-vous l'appel ?", "APPELLE")
    with pytest.raises(ValueError, match="suivi dupliqué"):
        contribution(suivis=(s, s))


def test_les_textes_trop_longs_sont_refuses_et_non_tronques():
    with pytest.raises(ValueError, match="trop long"):
        claim(affirmation="x" * 2001)
    with pytest.raises(ValueError, match="trop long"):
        preuve(locator="git://" + "x" * 2000)


def test_les_collections_exigent_les_objets_du_contrat():
    with pytest.raises(TypeError, match="ClaimInvestigation"):
        contribution(claims=({"id": "claim"},))
    with pytest.raises(TypeError, match="PreuveInvestigation"):
        claim(preuves=({"source_id": "s"},))


def test_une_sortie_json_est_deserialisee_strictement():
    original = contribution().as_dict()
    relu = contribution_depuis_dict(original)
    assert relu == contribution()
    assert relu.claims[0].preuves[0].lignes == (10, 14)


def test_la_deserialisation_refuse_les_champs_inventes_par_le_modele():
    document = contribution().as_dict()
    document["decision_automatique"] = True
    with pytest.raises(ValueError, match="champs inconnus"):
        contribution_depuis_dict(document)


@pytest.mark.parametrize("champ,valeur", [
    ("claims", {}), ("inconnues", "question"), ("suivis", {"twin_id": "fraude"}),
])
def test_la_deserialisation_exige_des_listes_pour_les_collections(champ, valeur):
    document = contribution().as_dict()
    document[champ] = valeur
    with pytest.raises(TypeError, match=rf"{champ} doit être une liste"):
        contribution_depuis_dict(document)


def test_la_deserialisation_exige_une_liste_de_preuves():
    document = contribution().as_dict()
    document["claims"][0]["preuves"] = {"source_id": "git-api"}
    with pytest.raises(TypeError, match=r"claims\[0\]\.preuves doit être une liste"):
        contribution_depuis_dict(document)

    document = contribution().as_dict()
    document["claims"][0]["preuves"][0]["contenu_secret"] = "x"
    with pytest.raises(ValueError, match="champs inconnus"):
        contribution_depuis_dict(document)
