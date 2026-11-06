"""Passerelle contexte/twins/sources → dossier de raisonnement."""
from meridian.application import contexte_raisonnement as passerelle
from meridian.application import noyau_raisonnement as noyau
from meridian.application import composition
from meridian.domain import profils


PACK = {
    "fingerprint": "ctx-test",
    "completude": "partiel",
    "limites": ["une preuve est périmée"],
    "preuves": ["p-1"],
    "entites": ["twin-alpha"],
    "faits": [
        {"id": "f-1", "type": "CONSTAT", "titre": "Le service Alpha appelle Beta",
         "specialiste": "preuve", "confiance": 0.8, "preuves": ["p-1"],
         "donnees": {"twin_id": "twin-alpha", "source_id": "git"}},
        {"id": "f-2", "type": "HYPOTHESE", "titre": "Le cache réduit la latence",
         "specialiste": "impact", "confiance": 0.5,
         "donnees": {"twin_id": "twin-alpha"}},
    ],
}

SPECIALISTES = {
    "propositions": [
        {"specialiste": "impact", "type": "RISQUE", "titre": "Dépendance non prouvée",
         "resume": "La dépendance n'a pas de preuve.", "preuves": ["p-2"], "confiance": 0.7,
         "donnees": {"twin_id": "twin-alpha", "source": "graph"}},
    ],
}


def test_pack_devient_contexte_et_constats():
    contexte = passerelle.depuis_pack(PACK)
    assert contexte.fingerprint == "ctx-test"
    assert contexte.twin_ids == ("twin-alpha",)
    assert contexte.preuve_ids == ("p-1",)
    assert contexte.source_ids == ("git",)
    assert contexte.completude == "partiel"

    constats = passerelle.constats_depuis_pack(PACK)
    assert len(constats) == 2
    assert constats[0].twin_id == "twin-alpha"
    assert constats[0].preuve_id == "p-1"
    assert constats[1].type == "HYPOTHESE"


def test_specialistes_deviennent_des_constats():
    constats = passerelle.constats_depuis_specialistes(SPECIALISTES)
    assert len(constats) == 1
    assert constats[0].provenance == "impact"
    assert constats[0].source_id == "graph"


def test_analyser_reponse_reprend_le_plan_et_le_contexte():
    profil = profils.resoudre_profil(profil="architecte")
    plan = composition.planifier(profil, "concevoir une architecture")
    dossier = noyau.analyser_reponse(
        "Conçois une architecture", {"reponse": "Proposition"},
        pack_contexte=PACK, dossier_specialistes=SPECIALISTES,
        plan_composition=plan, trace_id="tr-test")
    assert dossier.contexte is not None
    assert dossier.contexte.fingerprint == "ctx-test"
    assert dossier.constats and dossier.constats[0].twin_id == "twin-alpha"
    assert dossier.trace_id == "tr-test"
    assert {m for m in dossier.plan.methodes} <= {m.id for m in plan.methodes}


def test_attacher_ne_duplique_pas_les_constats():
    dossier = noyau.analyser_reponse(
        "Conçois une architecture", {"reponse": "Proposition"})
    passerelle.attacher(dossier, pack=PACK, specialistes=SPECIALISTES)
    premier = len(dossier.constats)
    passerelle.attacher(dossier, pack=PACK, specialistes=SPECIALISTES)
    assert len(dossier.constats) == premier


def test_contexte_de_chat_porte_le_poste_et_l_autorite_sans_les_confondre():
    contexte = passerelle.depuis_scope({
        "question": "Quel est l'impact ?", "twin_ids": ["twin-alpha"],
        "acteur": "usr-1", "poste": "Architecte", "profil": "architecte",
        "autorite": "proposition", "espace": "architecture",
    })
    assert contexte.acteur == "usr-1"
    assert contexte.poste == "Architecte"
    assert contexte.profil == "architecte"
    assert contexte.autorite == "proposition"
    assert contexte.espace == "architecture"
    sans_acteur = passerelle._empreinte_scope({"twin_ids": ["twin-alpha"]})
    avec_acteur = passerelle._empreinte_scope({"twin_ids": ["twin-alpha"], "acteur": "usr-1"})
    assert avec_acteur != sans_acteur
