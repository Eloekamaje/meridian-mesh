"""Profils : composition, alias, inférence, autorité bornée et défaut en lecture seule."""
from dataclasses import FrozenInstanceError

import pytest

from jumeau import profils
from jumeau.profils import (
    AUTORITES,
    CATALOGUE_PROFILS,
    METHODES,
    POSTURES,
    SOURCES,
    Profil,
    autorise,
    autorite_superieure,
    resoudre_profil,
)


def _champs(**extra):
    base = {
        "id": "profil_test",
        "libelle": "Profil de test",
        "postures": ("explorateur",),
        "methodes": ("adr",),
        "competences": ("analyse",),
        "domaines": (),
        "autorite": "lecture",
        "confiance": 0.5,
        "source": "explicite",
        "inconnu": False,
    }
    base.update(extra)
    return base


def test_profil_explicite_connu_et_alias():
    developpeur = resoudre_profil(profil="developpeur")
    assert developpeur.id == "developpeur"
    assert developpeur.source == "explicite"
    assert developpeur.confiance == 1.0
    assert developpeur.autorite == "proposition"
    assert developpeur.inconnu is False
    assert isinstance(developpeur.postures, tuple)

    po = resoudre_profil(profil="PO")
    assert po.id == "product_owner"
    assert po.source == "explicite"

    daf = resoudre_profil(profil="Directeur général")
    assert daf.id == "directeur"


def test_identite_par_role_groupe_et_alias_partiel():
    po = resoudre_profil(identite={"role": "Product Owner"})
    assert po.id == "product_owner"
    assert po.source == "identite"
    assert po.autorite == "proposition"
    assert po.inconnu is False

    dev = resoudre_profil(identite={"groups": ["ROLE_DEVELOPPEUR"]})
    assert dev.id == "developpeur"
    assert dev.source == "identite"

    analyste = resoudre_profil(identite={"poste": "Analyste fonctionnel senior"})
    assert analyste.id == "analyste_fonctionnel"
    assert analyste.source == "identite"


def test_priorite_explicite_identite_question():
    explicite = resoudre_profil(profil="support", identite={"role": "Développeur"},
                                question="endpoint API")
    assert explicite.id == "support"
    assert explicite.source == "explicite"

    identite = resoudre_profil(identite={"role": "Support"}, question="endpoint API")
    assert identite.id == "support"
    assert identite.source == "identite"


@pytest.mark.parametrize(
    ("question", "attendu"),
    [
        ("Peux-tu ajouter un endpoint API et un test ?", "developpeur"),
        ("Quelle priorité pour la roadmap produit ?", "product_owner"),
        ("Incident de production, SLA dépassé", "support"),
        ("Contrôle de conformité sur ce risque", "risque"),
    ],
)
def test_inference_par_mots_cles(question, attendu):
    profil = resoudre_profil(question=question)
    assert profil.id == attendu
    assert profil.source == "infere"
    assert 0.55 <= profil.confiance <= 0.8
    assert profil.inconnu is False
    assert profil.autorite == "lecture"


def test_une_inference_ne_grant_jamais_de_decision():
    directeur = resoudre_profil(question="Quel budget et quel arbitrage pour cette direction ?")
    assert directeur.id == "directeur"
    assert directeur.source == "infere"
    assert directeur.autorite == "lecture"
    assert autorise(directeur, "lire") is True
    assert autorise(directeur, "proposer") is False
    assert autorise(directeur, "decider") is False

    risque = resoudre_profil(question="Risque de conformité et contrôle interne")
    assert risque.id == "risque"
    assert risque.autorite == "lecture"
    assert autorise(risque, "approuver") is False


def test_question_sans_mot_cle_retombe_en_lecture_seule():
    profil = resoudre_profil(question="Bonjour, comment vas-tu aujourd'hui ?")
    assert profil.id == "generaliste"
    assert profil.inconnu is True
    assert profil.source == "defaut"
    assert profil.autorite == "lecture"
    assert profil.confiance <= 0.4


def test_profil_explicite_inconnu_ne_declenche_pas_l_inference():
    profil = resoudre_profil(profil="super_heros", question="endpoint API et test")
    assert profil.id == "generaliste"
    assert profil.inconnu is True
    assert profil.source == "defaut"
    assert profil.autorite == "lecture"
    assert profil.confiance <= 0.4


def test_plafond_d_autorite_abaisse_sans_jamais_relever():
    assert resoudre_profil(profil="directeur", autorite_max="proposition").autorite == "proposition"
    assert resoudre_profil(profil="directeur", autorite_max="lecture").autorite == "lecture"
    assert resoudre_profil(profil="directeur", autorite_max="action").autorite == "decision"
    assert resoudre_profil(profil="risque", autorite_max="proposition").autorite == "proposition"
    assert resoudre_profil(profil="developpeur", autorite_max="decision").autorite == "proposition"
    assert resoudre_profil(question="budget et arbitrage", autorite_max="action").autorite == "lecture"
    assert resoudre_profil(profil="inconnu", autorite_max="action").autorite == "lecture"


def test_types_invalides_du_profil():
    with pytest.raises(TypeError):
        Profil(**_champs(id=1))
    with pytest.raises(ValueError):
        Profil(**_champs(id=""))
    with pytest.raises(TypeError):
        Profil(**_champs(libelle=None))
    with pytest.raises(TypeError):
        Profil(**_champs(postures=["explorateur"]))
    with pytest.raises(ValueError):
        Profil(**_champs(postures=("pirate",)))
    with pytest.raises(ValueError):
        Profil(**_champs(methodes=("pirate",)))
    with pytest.raises(TypeError):
        Profil(**_champs(competences=(1,)))
    with pytest.raises(ValueError):
        Profil(**_champs(domaines=("",)))
    with pytest.raises(TypeError):
        Profil(**_champs(autorite=1))
    with pytest.raises(ValueError):
        Profil(**_champs(autorite="root"))
    with pytest.raises(TypeError):
        Profil(**_champs(confiance="0.5"))
    with pytest.raises(TypeError):
        Profil(**_champs(confiance=True))
    with pytest.raises(ValueError):
        Profil(**_champs(confiance=1.5))
    with pytest.raises(ValueError):
        Profil(**_champs(confiance=float("nan")))
    with pytest.raises(TypeError):
        Profil(**_champs(source=1))
    with pytest.raises(ValueError):
        Profil(**_champs(source="magie"))
    with pytest.raises(TypeError):
        Profil(**_champs(inconnu="non"))


def test_types_invalides_de_la_resolution():
    with pytest.raises(TypeError):
        resoudre_profil(profil=42)
    with pytest.raises(TypeError):
        resoudre_profil(identite=["developpeur"])
    with pytest.raises(TypeError):
        resoudre_profil(question=None)
    with pytest.raises(TypeError):
        resoudre_profil(domaines=[1])
    with pytest.raises(TypeError):
        resoudre_profil(domaines=42)
    with pytest.raises(TypeError):
        resoudre_profil(autorite_max=1)
    with pytest.raises(ValueError):
        resoudre_profil(autorite_max="root")


def test_catalogue_coherent_et_autorites_bornees():
    requis = {
        "business_analyst", "analyste_fonctionnel", "developpeur", "product_owner",
        "scrum_master", "chef_projet", "directeur", "support", "risque", "data_steward",
        "architecte", "generaliste",
    }
    assert requis <= set(CATALOGUE_PROFILS)
    assert len(CATALOGUE_PROFILS) >= len(requis)
    for identifiant, profil in CATALOGUE_PROFILS.items():
        assert identifiant == profil.id
        assert profil.domaines == ()
        assert set(profil.postures) <= POSTURES
        assert set(profil.methodes) <= METHODES
        assert profil.source in SOURCES
        assert 0.0 <= profil.confiance <= 1.0
        assert isinstance(profil.inconnu, bool)
    for identifiant, profil in CATALOGUE_PROFILS.items():
        if identifiant not in {"directeur", "risque"}:
            assert not autorite_superieure(profil, "proposition")
        assert profil.autorite != "action"
    assert CATALOGUE_PROFILS["directeur"].autorite == "decision"
    assert CATALOGUE_PROFILS["risque"].autorite == "approbation"
    assert CATALOGUE_PROFILS["generaliste"].autorite == "lecture"
    assert CATALOGUE_PROFILS["generaliste"].inconnu is True


def test_domaines_conserves_comme_contexte():
    explicite = resoudre_profil(profil="developpeur", domaines=("finance", "finance"))
    assert explicite.domaines == ("finance",)

    identite = resoudre_profil(
        identite={"role": "Data steward", "domaines": ["sante"]},
        domaines=["finance"],
    )
    assert identite.domaines == ("finance", "sante")
    assert identite.id == "data_steward"

    inconnu = resoudre_profil(question="rien de reconnaissable", domaines=("retail",))
    assert inconnu.domaines == ("retail",)
    assert inconnu.autorite == "lecture"


def test_helpers_d_autorite_et_de_serialisation():
    assert autorite_superieure("decision", "proposition") is True
    assert autorite_superieure("lecture", "lecture") is False
    assert autorite_superieure("action", "decision") is True
    assert autorite_superieure(CATALOGUE_PROFILS["risque"], "proposition") is True

    dev = resoudre_profil(profil="developpeur")
    assert autorise(dev, "lire") is True
    assert autorise(dev, "proposer") is True
    assert autorise(dev, "approuver") is False
    assert autorise(dev, "decider") is False
    assert autorise(dev, "exécuter") is False

    risque = resoudre_profil(profil="risque")
    assert autorise(risque, "approuver") is True
    assert autorise(risque, "decider") is False

    with pytest.raises(ValueError):
        autorise(dev, "danser")
    with pytest.raises(TypeError):
        autorise("developpeur", "lire")

    donnees = dev.as_dict()
    assert donnees["id"] == "developpeur"
    assert donnees["autorite"] == "proposition"
    assert donnees["domaines"] == ()
    with pytest.raises(FrozenInstanceError):
        dev.libelle = "Autre"


def test_ordre_des_autorites_du_module():
    assert AUTORITES == ("lecture", "proposition", "approbation", "decision", "action")
    assert profils.AUTORITES == AUTORITES
