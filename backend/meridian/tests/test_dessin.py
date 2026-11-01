"""Schémas dessinés par le harness : l'agent choisit et nomme, chaque flèche est fondée, le harness écrit le Mermaid."""
import json
from meridian.adapters.outbound.connectors import appels
from meridian.adapters.outbound.llm import flore
from meridian.domain import schemas

LIGNES = {"app/routes.py#L64-L64": ["    slug = get_slug_for_article(article.title)"],
          "app/routes.py#L71-L71": ["    article = await repo.create_article(slug=slug)"]}


def lire(citation):
    if citation not in LIGNES:
        raise LookupError("absent")
    return LIGNES[citation], f"git://conduit@abc:{citation}", citation.replace("#L", ":").split("-")[0]


def dessin():
    return schemas.Dessin({812: {"statut": "PROPOSED", "verification": {"etat": "verifie"}},
                           814: {"statut": "PROPOSED", "verification": {"etat": "en_partie"}}}, lire)


BOITES = [{"id": "route", "libelle": "Publication [d'un] article"}, {"id": "adresse", "libelle": "Adresse : depuis le titre"},
          {"id": "depot", "libelle": "Enregistrement"}, {"id": "base", "libelle": "Base de données"}]


def test_fleches_fondees_gardees_les_autres_refusees_avec_raison():
    d = dessin()
    rapport = d.dessiner("sequence", "Publier un article", BOITES, [
        {"de": "route", "vers": "adresse", "libelle": "fabrique l'adresse", "fondement": "app/routes.py#L64-L64",
         "appel": "get_slug_for_article"},
        {"de": "route", "vers": "depot", "libelle": "enregistre", "fondement": "app/routes.py#L71-L71",
         "appel": "create_article"},
        {"de": "depot", "vers": "base", "libelle": "écrit", "fondement": "c:812"},
        {"de": "route", "vers": "base", "libelle": "faux", "fondement": "app/routes.py#L64-L64", "appel": "delete_all"},
        {"de": "route", "vers": "base", "libelle": "partiel", "fondement": "c:814"},
        {"de": "route", "vers": "fantome", "fondement": "c:812"},
        {"de": "route", "vers": "base", "fondement": "app/routes.py#L999", "appel": "x"}])
    assert "3 flèche(s)" in rapport and "ne contient pas d'appel à delete_all" in rapport
    assert "c:814 ne tient pas" in rapport and "boîte inconnue" in rapport and "introuvable" in rapport
    assert d.mermaid.splitlines()[0] == "sequenceDiagram"
    assert "participant route as Publication d'un article" in d.mermaid  # crochets retirés du libellé
    assert "participant adresse as Adresse depuis le titre" in d.mermaid  # deux-points retirés
    assert "route->>adresse: fabrique l'adresse" in d.mermaid
    assert [p["detail"] for p in d.preuves] == ["git://conduit@abc:app/routes.py#L64-L64",
                                                "git://conduit@abc:app/routes.py#L71-L71"]
    assert "lu dans le code" in d.legende and "vert = vérifié" in d.legende and "4 lien(s) non dessiné(s)" in d.legende
    assert d.structure["type"] == "sequence" and len(d.structure["boites"]) == 4
    assert [(f["de"], f["vers"], f["etat"]) for f in d.structure["fleches"]] == [
        ("route", "adresse", "code"), ("route", "depot", "code"), ("depot", "base", "verifie")]


def test_flux_avec_groupes_et_styles_poses_par_le_harness():
    d = dessin()
    d.dessiner("flux", "", BOITES, [{"de": "depot", "vers": "base", "libelle": "écrit", "fondement": "c:812"}],
               [{"libelle": "Stockage", "ids": ["depot", "base"]}])
    assert d.mermaid.startswith("flowchart LR") and 'subgraph g0["Stockage"]' in d.mermaid
    assert 'depot -->|"écrit"| base' in d.mermaid and "linkStyle 0 stroke:#34D399" in d.mermaid


def test_rien_de_fonde_rien_de_dessine_et_type_inconnu():
    d = dessin()
    assert "rien n'est dessiné" in d.dessiner("flux", "", BOITES, [{"de": "route", "vers": "base", "fondement": "x"}])
    assert d.bloc() == "" and d.structure is None
    assert "Type inconnu" in d.dessiner("camembert", "", BOITES, [])


def test_le_schema_prend_place_apres_le_premier_paragraphe():
    d = dessin()
    d.dessiner("flux", "", BOITES, [{"de": "depot", "vers": "base", "libelle": "écrit", "fondement": "c:812"}])
    texte = flore.avec_schema("La réponse.\n\nLa suite.", d)
    assert texte.startswith("La réponse.\n\n```mermaid\nflowchart LR") and texte.endswith("La suite.")
    assert flore.avec_schema("Seul.", None) == "Seul."


# --- Enchaînement lu dans le graphe d'appels (formats réels de l'index) ------------------------------------------

P = "proj"
# Formats réels des deux outils en `format=json` (relevés sur l'index) : l'enchaînement ne découpe plus du texte.
FONCTIONS = {"create_new_article": ("app.routes", "create_new_article", "app/routes.py", 59, 72),
             "get_slug_for_article": ("app.services", "get_slug_for_article", "app/services.py", 10, 14),
             "create_article": ("app.repo.Repo", "create_article", "app/repo.py", 20, 30)}
APPELES = {"create_new_article": [("app.services", "get_slug_for_article", "lsp", 0.9),
                                  ("app.repo.Repo", "create_article", "lsp", 0.9),
                                  ("app.db.errors", "EntityDoesNotExist", "lsp", 0.85)],
           "get_slug_for_article": [], "create_article": []}


def appeler(outil, project, **a):
    nom = a.get("name_pattern") or a.get("function_name")
    if outil == "search_graph":
        trouve = FONCTIONS.get(nom)
        groupes = [] if not trouve else [
            {"qn_prefix": f"{P}.{trouve[0]}", "file": trouve[2], "rows": [[trouve[1], "Function", f"{trouve[3]}-{trouve[4]}", 1, 0]]}]
        return json.dumps({"groups": groupes})
    return json.dumps({"callees": {"groups": [
        {"qn_prefix": f"{P}.{prefixe}", "rows": [[court, 1, strategie, confiance]]}
        for prefixe, court, strategie, confiance in APPELES.get(nom, [])]}})


def test_enchainement_paires_reelles_ligne_d_appel_et_bruit_ecarte(monkeypatch):
    fichier = [""] * 72
    fichier[63] = "    slug = get_slug_for_article(titre)"
    fichier[70] = "    await repo.create_article(slug)"
    monkeypatch.setattr(appels, "lire_au_sha", lambda d, s: lambda chemin: fichier if chemin == "app/routes.py" else None)
    f = appels.enchainement({"index_code": P, "emplacement": "/x", "curseur": "c"}, "create_new_article", appeler)
    assert [(x["vers"], x["ligne"]) for x in f] == [("app.services.get_slug_for_article", 64),
                                                     ("app.repo.Repo.create_article", 71)]  # erreurs : bruit écarté
    assert "fondement : app/routes.py#L64-L64" in appels.texte(f)


def test_appel_non_retrouve_dans_le_corps_non_rendu(monkeypatch):
    monkeypatch.setattr(appels, "lire_au_sha", lambda d, s: lambda chemin: [""] * 72)
    assert appels.enchainement({"index_code": P, "emplacement": "/x", "curseur": "c"}, "create_new_article", appeler) == []
