"""Identité typée : un dépôt prouve un rattachement, il ne devient jamais le nom d'une application."""
import json

from jumeau.identite import resoudre

JUMEAUX = [
    {"id": "conduit", "nom": "Conduit", "mission": "Publie et organise les articles", "domaine": "Contenu",
     "statut": "actif",
     "sources_detail": [{"cle": "git-conduit", "nom": "Dépôt conduit · main · aaaaaaaaaaaa"}]},
    {"id": "nouveau-jumeau", "nom": "Nouveau jumeau", "mission": "dfggg", "domaine": "Inconnu",
     "statut": "provisoire",
     "sources_detail": [{"cle": "git-gsf-mockup", "nom": "Dépôt gsf-mockup · main · 11cdf5b3a732"}]},
]

PARTAGES = [
    {"id": "alpha", "nom": "Alpha", "mission": "Gère les dossiers", "domaine": "Client", "statut": "actif",
     "sources_detail": [{"cle": "git-partage", "nom": "Dépôt partage · main · bbbbbbbbbbbb"}]},
    {"id": "beta", "nom": "Beta", "mission": "Suit les dossiers", "domaine": "Client", "statut": "actif",
     "sources_detail": [{"cle": "git-partage", "nom": "Dépôt partage · main · bbbbbbbbbbbb"}]},
]


def test_un_depot_mene_au_twin_provisoire_puis_a_l_application_candidate():
    r = resoudre("régénère le flux du gsf-mockup", JUMEAUX)
    assert r.twin_id == "nouveau-jumeau"
    assert r.application_id == "nouveau-jumeau"
    assert r.statut == "provisoire"
    assert [e["type"] for e in r.chemin] == ["source", "twin", "application"]
    assert r.chemin[0]["id"] == "repo:gsf-mockup"
    assert r.chemin[1]["id"] == "nouveau-jumeau"
    assert r.chemin[2]["statut"] == "candidat"
    assert r.requires_confirmation is True
    assert r.mentions[0]["matched_on"] == "source"
    assert r.mentions[0]["surface"] == "gsf-mockup"
    assert r.mentions[0]["type"] == "source"
    assert r.application_id != "gsf-mockup" and r.chemin[-1]["id"] != "gsf-mockup"


def test_une_application_canonique_ne_passe_pas_par_son_depot():
    r = resoudre("régénère le flux de Conduit", JUMEAUX)
    assert r.twin_id == "conduit"
    assert r.application_id == "conduit"
    assert r.statut == "canonique"
    assert r.requires_confirmation is False
    assert [e["type"] for e in r.chemin] == ["application"]
    assert "source" not in [e["type"] for e in r.chemin]


def test_un_nom_de_twin_provisoire_est_une_resolution_pas_un_echec():
    r = resoudre("Nouveau jumeau", JUMEAUX)
    assert r.twin_id == "nouveau-jumeau"
    assert r.statut == "provisoire"
    assert r.requires_confirmation is True
    assert r.absent is False
    assert r.chemin[0]["type"] == "twin"
    assert r.chemin[-1]["type"] == "application"


def test_une_faute_de_frappe_controlee_resout_l_application():
    r = resoudre("régénère le flux de Conduite", JUMEAUX)
    assert r.twin_id == "conduit"
    assert r.statut == "canonique"
    assert 0.85 <= r.confiance < 1.0
    assert r.mentions[0]["matched_on"] == "nom"


def test_une_question_inconnue_reste_non_concluante():
    r = resoudre("Quel est le taux de change de la livre sterling ?", JUMEAUX)
    assert r.absent is True
    assert r.twin_id is None
    assert r.application_id is None
    assert r.statut == "absent"
    assert "aucun candidat" in r.motif.lower()
    assert "absence non prouvée" in r.motif
    assert r.mentions == [{"surface": "Quel est le taux de change de la livre sterling ?", "type": "inconnu",
                           "id": None, "matched_on": "aucun", "confiance": 0.0}]


def test_deux_twins_sur_le_meme_depot_sont_ambigus():
    r = resoudre("régénère le flux de partage", PARTAGES)
    assert r.ambigu is True
    assert r.absent is False
    assert r.statut == "ambigu"
    assert r.twin_id is None
    assert r.application_id is None
    assert {c["id"] for c in r.candidats} == {"alpha", "beta"}
    assert len(r.mentions) == 1 and r.mentions[0]["type"] == "source"


def test_le_preambule_rend_l_identite_provisoire_visible():
    r = resoudre("régénère le flux du gsf-mockup", JUMEAUX)
    p = r.preambule()
    assert "provisoire" in p and "gsf-mockup" in p and "promouvoir" in p
    assert resoudre("régénère le flux de Conduit", JUMEAUX).preambule() == ""
    assert resoudre("Quel est le taux de change de la livre sterling ?", JUMEAUX).preambule() == ""


def test_as_dict_est_serialisable_en_json():
    r = resoudre("régénère le flux du gsf-mockup", JUMEAUX)
    d = r.as_dict()
    assert d["question"] == r.question
    assert d["twin_id"] == "nouveau-jumeau"
    assert set(d) == {"question", "mentions", "chemin", "twin_id", "application_id", "statut", "confiance",
                      "motif", "candidats", "requires_confirmation", "ambigu", "absent"}
    assert json.loads(json.dumps(d, ensure_ascii=False)) == d
