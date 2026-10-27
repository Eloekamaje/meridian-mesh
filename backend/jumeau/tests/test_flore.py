"""Pont Flore → jumeau réel : la réponse du jumeau prend la forme d'une réponse de Flore."""
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


def test_reponse_au_format_flore():
    r = flore.vers_reponse_flore(JUMEAU, SOURCE, TEXTE)
    assert r["reponse"] == TEXTE and r["comportement"] == "expliquer"
    assert r["contributions"] == [{"jumeau": "Méridian", "texte": f"Réponse fondée sur mon code au commit {SHA}."}]
    assert len(r["preuves"]) == 2


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
