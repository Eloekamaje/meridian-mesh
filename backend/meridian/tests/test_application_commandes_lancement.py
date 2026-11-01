"""Lancement d'une commande : validation, registre, rejeu et échec de naissance, sans HTTP ni Mongo."""
import asyncio

import pytest

from meridian.application import commandes


class Store:
    def __init__(self, doc, *, jumeau_existe=False, insertion=True):
        self.doc = doc
        self._jumeau_existe = jumeau_existe
        self._insertion = insertion
        self.insertions = []
        self.lancements = []
        self.echecs = []

    async def lire(self, cid):
        return self.doc

    async def jumeau_existe(self, jid):
        return self._jumeau_existe

    async def inserer_jumeau(self, doc):
        self.insertions.append(doc)
        return self._insertion

    async def marquer_lancee(self, cid, patch):
        self.lancements.append((cid, patch))
        return True

    async def marquer_echec_naissance(self, cid, message, fin):
        self.echecs.append((cid, message, fin))


class Runtime:
    def __init__(self, *, disponible=True, actives=(), notification_erreur=False):
        self._disponible = disponible
        self._actives = set(actives)
        self._notification_erreur = notification_erreur
        self.demarrages = []
        self.notifications = []

    def disponible(self):
        return self._disponible

    def en_cours(self, jid):
        return jid in self._actives

    async def demarrer(self, commande, jid, *, acteur, espace_id):
        self.demarrages.append((commande, jid, acteur, espace_id))

    async def notifier(self, jid, texte):
        self.notifications.append((jid, texte))
        if self._notification_erreur:
            raise RuntimeError("notification indisponible")


def _run(coro):
    return asyncio.run(coro)


def _doc(**modifications):
    doc = {
        "id": "c1",
        "etat": "brouillon",
        "jumeau": {"application_id": "paiements", "nom": "Paiements",
                   "proprietaire": "Équipe paiements"},
        "sources": [{"id": "s1", "connecteur": "github", "nom": "code", "statut": "prete"}],
    }
    doc.update(modifications)
    return doc


def _branche(connecteur):
    return connecteur in {"github", "servicenow", "cmdb", "datadog", "otlp", "confluence"}


def _lancer(store, runtime):
    return _run(commandes.lancer_commande(
        store, runtime, "c1",
        acteur="ana", espace_id="espace-1", connecteur_branche=_branche,
    ))


def test_lancement_refuse_une_identite_incomplete():
    store = Store(_doc(jumeau={"application_id": "", "nom": "Paiements", "proprietaire": "Équipe"}))
    runtime = Runtime()
    with pytest.raises(commandes.IdentiteInvalide, match="Identité incomplète"):
        _lancer(store, runtime)
    assert store.insertions == [] and store.lancements == [] and runtime.demarrages == []


def test_lancement_refuse_un_nom_ou_un_proprietaire_trop_long():
    store = Store(_doc(jumeau={"application_id": "paiements", "nom": "x" * 201,
                               "proprietaire": "Équipe"}))
    with pytest.raises(commandes.IdentiteInvalide, match="trop long"):
        _lancer(store, Runtime())


def test_lancement_refuse_un_application_id_invalide():
    store = Store(_doc(jumeau={"application_id": "Paiements !", "nom": "Paiements",
                               "proprietaire": "Équipe"}))
    with pytest.raises(commandes.IdentiteInvalide, match="application_id invalide"):
        _lancer(store, Runtime())


def test_lancement_exige_au_moins_une_source_prete():
    store = Store(_doc(sources=[{"id": "s1", "connecteur": "github", "nom": "code",
                                 "statut": "a_configurer"}]))
    with pytest.raises(commandes.SourcePreteRequise, match="Au moins une source prête"):
        _lancer(store, Runtime())


def test_lancement_refuse_une_source_prete_dont_le_connecteur_n_est_pas_branche():
    store = Store(_doc(sources=[{"id": "s1", "connecteur": "postgresql", "nom": "base",
                                 "statut": "prete"}]))
    with pytest.raises(commandes.ConnecteurNonBranche, match="base"):
        _lancer(store, Runtime())


def test_lancement_exige_la_couche_cognitive_postgres():
    with pytest.raises(commandes.NaissanceIndisponible, match="JUMEAU_PG_DSN"):
        _lancer(Store(_doc()), Runtime(disponible=False))


def test_lancement_exige_code_ou_ancre_et_substance():
    store = Store(_doc(sources=[{"id": "s1", "connecteur": "datadog", "nom": "métriques",
                                 "statut": "prete"}]))
    with pytest.raises(commandes.NaissanceImpossible, match="Aucune source prête"):
        _lancer(store, Runtime())


def test_lancement_refuse_un_jumeau_deja_present_ou_en_cours_de_naissance():
    store = Store(_doc(), jumeau_existe=True)
    with pytest.raises(commandes.JumeauExistant, match="déjà cet identifiant"):
        _lancer(store, Runtime())

    store = Store(_doc())
    with pytest.raises(commandes.JumeauExistant, match="déjà cet identifiant"):
        _lancer(store, Runtime(actives={"paiements"}))
    assert store.insertions == []


def test_lancement_refuse_une_course_perdue_a_l_insertion():
    store = Store(_doc(), insertion=False)
    with pytest.raises(commandes.JumeauExistant, match="déjà cet identifiant"):
        _lancer(store, Runtime())
    assert len(store.insertions) == 1 and store.lancements == []


def test_rejeu_idempotent_ne_reecrit_rien():
    store = Store(_doc(
        etat="lancee", jumeau_id="paiements",
        naissance={"etat": "en_cours"},
        sources=[{"id": "s1", "statut": "prete"}, {"id": "s2", "statut": "a_configurer"}],
    ))
    runtime = Runtime()
    assert _lancer(store, runtime) == {
        "ok": True, "jumeau_id": "paiements", "sources_lancees": 1,
        "sources_reportees": 1, "naissance": "en_cours", "deja": True,
    }
    assert store.insertions == [] and store.lancements == [] and runtime.demarrages == []


def test_lancement_reussi_cree_le_jumeau_met_a_jour_la_commande_et_demarre_la_naissance():
    source = {"id": "s1", "connecteur": "github", "nom": "code", "statut": "prete"}
    store = Store(_doc(
        jumeau={"application_id": " Paiements ", "nom": " Paiements ",
                "proprietaire": " Équipe paiements "},
        sources=[source, {"id": "s2", "connecteur": "jira", "nom": "suivi",
                          "statut": "a_configurer"}],
    ))
    runtime = Runtime()
    resultat = _lancer(store, runtime)
    assert resultat["ok"] and resultat["jumeau_id"] == "paiements"
    assert resultat["sources_lancees"] == 1 and resultat["sources_reportees"] == 1
    assert resultat["naissance"] == "en_cours" and "deja" not in resultat

    nouveau = store.insertions[0]
    assert nouveau["id"] == "paiements"
    assert nouveau["nom"] == "Paiements"
    assert nouveau["proprietaire"] == "Équipe paiements"
    assert nouveau["sources"] == {"github": True}
    assert nouveau["couverture"] == 29

    cid, patch = store.lancements[0]
    assert cid == "c1" and patch["etat"] == "lancee"
    assert patch["jumeau_id"] == "paiements"
    assert patch["naissance"]["etat"] == "en_cours"

    commande, jid, acteur, espace_id = runtime.demarrages[0]
    assert jid == "paiements" and acteur == "ana" and espace_id == "espace-1"
    assert commande["jumeau"]["application_id"] == "paiements"
    assert commande["jumeau"]["nom"] == "Paiements"
    assert commande["sources"] == [source, {"id": "s2", "connecteur": "jira", "nom": "suivi",
                                            "statut": "a_configurer"}]


def test_echec_de_naissance_met_a_jour_la_commande_et_notifie():
    store = Store(_doc())
    runtime = Runtime()
    commande = _doc()
    _run(commandes.echec_naissance(
        store, runtime, commande, "paiements", "durée dépassée",
        maintenant="2026-01-01T00:00:00+00:00",
    ))
    assert store.echecs == [("c1", "durée dépassée", "2026-01-01T00:00:00+00:00")]
    assert runtime.notifications == [
        ("paiements", "La naissance de Paiements a échoué : durée dépassée.")
    ]


def test_echec_de_naissance_utilise_l_identifiant_si_le_nom_manque():
    store = Store(_doc(jumeau={}))
    runtime = Runtime()
    _run(commandes.echec_naissance(store, runtime, _doc(jumeau={}), "paiements", "erreur"))
    assert runtime.notifications == [
        ("paiements", "La naissance de paiements a échoué : erreur.")
    ]


def test_une_notification_manquee_ne_masque_pas_l_echec_deja_enregistre():
    store = Store(_doc())
    runtime = Runtime(notification_erreur=True)
    _run(commandes.echec_naissance(store, runtime, _doc(), "paiements", "erreur"))
    assert len(store.echecs) == 1 and store.echecs[0][:2] == ("c1", "erreur")
