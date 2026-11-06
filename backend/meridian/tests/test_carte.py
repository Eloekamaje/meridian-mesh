"""La carte d'un jumeau : sa porte extérieure, lue sans le réveiller."""
import asyncio
from datetime import datetime, timezone

from meridian.adapters.outbound.postgres import carte, depot
from meridian.domain.partage import Consommateur

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
    assert "Code : tbt-api · main · aaaaaaaaaaaa" in texte
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


def test_carte_porte_identite_owner_criticite_fraicheur_et_couverture():
    fiche = {
        "contenu": ("## En 30 secondes\n"
                    "Une application de paiement.\n"
                    "Criticité : élevée — paie\n"),
        "couverture": {"total": 7, "answered": 3, "partial": 2, "unknown": 2, "contradicted": 0},
        "stale": True,
        "cree_le": datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc),
    }
    c = carte.carte(
        {**JUMEAU, "type": "APPLICATION", "application_id": "tbt", "perimetre": "paiement"},
        SOURCES, CLAIMS, RELATIONS, NOMS, fiche=fiche)
    assert c["type"] == "APPLICATION" and c["application_id"] == "tbt" and c["perimetre"] == "paiement"
    assert c["equipe"] == "Équipe TBT"
    assert c["criticite"].startswith("élevée")
    assert c["couverture"]["answered"] == 3
    assert c["fraicheur"]["sources"][0]["commit"] == "a" * 12
    assert c["fraicheur"]["fiche"] == {
        "cree_le": "2026-11-05T08:00:00+00:00",
        "stale": True,
    }


def test_carte_dependances_business_sans_dependance_technique():
    c = carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS)
    assert "Fraude" in c["dependances"] and "Comptes" in c["dependances"]
    assert "fastapi" not in c["dependances"]  # la dépendance technique reste à la porte intérieure


def test_carte_du_jumeau_refuse_un_autre_tenant(monkeypatch):
    monkeypatch.setattr(depot, "jumeau_carte", lambda c, j: {"id": "x", "tenant_id": "autre"})
    assert asyncio.run(carte.carte_du_jumeau(None, None, "x", tenant_id="banque")) is None


def test_perimetre_autorise_normalise_les_slugs():
    jumeau = {**JUMEAU, "perimetre": "Paiement"}
    assert carte.perimetre_autorise(jumeau, Consommateur("banque", portfolio_id="paiement"))
    assert not carte.perimetre_autorise(jumeau, Consommateur("banque", portfolio_id="fraude"))
    assert not carte.perimetre_autorise(jumeau, Consommateur("banque"))


def test_perimetre_id_prime_sur_le_texte_libre():
    jumeau = {**JUMEAU, "perimetre": "Paiement", "perimetre_id": "portefeuille-cartes"}
    assert carte.perimetre_autorise(
        jumeau, Consommateur("banque", portfolio_id="portefeuille-cartes"))
    assert not carte.perimetre_autorise(
        jumeau, Consommateur("banque", portfolio_id="paiement"))


def test_carte_du_jumeau_refuse_un_autre_perimetre(monkeypatch):
    monkeypatch.setattr(
        depot, "jumeau_carte",
        lambda c, j: {"id": "x", "tenant_id": "banque", "perimetre": "Paiement"})
    assert asyncio.run(carte.carte_du_jumeau(
        None, None, "x", tenant_id="banque",
        consommateur=Consommateur("banque", portfolio_id="fraude"))) is None


def test_carte_architecture_inclut_les_dependances_techniques():
    c = carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS, audience="architecture")
    assert c["dependances_techniques"] == ["fastapi"]
    assert c["audience"] == "architecture"
    assert "dependances_techniques" not in carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS)


def test_carte_audit_inclut_questions_et_claims():
    fiche = {"questions": [{"cle": "sert", "statut": "answered"}], "claims": [7], "couverture": {}}
    c = carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS, fiche=fiche, audience="audit")
    assert c["questions"][0]["cle"] == "sert" and c["claims"] == [7]
    assert "questions" not in carte.carte(JUMEAU, SOURCES, CLAIMS, RELATIONS, NOMS, fiche=fiche)
