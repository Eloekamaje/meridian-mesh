"""Pont Flore → jumeau réel : la réponse du jumeau prend la forme d'une réponse de Flore."""
import asyncio

import pytest
from jumeau import flore

SHA = "35fcbdd2ae9a"
TEXTE = (f"Je protège mes routes avec `autorisations` git://meridian-mesh@{SHA}:backend/server.py#L102-L108 "
         f"et je lis MONGO_URL git://meridian-mesh@{SHA}:backend/server.py#L32-L32, "
         f"encore git://meridian-mesh@{SHA}:backend/server.py#L102-L108.")
JUMEAU = {"id": "meridian", "nom": "Méridian", "equipe": "equipe-meridian"}
SOURCE = {"nom": "meridian-mesh", "curseur": SHA + "0" * 28}


def test_preuves_extraites_des_citations_sans_doublon():
    preuves = flore.preuves_depuis(TEXTE, [SOURCE])
    assert preuves == [
        {"source": "backend/server.py:102-108", "detail": f"git://meridian-mesh@{SHA}:backend/server.py#L102-L108"},
        {"source": "backend/server.py:32", "detail": f"git://meridian-mesh@{SHA}:backend/server.py#L32-L32"},
    ]


def test_preuves_bornees():
    texte = " ".join(f"git://meridian-mesh@{SHA}:f.py#L{n}-L{n}" for n in range(1, 30))
    assert len(flore.preuves_depuis(texte, [SOURCE])) == flore.MAX_PREUVES


def test_reponse_au_format_flore_preuves_hors_du_texte():
    r = flore.vers_reponse_flore(JUMEAU, [SOURCE], TEXTE)
    assert r["comportement"] == "expliquer"
    assert "git://" not in r["reponse"] and "#L" not in r["reponse"]
    assert r["contributions"] == [{"jumeau": "Méridian", "texte": "Connaissances et code de l'application consultés."}]
    assert len(r["preuves"]) == 2


def test_citations_retirees_proprement_du_texte():
    texte = ("Les droits sont une liste blanche (`backend/server.py#L91-L112`). "
             "Le niveau décide des champs `backend/server.py#L122-L136` renvoyés.\n"
             "- Portée bornée — backend/portee.py#L7-L8")
    assert flore.retirer_citations(texte) == ("Les droits sont une liste blanche. "
                                              "Le niveau décide des champs renvoyés.\n- Portée bornée")


def test_cle_de_fil_personnelle_hors_travail_partagee_dans_un_travail():
    assert flore.cle_fil("alice", None) != flore.cle_fil("bob", None)
    assert flore.cle_fil("alice", "case-42") == flore.cle_fil("bob", "case-42")


def test_citations_courtes_reconstruites_au_commit_du_jumeau():
    texte = "Liste blanche `backend/server.py#L91-L112` et portée backend/portee.py#L7 ; voir aussi #L31-L42."
    assert flore.preuves_depuis(texte, [SOURCE]) == [
        {"source": "backend/server.py:91-112", "detail": f"git://meridian-mesh@{SHA}:backend/server.py#L91-L112"},
        {"source": "backend/portee.py:7", "detail": f"git://meridian-mesh@{SHA}:backend/portee.py#L7-L7"},
    ]


def test_citation_forme_longue_et_courte_dedoublonnees():
    texte = f"git://meridian-mesh@{SHA}:backend/server.py#L32-L32 puis backend/server.py#L32"
    assert len(flore.preuves_depuis(texte, [SOURCE])) == 1


def test_ni_url_ni_numero_de_version_ne_deviennent_des_preuves():
    texte = "Voir https://github.com/x/y.py#L3, la v1.2#L3 et http://hote/a.py#L1-L2."
    assert flore.preuves_depuis(texte, [SOURCE]) == []


@pytest.mark.parametrize("texte,attendu", [
    ("Contrôlé (voir a.py#L1) et plus.", "Contrôlé et plus."),
    ("Deux sources (a.py#L1, b.py#L2-L4).", "Deux sources."),
    ("Voir a.py#L1, b.py#L2 et c.py#L3 pour le détail.", "Voir pour le détail."),
    ("Lien https://x.com/a/b.py#L3 conservé.", "Lien https://x.com/a/b.py#L3 conservé."),
])
def test_retrait_des_citations_sans_restes(texte, attendu):
    assert flore.retirer_citations(texte) == attendu


def test_citations_invalides_absentes_du_volet():
    r = flore.vers_reponse_flore(JUMEAU, [SOURCE], "A `a.py#L1` et B `b.py#L2`.", invalides=["b.py#L2-L2"])
    assert [p["source"] for p in r["preuves"]] == ["a.py:1"]


def test_echec_du_relecteur_ne_supprime_pas_la_reponse(monkeypatch):
    async def relecteur_en_panne(*_, **__):
        raise TimeoutError("429")
    monkeypatch.setattr(flore.contradicteur, "relire", relecteur_en_panne)
    verdict = asyncio.run(flore.relire_sans_risque("q", "r", SOURCE, None, None))
    # La réponse passe quand même, mais elle ne s'affiche pas comme « relue » (plan de remédiation L0.1).
    assert verdict == {"ok": True, "problemes": [], "etat": "indisponible"}


def test_fiche_affichable_sans_citations_avec_ses_preuves():
    contenu = "# Fiche\n\n**Ce qu'elle fait**\n- Gère les comptes `backend/app/models.py#L87-L93`.\n"
    r = flore.fiche_affichable({"sha": SHA, "contenu": contenu}, [SOURCE])
    assert "#L" not in r["contenu"] and "Gère les comptes." in r["contenu"]
    assert r["preuves"] == [{"source": "backend/app/models.py:87-93",
                             "detail": f"git://meridian-mesh@{SHA}:backend/app/models.py#L87-L93"}]


def test_citations_separees_par_un_point_median_retirees_sans_reste():
    texte = "Le fil des auteurs suivis. `a.py#L1` · `b.py#L2` · `c.py#L3`\nSuite."
    assert flore.retirer_citations(texte) == "Le fil des auteurs suivis.\nSuite."


def test_preuves_de_plusieurs_depots_etiquetees_par_depot():
    front = {"nom": "front", "curseur": "f" * 40}
    texte = "API `meridian-mesh:app/main.py#L3` et écran `front:src/App.jsx#L10-L12`, plus `inconnu:x.py#L1`."
    preuves = flore.preuves_depuis(texte, [SOURCE, front])
    assert preuves == [
        {"source": "meridian-mesh · app/main.py:3", "detail": f"git://meridian-mesh@{SHA}:app/main.py#L3-L3"},
        {"source": "front · src/App.jsx:10-12", "detail": "git://front@ffffffffffff:src/App.jsx#L10-L12"}]
    assert "meridian-mesh:" not in flore.retirer_citations(texte) and "#L" not in flore.retirer_citations(texte)


def test_fiche_affichable_liste_les_depots_avec_branche_et_commit():
    front = {"nom": "front", "curseur": "f" * 40, "branche": "develop"}
    fiche = flore.fiche_affichable({"sha": "x", "contenu": "Rien."}, [SOURCE, front])
    assert fiche["depots"][1] == {"nom": "front", "branche": "develop", "commit": "ffffffffffff"}


def test_contexte_d_un_jumeau_sans_code_mobilisable(monkeypatch):
    import contextlib
    from jumeau import connaissance, depot, gardien, lecteurs
    from jumeau.lecteurs import LecteurMemoire
    dd = LecteurMemoire("Datadog svc", "svc", {"r": {"titre": "t", "versions": {"1": ["a"]}}}, systeme="datadog")
    monkeypatch.setenv("JUMEAU_PG_DSN", "dsn")
    monkeypatch.setattr(flore.psycopg, "connect", lambda dsn: contextlib.nullcontext())
    monkeypatch.setattr(depot, "jumeau_par_id", lambda c, j: JUMEAU)
    monkeypatch.setattr(depot, "sources_du_jumeau", lambda c, j: [])
    monkeypatch.setattr(depot, "toutes_les_sources", lambda c, j: [])
    monkeypatch.setattr(depot, "consignes_du_jumeau", lambda c, j: [])
    monkeypatch.setattr(lecteurs, "lecteurs_de", lambda s: [dd])
    monkeypatch.setattr(connaissance, "connaissances", lambda *a, **k: [])
    monkeypatch.setattr(gardien, "fiche_courante", lambda c, j: None)
    ctx, dsn = flore._contexte("meridian", "alice", None)
    assert ctx["sources"] == [] and ctx["lecteurs"] == [dd] and dsn == "dsn"
    monkeypatch.setattr(lecteurs, "lecteurs_de", lambda s: [])
    assert flore._contexte("meridian", "alice", None) == (None, None)  # ni code ni source : rien à mobiliser


# --- Routage : l'application nommée dans la question (constaté : 60 s par l'orchestration, faute de sélection) ----

JUMEAUX = [{"id": "conduit", "nom": "Conduit"}, {"id": "gestion-des-articles", "nom": "Gestion des articles"},
           {"id": "meridian", "nom": "Méridian Mesh"}]


def test_application_nommee_nom_identifiant_et_faute_de_frappe():
    assert flore.application_nommee("illustre-moi la publication d'un article dans Conduit", JUMEAUX) == ["conduit"]
    assert flore.application_nommee("que fait l'application conduite ?", JUMEAUX) == ["conduit"]
    assert flore.application_nommee("Que fait la Gestion des articles ?", JUMEAUX) == ["gestion-des-articles"]
    assert flore.application_nommee("à quoi sert Meridian ?", JUMEAUX) == ["meridian"]


def test_aucune_ou_plusieurs_applications_nommees_laissent_l_orchestration():
    assert flore.application_nommee("qui es-tu ?", JUMEAUX) == []
    assert flore.application_nommee("comment conduire le projet ?", JUMEAUX) == []  # « conduire » n'est pas Conduit
    assert flore.application_nommee("Conduit échange-t-il avec Méridian ?", JUMEAUX) == []
    assert flore.application_nommee("la publication d'un article", JUMEAUX) == []  # « article » seul n'est pas un nom


def test_pastilles_numerotees_dans_l_ordre_du_volet_et_citations_fausses_retirees():
    texte = ("Les droits sont une liste blanche (`backend/server.py#L91-L112`). "
             "Le niveau décide des champs `backend/server.py#L122-L136` et `backend/server.py#L91-L112` renvoyés.\n"
             "- Portée bornée — backend/portee.py#L7-L8\n- Inventé `x.py#L1-L2`")
    preuves = flore.preuves_depuis(texte, [SOURCE], exclure={("", "x.py", 1, 2)} | set())
    preuves = [p for p in preuves if "x.py" not in p["detail"]]  # x.py : citation fausse, hors du volet
    assert flore.pastiller(texte, preuves, [SOURCE]) == (
        "Les droits sont une liste blanche [1](#preuve-1). "
        "Le niveau décide des champs [2](#preuve-2) [1](#preuve-1) renvoyés.\n"
        "- Portée bornée [3](#preuve-3)\n- Inventé")


def test_la_reponse_porte_ses_pastilles_et_le_volet_reste_le_meme():
    r = flore.vers_reponse_flore(JUMEAU, [SOURCE], TEXTE)
    assert "git://" not in r["reponse"] and "[1](#preuve-1)" in r["reponse"] and "[2](#preuve-2)" in r["reponse"]
    assert len(r["preuves"]) == 2


def test_le_depot_d_une_preuve_se_lit_dans_son_emplacement():
    from jumeau.routes import depot_du_locator
    assert depot_du_locator(f"git://meridian-mesh@{SHA}:backend/server.py#L1-L2") == "meridian-mesh"
    assert depot_du_locator("confluence://TBT/123@7#L1") is None
    assert depot_du_locator("git://../etc@x:passwd#L1-L1") is None  # un nom de dépôt, rien d'autre
