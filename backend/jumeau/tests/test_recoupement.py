"""Vérifier comme on teste (Harness v3 §2) : recettes, juge d'appui, recoupement, maturité M3 et contradictions."""
import asyncio
import subprocess

import pytest

from jumeau import depot, recoupement
from jumeau.juge import Appui
from jumeau.lecteurs import LecteurMemoire
from jumeau.tests.conftest import JUMEAU, besoin_pg


def appui(id, appui="oui", concordance="concordantes", copie=False, citations=()):
    return Appui(id=id, appui=appui, concordance=concordance, copie=copie, raison="r", citations=list(citations))


@pytest.mark.parametrize("decision, systemes, attendu", [
    (appui(1), {"git", "confluence"}, "recoupe"),
    (appui(1, copie=True), {"git", "confluence"}, "selon"),           # une recopie ne compte qu'une fois
    (appui(1, appui="partiel"), {"git", "confluence"}, "en_partie"),  # Google Check Grounding : partiel = non ancré
    (appui(1, appui="partiel", concordance="une_seule_source"), {"git"}, "en_partie"),
    (appui(1, concordance="contradictoires"), {"git", "confluence"}, "conteste"),
    (appui(1, concordance="concordantes"), {"git"}, "selon"),         # un seul système : jamais recoupé
    (appui(1, appui="non"), {"git", "confluence"}, "non_appuye"),
])
def test_etat_du_jugement(decision, systemes, attendu):
    assert recoupement.etat_du_jugement(decision, systemes) == attendu


def _proposer(conn, jumeau, source_id, predicat, objet, preuves):
    cid = None
    for p in preuves:
        cid = depot.enregistrer_proposition(conn, jumeau, p.pop("source_id", source_id),
                                            {"sujet": "TBT", "predicat": predicat, "objet": objet, "type": "T",
                                             "confiance": 0.5}, p, {"extracteur": "test"})
    return cid


def _code(sha, chemin, ligne):
    return {"locator": f"git://tbt@{sha[:12]}:{chemin}#L{ligne}-L{ligne}", "chemin": chemin, "sha": sha,
            "ligne_debut": ligne, "ligne_fin": ligne, "hash": "h"}


@besoin_pg
def test_une_passe_recettes_juge_recoupement_maturite(conn, depot_git):
    sha = subprocess.run(["git", "-C", str(depot_git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    depot.declarer_source(conn, j, {"type": "GIT", "nom": "tbt", "emplacement": str(depot_git), "curseur": sha})
    depot.declarer_source(conn, j, {"type": "CONFLUENCE", "nom": "Wiki", "emplacement": "TBT"})
    ids = {s["nom"]: s["id"] for s in depot.toutes_les_sources(conn, "tbt")}
    wiki = LecteurMemoire("Wiki", "TBT", {"12": {"titre": "Règles", "versions": {"3": ["Seuls les conseillers valident."]}}},
                          systeme="confluence")
    wiki.source_id = ids["Wiki"]
    page = {"type": "DOCUMENTATION", "locator": "confluence://TBT/12@3#L1-L1", "chemin": "12", "sha": "3",
            "ligne_debut": 1, "ligne_fin": 1, "hash": "h", "source_id": ids["Wiki"]}

    fastapi = _proposer(conn, j, ids["tbt"], "DEPEND_DE", "fastapi", [_code(sha, "requirements.txt", 1)])
    redis = _proposer(conn, j, ids["tbt"], "DEPEND_DE", "redis", [_code(sha, "requirements.txt", 1)])
    regle = _proposer(conn, j, ids["tbt"], "APPLIQUE_REGLE", "Seuls les conseillers valident",
                      [_code(sha, "app.py", 10), dict(page)])
    acteur = _proposer(conn, j, ids["tbt"], "SERT_ACTEUR", "Les conseillers", [_code(sha, "app.py", 20)])

    vus = []

    async def juger(modele, dossiers):
        vus.append(sorted(d["id"] for d in dossiers))
        return {d["id"]: appui(d["id"], concordance="concordantes" if len(d["extraits"]) > 1 else "une_seule_source",
                               citations=[" ".join(d["extraits"][0]["lignes"])])
                for d in dossiers}

    bilan = asyncio.run(recoupement.verifier(conn, j, [wiki], juger=juger))
    # `pannes` : une décision du juge qui manque est comptée, plus seulement reléguée à « en_attente » (L1.7).
    assert bilan == {"verifie": 1, "selon": 1, "recoupe": 1, "conteste": 0, "en_partie": 0, "non_appuye": 1,
                     "incertain": 0, "en_attente": 0, "pannes": 0}
    etats = recoupement.etats(conn, "tbt")
    assert {cid: etats[cid]["etat"] for cid in (fastapi, redis, regle, acteur)} == {
        fastapi: "verifie", redis: "non_appuye", regle: "recoupe", acteur: "selon"}
    assert etats[fastapi]["methode"] == "recette" and etats[regle]["systemes"] == ["confluence", "git"]
    maturites = dict(conn.execute("SELECT id, maturite FROM claim WHERE jumeau_id = 'tbt'").fetchall())
    # Deux systèmes ET recoupés : seul chemin vers M3. `acteur` (SERT_ACTEUR) n'est prouvé que par du code : une
    # ligne de code ne dit pas qui sert l'application, l'hypothèse reste M1 (plan de remédiation L1bis.2).
    assert maturites[regle] == "M3" and maturites[acteur] == "M1"

    # Rien n'a changé : rien n'est rejoué, le juge n'est pas rappelé.
    assert asyncio.run(recoupement.verifier(conn, j, [wiki], juger=juger))["recoupe"] == 0 and len(vus) == 1


@besoin_pg
def test_deux_systemes_discordants_ouvrent_une_contradiction_et_restent_m2(conn, depot_git):
    sha = subprocess.run(["git", "-C", str(depot_git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    depot.declarer_source(conn, j, {"type": "GIT", "nom": "tbt", "emplacement": str(depot_git), "curseur": sha})
    depot.declarer_source(conn, j, {"type": "CONFLUENCE", "nom": "Wiki", "emplacement": "TBT"})
    ids = {s["nom"]: s["id"] for s in depot.toutes_les_sources(conn, "tbt")}
    wiki = LecteurMemoire("Wiki", "TBT", {"12": {"titre": "R", "versions": {"3": ["L'agence valide aussi."]}}},
                          systeme="confluence")
    wiki.source_id = ids["Wiki"]
    cid = _proposer(conn, j, ids["tbt"], "APPLIQUE_REGLE", "Seuls les conseillers valident",
                    [_code(sha, "app.py", 10), {"type": "DOCUMENTATION", "locator": "confluence://TBT/12@3#L1-L1",
                                                "chemin": "12", "sha": "3", "ligne_debut": 1, "ligne_fin": 1,
                                                "hash": "h", "source_id": ids["Wiki"]}])

    async def juger(modele, dossiers):
        return {d["id"]: appui(d["id"], concordance="contradictoires", citations=[" ".join(d["extraits"][0]["lignes"])])
                for d in dossiers}

    assert asyncio.run(recoupement.verifier(conn, j, [wiki], juger=juger))["conteste"] == 1
    c = conn.execute("SELECT systeme_a, systeme_b, statut, signalee_par FROM contradiction WHERE claim_id = %s",
                     (cid,)).fetchall()
    assert len(c) == 1 and {c[0][0], c[0][1]} == {"git", "confluence"} and c[0][2:] == ("OUVERTE", "juge-recoupement")
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M2"


@besoin_pg
def test_juge_en_panne_ou_borne_laisse_en_attente(conn, depot_git):
    sha = subprocess.run(["git", "-C", str(depot_git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    depot.declarer_source(conn, j, {"type": "GIT", "nom": "tbt", "emplacement": str(depot_git), "curseur": sha})
    sid = depot.toutes_les_sources(conn, "tbt")[0]["id"]
    for n in range(3):
        _proposer(conn, j, sid, "SERT_ACTEUR", f"acteur {n}", [_code(sha, "app.py", n + 1)])

    async def panne(modele, dossiers):
        return {}

    bilan = asyncio.run(recoupement.verifier(conn, j, juger=panne, limite=2))
    # 3 connaissances attendent (2 jugées par un lot en panne + 1 au-delà de la limite), et 2 pannes sont comptées :
    # une décision qui manque n'est plus seulement reléguée à « en attente » (L1.7).
    assert (bilan["en_attente"], bilan["pannes"]) == (3, 2)
    # Rien n'est jugé, et l'état le dit : « en_attente » plutôt qu'une absence d'état (L1.6).
    assert {e["etat"] for e in recoupement.etats(conn, "tbt").values()} == {"en_attente"}


# --- L1.4 : ce qu'une comparaison de mots peut dire, et ce qu'elle ne peut pas ------------------------------------

def test_une_observation_de_silence_mais_aucun_veto():
    """Une ligne de code ne répète pas les mots d'une phrase métier : la mention est une **observation**, jamais un
    veto. En faire un veto a fait tomber deux tests de recoupement légitime — c'est la raison de ce test."""
    extraits = [{"systeme": "git", "lignes": ["    user = repo.get_by_email(email)"]},
                {"systeme": "confluence", "lignes": ["Seuls les conseillers valident les dossiers."]}]
    objet = "Seuls les conseillers valident"
    assert recoupement.mentionne_enonce(objet, extraits[1]["lignes"]) is True
    assert recoupement.mentionne_enonce(objet, extraits[0]["lignes"]) is False
    assert recoupement.systemes_muets(objet, extraits) == ["git"]
    # Le verdict, lui, ne dépend pas de cette observation.
    assert recoupement.etat_du_jugement(appui(1), {"git", "confluence"}) == "recoupe"


def test_la_mention_reconnait_la_meme_chose_sous_deux_ecritures():
    assert recoupement.mentionne_enonce("PostgreSQL", ["image: postgres:16"])
    assert recoupement.mentionne_enonce("Répondre aux questions", ["def repondre(question):"])
    assert not recoupement.mentionne_enonce("PostgreSQL", ["image: nginx:1"])


def test_une_regle_de_verification_qui_change_rejoue_ses_connaissances():
    preuves = [{"id": 7}, {"id": 9}]
    v = recoupement.VERSION_REGLE["APPLIQUE_REGLE"]
    assert recoupement.empreinte("APPLIQUE_REGLE", preuves) == f"{v}:7,9"  # vérifiée sous une autre règle : rejouée
    assert recoupement.empreinte("detient", preuves) == f"{v}:7,9"
    assert recoupement.empreinte("DEPEND_DE", preuves) == "7,9"  # règle inchangée : rien n'est rejoué
