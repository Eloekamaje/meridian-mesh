"""Dérivation de l'état produit : la règle est générale, pas liée à une application."""
from meridian.application import etat_produit as etat


def lien(de, type_, etat_="verifie", predicat=""):
    return etat.Lien(de=de, vers=f"{de}:{type_}", type=type_, preuve=f"{de}:{type_}",
                     etat=etat_, predicat=predicat)


def test_la_chaine_complete_et_les_manques_sont_nommes():
    capacites = [
        {"id": "inscription", "libelle": "Inscription"},
        {"id": "equipe", "libelle": "Créer une équipe"},
        {"id": "tableau", "libelle": "Créer un tableau"},
        {"id": "accueil", "libelle": "Accueil"},
        {"id": "tache", "libelle": "Tâche"},
    ]
    liens = [
        lien("inscription", "EXPOSE_PAR"), lien("inscription", "CONSOMME"),
        lien("inscription", "CABLAGE", predicat="APPELLE"), lien("inscription", "DETIENT"),
        lien("equipe", "EXPOSE_PAR"), lien("equipe", "CONSOMME"),
        lien("equipe", "CABLAGE", predicat="HANDLER_VIDE"), lien("equipe", "DETIENT"),
        lien("tableau", "EXPOSE_PAR"), lien("tableau", "CONSOMME"),
        lien("tableau", "CABLAGE", predicat="STUB"), lien("tableau", "DETIENT"),
        lien("accueil", "EXPOSE_PAR"), lien("accueil", "CONSOMME"),
        lien("accueil", "CABLAGE", predicat="DONNEES_FIXES"), lien("accueil", "DETIENT"),
    ]
    etats = {e.id: e for e in etat.deriver(capacites, liens)}
    assert etats["inscription"].statut == "ok"
    assert etats["equipe"].statut == "absent" and etats["equipe"].manques == ("câblage UI",)
    assert etats["tableau"].statut == "absent" and etats["tableau"].manques == ("câblage UI",)
    assert etats["accueil"].statut == "partiel" and etats["accueil"].manques == ("données réelles",)
    assert etats["tache"].statut == "absent" and etats["tache"].manques == ("exposition",)


def test_une_preuve_non_tenue_rend_inconnu():
    capacites = [{"id": "recherche", "libelle": "Rechercher"}]
    liens = [
        lien("recherche", "EXPOSE_PAR"),
        lien("recherche", "CONSOMME"),
        lien("recherche", "CABLAGE", predicat="APPELLE"),
        lien("recherche", "DETIENT", etat_="en_partie"),
    ]
    [resultat] = etat.deriver(capacites, liens)
    assert resultat.statut == "inconnu"
    assert resultat.manques == ("donnée",)


def test_une_capacite_sans_donnee_requise_peut_etre_ok():
    capacites = [{"id": "export", "libelle": "Exporter"}]
    liens = [
        lien("export", "EXPOSE_PAR"),
        lien("export", "CONSOMME"),
        lien("export", "CABLAGE", predicat="APPELLE"),
    ]
    [resultat] = etat.deriver(capacites, liens, donnees_requises=set())
    assert resultat.statut == "ok"


def test_le_module_ne_connait_aucune_application():
    capacites = [{"id": "facture", "libelle": "Payer une facture"}]
    liens = [
        lien("facture", "EXPOSE_PAR", etat_="selon"),
        lien("facture", "CONSOMME", etat_="selon"),
        lien("facture", "CABLAGE", predicat="APPELLE", etat_="selon"),
        lien("facture", "DETIENT", etat_="selon"),
    ]
    [resultat] = etat.deriver(capacites, liens)
    assert resultat.statut == "ok"
    assert resultat.preuves == ("facture:EXPOSE_PAR", "facture:CONSOMME",
                                "facture:CABLAGE", "facture:DETIENT")


def test_l_etat_de_verification_du_claim_est_lu_quand_le_lien_ne_le_porte_pas():
    claims = {
        "r1": {"predicat": "EXPOSE", "verification": {"etat": "verifie"}},
        "s1": {"predicat": "USES", "verification": {"etat": "verifie"}},
        "w1": {"predicat": "APPELLE", "verification": {"etat": "verifie"}},
        "d1": {"predicat": "DETIENT", "verification": {"etat": "en_partie"}},
    }
    liens = [
        etat.Lien("cap", "r1", "EXPOSE_PAR"),
        etat.Lien("cap", "s1", "CONSOMME"),
        etat.Lien("cap", "w1", "CABLAGE"),
        etat.Lien("cap", "d1", "DETIENT"),
    ]
    [resultat] = etat.deriver([{"id": "cap", "libelle": "Cap"}], liens, claims=claims)
    assert resultat.statut == "inconnu"
    assert resultat.manques == ("donnée",)
    assert resultat.preuves == ()


def test_la_projection_est_generique_et_ne_connait_aucune_application():
    etats = [
        etat.EtatCapacite("a", "Capacité A", "ok", expose=True, consomme=True, cablage=True, donnee=True,
                          exposition_fondement="c:1", donnee_fondement="c:2"),
        etat.EtatCapacite("b", "Capacité B", "absent", expose=False),
    ]
    schema = etat.projeter(etats, titre="État")
    assert schema["type"] == "architecture"
    assert [b["id"] for b in schema["boites"]] == ["cap-a", "cap-b", "api", "donnees"]
    assert schema["boites"][2]["statut"] == "partiel"  # une capacité expose, l'autre non
    assert schema["boites"][3]["statut"] == "ok"  # une donnée tenue
    assert schema["fleches"] == [
        {"de": "cap-a", "vers": "api", "libelle": "appelle", "fondement": "c:1", "appel": ""},
        {"de": "api", "vers": "donnees", "libelle": "lit / écrit", "fondement": "c:2", "appel": ""},
    ]


def test_la_projection_montre_les_manques_sans_inventer_de_fleche():
    etats = [etat.EtatCapacite("x", "Capacité X", "absent", expose=False)]
    schema = etat.projeter(etats, titre="État")
    assert schema["boites"][-2]["statut"] == "absent"  # API absente
    assert schema["fleches"] == []  # aucune flèche inventée


def test_la_projection_ne_penalise_pas_l_api_pour_une_capacite_sans_route():
    etats = [etat.EtatCapacite("a", "Capacité A", "ok", expose=True),
             etat.EtatCapacite("b", "Capacité B", "absent", expose=None)]
    schema = etat.projeter(etats, titre="État")
    assert schema["boites"][-2]["statut"] == "ok"  # l'API couvre ce qu'elle expose
