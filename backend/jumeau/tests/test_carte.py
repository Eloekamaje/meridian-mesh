"""La carte d'un jumeau : sa porte extérieure, lue sans le réveiller."""
from jumeau import carte

CLAIMS = [
    {"predicat": "REALISE_CAPACITE", "objet": "Gérer les dossiers", "statut": "ACCEPTED"},
    {"predicat": "REALISE_CAPACITE", "objet": "Orienter une personne", "statut": "PROPOSED"},
    {"predicat": "EXPOSE", "objet": "GET /dossiers", "statut": "PROPOSED"},
    {"predicat": "ECHANGE_AVEC", "objet": "Envoie les alertes au service Fraude", "statut": "PROPOSED"},
    {"predicat": "DEPEND_DE", "objet": "fastapi", "statut": "PROPOSED"},
    {"predicat": "REALISE_CAPACITE", "objet": "Ancienne capacité", "statut": "CONTESTED"},
]
JUMEAU = {"id": "tbt", "nom": "TBT", "equipe": "Équipe TBT", "domaine": "Paiement", "mission": "Traite les virements"}
SOURCES = [{"nom": "tbt-api", "branche": "main", "curseur": "a" * 40}]
RELATIONS = [{"id": "r1", "source": "tbt", "cible": "fraude", "etat": "confirmee"},
             {"id": "r2", "source": "comptes", "cible": "tbt", "etat": "validation"},
             {"id": "r3", "source": "x", "cible": "y", "etat": "confirmee"}]
NOMS = {"fraude": "Fraude", "comptes": "Comptes"}


def test_carte_d_un_jumeau():
    c = carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS)
    assert c["capacites"] == ["Gérer les dossiers ✓", "Orienter une personne"]   # contestée : hors carte
    assert c["offre"] == ["GET /dossiers"]
    assert c["echanges"] == ["Envoie les alertes au service Fraude"]
    assert c["voisins"] == [{"jumeau": "fraude", "nom": "Fraude", "sens": "vers", "etat": "confirmee", "relation": "r1"},
                            {"jumeau": "comptes", "nom": "Comptes", "sens": "depuis", "etat": "validation", "relation": "r2"}]
    assert c["code"] == ["tbt-api · main · aaaaaaaaaaaa"]
    assert "fastapi" not in str(c)  # l'extraction technique reste à la porte intérieure


def test_carte_en_texte_court_pour_un_prompt():
    texte = carte.texte(carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS))
    assert texte.startswith("### TBT [tbt]")
    assert "Mission : Traite les virements" in texte
    assert "Voisins : Fraude (vers, confirmee) [r:r1] ; Comptes (depuis, validation) [r:r2]" in texte  # citables
    assert len(texte) < 800


def test_carte_porte_l_ancre_d_identite_cmdb():
    c = carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS, ci="TBT-PROD")
    assert c["ci"] == "TBT-PROD" and "CMDB TBT-PROD" in carte.texte(c)
    assert "CMDB" not in carte.texte(carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS))


def test_carte_porte_la_verification_et_ecarte_le_non_appuye():
    claims = [{"predicat": "ECHANGE_AVEC", "objet": "Fraude", "statut": "PROPOSED",
               "verification": {"etat": "selon", "systemes": ["git"]}},
              {"predicat": "ECHANGE_AVEC", "objet": "Comptes", "statut": "PROPOSED", "verification": {"etat": "recoupe"}},
              {"predicat": "ECHANGE_AVEC", "objet": "Aucun autre système", "statut": "PROPOSED",
               "verification": {"etat": "non_appuye"}},
              {"predicat": "ECHANGE_AVEC", "objet": "Paie", "statut": "PROPOSED", "verification": {"etat": "en_partie"}},
              {"predicat": "ECHANGE_AVEC", "objet": "Courriel", "statut": "PROPOSED"}]
    c = carte.carte(JUMEAU, SOURCES, claims, [], {})
    assert c["echanges"] == ["Fraude (d'après le code)", "Comptes (recoupé)", "Courriel"]


def test_une_connaissance_incertaine_ne_se_publie_pas():
    claims = [{"predicat": "ECHANGE_AVEC", "objet": "Fraude", "statut": "PROPOSED", "verification": {"etat": "incertain"}},
              {"predicat": "ECHANGE_AVEC", "objet": "Comptes", "statut": "PROPOSED", "verification": {"etat": "verifie"}}]
    assert carte.carte(JUMEAU, SOURCES, claims, [], {})["echanges"] == ["Comptes (vérifié)"]
