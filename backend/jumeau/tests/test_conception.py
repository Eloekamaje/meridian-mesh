"""Conception greenfield : une proposition d'architecture, sans jumeau, sans preuve, sans registre."""
import asyncio
import json

from jumeau import agent, conception
from jumeau.conception import ArchitectureCible, Composant, Lien


def dating():
    """Une demande d'application de rencontre : au moins huit composants, dont les capacités attendues."""
    return ArchitectureCible(
        titre="Application de rencontre",
        resume="Une proposition d'application de rencontre centrée sur le consentement, la sécurité et la "
               "maîtrise des données personnelles.",
        hypotheses=[
            "Le service démarre sur mobile pour un marché francophone.",
            "Un like mutuel est nécessaire pour ouvrir une conversation.",
            "La position est approximative, désactivable et jamais partagée en continu.",
        ],
        composants=[
            Composant(id="profil", nom="Profil et préférences", role="Déclarer son profil et ses critères."),
            Composant(id="matching", nom="Matching et likes", role="Proposer des profils et enregistrer les likes."),
            Composant(id="messagerie", nom="Messagerie", role="Permettre les échanges après un like mutuel."),
            Composant(id="geolocalisation", nom="Géolocalisation", role="Situer les profils à une échelle approximative."),
            Composant(id="moderation", nom="Modération et sécurité", role="Signaler, masquer et bloquer les abus."),
            Composant(id="abonnement", nom="Abonnement et paiement", role="Gérer les offres et les paiements."),
            Composant(id="notifications", nom="Notifications", role="Prévenir des nouveaux messages et likes."),
            Composant(id="recherche", nom="Recherche et découverte", role="Parcourir les profils compatibles."),
            Composant(id="stockage", nom="Stockage et confidentialité", role="Conserver les données avec minimisation."),
            Composant(id="api", nom="API et applications", role="Exposer les capacités aux clients mobiles."),
        ],
        liens=[
            Lien(de="profil", vers="matching", libelle="fournit les préférences"),
            Lien(de="matching", vers="messagerie", libelle="ouvre la conversation après un like mutuel"),
            Lien(de="geolocalisation", vers="recherche", libelle="filtre les profils à proximité"),
            Lien(de="recherche", vers="profil", libelle="parcourt les profils"),
            Lien(de="moderation", vers="messagerie", libelle="signale et bloque les messages abusifs"),
            Lien(de="abonnement", vers="matching", libelle="ouvre les fonctionnalités payantes"),
            Lien(de="notifications", vers="messagerie", libelle="prévient d'un nouveau message"),
            Lien(de="api", vers="profil", libelle="expose le profil aux applications"),
            Lien(de="stockage", vers="profil", libelle="conserve les données avec minimisation"),
        ],
        hors_scope=[
            "Le paiement in-app des magasins d'applications.",
            "La vérification d'identité par un prestataire tiers.",
        ],
    )


def faux_agent(monkeypatch, sortie=None, erreur=None):
    """Remplace l'agent Strands : reçoit la consigne et rend la sortie structurée demandée."""
    vus = {}

    class Faux:
        def __init__(self, **kw):
            vus["creation"] = kw
            self.event_loop_metrics = type("Metriques", (), {
                "accumulated_usage": {"inputTokens": 120, "outputTokens": 80, "totalTokens": 200},
                "tool_metrics": {},
            })()

        async def invoke_async(self, consigne, structured_output_model=None):
            vus["consigne"], vus["structure"] = consigne, structured_output_model
            if erreur is not None:
                raise erreur
            return type("Resultat", (), {"structured_output": sortie})()

    monkeypatch.setattr(conception, "Agent", Faux)
    return vus


def reponse_dating(monkeypatch):
    vus = faux_agent(monkeypatch, dating())
    return asyncio.run(conception.repondre("Conçois une application de rencontre", "concevoir", modele=object())), vus


def test_dating_propose_au_moins_huit_composants_attendus(monkeypatch):
    r, vus = reponse_dating(monkeypatch)
    assert r is not None and r["comportement"] == "concevoir" and r["proposition"] is True
    assert vus["structure"] is ArchitectureCible
    assert vus["creation"]["tools"] == [] and vus["creation"]["callback_handler"] is None
    assert "proposition" in vus["creation"]["system_prompt"].lower()
    boites = r["schemas"][0]["boites"]
    assert len(boites) >= 8
    libelles = " ".join(boite["libelle"].lower() for boite in boites)
    for attendu in ("matching", "like", "messagerie", "géolocalisation", "modération", "sécurité",
                    "abonnement", "paiement"):
        assert attendu in libelles


def test_prompt_exige_greenfield_securite_et_aucune_preuve_inventee(monkeypatch):
    _, vus = reponse_dating(monkeypatch)
    prompt = vus["creation"]["system_prompt"].lower()
    for attendu in ("greenfield", "hypothèses", "composants", "liens", "sécurité", "vie privée",
                    "preuve", "jumeau", "registre"):
        assert attendu in prompt
    assert "proposition" in vus["consigne"].lower()


def test_schema_de_proposition_sans_preuve_ni_jumeau(monkeypatch):
    r, _ = reponse_dating(monkeypatch)
    schema = r["schemas"][0]
    assert schema["type"] == "architecture" and schema["mode"] == "proposition"
    assert schema["groupes"] == []
    assert schema["fleches"] and {fleche["etat"] for fleche in schema["fleches"]} == {"propose"}
    assert "preuves" not in schema and "jumeaux" not in schema
    assert "preuve" not in json.dumps(schema, ensure_ascii=False).lower()
    assert "jumeau" not in json.dumps(schema, ensure_ascii=False).lower()
    assert r["preuves"] == [] and r["contributions"] == [] and r["jumeaux_participants"] == []


def test_hypotheses_non_vides_et_texte_qui_dit_proposition(monkeypatch):
    r, _ = reponse_dating(monkeypatch)
    hypotheses = r["schemas"][0]["hypotheses"]
    assert hypotheses
    assert "proposition" in r["reponse"].lower()
    assert all(hypothese in r["reponse"] for hypothese in hypotheses)


def test_ids_invalides_dedupliques_et_liens_orphelins_ignores():
    plan = ArchitectureCible(
        titre="Essai", resume="Une proposition de test.",
        composants=[
            Composant(id="matching!", nom="Matching", role="likes"),
            Composant(id="matching", nom="Doublon", role="doublon"),
            Composant(id="", nom="Paiement", role="payer"),
            Composant(id="1-paiement", nom="Paiement bis", role="payer autrement"),
            Composant(id="!!!", nom="", role="sans identifiant"),
        ],
        liens=[
            Lien(de="matching!", vers="Paiement", libelle="abonne"),
            Lien(de="matching", vers="1-paiement", libelle="paie"),
            Lien(de="matching", vers="absent", libelle="orphelin"),
            Lien(de="absent", vers="Paiement", libelle="orphelin"),
            Lien(de="matching!", vers="Paiement", libelle="abonne"),
        ],
    )
    schema = conception.construire_schema(plan)
    assert [boite["id"] for boite in schema["boites"]] == ["matching", "Paiement", "b_1_paiement"]
    assert [(f["de"], f["vers"]) for f in schema["fleches"]] == [("matching", "Paiement"),
                                                                 ("matching", "b_1_paiement")]


def test_bornes_de_douze_boites_et_vingt_liens():
    composants = [Composant(id=f"c{i}", nom=f"Composant {i}", role="r") for i in range(15)]
    liens = [Lien(de=f"c{i % 12}", vers=f"c{(i + 1) % 12}", libelle=f"lien {i}") for i in range(24)]
    schema = conception.construire_schema(ArchitectureCible(titre="Grand", resume="Essai", composants=composants,
                                                            liens=liens))
    assert len(schema["boites"]) == conception.MAX_BOITES == 12
    assert len(schema["fleches"]) == conception.MAX_LIENS == 20


def test_cible_nomme_le_titre():
    schema = conception.construire_schema(dating(), cible="Dating")
    assert schema["titre"] == "Dating"


def test_modele_absent_rend_none(monkeypatch):
    monkeypatch.setattr(agent, "modele", lambda: None)
    assert asyncio.run(conception.repondre("Conçois une application", "concevoir")) is None


def test_modele_non_configure_rend_none(monkeypatch):
    def panne():
        raise RuntimeError("clé absente")

    monkeypatch.setattr(agent, "modele", panne)
    assert asyncio.run(conception.repondre("Conçois une application", "concevoir")) is None


def test_panne_du_modele_ne_fuit_pas(monkeypatch):
    faux_agent(monkeypatch, erreur=RuntimeError("secret interne à ne pas diffuser"))
    assert asyncio.run(conception.repondre("Conçois une application", "concevoir", modele=object())) is None


def test_reponse_serialisable_en_json(monkeypatch):
    r, _ = reponse_dating(monkeypatch)
    copie = json.loads(json.dumps(r, ensure_ascii=False))
    assert copie["schemas"][0]["mode"] == "proposition"
    assert copie["comportement"] == "concevoir"
    assert copie["usage"]["modele"] == "inconnu" and copie["durees"]
