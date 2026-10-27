"""Adaptateur codebase-memory-mcp → Claims prouvés (tests unitaires, sans base ni réseau)."""
import hashlib

import pytest

from jumeau.adaptateur import adapter, localiser, preuve

SHA = "a3f9c1d"

FICHIERS = {
    "backend/server.py": [
        "import os",
        "client = AsyncIOMotorClient(os.environ[\"MONGO_URL\"])",
        "",
        "@api_router.get(\"/health\")",
        "async def health():",
        "    return {\"status\": \"ok\"}",
    ],
    "backend/requirements.txt": ["fastapi==0.110.1", "uvicorn==0.25.0", "motor==3.3.1"],
    "docker-compose.yml": ["services:", "  mongo:", "    image: mongo:7.0"],
}


def lire(chemin):
    return FICHIERS.get(chemin)


def resultats(**surcharges):
    base = {
        "routes": [{"chemin": "backend/server.py", "debut": "5", "fin": "6", "methode": "GET", "route": "/health"}],
        "paquets": [{"chemin": "backend/requirements.txt", "paquet": "motor"}],
        "variables": [{"chemin": "backend/server.py", "variable": "MONGO_URL"}],
        "images": [{"chemin": "docker-compose.yml", "image": "docker.io/library/mongo"}],
    }
    base.update(surcharges)
    return base


def test_localiser_retourne_la_premiere_ligne_contenant_le_jeton():
    assert localiser(["a", "fastapi==1", "motor==3"], "motor") == 3


def test_localiser_ignore_les_correspondances_partielles():
    assert localiser(["motorcycle==1", "motor==3"], "motor") == 2


def test_localiser_retourne_none_si_absent():
    assert localiser(["fastapi==1"], "motor") is None


def test_preuve_porte_locator_hash_et_citation():
    p = preuve("meridian", SHA, "backend/requirements.txt", FICHIERS["backend/requirements.txt"], 3, 3)
    assert p["locator"] == f"git://meridian@{SHA}:backend/requirements.txt#L3-L3"
    assert p["citation"] == "motor==3.3.1"
    assert p["hash"] == hashlib.sha256(b"motor==3.3.1").hexdigest()


def test_route_devient_claim_api_usage_avec_decorateur_dans_la_preuve():
    claims = adapter(resultats(paquets=[], variables=[], images=[]), lire, "meridian", SHA, "TBT")
    assert len(claims) == 1
    c = claims[0]
    assert (c["sujet"], c["predicat"], c["objet"], c["type"]) == ("TBT", "EXPOSE", "GET /health", "API_USAGE")
    assert c["preuves"][0]["ligne_debut"] == 4  # le décorateur, juste au-dessus du def
    assert "/health" in c["preuves"][0]["citation"]


def test_paquet_variable_et_image_deviennent_des_dependances_localisees():
    claims = adapter(resultats(routes=[]), lire, "meridian", SHA, "TBT")
    par_objet = {c["objet"]: c for c in claims}
    assert par_objet["motor"]["predicat"] == "DEPEND_DE"
    assert par_objet["motor"]["preuves"][0]["ligne_debut"] == 3
    assert par_objet["MONGO_URL"]["predicat"] == "LIT_VARIABLE"
    assert par_objet["MONGO_URL"]["preuves"][0]["ligne_debut"] == 2
    assert par_objet["docker.io/library/mongo"]["predicat"] == "EXECUTE_IMAGE"
    assert par_objet["docker.io/library/mongo"]["preuves"][0]["ligne_debut"] == 3


def test_claim_rejete_si_la_preuve_ne_se_verifie_pas():
    fausse_route = [{"chemin": "backend/server.py", "debut": "5", "fin": "6", "methode": "GET", "route": "/inexistante"}]
    paquet_absent = [{"chemin": "backend/requirements.txt", "paquet": "django"}]
    fichier_absent = [{"chemin": "nulle/part.py", "variable": "X"}]
    claims = adapter(
        resultats(routes=fausse_route, paquets=paquet_absent, variables=fichier_absent, images=[]),
        lire, "meridian", SHA, "TBT",
    )
    assert claims == []


def test_route_parametree_normalisee_par_cbm_est_verifiee():
    fichiers = {"api.py": ['@api_router.post("/jumeaux/{jid}/admettre")', "async def admettre(jid):", "    pass"]}
    route = [{"chemin": "api.py", "debut": "2", "fin": "3", "methode": "POST", "route": "/jumeaux/{}/admettre"}]
    claims = adapter({"routes": route}, fichiers.get, "meridian", SHA, "TBT")
    assert [c["objet"] for c in claims] == ["POST /jumeaux/{}/admettre"]


def test_route_parametree_ne_correspond_pas_a_un_autre_chemin():
    fichiers = {"api.py": ['@api_router.post("/jumeaux/{jid}/examiner")', "async def f(jid):", "    pass"]}
    route = [{"chemin": "api.py", "debut": "2", "fin": "3", "methode": "POST", "route": "/jumeaux/{}/admettre"}]
    assert adapter({"routes": route}, fichiers.get, "meridian", SHA, "TBT") == []


def test_route_ne_se_prouve_pas_par_un_chemin_plus_long():
    fichiers = {"api.py": ['@router.get("/items/{id}")', "def f(id):", "    pass"]}
    route = [{"chemin": "api.py", "debut": "2", "fin": "3", "methode": "GET", "route": "/items"}]
    assert adapter({"routes": route}, fichiers.get, "meridian", SHA, "TBT") == []


def test_ligne_manquante_ignoree_sans_interrompre_l_ingestion():
    sans_ligne = [{"chemin": "backend/server.py", "debut": None, "fin": None, "methode": "GET", "route": "/health"}]
    claims = adapter(resultats(routes=sans_ligne, variables=[], images=[]), lire, "meridian", SHA, "TBT")
    assert [c["objet"] for c in claims] == ["motor"]


def test_localiser_ignore_un_paquet_scope():
    assert localiser(['"@types/node": "^20"', '"node": "20"'], "node") == 2


def test_route_hors_bornes_rejetee():
    hors = [{"chemin": "backend/server.py", "debut": "99", "fin": "120", "methode": "GET", "route": "/health"}]
    assert adapter(resultats(routes=hors, paquets=[], variables=[], images=[]), lire, "meridian", SHA, "TBT") == []


def test_doublons_fusionnes_en_un_claim_a_plusieurs_preuves():
    deux = [{"chemin": "backend/server.py", "variable": "MONGO_URL"}, {"chemin": "backend/server.py", "variable": "MONGO_URL"}]
    claims = adapter(resultats(routes=[], paquets=[], variables=deux, images=[]), lire, "meridian", SHA, "TBT")
    assert len(claims) == 1 and len(claims[0]["preuves"]) == 1


@pytest.mark.parametrize("type_claim,attendu", [("API_USAGE", 0.9), ("DEPENDENCY", 0.85)])
def test_confiance_initiale_par_regle(type_claim, attendu):
    claims = adapter(resultats(), lire, "meridian", SHA, "TBT")
    assert {c["confiance"] for c in claims if c["type"] == type_claim} == {attendu}


def test_decorateur_sur_plusieurs_lignes():
    fichiers = {"api.py": ["@router.put(", '    "/{slug}",', '    name="articles:update",', ")",
                           "async def modifier(slug):", "    pass"]}
    route = [{"chemin": "api.py", "debut": "5", "fin": "6", "methode": "PUT", "route": "/{}"}]
    [c] = adapter({"routes": route}, fichiers.get, "d", SHA, "App")
    assert c["preuves"][0]["ligne_debut"] == 1 and c["preuves"][0]["ligne_fin"] == 6


def test_route_recomposee_avec_le_prefixe_du_routeur():
    fichiers = {"articles.py": ['@router.get("", name="liste")', "def lister():", "    pass", "",
                                '@router.delete("/{slug}")', "def supprimer(slug):", "    pass"],
                "comments.py": ['@router.delete("/{slug}")', "def supprimer(slug):", "    pass"]}
    routes = [
        {"chemin": "articles.py", "debut": "2", "fin": "3", "methode": "GET", "route": ""},
        {"chemin": "articles.py", "debut": "2", "fin": "3", "methode": "ANY", "route": "/articles"},
        {"chemin": "articles.py", "debut": "6", "fin": "7", "methode": "DELETE", "route": "/{slug}"},
        {"chemin": "articles.py", "debut": "6", "fin": "7", "methode": "ANY", "route": "/articles"},
        {"chemin": "comments.py", "debut": "2", "fin": "3", "methode": "DELETE", "route": "/{slug}"},
        {"chemin": "comments.py", "debut": "2", "fin": "3", "methode": "ANY", "route": "/articles/{slug}/comments"},
    ]
    objets = sorted(c["objet"] for c in adapter({"routes": routes}, fichiers.get, "d", SHA, "App"))
    assert objets == ["DELETE /articles/{slug}", "DELETE /articles/{slug}/comments/{slug}", "GET /articles"]
