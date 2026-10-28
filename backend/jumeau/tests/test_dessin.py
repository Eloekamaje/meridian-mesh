"""Schémas dessinés par le harness : l'agent choisit et nomme, chaque flèche est fondée, le harness écrit le Mermaid."""
from jumeau import appels, flore, schemas

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


def test_flux_avec_groupes_et_styles_poses_par_le_harness():
    d = dessin()
    d.dessiner("flux", "", BOITES, [{"de": "depot", "vers": "base", "libelle": "écrit", "fondement": "c:812"}],
               [{"libelle": "Stockage", "ids": ["depot", "base"]}])
    assert d.mermaid.startswith("flowchart LR") and 'subgraph g0["Stockage"]' in d.mermaid
    assert 'depot -->|"écrit"| base' in d.mermaid and "linkStyle 0 stroke:#34D399" in d.mermaid


def test_rien_de_fonde_rien_de_dessine_et_type_inconnu():
    d = dessin()
    assert "rien n'est dessiné" in d.dessiner("flux", "", BOITES, [{"de": "route", "vers": "base", "fondement": "x"}])
    assert d.bloc() == "" and "Type inconnu" in d.dessiner("camembert", "", BOITES, [])


def test_le_schema_prend_place_apres_le_premier_paragraphe():
    d = dessin()
    d.dessiner("flux", "", BOITES, [{"de": "depot", "vers": "base", "libelle": "écrit", "fondement": "c:812"}])
    texte = flore.avec_schema("La réponse.\n\nLa suite.", d)
    assert texte.startswith("La réponse.\n\n```mermaid\nflowchart LR") and texte.endswith("La suite.")
    assert flore.avec_schema("Seul.", None) == "Seul."


# --- Enchaînement lu dans le graphe d'appels (formats réels de l'index) ------------------------------------------

P = "proj"
RECHERCHE = {"create_new_article": f"  {P}.app.routes.create_new_article Function app/routes.py 59-72 1 9",
             "get_slug_for_article": f"  {P}.app.services.get_slug_for_article Function app/services.py 10-14 1 0",
             "create_article": f"  {P}.app.repo.Repo.create_article Method app/repo.py 20-30 1 0"}
TRACES = {"create_new_article": f"callees: 3  (cols: qn hop)\n  {P}.app.services.get_slug_for_article 1\n"
                                f"  {P}.app.repo.Repo.create_article 1\n  {P}.app.db.errors.EntityDoesNotExist 1\n",
          "get_slug_for_article": "callees: 0", "create_article": "callees: 0"}


def appeler(outil, project, **a):
    nom = a.get("name_pattern") or a.get("function_name")
    return RECHERCHE.get(nom, "") if outil == "search_graph" else TRACES.get(nom, "")


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
