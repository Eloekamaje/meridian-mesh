"""Découverte d'interfaces : posture lecture/écriture, preuves, limites et aucune invention."""
from jumeau import graphe, interface_outils, interfaces, interfaces_depot
from jumeau.specialiste_decouverte import SpecialisteDecouverte
from jumeau.specialistes import ContexteSpecialiste, Specialiste


def _contrat(identifiant="ctr-1", application="comptes", format_="openapi"):
    return interfaces.Contract(
        id=identifiant, format=format_, version="1.0.0", digest="digest",
        locator="specs/comptes.yaml", application_id=application, environment="prod")


def _operation(identifiant, contract_id, method, path, name, protocol="rest", environment="prod"):
    return interfaces.Operation(
        id=identifiant, contract_id=contract_id, protocol=protocol, method=method, path=path,
        name=name, version="1.0.0", environment=environment)


def _graphe():
    return interfaces.InterfaceGraph(
        contracts=[_contrat()],
        operations=[
            _operation("op-get", "ctr-1", "GET", "/comptes", "listerComptes"),
            _operation("op-post", "ctr-1", "POST", "/comptes", "creerCompte"),
        ],
        bindings=[interfaces.Binding(
            id="bnd-1", protocol="rest", url="https://api.example.test/v1", environment="prod")],
        assertions=[interfaces.Assertion(
            subject="comptes", predicate="EXPOSE", object="GET /comptes", mode="declared",
            source="openapi", locator="specs/comptes.yaml", environment="prod",
            confidence=0.95, evidence="digest")],
    )


def _brancher(monkeypatch, resultat):
    appels = []

    def faux_lire_graph(conn, tenant, application_id=None):
        appels.append((conn, tenant, application_id))
        return resultat

    monkeypatch.setattr(interfaces_depot, "lire_graph", faux_lire_graph)
    return appels


def _contexte(**valeurs):
    base = {"tenant": "banque", "application_id": "comptes"}
    base.update(valeurs)
    return ContexteSpecialiste(**base)


def _par_operation(resultat):
    return {p.donnees.get("operation_id"): p for p in resultat.propositions
            if p.donnees.get("operation_id")}


def test_lecture_et_ecriture_sont_separees_avec_preuves(monkeypatch):
    graph = _graphe()
    conn = object()
    appels = _brancher(monkeypatch, graph)
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=conn))

    assert appels == [(conn, "banque", "comptes")]
    assert resultat.specialiste == "decouverte" and resultat.statut == "ok"
    operations = _par_operation(resultat)
    lecture = operations["op-get"]
    ecriture = operations["op-post"]

    assert lecture.type == "PROPOSITION"
    assert lecture.donnees["capacite"] == "observer"
    assert lecture.donnees["lecture_seule"] is True
    assert lecture.donnees["approbation_requise"] is False
    assert lecture.actions == ("observer_interface",)
    assert "GET /comptes" in lecture.titre and "listerComptes" in lecture.titre
    assert "op-get" in lecture.preuves
    assert "specs/comptes.yaml" in lecture.preuves

    assert ecriture.type == "PROPOSITION"
    assert ecriture.donnees["capacite"] == "agir"
    assert ecriture.donnees["lecture_seule"] is False
    assert ecriture.donnees["approbation_requise"] is True
    assert "approbation requise" in ecriture.resume
    assert set(ecriture.actions) == {"observer_interface", "demander_specification"}
    assert "op-post" in ecriture.preuves and "creerCompte" in ecriture.titre

    modele = next(p for p in resultat.propositions if p.type == "MODELE")
    assert (modele.donnees["contrats"], modele.donnees["operations"], modele.donnees["bindings"]) == (1, 2, 1)
    assert (modele.donnees["lectures"], modele.donnees["ecritures"]) == (1, 1)
    assert modele.donnees["approbation_requise"] is True
    assert modele.donnees["operations_sous_approbation"] == ["op-post"]
    assert [fiche["operation_id"] for fiche in modele.donnees["priorite_observation"]] == ["op-get", "op-post"]
    assert modele.donnees["detail_contrats"][0]["locator"] == "specs/comptes.yaml"
    assert modele.donnees["detail_bindings"][0]["id"] == "bnd-1"
    assert "approbation requise" in modele.resume


def test_les_operations_proposees_viennent_toutes_du_graphe(monkeypatch):
    _brancher(monkeypatch, _graphe())
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=object()))

    connues = {operation.id for operation in _graphe().operations}
    proposees = {p.donnees["operation_id"] for p in resultat.propositions
                 if p.donnees.get("operation_id")}
    assert proposees == connues
    assert all(p.donnees["origine"] == "graphe_interfaces" for p in resultat.propositions
               if p.donnees.get("operation_id"))


def test_graphe_absent_retourne_partiel_sans_proposition(monkeypatch):
    _brancher(monkeypatch, None)
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=object()))

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert any("graphe d'interfaces absent" in limite for limite in resultat.limites)


def test_sans_connexion_retourne_partiel_sans_proposition(monkeypatch):
    def interdit(*args, **kwargs):
        raise AssertionError("lire_graph ne doit pas être appelé sans connexion")

    monkeypatch.setattr(interfaces_depot, "lire_graph", interdit)
    resultat = SpecialisteDecouverte().analyser(_contexte())

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert any("connexion absente" in limite for limite in resultat.limites)


def test_graphe_vide_est_partiel_et_le_modele_ne_compte_rien(monkeypatch):
    _brancher(monkeypatch, interfaces.InterfaceGraph())
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=object()))

    assert resultat.statut == "partiel"
    assert any("aucune opération prouvée" in limite for limite in resultat.limites)
    modele = next(p for p in resultat.propositions if p.type == "MODELE")
    assert (modele.donnees["contrats"], modele.donnees["operations"], modele.donnees["bindings"]) == (0, 0, 0)
    assert modele.donnees["priorite_observation"] == []
    assert any("demander_specification" in p.actions for p in resultat.propositions)


def test_graphe_partiel_est_signale_sans_perdre_les_preuves(monkeypatch):
    graph = _graphe()
    graph.partial = True
    graph.diagnostics.append("paths absente ou invalide")
    _brancher(monkeypatch, graph)
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=object()))

    assert resultat.statut == "partiel"
    assert any("graphe d'interfaces partiel" in limite and "paths absente" in limite
               for limite in resultat.limites)
    modele = next(p for p in resultat.propositions if p.type == "MODELE")
    assert modele.donnees["graphe_partiel"] is True
    assert "op-get" in _par_operation(resultat)["op-get"].preuves


def test_twin_manquant_seulement_avec_un_identifiant_explicite_et_un_store(monkeypatch):
    _brancher(monkeypatch, _graphe())
    store = graphe.GrapheMemoire()
    resultat = SpecialisteDecouverte().analyser(
        _contexte(conn=object(), twin_ids=("process-paiement",), store=store))

    proposition = next(p for p in resultat.propositions
                       if p.donnees.get("twin_id") == "process-paiement")
    assert proposition.type == "PROPOSITION"
    assert proposition.actions == ("creer_twin", "demander_specification")
    assert proposition.donnees["type_suggere"] is None
    assert proposition.donnees["source"] == "contexte.twin_ids"
    assert "process-paiement" in proposition.titre


def test_un_twin_deja_present_ou_l_application_n_est_pas_declare_manquant(monkeypatch):
    _brancher(monkeypatch, _graphe())
    store = graphe.GrapheMemoire()
    store.upsert_twin(graphe.NoeudTwin(
        id="process-paiement", tenant_id="banque", type="PROCESS", label="Paiement"))
    resultat = SpecialisteDecouverte().analyser(
        _contexte(conn=object(), twin_ids=("process-paiement", "comptes"), store=store))

    assert not any(p.donnees.get("twin_id") for p in resultat.propositions)


def test_sans_store_un_twin_explicite_n_est_pas_declare_manquant(monkeypatch):
    _brancher(monkeypatch, _graphe())
    resultat = SpecialisteDecouverte().analyser(
        _contexte(conn=object(), twin_ids=("process-paiement",)))

    assert resultat.statut == "partiel"
    assert not any("creer_twin" in p.actions for p in resultat.propositions)
    assert any("store de graphe" in limite for limite in resultat.limites)


def test_une_situation_sans_store_ne_produit_aucun_type_invente(monkeypatch):
    _brancher(monkeypatch, _graphe())
    resultat = SpecialisteDecouverte().analyser(
        _contexte(conn=object(), situation_id="sit-paiement"))

    assert resultat.statut in {"ok", "partiel"}
    assert not any("creer_twin" in p.actions for p in resultat.propositions)
    assert not any(p.donnees.get("twin_id") == "sit-paiement" for p in resultat.propositions)


def test_manifestes_absents_ne_devine_pas_la_posture(monkeypatch):
    _brancher(monkeypatch, _graphe())
    monkeypatch.setattr(interface_outils, "manifests_depuis_interface", lambda *args, **kwargs: [])
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=object()))

    assert resultat.statut == "partiel"
    assert any("manifestes insuffisants" in limite for limite in resultat.limites)
    for proposition in _par_operation(resultat).values():
        assert proposition.type == "CONSTAT"
        assert proposition.donnees["capacite"] is None
        assert proposition.donnees["posture"] == "inconnue"
        assert proposition.actions == ("demander_specification",)
    modele = next(p for p in resultat.propositions if p.type == "MODELE")
    assert modele.donnees["postures_inconnues"] == 2
    assert modele.donnees["lectures"] == 0 and modele.donnees["ecritures"] == 0


def test_sans_application_aucun_graphe_n_est_lu(monkeypatch):
    def interdit(*args, **kwargs):
        raise AssertionError("lire_graph exige une application")

    monkeypatch.setattr(interfaces_depot, "lire_graph", interdit)
    resultat = SpecialisteDecouverte().analyser(
        ContexteSpecialiste(tenant="banque", twin_ids=("process-paiement",), conn=object()))

    assert resultat.statut == "partiel"
    assert any("application_id absent" in limite for limite in resultat.limites)
    assert not any(p.donnees.get("operation_id") for p in resultat.propositions)


def test_une_erreur_de_lecture_ne_rend_que_le_type(monkeypatch):
    def casse(*args, **kwargs):
        raise RuntimeError("secret interne à ne pas recopier")

    monkeypatch.setattr(interfaces_depot, "lire_graph", casse)
    resultat = SpecialisteDecouverte().analyser(_contexte(conn=object()))

    assert resultat.statut == "erreur"
    assert resultat.erreur == "RuntimeError"
    assert resultat.propositions == []
    assert all("secret" not in limite for limite in resultat.limites)


def test_le_specialiste_respecte_le_protocole():
    specialiste = SpecialisteDecouverte()
    assert (specialiste.nom, specialiste.autorite) == ("decouverte", "proposition")
    assert isinstance(specialiste, Specialiste)
