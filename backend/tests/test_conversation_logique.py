"""Logique pure de la conversation : versions, branches, messages de Flore (contrat Conversation v1, §1 et §3)."""
import copy

import pytest

import conversation as c


def rep(texte, **kw):
    return {"reponse": texte, "preuves": [], "contributions": [], "comportement": "repondre",
            "relecture_etat": "relue", "corrige": False, "origine": "modele", "durees": {}, **kw}


def fil():
    return [{"role": "utilisateur", "texte": "Q1", "quand": "t"}, c.message_flore(rep("R1")),
            {"role": "utilisateur", "texte": "Q2", "quand": "t"}, c.message_flore(rep("R2"))]


def test_message_flore_a_la_forme_du_contrat():
    m = c.message_flore(rep("Bonjour", preuves=[{"id": "p"}]))
    assert m["role"] == "flore" and m["texte"] == "Bonjour" and m["interrompu"] is False
    assert m["version"] == 0 and len(m["versions"]) == 1
    assert m["versions"][0]["texte"] == "Bonjour" and m["versions"][0]["preuves"] == [{"id": "p"}]
    assert m["quand"] and m["versions"][0]["quand"]


def test_message_flore_garde_l_usage_et_le_cout():
    m = c.message_flore(rep("R", usage={"total": 1200, "cout": {"montant": 0.0005, "devise": "USD"}}))
    assert m["usage"]["total"] == 1200
    assert m["versions"][0]["usage"]["cout"]["devise"] == "USD"


def test_message_interrompu_garde_le_texte_ecrit():
    m = c.message_interrompu("Début de ré")
    assert m["interrompu"] is True and m["texte"] == "Début de ré"
    assert m["versions"][0]["interrompu"] is True


def test_ajouter_version_rend_la_nouvelle_active_sans_muter():
    m = c.message_flore(rep("A"))
    avant = copy.deepcopy(m)
    n = c.ajouter_version(m, rep("B", corrige=True))
    assert m == avant
    assert n["texte"] == "B" and n["corrige"] is True and n["version"] == 1
    assert [v["texte"] for v in n["versions"]] == ["A", "B"]


def test_ajouter_version_efface_le_retour_de_l_ancienne():
    m = {**c.message_flore(rep("A")), "retour": {"valeur": "faux"}}
    assert "retour" not in c.ajouter_version(m, rep("B"))


def test_ajouter_version_sur_un_message_ancien_sans_versions():
    ancien = {"role": "flore", "texte": "vieux", "preuves": [], "quand": "t"}
    n = c.ajouter_version(ancien, rep("neuf"))
    assert [v["texte"] for v in n["versions"]] == ["vieux", "neuf"] and n["version"] == 1


def test_choisir_version_remonte_les_champs_du_haut():
    n = c.ajouter_version(c.message_flore(rep("A", origine="modele")), rep("B", origine="demonstration"))
    m = c.choisir_version(n, 0)
    assert m["texte"] == "A" and m["origine"] == "modele" and m["version"] == 0 and len(m["versions"]) == 2
    assert n["version"] == 1  # l'entrée n'est pas modifiée


@pytest.mark.parametrize("index", [-1, 2, 99])
def test_choisir_version_hors_bornes(index):
    n = c.ajouter_version(c.message_flore(rep("A")), rep("B"))
    with pytest.raises(ValueError, match="version"):
        c.choisir_version(n, index)


def test_ranger_branche_et_modifier():
    msgs = fil()
    avant = copy.deepcopy(msgs)
    n = c.ranger_branche_et_modifier(msgs, 0, "Q1 bis")
    assert msgs == avant
    assert len(n) == 1 and n[0]["texte"] == "Q1 bis"
    assert [b["texte"] for b in n[0]["branches"]] == ["Q1", "Q1 bis"] and n[0]["branche"] == 1
    assert [m["texte"] for m in n[0]["branches"][0]["suite"]] == ["R1", "Q2", "R2"]
    assert n[0]["branches"][1]["suite"] == []


def test_modifier_au_milieu_garde_le_debut():
    n = c.ranger_branche_et_modifier(fil(), 2, "Q2 bis")
    assert [m["texte"] for m in n] == ["Q1", "R1", "Q2 bis"]
    assert [m["texte"] for m in n[2]["branches"][0]["suite"]] == ["R2"]


def test_choisir_branche_restaure_et_range_la_courante():
    n = c.ranger_branche_et_modifier(fil(), 0, "Q1 bis")
    n = n[:1] + [c.message_flore(rep("R1 bis"))]  # la réponse à la nouvelle question
    r = c.choisir_branche(n, 0, 0)
    assert [m["texte"] for m in r] == ["Q1", "R1", "Q2", "R2"] and r[0]["branche"] == 0
    assert [m["texte"] for m in r[0]["branches"][1]["suite"]] == ["R1 bis"]
    retour = c.choisir_branche(r, 0, 1)
    assert [m["texte"] for m in retour] == ["Q1 bis", "R1 bis"]


def test_modifier_deux_fois_accumule_trois_branches():
    n = c.ranger_branche_et_modifier(fil(), 0, "B")
    n = c.ranger_branche_et_modifier(n + [c.message_flore(rep("RB"))], 0, "C")
    assert [b["texte"] for b in n[0]["branches"]] == ["Q1", "B", "C"] and n[0]["branche"] == 2
    assert [m["texte"] for m in n[0]["branches"][1]["suite"]] == ["RB"]


@pytest.mark.parametrize("n,texte", [(-1, "x"), (9, "x"), (1, "x"), (0, "  ")])
def test_modifier_refuse_ce_qui_n_est_pas_une_question_valide(n, texte):
    with pytest.raises(ValueError):
        c.ranger_branche_et_modifier(fil(), n, texte)


@pytest.mark.parametrize("n,index", [(9, 0), (1, 0), (0, 0)])
def test_choisir_branche_refuse(n, index):
    with pytest.raises(ValueError):
        c.choisir_branche(fil(), n, index)


def test_choisir_branche_index_hors_bornes():
    n = c.ranger_branche_et_modifier(fil(), 0, "B")
    with pytest.raises(ValueError, match="branche"):
        c.choisir_branche(n, 0, 5)


def test_normaliser_donne_la_version_0_a_un_message_ancien():
    ancien = {"role": "flore", "texte": "vieux", "comportement": "x", "quand": "t"}
    n = c.normaliser(ancien)
    assert n["version"] == 0 and n["versions"][0]["texte"] == "vieux" and n["interrompu"] is False
    assert "versions" not in ancien
    assert c.normaliser(c.message_flore({"reponse": "a"}))["versions"][0]["texte"] == "a"
    q = {"role": "utilisateur", "texte": "q"}
    assert c.normaliser(q) == q


def test_correspond_cherche_titre_et_texte_sans_casse_ni_regex():
    msgs = [{"role": "utilisateur", "texte": "Quel ÉTAT ?"}, {"role": "flore", "texte": "a.b (x)"}]
    assert c.correspond("Socle", msgs, "socle") and c.correspond("", msgs, "état")
    assert c.correspond("", msgs, "a.b (") and not c.correspond("", msgs, "a.*")
    assert not c.correspond("Socle", msgs, "zzz")
    assert c.correspond("Socle", msgs, "  ") and c.correspond(None, [{"texte": None}], "")


ACTIVITE = [{"label": "Je lis le code concerné…", "outil": {"id": "u1", "nom": "lire_code", "etat": "fait", "duree": 0.1}},
            {"label": "Je suis l'enchaînement…", "outil": {"id": "u2", "nom": "suivre_appels", "etat": "en_cours"}}]


def test_l_activite_du_tour_est_gardee_avec_la_reponse_et_sa_version():
    m = c.message_flore({"reponse": "ok", "activite": ACTIVITE})
    assert m["activite"] == ACTIVITE and m["versions"][0]["activite"] == ACTIVITE


def test_un_tour_arrete_garde_son_activite():
    m = c.message_interrompu("Début", ACTIVITE)
    assert m["interrompu"] is True and m["activite"] == ACTIVITE
    assert "activite" not in c.message_interrompu("Début")


def test_decider_une_proposition_une_seule_fois_sans_muter():
    m = c.message_flore({"reponse": "ok", "a_approuver": [{"claim": 3, "jumeau": "conduit", "objet": "x"}]})
    apres = c.decider_proposition(m, 3, "ACCEPTED", "architecte", quand="t")
    assert apres["a_approuver"][0]["decision"] == {"valeur": "ACCEPTED", "par": "architecte", "quand": "t"}
    assert apres["versions"][0]["a_approuver"][0]["decision"]["valeur"] == "ACCEPTED"
    assert "decision" not in m["a_approuver"][0]
    with pytest.raises(ValueError, match="déjà"):
        c.decider_proposition(apres, 3, "CONTESTED", "architecte")
    with pytest.raises(LookupError):
        c.decider_proposition(m, 99, "ACCEPTED", "architecte")
    with pytest.raises(ValueError):
        c.decider_proposition({"role": "utilisateur", "texte": "q"}, 3, "ACCEPTED", "architecte")
