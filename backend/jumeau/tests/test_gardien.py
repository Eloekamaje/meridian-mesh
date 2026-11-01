"""Gardien du jumeau : signaux d'un changement, situation pour « Aujourd'hui », fiche vivante."""
import asyncio
import contextlib
import os
import subprocess
import uuid
from datetime import datetime

import pytest

from jumeau import depot, gardien
from jumeau.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim

AVANT = {("EXPOSE", "GET /virements"), ("EXPOSE", "GET /soldes"), ("DEPEND_DE", "fastapi")}
APRES = {("EXPOSE", "GET /soldes"), ("EXPOSE", "POST /virements/instantanes"), ("DEPEND_DE", "fastapi"),
         ("DEPEND_DE", "kafka-python"), ("LIT_VARIABLE", "KAFKA_URL")}
COMMITS = [{"sha": "b2", "date": "2026-10-27", "auteur": "Alice", "message": "Virements instantanés via Kafka",
            "fichiers": ["api.py"]},
           {"sha": "b1", "date": "2026-10-26", "auteur": "Bob", "message": "Retire l'ancien endpoint de virement",
            "fichiers": ["api.py"]}]


def test_signaux_d_un_changement_classes_par_gravite():
    s = gardien.signaux(AVANT, APRES)
    assert [(x["type"], x["objet"]) for x in s] == [
        ("SERVICE_RETIRE", "GET /virements"),
        ("SERVICE_AJOUTE", "POST /virements/instantanes"),
        ("DEPENDANCE_AJOUTEE", "kafka-python"),
        ("REGLAGE_AJOUTE", "KAFKA_URL"),
    ]
    assert s[0]["gravite"] == "haute" and s[-1]["gravite"] == "basse"


def test_aucun_signal_sans_changement_de_connaissances():
    assert gardien.signaux(AVANT, AVANT) == []


def test_situation_pour_aujourd_hui():
    jumeau = {"id": "tbt", "nom": "TBT"}
    s = gardien.situation(jumeau, "abcdef1234567890", gardien.signaux(AVANT, APRES), COMMITS,
                          "TBT propose désormais des virements instantanés.")
    assert s["id"] == "sit-gardien-tbt-abcdef123456" and s["nature"] == "changement" and s["jumeaux"] == ["tbt"]
    assert s["priorite"] == "haute"  # un service a été retiré
    assert s["resume"] == "TBT propose désormais des virements instantanés."
    assert "1 service retiré" in s["titre"] and "1 nouveau service" in s["titre"]
    assert s["decouverte_pourquoi"] == ["Virements instantanés via Kafka (Alice, 2026-10-27)",
                                        "Retire l'ancien endpoint de virement (Bob, 2026-10-26)"]
    assert any("GET /virements" in r for r in s["reste_a_comprendre"])
    assert datetime.fromisoformat(s["detectee"]).tzinfo is not None and s["reel"] is True


def test_situation_sans_recit_reste_lisible():
    s = gardien.situation({"id": "tbt", "nom": "TBT"}, "a" * 40, gardien.signaux(AVANT, APRES), COMMITS, None)
    assert s["resume"] and "TBT" in s["resume"]


@besoin_pg
def test_fiche_vivante_versionnee_par_commit(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    gardien.enregistrer_fiche(conn, "tbt", "sha1", "Première fiche")
    gardien.enregistrer_fiche(conn, "tbt", "sha2", "Fiche à jour")
    gardien.enregistrer_fiche(conn, "tbt", "sha2", "Fiche à jour, réécrite")
    assert gardien.fiche_courante(conn, "tbt") == {"sha": "sha2", "contenu": "Fiche à jour, réécrite"}
    assert gardien.fiche_courante(conn, "inconnu") is None


@besoin_pg
def test_connaissances_courantes_en_couples(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    assert gardien.connaissances_courantes(conn, "tbt") == {("DEPEND_DE", "motor"), ("DEPEND_DE", "fastapi")}


@besoin_pg
@pytest.mark.skipif(not os.environ.get("MONGO_URL") or not os.environ.get("CBM_BIN"), reason="Mongo et cbm requis")
def test_bout_en_bout_un_commit_devient_une_situation_dans_aujourd_hui(conn, tmp_path, monkeypatch, index_jetables):
    from motor.motor_asyncio import AsyncIOMotorClient
    from jumeau import cbm, ingerer

    depot_app = tmp_path / "tbt"
    depot_app.mkdir()
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")

    def commiter(fichiers, message):
        for nom, contenu in fichiers.items():
            (depot_app / nom).write_text(contenu)
        subprocess.run(["git", "-C", str(depot_app), "add", "."], check=True)
        subprocess.run(["git", "-C", str(depot_app), "-c", "user.name=Alice", "-c", "user.email=a@a", "commit", "-qm",
                        message], check=True)

    subprocess.run(["git", "init", "-q", str(depot_app)], check=True)
    commiter({"requirements.txt": "fastapi==0.1\n",
              "api.py": 'from fastapi import FastAPI\napp = FastAPI()\n\n\n@app.get("/virements")\ndef virements():\n    return []\n'},
             "Première version")
    jumeau = {"id": "tbt-essai", "tenant_id": "local", "nom": "TBT", "equipe": "equipe-tbt"}
    ingerer.ingerer(conn, jumeau, depot_app)
    commiter({"requirements.txt": "fastapi==0.1\nkafka-python==2.0\n",
              "api.py": 'from fastapi import FastAPI\napp = FastAPI()\n\n\n@app.get("/soldes")\ndef soldes():\n    return []\n'},
             "Remplace les virements par la consultation des soldes")

    async def rediger_factice(ctx, dsn, sigs, commits):
        return "Fiche de TBT", f"{len(sigs)} changements observés."

    async def rediger_en_panne(*_):
        raise TimeoutError("quota du modèle")

    async def scenario():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        nom_db = f"test_gardien_{uuid.uuid4().hex[:8]}"
        db = client[nom_db]
        try:
            await db.situations.insert_one({"id": "sit-gardien-tbt-essai-ancien", "statut": "active"})
            bilan = await gardien.veiller(conn, db, "tbt-essai", [depot_app], rediger=rediger_en_panne)
            assert gardien.fiche_courante(conn, "tbt-essai") is None  # l'IA est tombée…
            reprise = await gardien.veiller(conn, db, "tbt-essai", [depot_app], rediger=rediger_factice)
            sits = await db.situations.find({"statut": "active"}, {"_id": 0}).to_list(10)
            archivee = await db.situations.find_one({"id": "sit-gardien-tbt-essai-ancien"})
            registre = await db.jumeaux.find_one({"id": "tbt-essai"}, {"_id": 0})
            encore = await gardien.veiller(conn, db, "tbt-essai", [depot_app], rediger=rediger_factice)
            assert archivee["statut"] == "archivee" and reprise["changement"] and reprise["signaux"] == 0
            return bilan, sits, registre, encore
        finally:
            await client.drop_database(nom_db)
            client.close()

    try:
        bilan, sits, registre, encore = asyncio.run(scenario())
    finally:
        cbm.texte("delete_project", "--project", depot.source_du_jumeau(conn, "tbt-essai")["index_code"])
    assert bilan["changement"] and bilan["commits"] == 1
    [s] = sits
    assert s["priorite"] == "haute" and s["jumeaux"] == ["tbt-essai"]
    assert {"GET /virements", "GET /soldes", "kafka-python"} <= set(s["decouverte_quoi"].replace(";", ":").split(": "))
    assert s["decouverte_pourquoi"] == ["Remplace les virements par la consultation des soldes (Alice, " +
                                        s["decouverte_pourquoi"][0].split("(Alice, ")[1]]
    assert gardien.fiche_courante(conn, "tbt-essai")["contenu"] == "Fiche de TBT"
    assert registre["reel"] is True
    assert encore == {"changement": False}  # rien de neuf : le gardien ne refait rien


def test_une_passe_ratee_n_arrete_pas_la_surveillance(monkeypatch):
    passes = []

    async def veiller_capricieux(*_):
        passes.append(1)
        if len(passes) == 1:
            raise RuntimeError("quota du modèle")
        return {"changement": False}
    monkeypatch.setattr(gardien, "veiller", veiller_capricieux)
    asyncio.run(gardien.surveiller(contextlib.nullcontext, None, "tbt", "/d", intervalle=0, passes=2))
    assert len(passes) == 2


def test_mots_lus_sans_les_citations():
    from jumeau import gardien
    assert gardien.mots("Une maquette `memory/PRD.md#L4-L4` de suivi `app.py#L3`.") == 4


def test_consolidation_l_agent_juge_le_harness_valide_et_execute(monkeypatch):
    import asyncio
    from jumeau import gardien
    lignes = [{"id": 1, "predicat": "REALISE_CAPACITE", "objet": "Saisir hors ligne", "statut": "ACCEPTED"},
              {"id": 2, "predicat": "REALISE_CAPACITE", "objet": "Saisir un dossier hors ligne", "statut": "PROPOSED"},
              {"id": 3, "predicat": "REALISE_CAPACITE", "objet": "Orienter", "statut": "PROPOSED"},
              {"id": 4, "predicat": "DETIENT", "objet": "Les dossiers", "statut": "PROPOSED"},
              {"id": 5, "predicat": "APPLIQUE_REGLE", "objet": "Double approbation", "statut": "PROPOSED"},
              {"id": 6, "predicat": "APPLIQUE_REGLE", "objet": "Deux approbateurs", "statut": "PROPOSED"}]
    G, D, C = gardien.Groupe, gardien.Decision, gardien.Consolidation
    reponses = [C(decisions=[D(question="sert", groupes=[G(garder=1, retirer=[2, 4, 1], raison="même idée")])]),
                C(decisions=[D(question="sert", groupes=[G(garder=1, retirer=[2], raison="même idée")]),
                             D(question="regles", groupes=[G(garder=5, retirer=[6], raison="même règle")])])]
    consignes, fusions = [], []

    class Juge:
        async def invoke_async(self, consigne, structured_output_model):
            consignes.append(consigne)
            return type("Resultat", (), {"structured_output": reponses.pop(0)})()

    monkeypatch.setattr(gardien, "_juge", lambda: Juge())
    monkeypatch.setattr(gardien.connaissance, "connaissances", lambda conn, jid, limite: lignes)
    monkeypatch.setattr(gardien.depot, "fusionner", lambda conn, jid, g, r: fusions.append((g, r)))
    bilan = asyncio.run(gardien.consolider(None, "x"))
    assert "- 1 (validée) : Saisir hors ligne" in consignes[0] and "[regles]" in consignes[0]
    assert "Les dossiers" not in consignes[0]       # une seule réponse : rien à juger
    assert "regles" in consignes[1]                  # question oubliée : décision redemandée
    assert fusions == [(1, 2), (5, 6)] and bilan == {"fusions": 2, "refus": 0}


def _lecteur(version):
    from jumeau.lecteurs import LecteurMemoire
    return LecteurMemoire("Datadog svc", "svc", {"r": {"titre": "t", "versions": {version: ["a"]}}}, systeme="datadog")


def test_veille_sans_depot_la_version_est_l_empreinte_des_sources(monkeypatch):
    fiches, redigees = {}, []
    monkeypatch.setattr(depot, "jumeau_par_id", lambda c, j: {"id": j, "nom": "P", "tenant_id": "t", "equipe": "e"})
    monkeypatch.setattr(depot, "sources_du_jumeau", lambda c, j: [])
    monkeypatch.setattr(depot, "toutes_les_sources", lambda c, j: [])
    monkeypatch.setattr(depot, "consignes_du_jumeau", lambda c, j: [])
    monkeypatch.setattr(gardien, "connaissances_courantes", lambda c, j: set())
    monkeypatch.setattr(gardien.connaissance, "connaissances", lambda *a, **k: [])
    monkeypatch.setattr(gardien, "fiche_du_sha", lambda c, j, sha: sha in fiches)
    monkeypatch.setattr(gardien, "enregistrer_fiche", lambda c, j, sha, contenu: fiches.__setitem__(sha, contenu))
    monkeypatch.setattr(gardien, "fiche_recente", lambda c, j, delai: None)

    async def rien(*a, **k):
        return {}

    async def rediger(ctx, dsn, sigs, commits):
        redigees.append(ctx["lecteurs"])
        return "Fiche", None
    monkeypatch.setattr(gardien, "consolider", rien)
    monkeypatch.setattr(gardien.poignee, "serrer", rien)
    version = {"v": "1"}
    monkeypatch.setattr(gardien.lecteurs, "lecteurs_de", lambda s: [_lecteur(version["v"])])

    def passe():
        return asyncio.run(gardien.veiller(None, None, "p", rediger=rediger))
    premiere = passe()
    assert premiere["changement"] and premiere["depots"] == [] and len(fiches) == 1
    assert passe() == {"changement": False}  # rien n'a avancé : pas de nouvelle fiche
    version["v"] = "2"
    assert passe()["changement"] and len(fiches) == 2  # une source a avancé : nouvelle fiche


def test_sans_depot_une_source_injoignable_ou_une_fiche_recente_ne_font_pas_rediger(monkeypatch):
    monkeypatch.setattr(depot, "jumeau_par_id", lambda c, j: {"id": j, "nom": "P", "tenant_id": "t", "equipe": "e"})
    monkeypatch.setattr(depot, "sources_du_jumeau", lambda c, j: [])
    monkeypatch.setattr(depot, "toutes_les_sources", lambda c, j: [])
    monkeypatch.setattr(gardien, "connaissances_courantes", lambda c, j: set())
    monkeypatch.setattr(gardien, "fiche_du_sha", lambda c, j, sha: False)

    async def rediger(*a):
        raise AssertionError("aucune rédaction attendue")

    class Panne:
        nom = "Datadog svc"
        def version_courante(self):
            raise OSError("réseau")
    monkeypatch.setattr(gardien.lecteurs, "lecteurs_de", lambda s: [Panne()])
    r = asyncio.run(gardien.veiller(None, None, "p", rediger=rediger))
    assert r["changement"] is False and "injoignable" in r["erreur"]
    monkeypatch.setattr(gardien.lecteurs, "lecteurs_de", lambda s: [_lecteur("2")])
    monkeypatch.setattr(gardien, "fiche_recente", lambda c, j, delai: "2026-10-28T08:00:00+00:00")
    assert asyncio.run(gardien.veiller(None, None, "p", rediger=rediger))["fiche_recente"]


def test_synchronisation_graphe_depuis_postgres_et_relations(monkeypatch):
    from jumeau.graphe import GrapheMemoire

    class _Curseur:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, _sql, _params):
            return self

        def fetchall(self):
            return [{"id": "a", "tenant_id": "demo", "type": "APPLICATION", "label": "A"},
                    {"id": "b", "tenant_id": "demo", "type": "APPLICATION", "label": "B"}]

    class _Conn:
        def cursor(self, row_factory=None):
            return _Curseur()

    class _Relations:
        def find(self, _filtre, _projection):
            async def lignes():
                yield {"id": "r1", "source": "a", "cible": "b", "type": "echange", "etat": "confirmee"}
            return lignes()

    class _Db:
        relations = _Relations()

    store = GrapheMemoire()
    monkeypatch.setenv("GRAPH_STORE", "memoire")
    monkeypatch.setenv("JUMEAU_GRAPH_PROJECTION", "direct")
    rapport = asyncio.run(gardien._synchroniser_graphe(
        _Conn(), _Db(), {"id": "a", "tenant_id": "demo"}, store=store))
    assert rapport["twins"] == 2 and rapport["relations"] == 1
    assert set(store.noeuds) == {("demo", "a"), ("demo", "b")}
    assert store.aretes[("demo", "r1")].target == "b"
