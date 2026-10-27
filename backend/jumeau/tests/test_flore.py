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
    preuves = flore.preuves_depuis(TEXTE, SOURCE)
    assert preuves == [
        {"source": "backend/server.py:102-108", "detail": f"git://meridian-mesh@{SHA}:backend/server.py#L102-L108"},
        {"source": "backend/server.py:32", "detail": f"git://meridian-mesh@{SHA}:backend/server.py#L32-L32"},
    ]


def test_preuves_bornees():
    texte = " ".join(f"git://d@{SHA}:f.py#L{n}-L{n}" for n in range(1, 30))
    assert len(flore.preuves_depuis(texte, SOURCE)) == flore.MAX_PREUVES


def test_reponse_au_format_flore_preuves_hors_du_texte():
    r = flore.vers_reponse_flore(JUMEAU, SOURCE, TEXTE)
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
    assert flore.preuves_depuis(texte, SOURCE) == [
        {"source": "backend/server.py:91-112", "detail": f"git://meridian-mesh@{SHA}:backend/server.py#L91-L112"},
        {"source": "backend/portee.py:7", "detail": f"git://meridian-mesh@{SHA}:backend/portee.py#L7-L7"},
    ]


def test_citation_forme_longue_et_courte_dedoublonnees():
    texte = f"git://meridian-mesh@{SHA}:backend/server.py#L32-L32 puis backend/server.py#L32"
    assert len(flore.preuves_depuis(texte, SOURCE)) == 1


def test_ni_url_ni_numero_de_version_ne_deviennent_des_preuves():
    texte = "Voir https://github.com/x/y.py#L3, la v1.2#L3 et http://hote/a.py#L1-L2."
    assert flore.preuves_depuis(texte, SOURCE) == []


@pytest.mark.parametrize("texte,attendu", [
    ("Contrôlé (voir a.py#L1) et plus.", "Contrôlé et plus."),
    ("Deux sources (a.py#L1, b.py#L2-L4).", "Deux sources."),
    ("Voir a.py#L1, b.py#L2 et c.py#L3 pour le détail.", "Voir pour le détail."),
    ("Lien https://x.com/a/b.py#L3 conservé.", "Lien https://x.com/a/b.py#L3 conservé."),
])
def test_retrait_des_citations_sans_restes(texte, attendu):
    assert flore.retirer_citations(texte) == attendu


def test_citations_invalides_absentes_du_volet():
    r = flore.vers_reponse_flore(JUMEAU, SOURCE, "A `a.py#L1` et B `b.py#L2`.", invalides=["b.py#L2-L2"])
    assert [p["source"] for p in r["preuves"]] == ["a.py:1"]


def test_echec_du_relecteur_ne_supprime_pas_la_reponse(monkeypatch):
    async def relecteur_en_panne(*_, **__):
        raise TimeoutError("429")
    monkeypatch.setattr(flore.contradicteur, "relire", relecteur_en_panne)
    verdict = asyncio.run(flore.relire_sans_risque("q", "r", SOURCE, None, None))
    assert verdict == {"ok": True, "problemes": []}


def test_fiche_affichable_sans_citations_avec_ses_preuves():
    contenu = "# Fiche\n\n**Ce qu'elle fait**\n- Gère les comptes `backend/app/models.py#L87-L93`.\n"
    r = flore.fiche_affichable({"sha": SHA + "0" * 28, "contenu": contenu}, SOURCE)
    assert "#L" not in r["contenu"] and "Gère les comptes." in r["contenu"]
    assert r["preuves"] == [{"source": "backend/app/models.py:87-93",
                             "detail": f"git://meridian-mesh@{SHA}:backend/app/models.py#L87-L93"}]


def test_citations_separees_par_un_point_median_retirees_sans_reste():
    texte = "Le fil des auteurs suivis. `a.py#L1` · `b.py#L2` · `c.py#L3`\nSuite."
    assert flore.retirer_citations(texte) == "Le fil des auteurs suivis.\nSuite."
