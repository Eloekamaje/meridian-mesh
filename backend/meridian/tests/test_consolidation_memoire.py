"""Consolidation de la mémoire : doublons et conflits proposés, approbation humaine obligatoire."""
import copy
import json

import pytest

from meridian.application import consolidation_memoire as consolidation


def memoire(identifiant, contenu, **extras):
    """Une mémoire organisationnelle minimale, tenant et scope explicites."""
    base = {
        "id": identifiant,
        "tenant_id": "tenant-a",
        "scope": "scope-a",
        "classe": "organisationnelle",
        "contenu": contenu,
    }
    base.update(extras)
    return base


def test_doublons_exacts_normalises_en_accents_casse_et_espaces():
    memoires = [
        memoire("m1", "Café d'équipe"),
        memoire("m2", "cafe d equipe", evidences=["ev-2"]),
        memoire("m3", "  CAFÉ   D'ÉQUIPE  ", evidences=["ev-1", "ev-2"]),
    ]

    proposition = consolidation.proposer(memoires)

    assert len(proposition.groupes) == 1
    groupe = proposition.groupes[0]
    assert groupe.keep_id == "m1"
    assert set(groupe.remove_ids) == {"m2", "m3"}
    assert groupe.confiance == 1.0
    assert groupe.evidences == ("ev-1", "ev-2")
    assert "doublon exact" in groupe.raison


def test_quasi_doublon_au_seuil_et_confiance_mesuree():
    proposition = consolidation.proposer(
        [memoire("m1", "Sauvegarde quotidienne des donnees"),
         memoire("m2", "Sauvegarde quotidienne des donnees critiques")],
        seuil_similarite=0.75,
    )

    assert len(proposition.groupes) == 1
    assert proposition.groupes[0].confiance == pytest.approx(0.8)
    assert "quasi-doublon" in proposition.groupes[0].raison


def test_tenant_scope_et_classe_ne_se_croisent_jamais():
    reference = memoire("m1", "Le service est actif", scope="scope-a")
    autre_scope = memoire("m2", "Le service est actif", scope="scope-b")
    autre_tenant = memoire("m3", "Le service est actif", tenant_id="tenant-b")
    autre_classe = memoire("m4", "Le service est actif", classe="episodique")

    proposition = consolidation.proposer([reference, autre_scope, autre_tenant, autre_classe])
    assert proposition.groupes == () and proposition.conflits == ()

    filtree = consolidation.proposer([reference, autre_tenant], tenant_id="tenant-a")
    assert filtree.groupes == () and filtree.conflits == ()
    assert any("tenant" in limite for limite in filtree.limites)


def test_polarite_opposee_est_un_conflit_et_jamais_une_fusion():
    proposition = consolidation.proposer(
        [memoire("m1", "Le service est actif"), memoire("m2", "Le service n'est pas actif")],
        seuil_similarite=0.0,
    )

    assert proposition.groupes == ()
    assert len(proposition.conflits) == 1
    conflit = proposition.conflits[0]
    assert set(conflit.ids) == {"m1", "m2"}
    assert conflit.type == "fait"


def test_meme_cle_valeurs_differentes_est_un_conflit_valeur():
    proposition = consolidation.proposer(
        [memoire("m1", "Couleur: bleu"), memoire("m2", "couleur = rouge")],
        seuil_similarite=0.0,
    )

    assert proposition.groupes == ()
    assert len(proposition.conflits) == 1
    assert proposition.conflits[0].type == "valeur"
    assert proposition.conflits[0].gravite == "haute"


def test_preference_opposee_type_preference():
    proposition = consolidation.proposer(
        [memoire("m1", "Je préfère le bleu"), memoire("m2", "Je ne préfère pas le bleu")],
        seuil_similarite=0.0,
    )

    assert proposition.groupes == ()
    assert proposition.conflits[0].type == "preference"


def test_proposition_deterministe_et_sans_mutation_des_entrees():
    memoires = [
        memoire("m2", "Le service est actif"),
        memoire("m1", "le service est actif"),
        memoire("m3", "Le service n'est pas actif"),
    ]
    avant = copy.deepcopy(memoires)

    premier = consolidation.proposer(memoires)
    second = consolidation.proposer(list(reversed(memoires)))

    assert premier.as_dict() == second.as_dict()
    assert memoires == avant
    json.dumps(premier.as_dict(), ensure_ascii=False)


def test_approbation_exige_un_acteur_et_seulement_les_ids_choisis():
    proposition = consolidation.proposer([
        memoire("m1", "Politique de sauvegarde"),
        memoire("m2", "politique de sauvegarde"),
        memoire("c1", "Le service est actif"),
        memoire("c2", "Le service n'est pas actif"),
    ])

    with pytest.raises(ValueError):
        consolidation.approuver(proposition, acteur="   ")

    plan = consolidation.approuver(proposition, acteur="alice", ids=["m1"])
    assert plan["acteur"] == "alice"
    assert len(plan["groupes"]) == 1 and plan["groupes"][0]["garder"] == "m1"
    assert plan["groupes"][0]["retirer"] == ["m2"]
    assert plan["conflits"] == []
    assert plan["ecritures"] is False

    conflit = consolidation.approuver(proposition, acteur="alice", ids=["c1"])
    assert conflit["groupes"] == []
    assert len(conflit["conflits"]) == 1
    assert conflit["conflits"][0]["action"] == "trancher"

    vide = consolidation.approuver(proposition, acteur="alice")
    assert vide["groupes"] == [] and vide["conflits"] == []
    assert any("aucune sélection explicite" in limite for limite in vide["limites"])

    inconnu = consolidation.approuver(proposition, acteur="alice", ids=["absent"])
    assert inconnu["groupes"] == [] and inconnu["ignores"] == ["absent"]


def test_approbation_depuis_un_dict_et_alias_pur():
    proposition = consolidation.proposer([
        memoire("m1", "Politique de sauvegarde"),
        memoire("m2", "politique de sauvegarde"),
    ])

    depuis_dict = consolidation.approuver(proposition.as_dict(), acteur="alice", ids=["m1"])
    alias = consolidation.fusionner_memoires(proposition, acteur="alice", ids=["m1"])

    assert depuis_dict == alias
    assert depuis_dict["ecritures"] is False
    assert proposition.as_dict()["groupes"][0]["remove_ids"] == ["m2"]


def test_approuver_ne_modifie_pas_la_proposition():
    proposition = consolidation.proposer([
        memoire("m1", "Politique de sauvegarde"),
        memoire("m2", "politique de sauvegarde"),
    ])
    avant = copy.deepcopy(proposition.as_dict())

    consolidation.approuver(proposition, acteur="alice", ids=["m1"])

    assert proposition.as_dict() == avant


def test_aucun_secret_n_est_recopie_dans_la_proposition_ni_le_plan():
    secret = "supersecret123"
    proposition = consolidation.proposer([
        memoire("m1", f"Le jeton vaut token={secret}",
                evidences=[f"https://user:motdepasse@hote.test/x?token={secret}", f"token={secret}",
                           "secret-de-test"]),
        memoire("m2", f"le jeton vaut token={secret}."),
    ])
    plan = consolidation.approuver(proposition, acteur="alice", ids=["m1"])
    rendu = json.dumps([proposition.as_dict(), plan], ensure_ascii=False)

    assert proposition.groupes
    assert secret not in rendu
    assert "motdepasse" not in rendu
    assert "secret-de-test" not in rendu
    assert "***" in rendu


def test_proposition_vide_seuil_et_type_de_conflit_invalides():
    vide = consolidation.proposer([])
    assert vide.groupes == () and vide.conflits == ()
    assert any("aucune mémoire exploitable" in limite for limite in vide.limites)

    with pytest.raises(ValueError):
        consolidation.proposer([], seuil_similarite=1.5)
    with pytest.raises(ValueError):
        consolidation.Conflit(ids=("a", "b"), type="inconnu")


def test_groupes_bornes_et_limite_declaree():
    memoires = []
    for indice in range(consolidation.MAX_GROUPES + 10):
        contenu = f"regle unique {indice} alpha beta"
        memoires.extend([
            memoire(f"a{indice:03d}", contenu),
            memoire(f"b{indice:03d}", contenu.upper()),
        ])

    proposition = consolidation.proposer(memoires)

    assert len(proposition.groupes) == consolidation.MAX_GROUPES
    assert any("groupes de fusion tronqués" in limite for limite in proposition.limites)
