"""Jeu d'or outils/Claims/décisions : validation et notation sans modèle ni réseau."""
import json

import pytest

from meridian.application import evaluation_gold as eg
from meridian.application import evaluation_outils as eo


def _jeu():
    return eg.charger()


def _candidat(cas):
    return cas.attendu()


def test_le_jeu_est_valide_et_couvre_outils_claims_decisions():
    jeu = _jeu()
    rapport = eg.valider(jeu)

    assert rapport["valide"] is True
    assert rapport["cas"] == jeu.taille >= 8
    identifiants = [cas.id for cas in jeu.cas]
    assert len(identifiants) == len(set(identifiants))
    tags = {tag for cas in jeu.cas for tag in cas.tags}
    assert {"claims", "decision", "preuve", "garde", "abstention"} <= tags
    assert any(cas.claims for cas in jeu.cas)
    assert any(cas.decision.verdict == "S_ABSTENIR" for cas in jeu.cas)
    assert any(cas.decision.recommandation for cas in jeu.cas)
    assert eg.valider({"cas": [cas.as_dict() for cas in jeu.cas]})["valide"] is True


def test_les_outils_du_jeu_sont_reels_et_les_claims_sont_coherents():
    noms = {
        nom
        for cas in eo.JEU_COGNITIF.cas
        for nom in (*cas.outils_attendus, *cas.outils_interdits)
    }
    noms |= {
        "resoudre_application", "mobiliser_jumeaux", "concevoir_architecture",
        "rechercher_outil", "decrire_outil",
    }
    for cas in _jeu().cas:
        assert set(cas.outils_attendus) <= noms
        assert set(cas.outils_interdits) <= noms
        for claim in cas.claims:
            if claim.statut == "ACCEPTED":
                assert claim.preuve_requise is True
        if cas.decision.verdict == "S_ABSTENIR":
            assert cas.decision.abstention is True
        assert eg.AUTORITES.index(cas.decision.autorite_max) <= eg.AUTORITES.index("proposition")


def test_un_selectionneur_parfait_passe_tout_le_jeu():
    resultat = eg.evaluer(_jeu(), _candidat)

    assert resultat["passe"] == resultat["total"] == _jeu().taille
    assert resultat["pass_rate"] == resultat["score_moyen"] == 1.0
    assert resultat["faux_positifs"] == resultat["faux_negatifs"] == 0
    assert all(detail["ok"] and detail["score"] == 1.0 for detail in resultat["details"])


def test_un_outil_manquant_est_un_echec_partiel():
    def incomplet(cas):
        candidat = _candidat(cas)
        if cas.id == "claim-dependance-prouvee":
            candidat["outils"] = ["resoudre_application"]
        return candidat

    resultat = eg.evaluer(_jeu(), incomplet)
    detail = next(d for d in resultat["details"] if d["cas_id"] == "claim-dependance-prouvee")

    assert detail["ok"] is False
    assert detail["outils"]["ok"] is False
    assert any("manquants" in raison for raison in detail["raisons"])
    assert resultat["passe"] < resultat["total"]


def test_un_claim_accepte_sans_preuve_est_refuse():
    def sans_preuve(cas):
        candidat = _candidat(cas)
        if cas.id == "claim-dependance-prouvee":
            candidat["claims"][0]["preuves"] = []
        return candidat

    resultat = eg.evaluer(_jeu(), sans_preuve)
    detail = next(d for d in resultat["details"] if d["cas_id"] == "claim-dependance-prouvee")

    assert detail["claims"]["ok"] is False
    assert any("preuve SUPPORT absente" in raison for raison in detail["raisons"])


def test_un_statut_de_claim_incorrect_est_refuse():
    def mauvais_statut(cas):
        candidat = _candidat(cas)
        if cas.id == "claim-contredite":
            candidat["claims"][0]["statut"] = "ACCEPTED"
        return candidat

    resultat = eg.evaluer(_jeu(), mauvais_statut)
    detail = next(d for d in resultat["details"] if d["cas_id"] == "claim-contredite")

    assert detail["claims"]["ok"] is False
    assert any("CONTESTED" in raison for raison in detail["raisons"])


def test_une_recommandation_sans_baseline_est_refusee():
    def recommandation_interdite(cas):
        candidat = _candidat(cas)
        if cas.id == "decision-baseline-absente":
            candidat["decision"]["recommandation"] = "Financer l'initiative"
        return candidat

    resultat = eg.evaluer(_jeu(), recommandation_interdite)
    detail = next(d for d in resultat["details"] if d["cas_id"] == "decision-baseline-absente")

    assert detail["decision"]["ok"] is False
    assert any("recommandation inattendue" in raison for raison in detail["raisons"])


def test_une_autorite_superieure_est_refusee():
    def decision_interdite(cas):
        candidat = _candidat(cas)
        if cas.id == "decision-risque-approbation":
            candidat["decision"]["autorite"] = "decision"
        return candidat

    resultat = eg.evaluer(_jeu(), decision_interdite)
    detail = next(d for d in resultat["details"] if d["cas_id"] == "decision-risque-approbation")

    assert detail["decision"]["ok"] is False
    assert any("autorité" in raison for raison in detail["raisons"])


def test_une_ecriture_est_refusee_par_le_critere_must_not_write():
    def avec_ecriture(cas):
        candidat = _candidat(cas)
        if cas.id == "lecture-ecriture-interdite":
            candidat["outils"].append("comptes.creercompte")
        return candidat

    resultat = eg.evaluer(_jeu(), avec_ecriture)
    detail = next(d for d in resultat["details"] if d["cas_id"] == "lecture-ecriture-interdite")

    assert detail["outils"]["ok"] is False
    assert any("interdits" in raison or "must_not_write" in raison
               for raison in detail["raisons"])


def test_un_selectionneur_en_erreur_ne_bloque_pas_la_notation():
    def en_panne(cas):
        raise RuntimeError("échec simulé")

    resultat = eg.evaluer(_jeu(), en_panne)

    assert resultat["passe"] == 0
    assert resultat["total"] == _jeu().taille
    assert all("sélectionneur en erreur" in detail["raisons"][0]
               for detail in resultat["details"])


def test_un_selectionneur_asynchrone_est_execute():
    async def parfait(cas):
        return _candidat(cas)

    resultat = eg.evaluer(_jeu(), parfait)
    assert resultat["passe"] == resultat["total"]


def test_un_cas_malforme_est_refuse():
    with pytest.raises(eo.CasInvalide, match="champ inconnu"):
        eg.JeuGold().charger_json(json.dumps([{
            "id": "x", "question": "q", "outils_attendus": ["resoudre_application"],
            "inconnu": True,
        }]))
    with pytest.raises(eo.CasInvalide, match="ACCEPTED"):
        eg.JeuGold().charger_json(json.dumps([{
            "id": "x", "question": "q", "outils_attendus": ["resoudre_application"],
            "claims": [{"id": "c", "statut": "ACCEPTED", "preuve_requise": False}],
        }]))
    with pytest.raises(eo.CasInvalide, match="borné à proposition"):
        eg.JeuGold().charger_json(json.dumps([{
            "id": "x", "question": "q", "outils_attendus": ["resoudre_application"],
            "decision": {"verdict": "proposer", "autorite_max": "decision"},
        }]))
